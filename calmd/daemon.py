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

from calm.config import (
    DEFAULT_MODEL_PATH,
    FAST_MODEL_PATH,
    ensure_default_config_file,
    load_calmd_config,
)
from calm.platform_support import ensure_supported_runtime

from .backend.interface import InferenceBackend
from .prompts import (
    SMART_MODE_SYSTEM_PROMPT,
    render_smart_prompt,
)

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
        self.config = load_calmd_config()
        self.backend: InferenceBackend | None = None
        self.smart_base_state: Any | None = None
        self._load_error: str | None = None
        self._warmup_error: str | None = None
        self._ready = False
        self._model_loaded = False
        self._loading = False
        self._offloaded = False
        self._warmup_status = "pending"
        self._state_lock = threading.Lock()
        self._state_cv = threading.Condition(self._state_lock)
        self._backend_lock = threading.Lock()
        self._server_socket: socket.socket | None = None
        self._skip_warmup = self.config.skip_warmup
        self._load_skip_warmup = self._skip_warmup
        self._warmup_delay_secs = 3.0
        self._idle_offload_secs = self.config.idle_offload_secs
        self._last_activity_at = time.monotonic()
        self._active_requests = 0
        self._recovery_attempts = 0
        self._fatal_error: str | None = None
        self._shutting_down = False

    def _init_backend(self, model_path: str) -> InferenceBackend:
        self._log(f"loading model backend: {model_path}")
        from .backend.mlx_backend import MLXBackend

        try:
            backend = MLXBackend(config=self.config)
            backend.load_model(model_path)
            self._log("mlx_lm backend loaded")
            return backend
        except Exception as exc:
            if _is_oom_error(exc) and model_path != FAST_MODEL_PATH:
                print(
                    f"warning: model load OOM for {model_path}; retrying with fast model {FAST_MODEL_PATH}",
                    file=sys.stderr,
                )
                self._log("OOM detected, retrying fast model")
                backend = MLXBackend(config=self.config)
                backend.load_model(FAST_MODEL_PATH)
                self.model_path = FAST_MODEL_PATH
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
        self,
        backend: InferenceBackend,
        smart_base_state: Any,
    ) -> None:
        self.backend = backend
        self.smart_base_state = smart_base_state
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
        self.smart_base_state = None
        self._model_loaded = False
        self._loading = False
        self._ready = False
        self._offloaded = False
        self._load_error = message
        if fatal:
            self._fatal_error = message

    def _mark_warmup_complete_locked(self) -> None:
        if self._warmup_status != "skipped":
            self._warmup_status = "done"
        self._ready = True

    def _mark_warmup_failed_locked(self, message: str) -> None:
        # Warmup errors should not make daemon unusable.
        if self._warmup_status != "skipped":
            self._warmup_status = "error"
        self._warmup_error = message
        self._ready = True

    def _mark_offloaded_locked(self) -> None:
        self.backend = None
        self.smart_base_state = None
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
            smart_base_state = backend.build_base_state(SMART_MODE_SYSTEM_PROMPT)
            with self._state_cv:
                self._mark_loaded_locked(backend, smart_base_state)
                self._state_cv.notify_all()
            self._log("model loaded")

            with self._state_cv:
                if self._load_skip_warmup:
                    self._log("daemon ready (warmup skipped immediately)")
                    return

                # Reactive warmup: wait a few seconds before starting background inference.
                # If a client connects and requests health/query, it will set _load_skip_warmup.
                self._log(
                    f"waiting {self._warmup_delay_secs}s before starting warmup..."
                )
                was_notified = self._state_cv.wait(timeout=self._warmup_delay_secs)
                if was_notified or self._load_skip_warmup:
                    self._log("daemon ready (warmup skipped due to client activity)")
                    return

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
            smart_base_state = self.smart_base_state
        if backend is None or smart_base_state is None:
            return

        try:
            with self._backend_lock:
                smart_state = backend.clone_state(smart_base_state)
                backend.prefill(
                    smart_state,
                    render_smart_prompt(
                        query="list files in current directory",
                        stdin_text=None,
                        history=None,
                        shell="zsh",
                        cwd=os.getcwd(),
                        os_name=os.uname().sysname,
                        stdout_isatty=True,
                    ),
                )
                backend.generate_completion(
                    smart_state,
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
            self._log("shutting down, bye!")
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
                if self.backend is not None:
                    if not self._ready:
                        self._log("on-demand skip_warmup triggered by request")
                        self._load_skip_warmup = True
                        if self._warmup_status in ("pending", "in_progress"):
                            self._warmup_status = "skipped"
                        self._ready = True
                        self._state_cv.notify_all()
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
        if _is_oom_error(exc) and self.model_path != FAST_MODEL_PATH:
            print(
                f"warning: backend crash looks like OOM; retrying with fast model {FAST_MODEL_PATH}",
                file=sys.stderr,
            )
            self.model_path = FAST_MODEL_PATH

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

        # Signal that we have a client waiting, which will skip/cancel the
        # background warmup delay.
        with self._state_cv:
            if not self._load_skip_warmup:
                self._load_skip_warmup = True
                if self._model_loaded and not self._ready:
                    # If we are in the grace period, notify the load thread.
                    self._state_cv.notify_all()

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
                    if mode == "smart":
                        response = self._answer_smart(req)
                    elif mode == "analysis":
                        # Backward compatibility.
                        response = self._answer_smart(req)
                    elif mode == "command":
                        # Backward compatibility.
                        response = self._answer_smart(req)
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

    def _answer_smart(self, req: dict[str, Any]) -> dict[str, Any]:
        backend = self.backend
        smart_base_state = self.smart_base_state
        if backend is None or smart_base_state is None:
            return {
                "type": "status",
                "status": "initializing",
                "message": "Model is still loading",
            }
        state = backend.clone_state(smart_base_state)
        prompt = render_smart_prompt(
            query=req["query"],
            stdin_text=req.get("stdin"),
            history=req.get("history"),
            shell=req.get("shell") or "unknown",
            cwd=req.get("cwd") or os.getcwd(),
            os_name=req.get("os_name") or os.uname().sysname,
            stdout_isatty=req.get("stdout_isatty", True),
            force_command=req.get("force_command", False),
            force_analysis=req.get("force_analysis", False),
        )
        self._log(f"smart prompt:\n{prompt}")
        prefill_response = (
            "[TYPE:" if not self.config.disable_prefill_completion else None
        )
        with self._backend_lock:
            backend.prefill(state, prompt)
            raw = backend.generate_completion(
                state,
                {
                    "max_tokens": 4096 if self.config.enable_thinking else 256,
                    "temperature": 0.1,
                    "stop": [
                        "[/CONTENT]",
                        "<|endoftext|>",
                        "<|im_start|>",
                    ]
                    + (
                        []
                        if self.config.enable_thinking
                        else [
                            "<think>",
                            "</think>",
                            "<thinking>",
                            "</thinking>",
                            "<thought>",
                            "</thought>",
                            "<reasoning>",
                            "</reasoning>",
                            "<reflection>",
                            "</reflection>",
                        ]
                    ),
                    "verbose": self.verbose,
                },
                prefill_response=prefill_response,
            )
        self._log_inference_metrics(backend, mode="smart")
        self._log(f"raw model output (smart):\n{raw}")
        parsed = _parse_smart_tags(raw)
        self._log(f"parsed output (smart):\n{parsed}")

        response = {
            "type": parsed.get("type", "analysis"),
            "content": parsed.get("content", raw.strip()),
            "runnable": parsed.get("runnable", False),
            "safe": parsed.get("safe", True),
        }
        if req.get("include_raw"):
            response["raw_output"] = raw
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
                "calmd stopping immediately" if force else "calmd stopping gracefully"
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
        thinking_enabled = metrics.get("thinking_enabled")
        thinking_flag = (
            f" thinking_enabled={thinking_enabled}"
            if thinking_enabled is not None
            else ""
        )
        self._log(
            f"{mode} inference_ms={inference_ms} "
            f"model_family={metrics.get('model_family', 'unknown')}{thinking_flag}"
        )


def _parse_smart_tags(raw: str) -> dict[str, Any]:
    text = _sanitize_model_text(raw)
    out: dict[str, Any] = {
        "type": "analysis",
        "runnable": False,
        "safe": True,
        "content": "",
    }

    type_match = re.search(r"\[TYPE:\s*(COMMAND|ANALYSIS)\]", text, re.IGNORECASE)
    if type_match:
        out["type"] = type_match.group(1).lower()

    runnable_match = re.search(r"\[RUNNABLE:\s*(YES|NO)\]", text, re.IGNORECASE)
    if runnable_match:
        out["runnable"] = runnable_match.group(1).upper() == "YES"

    safe_match = re.search(r"\[SAFE:\s*(YES|NO)\]", text, re.IGNORECASE)
    if safe_match:
        out["safe"] = safe_match.group(1).upper() == "YES"

    content_match = re.search(r"\[CONTENT\]([\s\S]*?)\[/CONTENT\]", text, re.IGNORECASE)
    if content_match:
        out["content"] = content_match.group(1).strip()
    else:
        # Fallback: remove only specific metadata tags, preserving other bracket literals.
        # This prevents stripping [0-9]+ regex classes or other valid bracketed content
        # when the model fails to emit a closing [/CONTENT] tag.
        cleaned = text
        cleaned = re.sub(
            r"\[TYPE:\s*(?:COMMAND|ANALYSIS)\]", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"\[RUNNABLE:\s*(?:YES|NO)\]", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\[SAFE:\s*(?:YES|NO)\]", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[CONTENT\]", "", cleaned, flags=re.IGNORECASE)
        out["content"] = cleaned.strip()

    return out


def _sanitize_model_text(text: str) -> str:
    cleaned = text.strip()
    # Strip common control/chat tokens leaked by some model templates.
    cleaned = re.sub(r"<\|endoftext\|>.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|im_start\|>.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<\|im_end\|>.*$", "", cleaned, flags=re.DOTALL)
    # Remove hidden reasoning tags if model emits them.
    cleaned = re.sub(
        r"<(think|thinking|thought|reasoning|reflection)>[\s\S]*?</\1>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"<(think|thinking|thought|reasoning|reflection)>[\s\S]*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"</(think|thinking|thought|reasoning|reflection)>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
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
    config = load_calmd_config()
    parser = argparse.ArgumentParser(
        prog="calmd",
        description="Local inference daemon for the calm CLI tool. [C]alm [A]nswers via (local) [L]anguage [M]odels.",
    )
    parser.add_argument(
        "-m",
        "--model-path",
        default=None,
        help=f"The path to the local model directory or Hugging Face repo. \
        Otherwise defaults to preset ({DEFAULT_MODEL_PATH})",
    )
    parser.add_argument(
        "--fast-model",
        action="store_true",
        default=None,
        help=f"use fast model preset ({FAST_MODEL_PATH})",
    )
    parser.add_argument("--socket", default=None)
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=None,
        help="log raw requests/prompts/model outputs",
    )
    args = parser.parse_args()
    explicit_model_path = args.model_path is not None
    args.model_path = args.model_path or config.model_path
    if args.fast_model is None:
        args.fast_model = False if explicit_model_path else config.use_fast_model
    else:
        args.fast_model = True
    args.socket = args.socket or str(config.socket_path)
    args.verbose = config.verbose if args.verbose is None else True
    return args


def main() -> int:
    if not ensure_supported_runtime("calmd"):
        return 1
    ensure_default_config_file()
    args = parse_args()
    model_path = FAST_MODEL_PATH if args.fast_model else args.model_path
    server = CalmdServer(
        model_path=model_path,
        socket_path=Path(args.socket).expanduser(),
        verbose=args.verbose,
    )
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
