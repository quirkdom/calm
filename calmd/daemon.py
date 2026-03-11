from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

from calmd.backend.interface import InferenceBackend
from calmd.backend.mlx_backend import MLXBackend
from calmd.prompts import (
    ANALYSIS_MODE_SYSTEM_PROMPT,
    COMMAND_MODE_SYSTEM_PROMPT,
    render_analysis_prompt,
    render_command_prompt,
)

SOCKET_PATH = Path(os.environ.get("CALMD_SOCKET", "~/.cache/calmd/socket")).expanduser()
DEFAULT_MODEL = "mlx-community/Qwen3.5-9B-OptiQ-4bit"
FAST_MODEL = "mlx-community/Qwen3.5-4B-OptiQ-4bit"
DEFAULT_IDLE_OFFLOAD_SECS = 15 * 60
MAX_AUTO_RECOVERIES = 3
FATAL_EXIT_GRACE_SECS = 0.5
CONTROL_EXIT_DELAY_SECS = 0.05


class CalmdServer:
    def __init__(
        self, model_path: str, socket_path: Path, verbose: bool = False
    ) -> None:
        self.model_path = model_path
        self.socket_path = socket_path
        self.verbose = verbose
        self.backend: InferenceBackend | None = None
        self.command_base_state: Any | None = None
        self.analysis_base_state: Any | None = None
        self._load_error: str | None = None
        self._warmup_error: str | None = None
        self._ready = False
        self._model_loaded = False
        self._loading = False
        self._offloaded = False
        self._warmup_status = "pending"
        self._state_lock = threading.Lock()
        self._state_cv = threading.Condition(self._state_lock)
        self._server_socket: socket.socket | None = None
        self._skip_warmup = os.environ.get("CALMD_SKIP_WARMUP", "0") == "1"
        self._load_skip_warmup = self._skip_warmup
        self._idle_offload_secs = int(
            os.environ.get("CALMD_IDLE_OFFLOAD_SECS", str(DEFAULT_IDLE_OFFLOAD_SECS))
        )
        self._last_activity_at = time.monotonic()
        self._active_requests = 0
        self._recovery_attempts = 0
        self._fatal_error: str | None = None
        self._shutting_down = False

    def _init_backend(self, model_path: str) -> InferenceBackend:
        self._log(f"loading model backend: {model_path}")
        try:
            backend = MLXBackend()
            backend.load_model(model_path)
            self._log("mlx_lm backend loaded")
            return backend
        except Exception as exc:
            if _is_oom_error(exc) and model_path != FAST_MODEL:
                print(
                    f"warning: model load OOM for {model_path}; retrying with fast model {FAST_MODEL}",
                    file=sys.stderr,
                )
                self._log("OOM detected, retrying fast model")
                backend = MLXBackend()
                backend.load_model(FAST_MODEL)
                self.model_path = FAST_MODEL
                self._log("mlx_lm fast backend loaded")
                return backend
            raise RuntimeError(
                f"failed to load backend for {model_path}: {exc}"
            ) from exc

    def _start_background_load(self, on_demand: bool = False) -> None:
        with self._state_cv:
            if self._loading or self._model_loaded or self._fatal_error:
                return
            self._load_skip_warmup = on_demand or self._skip_warmup
            self._mark_loading_locked()
            self._spawn_load_thread_locked()

    def _mark_loading_locked(self) -> None:
        self._loading = True
        self._ready = False
        self._offloaded = False
        self._load_error = None
        self._warmup_error = None
        self._warmup_status = "pending"

    def _mark_loaded_locked(
        self, backend: InferenceBackend, command_base_state: Any, analysis_base_state: Any
    ) -> None:
        self.backend = backend
        self.command_base_state = command_base_state
        self.analysis_base_state = analysis_base_state
        self._model_loaded = True
        self._loading = False
        self._offloaded = False
        self._warmup_status = "skipped" if self._load_skip_warmup else "in_progress"
        self._ready = self._load_skip_warmup
        self._load_error = None
        self._warmup_error = None
        self._last_activity_at = time.monotonic()

    def _mark_load_failed_locked(self, message: str, fatal: bool) -> None:
        self.backend = None
        self.command_base_state = None
        self.analysis_base_state = None
        self._model_loaded = False
        self._loading = False
        self._ready = False
        self._offloaded = False
        self._load_error = message
        if fatal:
            self._fatal_error = message

    def _mark_warmup_complete_locked(self) -> None:
        self._warmup_status = "done"
        self._ready = True

    def _mark_warmup_failed_locked(self, message: str) -> None:
        # Warmup errors should not make daemon unusable.
        self._warmup_status = "error"
        self._warmup_error = message
        self._ready = True

    def _mark_offloaded_locked(self) -> None:
        self.backend = None
        self.command_base_state = None
        self.analysis_base_state = None
        self._model_loaded = False
        self._ready = False
        self._offloaded = True
        self._warmup_status = "pending"
        self._warmup_error = None

    def _mark_fatal_locked(self, message: str) -> None:
        self._fatal_error = message
        self._load_error = message

    def _spawn_load_thread_locked(self) -> None:
        threading.Thread(target=self._load_backend, daemon=True).start()

    def _load_backend(self) -> None:
        try:
            backend = self._init_backend(self.model_path)
            command_base_state = backend.build_base_state(COMMAND_MODE_SYSTEM_PROMPT)
            analysis_base_state = backend.build_base_state(ANALYSIS_MODE_SYSTEM_PROMPT)
            with self._state_cv:
                self._mark_loaded_locked(
                    backend, command_base_state, analysis_base_state
                )
                self._state_cv.notify_all()
            self._log("model loaded")
            if self._load_skip_warmup:
                self._log("daemon ready (warmup skipped)")
            else:
                threading.Thread(target=self._warmup_backend, daemon=True).start()
        except Exception as exc:
            with self._state_cv:
                self._mark_load_failed_locked(str(exc), fatal=True)
                self._state_cv.notify_all()
            self._log(f"daemon failed to initialize: {exc}")
            self._schedule_fatal_shutdown()

    def _warmup_backend(self) -> None:
        with self._state_lock:
            backend = self.backend
            command_base_state = self.command_base_state
            analysis_base_state = self.analysis_base_state
        if backend is None or command_base_state is None or analysis_base_state is None:
            return

        try:
            command_state = backend.clone_state(command_base_state)
            backend.prefill(
                command_state,
                render_command_prompt(
                    query="list files in current directory",
                    history=None,
                    shell="zsh",
                    cwd=os.getcwd(),
                    os_name=os.uname().sysname,
                ),
            )
            backend.generate_completion(
                command_state,
                {
                    "max_tokens": 1,
                    "temperature": 0.0,
                    "stop": ["\n\n", "<|endoftext|>", "<|im_start|>"],
                    "verbose": False,
                },
            )

            analysis_state = backend.clone_state(analysis_base_state)
            backend.prefill(
                analysis_state,
                render_analysis_prompt("hello\nworld", "what does this contain?"),
            )
            backend.generate_completion(
                analysis_state,
                {
                    "max_tokens": 1,
                    "temperature": 0.0,
                    "stop": ["\n\n", "<|endoftext|>", "<|im_start|>"],
                    "verbose": False,
                },
            )
            with self._state_cv:
                self._mark_warmup_complete_locked()
                self._state_cv.notify_all()
            self._log("warmup complete; daemon ready")
        except Exception as exc:
            with self._state_cv:
                self._mark_warmup_failed_locked(str(exc))
                self._state_cv.notify_all()
            self._log(f"warmup skipped due to error: {exc}")

    def run(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        server.listen(64)
        self._server_socket = server
        self._start_background_load()
        threading.Thread(target=self._idle_offload_loop, daemon=True).start()

        def _shutdown(signum: int, frame: Any) -> None:
            _ = signum, frame
            self.close()
            raise SystemExit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                if self._shutting_down:
                    break
                raise
            with conn:
                data = self._recv_line(conn)
                response = self._handle_request(data)
                try:
                    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                except OSError:
                    self._log("client disconnected before response was sent")

    def close(self) -> None:
        with self._state_cv:
            self._shutting_down = True
            self._state_cv.notify_all()
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None
        if self.socket_path.exists():
            self.socket_path.unlink()

    def _idle_offload_loop(self) -> None:
        while True:
            with self._state_cv:
                if self._shutting_down:
                    return
                timeout = self._idle_offload_wait_timeout_locked()
                if timeout is None:
                    self._state_cv.wait()
                    continue
                was_notified = self._state_cv.wait(timeout=timeout)
                if was_notified:
                    continue
                if not self._should_offload_locked():
                    continue
            self._offload_backend("idle timeout")

    def _should_offload_locked(self) -> bool:
        if self._idle_offload_secs < 0:
            return False
        idle_for = time.monotonic() - self._last_activity_at
        return (
            self._model_loaded
            and self._ready
            and not self._loading
            and self._active_requests == 0
            and idle_for >= self._idle_offload_secs
        )

    def _idle_offload_wait_timeout_locked(self) -> float | None:
        if self._idle_offload_secs < 0:
            return None
        if not (
            self._model_loaded
            and self._ready
            and not self._loading
            and self._active_requests == 0
        ):
            return None
        idle_for = time.monotonic() - self._last_activity_at
        return max(0.0, self._idle_offload_secs - idle_for)

    def _offload_backend(self, reason: str, force: bool = False) -> None:
        with self._state_cv:
            if self._loading or not self._model_loaded:
                return
            if not force and self._active_requests > 0:
                return
            backend = self.backend
            self._mark_offloaded_locked()
            self._state_cv.notify_all()
        if backend is not None:
            try:
                backend.unload_model()
            except Exception as exc:
                self._log(f"failed to unload backend cleanly: {exc}")
        self._log(f"model offloaded ({reason})")

    def _wait_until_ready_for_request(self) -> dict[str, Any] | None:
        with self._state_cv:
            while True:
                if self._fatal_error:
                    return self._fatal_status_response()
                if self._offloaded and not self._loading:
                    self._load_skip_warmup = True
                    self._mark_loading_locked()
                    self._spawn_load_thread_locked()
                if self._load_error:
                    return {
                        "type": "status",
                        "status": "error",
                        "message": self._load_error,
                        "model_status": "error",
                        "warmup_status": self._warmup_status,
                        "accepting_requests": False,
                    }
                if self._ready and self.backend is not None:
                    return None
                if not self._model_loaded and not self._loading and not self._offloaded:
                    self._load_skip_warmup = True
                    self._mark_loading_locked()
                    self._spawn_load_thread_locked()
                self._state_cv.wait(timeout=0.1)

    def _begin_request(self) -> dict[str, Any] | None:
        with self._state_cv:
            self._active_requests += 1
        status = self._wait_until_ready_for_request()
        if status is not None:
            with self._state_cv:
                self._active_requests = max(0, self._active_requests - 1)
                self._state_cv.notify_all()
            return status
        return None

    def _finish_request(self) -> None:
        with self._state_cv:
            self._active_requests = max(0, self._active_requests - 1)
            self._last_activity_at = time.monotonic()
            self._state_cv.notify_all()

    def _recover_from_backend_crash(self, exc: Exception) -> dict[str, Any] | None:
        attempt = self._recovery_attempts + 1
        self._log(
            f"backend crash detected (attempt {attempt}/{MAX_AUTO_RECOVERIES}): {exc}"
        )

        if attempt > MAX_AUTO_RECOVERIES:
            with self._state_cv:
                self._mark_fatal_locked(
                    f"backend crashed more than {MAX_AUTO_RECOVERIES} times; exiting"
                )
                self._state_cv.notify_all()
            self._schedule_fatal_shutdown()
            return self._fatal_status_response()

        self._recovery_attempts = attempt
        if _is_oom_error(exc) and self.model_path != FAST_MODEL:
            print(
                f"warning: backend crash looks like OOM; retrying with fast model {FAST_MODEL}",
                file=sys.stderr,
            )
            self.model_path = FAST_MODEL

        self._offload_backend("backend crash", force=True)
        self._start_background_load(on_demand=True)
        status = self._wait_until_ready_for_request()
        return status

    def _schedule_fatal_shutdown(self) -> None:
        self._schedule_process_exit(delay_secs=FATAL_EXIT_GRACE_SECS, exit_code=1)

    def _schedule_process_exit(self, delay_secs: float, exit_code: int) -> None:
        threading.Thread(
            target=self._exit_after_delay,
            args=(delay_secs, exit_code),
            daemon=True,
        ).start()

    def _exit_after_delay(self, delay_secs: float, exit_code: int) -> None:
        time.sleep(delay_secs)
        self.close()
        os._exit(exit_code)

    def _fatal_status_response(self) -> dict[str, Any]:
        return {
            "type": "status",
            "status": "error",
            "message": self._fatal_error or "fatal daemon error",
            "model_status": "error",
            "warmup_status": self._warmup_status,
            "accepting_requests": False,
        }

    def _recv_line(self, conn: socket.socket) -> str:
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        return b"".join(chunks).decode("utf-8", errors="replace").strip()

    def _handle_request(self, raw_data: str) -> dict[str, Any]:
        self._log(f"raw request: {raw_data}")
        try:
            req = json.loads(raw_data)
        except json.JSONDecodeError:
            return {"type": "analysis", "answer": "Invalid request"}

        mode = req.get("mode")
        if mode == "health":
            return self._health_response()
        if mode == "control":
            return self._handle_control_request(req)

        query = (req.get("query") or "").strip()
        if not query:
            return {"type": "analysis", "answer": "Query is required"}

        status = self._begin_request()
        if status is not None:
            return status

        try:
            while True:
                try:
                    if mode == "analysis":
                        response = self._answer_analysis(req)
                    elif mode == "command":
                        response = self._answer_command(req)
                    else:
                        response = {"type": "analysis", "answer": "Invalid mode"}
                    self._recovery_attempts = 0
                    return response
                except Exception as exc:
                    recovery_status = self._recover_from_backend_crash(exc)
                    if recovery_status is not None:
                        return recovery_status
        finally:
            self._finish_request()

    def _answer_command(self, req: dict[str, Any]) -> dict[str, Any]:
        backend = self.backend
        command_base_state = self.command_base_state
        if backend is None or command_base_state is None:
            return {
                "type": "status",
                "status": "initializing",
                "message": "Model is still loading",
            }
        state = backend.clone_state(command_base_state)
        prompt = render_command_prompt(
            query=req["query"],
            history=req.get("history"),
            shell=req.get("shell") or "unknown",
            cwd=req.get("cwd") or os.getcwd(),
            os_name=req.get("os_name") or os.uname().sysname,
        )
        self._log(f"command prompt:\n{prompt}")
        backend.prefill(state, prompt)
        raw = backend.generate_completion(
            state,
            {
                "max_tokens": 96,
                "temperature": 0.2,
                "stop": [
                    "\n\n",
                    "<|endoftext|>",
                    "<|im_start|>",
                    "<think>",
                    "</think>",
                ],
                "verbose": self.verbose,
            },
        )
        self._log_inference_metrics(backend, mode="command")
        self._log(f"raw model output (command):\n{raw}")
        parsed = _parse_llm_json(raw)

        command = parsed.get("command")
        runnable = bool(parsed.get("runnable", False))
        if not command:
            response: dict[str, Any] = {
                "type": "analysis",
                "answer": parsed.get("analysis") or "No command found",
            }
            if req.get("include_metrics"):
                response["metrics"] = dict(getattr(backend, "last_metrics", {}) or {})
            return response
        response = {"type": "command", "command": command.strip(), "runnable": runnable}
        if req.get("include_metrics"):
            response["metrics"] = dict(getattr(backend, "last_metrics", {}) or {})
        return response

    def _handle_control_request(self, req: dict[str, Any]) -> dict[str, Any]:
        action = req.get("action")
        force = bool(req.get("force", False))

        if action == "offload":
            with self._state_lock:
                is_loaded = self._model_loaded
                is_offloaded = self._offloaded
                is_loading = self._loading
            if is_loaded:
                self._offload_backend("cli request", force=True)
                return {
                    "type": "status",
                    "status": "ready",
                    "message": "calmd model offloaded",
                }
            if is_offloaded:
                return {
                    "type": "status",
                    "status": "ready",
                    "message": "calmd model already offloaded",
                }
            if is_loading:
                return {
                    "type": "status",
                    "status": "initializing",
                    "message": "calmd is loading; cannot offload yet",
                }
            return {
                "type": "status",
                "status": "ready",
                "message": "calmd has no loaded model",
            }

        if action == "shutdown":
            delay_secs = 0.0 if force else CONTROL_EXIT_DELAY_SECS
            message = (
                "calmd stopping immediately"
                if force
                else "calmd stopping gracefully"
            )
            self._schedule_process_exit(delay_secs=delay_secs, exit_code=0)
            return {
                "type": "status",
                "status": "ready",
                "message": message,
            }

        return {
            "type": "status",
            "status": "error",
            "message": "Invalid control action",
        }

    def _answer_analysis(self, req: dict[str, Any]) -> dict[str, Any]:
        backend = self.backend
        analysis_base_state = self.analysis_base_state
        if backend is None or analysis_base_state is None:
            return {
                "type": "status",
                "status": "initializing",
                "message": "Model is still loading",
            }
        state = backend.clone_state(analysis_base_state)
        prompt = render_analysis_prompt(req.get("stdin") or "", req["query"])
        self._log(f"analysis prompt:\n{prompt}")
        backend.prefill(state, prompt)
        raw = backend.generate_completion(
            state,
            {
                "max_tokens": 96,
                "temperature": 0.1,
                "stop": [
                    "\n\n",
                    "<|endoftext|>",
                    "<|im_start|>",
                    "<think>",
                    "</think>",
                ],
                "verbose": self.verbose,
            },
        )
        self._log_inference_metrics(backend, mode="analysis")
        self._log(f"raw model output (analysis):\n{raw}")
        parsed = _parse_llm_json(raw)
        answer = parsed.get("analysis") or parsed.get("answer") or raw.strip()
        response: dict[str, Any] = {"type": "analysis", "answer": answer}
        if req.get("include_metrics"):
            response["metrics"] = dict(getattr(backend, "last_metrics", {}) or {})
        return response

    def _health_response(self) -> dict[str, Any]:
        with self._state_lock:
            if self._fatal_error:
                return self._fatal_status_response()
            if self._load_error:
                return {
                    "type": "status",
                    "status": "error",
                    "message": self._load_error,
                    "model_status": "error",
                    "warmup_status": self._warmup_status,
                    "accepting_requests": False,
                }
            if self._offloaded:
                return {
                    "type": "status",
                    "status": "ready",
                    "message": "ready (model offloaded)",
                    "model_status": "offloaded",
                    "warmup_status": "pending",
                    "accepting_requests": True,
                }
            if self._ready:
                return {
                    "type": "status",
                    "status": "ready",
                    "message": "ready",
                    "model_status": "loaded",
                    "warmup_status": self._warmup_status,
                    "warmup_error": self._warmup_error,
                    "accepting_requests": True,
                }
            if self._model_loaded:
                return {
                    "type": "status",
                    "status": "warming_up",
                    "message": "model loaded; warmup in progress",
                    "model_status": "loaded",
                    "warmup_status": self._warmup_status,
                    "accepting_requests": False,
                }
            return {
                "type": "status",
                "status": "initializing",
                "message": "model loading" if self._loading else "model initializing",
                "model_status": "loading" if self._loading else "not_loaded",
                "warmup_status": self._warmup_status,
                "accepting_requests": False,
            }

    def _log(self, message: str) -> None:
        if not self.verbose:
            return
        print(f"[calmd] {message}", file=sys.stderr, flush=True)

    def _log_inference_metrics(self, backend: Any, mode: str) -> None:
        if not self.verbose:
            return
        metrics = getattr(backend, "last_metrics", None)
        if not isinstance(metrics, dict):
            return
        inference_ms = metrics.get("inference_ms")
        if inference_ms is None:
            return
        thinking = metrics.get("thinking_disabled")
        thinking_flag = f" thinking_disabled={thinking}" if thinking is not None else ""
        self._log(
            f"{mode} inference_ms={inference_ms} "
            f"model_family={metrics.get('model_family', 'unknown')}{thinking_flag}"
        )


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = _sanitize_model_text(raw)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # Plain-text fallback from model output.
    first = text.splitlines()[0].strip() if text else ""
    return {"command": first or None, "analysis": text or None, "runnable": bool(first)}


def _sanitize_model_text(text: str) -> str:
    cleaned = text.strip()
    # Strip common control/chat tokens leaked by some model templates.
    cleaned = re.sub(r"<\|endoftext\|>.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|im_start\|>.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|im_end\|>.*$", "", cleaned, flags=re.DOTALL)
    # Remove hidden reasoning tags if model emits them.
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</think>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _is_oom_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "out of memory",
        "oom",
        "insufficient memory",
        "cannot allocate memory",
        "resource exhausted",
    )
    return any(marker in text for marker in markers)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="calmd", description="calm local inference daemon"
    )
    parser.add_argument("--model-path", default=DEFAULT_MODEL)
    parser.add_argument(
        "--fast-model",
        action="store_true",
        help=f"use fast model preset ({FAST_MODEL})",
    )
    parser.add_argument("--socket", default=str(SOCKET_PATH))
    parser.add_argument(
        "--verbose", action="store_true", help="log raw requests/prompts/model outputs"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = FAST_MODEL if args.fast_model else args.model_path
    server = CalmdServer(
        model_path=model_path,
        socket_path=Path(args.socket).expanduser(),
        verbose=args.verbose,
    )
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
