from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import sys
import threading
from pathlib import Path
from typing import Any

from calmd.backend.mlx_backend import MLXBackend, RuleBasedFallbackBackend
from calmd.prompts import (
    ANALYSIS_MODE_SYSTEM_PROMPT,
    COMMAND_MODE_SYSTEM_PROMPT,
    render_analysis_prompt,
    render_command_prompt,
)

SOCKET_PATH = Path(os.environ.get("CALMD_SOCKET", "~/.cache/calmd/socket")).expanduser()
DEFAULT_MODEL = "mlx-community/Qwen3.5-9B-OptiQ-4bit"
FAST_MODEL = "mlx-community/Qwen3.5-4B-OptiQ-4bit"


class CalmdServer:
    def __init__(
        self, model_path: str, socket_path: Path, verbose: bool = False
    ) -> None:
        self.model_path = model_path
        self.socket_path = socket_path
        self.verbose = verbose
        self.backend = None
        self.command_base_state = None
        self.analysis_base_state = None
        self._load_error: str | None = None
        self._warmup_error: str | None = None
        self._ready = False
        self._model_loaded = False
        self._warmup_status = "pending"
        self._state_lock = threading.Lock()
        self._server_socket: socket.socket | None = None
        self._skip_warmup = os.environ.get("CALMD_SKIP_WARMUP", "0") == "1"

    def _init_backend(self, model_path: str):
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
            print(
                f"warning: mlx_lm backend unavailable ({exc}); using fallback backend",
                file=sys.stderr,
            )
            backend = RuleBasedFallbackBackend()
            backend.load_model(model_path)
            self._log("fallback backend loaded")
            return backend

    def _load_backend(self) -> None:
        try:
            backend = self._init_backend(self.model_path)
            command_base_state = backend.build_base_state(COMMAND_MODE_SYSTEM_PROMPT)
            analysis_base_state = backend.build_base_state(ANALYSIS_MODE_SYSTEM_PROMPT)
            with self._state_lock:
                self.backend = backend
                self.command_base_state = command_base_state
                self.analysis_base_state = analysis_base_state
                self._model_loaded = True
                self._warmup_status = "skipped" if self._skip_warmup else "in_progress"
                self._ready = self._skip_warmup
            self._log("model loaded")
            if self._skip_warmup:
                self._log("daemon ready (warmup skipped)")
            else:
                threading.Thread(target=self._warmup_backend, daemon=True).start()
        except Exception as exc:
            with self._state_lock:
                self._load_error = str(exc)
            self._log(f"daemon failed to initialize: {exc}")

    def _warmup_backend(self) -> None:
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
            with self._state_lock:
                self._warmup_status = "done"
                self._ready = True
            self._log("warmup complete; daemon ready")
        except Exception as exc:
            with self._state_lock:
                self._warmup_status = "error"
                self._warmup_error = str(exc)
                # Warmup errors should not make daemon unusable.
                self._ready = True
            self._log(f"warmup skipped due to error: {exc}")

    def run(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        server.listen(64)
        self._server_socket = server
        threading.Thread(target=self._load_backend, daemon=True).start()

        def _shutdown(signum: int, frame: Any) -> None:
            _ = signum, frame
            self.close()
            raise SystemExit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while True:
            conn, _ = server.accept()
            with conn:
                data = self._recv_line(conn)
                response = self._handle_request(data)
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    def close(self) -> None:
        if self._server_socket is not None:
            self._server_socket.close()
            self._server_socket = None
        if self.socket_path.exists():
            self.socket_path.unlink()

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

        query = (req.get("query") or "").strip()
        if not query:
            return {"type": "analysis", "answer": "Query is required"}

        status = self._health_response()
        if status["status"] != "ready":
            return status

        if mode == "analysis":
            return self._answer_analysis(req)
        if mode == "command":
            return self._answer_command(req)
        return {"type": "analysis", "answer": "Invalid mode"}

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
            if self._load_error:
                return {
                    "type": "status",
                    "status": "error",
                    "message": self._load_error,
                    "model_status": "error",
                    "warmup_status": self._warmup_status,
                    "accepting_requests": False,
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
            "message": "model loading",
            "model_status": "loading",
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
