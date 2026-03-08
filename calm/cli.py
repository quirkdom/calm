from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("CALMD_SOCKET", "~/.cache/calmd/socket")).expanduser()
DAEMON_WAIT_TIMEOUT_SECS = float(os.environ.get("CALMD_WAIT_TIMEOUT", "300"))
DANGEROUS_TOKENS = {
    "rm",
    "mkfs",
    "dd",
    "shutdown",
    "reboot",
    "poweroff",
    "killall",
    "chmod",
    "chown",
    ">",
    ">>",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="calm", description="CLI answers via local calmd")
    parser.add_argument("-y", "--yolo", action="store_true", help="run command automatically")
    parser.add_argument("-f", "--force", action="store_true", help="allow dangerous commands")
    parser.add_argument("query", help="question or task")
    return parser.parse_args()


def detect_stdin() -> str | None:
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read()
    return data if data.strip() else None


def read_last_history_command() -> str | None:
    shell_path = os.environ.get("SHELL", "")
    home = Path.home()

    if shell_path.endswith("zsh"):
        path = home / ".zsh_history"
        parser = _parse_zsh_history
    elif shell_path.endswith("bash"):
        path = home / ".bash_history"
        parser = _parse_plain_history
    else:
        for candidate in (home / ".zsh_history", home / ".bash_history"):
            if candidate.exists():
                path = candidate
                parser = _parse_zsh_history if candidate.name == ".zsh_history" else _parse_plain_history
                break
        else:
            return None

    if not path.exists():
        return None

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    for line in reversed(lines):
        cmd = parser(line)
        if cmd:
            return cmd
    return None


def _parse_plain_history(line: str) -> str | None:
    text = line.strip()
    return text or None


def _parse_zsh_history(line: str) -> str | None:
    line = line.strip()
    if not line:
        return None
    if line.startswith(":") and ";" in line:
        return line.split(";", 1)[1].strip() or None
    return line


def make_request(payload: dict) -> dict:
    ensure_daemon_running()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(SOCKET_PATH))
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        data = _recv_line(client)

    return json.loads(data)


def _recv_line(client: socket.socket) -> str:
    chunks = []
    while True:
        chunk = client.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def is_dangerous(command: str) -> bool:
    # Conservative static check for obvious destructive operations.
    try:
        tokens = shlex.split(command)
    except ValueError:
        return True

    token_set = set(tokens)
    if token_set.intersection(DANGEROUS_TOKENS):
        return True
    if any(token.startswith("/") and token in {"/", "/etc", "/usr", "/bin", "/sbin"} for token in tokens):
        return True
    return False


def execute_command(command: str) -> int:
    proc = subprocess.run(command, shell=True)
    return proc.returncode


def ensure_daemon_running() -> None:
    health = _check_daemon_health()
    if health and health.get("status") == "ready":
        return

    if health is None:
        start_calmd()

    deadline = time.time() + DAEMON_WAIT_TIMEOUT_SECS
    last_note = 0.0
    last_status = ""
    while time.time() < deadline:
        health = _check_daemon_health()
        if health and health.get("status") == "ready":
            return
        if health and health.get("status") == "error":
            message = health.get("message", "calmd failed to initialize")
            raise RuntimeError(f"calmd failed to initialize: {message}")
        now = time.time()
        status = health.get("status", "starting") if health else "starting"
        if now - last_note >= 5.0 or status != last_status:
            print(f"waiting for calmd ({status})...", file=sys.stderr)
            last_note = now
            last_status = status
        time.sleep(0.05)

    raise RuntimeError(
        f"calmd not ready after {int(DAEMON_WAIT_TIMEOUT_SECS)}s; "
        "set CALMD_WAIT_TIMEOUT to increase wait duration"
    )


def _check_daemon_health() -> dict | None:
    if not SOCKET_PATH.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(SOCKET_PATH))
            client.sendall((json.dumps({"mode": "health"}) + "\n").encode("utf-8"))
            raw = _recv_line(client)
        response = json.loads(raw)
        if isinstance(response, dict) and response.get("type") == "status":
            return response
        # Backward compatibility with older daemon versions.
        return {"status": "ready", "message": "connected"}
    except OSError:
        return None
    except json.JSONDecodeError:
        return {"status": "initializing", "message": "invalid health response"}


def start_calmd() -> None:
    # Launch daemon as detached background process using the same Python env.
    cmd = [sys.executable, "-m", "calmd"]
    if "CALMD_SOCKET" in os.environ:
        cmd.extend(["--socket", str(SOCKET_PATH)])

    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def main() -> int:
    args = parse_args()

    stdin_text = detect_stdin()
    mode = "analysis" if stdin_text is not None else "command"

    payload = {
        "query": args.query,
        "mode": mode,
        "stdin": stdin_text,
        "history": read_last_history_command(),
        "shell": os.path.basename(os.environ.get("SHELL", "")) or "unknown",
        "cwd": os.getcwd(),
        "os_name": os.uname().sysname,
    }

    try:
        response = make_request(payload)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if response.get("type") == "analysis":
        print(response.get("answer", ""))
        return 0

    if response.get("type") == "status":
        print(f"error: calmd status={response.get('status')}: {response.get('message', '')}", file=sys.stderr)
        return 1

    if response.get("type") != "command":
        print("error: invalid daemon response", file=sys.stderr)
        return 1

    command = response.get("command", "").strip()
    runnable = bool(response.get("runnable", False))

    if not command:
        print("No command generated.", file=sys.stderr)
        return 1

    print(command)

    if not runnable:
        return 0

    if is_dangerous(command) and not args.force:
        print("Refusing dangerous command without --force", file=sys.stderr)
        return 1

    should_run = args.yolo
    if not should_run:
        answer = input("\nRun this command? [y/N] ").strip().lower()
        should_run = answer in {"y", "yes"}

    if should_run:
        return execute_command(command)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
