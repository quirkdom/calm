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

from calm.config import load_calm_cli_config
from calm.platform_support import ensure_supported_runtime
from calm.service import (
    debug_enabled,
    debug_log,
    find_custom_service,
    find_homebrew_service,
    install_service,
    managed_service_status,
    start_service,
    stop_service,
    uninstall_service,
    unset_skip_warmup_env,
)

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
DAEMON_ACTIONS = ("install", "uninstall", "start", "stop", "offload")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="calm",
        description="[C]alm [A]nswers via (local) [L]anguage [M]odels. \
        calm is a CLI tool that answers simple questions using a local language model. \
        calm runs and communicates with the calmd LM server daemon.",
    )
    parser.add_argument(
        "-y", "--yolo", action="store_true", help="run command automatically"
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="allow dangerous commands; with -d stop, force shutdown",
    )
    parser.add_argument(
        "-d",
        "--daemon",
        choices=DAEMON_ACTIONS,
        metavar="ACTION",
        help="manage calmd: install, uninstall, start, stop, offload",
    )
    parser.add_argument("query", nargs="?", help="question or task")
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
                parser = (
                    _parse_zsh_history
                    if candidate.name == ".zsh_history"
                    else _parse_plain_history
                )
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


def make_request(payload: dict, ensure_running: bool = True) -> dict:
    config = load_calm_cli_config()
    if ensure_running:
        ensure_daemon_running()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(config.socket_path))
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
    if any(
        token.startswith("/") and token in {"/", "/etc", "/usr", "/bin", "/sbin"}
        for token in tokens
    ):
        return True
    return False


def execute_command(command: str) -> int:
    proc = subprocess.run(command, shell=True)
    return proc.returncode


def ensure_daemon_running() -> None:
    config = load_calm_cli_config()
    health = _check_daemon_health()
    if health and health.get("status") == "ready":
        return

    last_note = 0.0
    last_status = ""
    pending_skip_warmup_unset = False
    if health is None:
        print("waiting for calmd (starting)...", file=sys.stderr)
        last_note = time.time()
        last_status = "starting"
        pending_skip_warmup_unset = start_calmd(skip_warmup=True)

    deadline = time.time() + config.wait_timeout_secs
    try:
        while time.time() < deadline:
            health = _check_daemon_health()
            if pending_skip_warmup_unset and health is not None:
                unset_skip_warmup_env()
                pending_skip_warmup_unset = False
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
    finally:
        if pending_skip_warmup_unset:
            unset_skip_warmup_env()

    raise RuntimeError(
        f"calmd not ready after {int(config.wait_timeout_secs)}s; "
        "set CALMD_WAIT_TIMEOUT_SECS to increase wait duration"
    )


def notify_if_daemon_offloaded() -> None:
    health = _check_daemon_health()
    if not health:
        return
    if health.get("status") != "ready":
        return
    if health.get("model_status") != "offloaded":
        return
    print("waking calmd (model was offloaded)...", file=sys.stderr)


def _check_daemon_health() -> dict | None:
    config = load_calm_cli_config()
    if not config.socket_path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(config.socket_path))
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


def start_calmd(skip_warmup: bool = False) -> bool:
    started_at = time.monotonic()
    if debug_enabled():
        debug_log(f"start_calmd entered skip_warmup={skip_warmup}")
    service = find_homebrew_service() or find_custom_service()
    if service is not None:
        status, message = start_service(skip_warmup=skip_warmup, service=service)
        if status == 0:
            debug_log(
                f"managed start completed elapsed_ms={int((time.monotonic() - started_at) * 1000)}"
            )
            return skip_warmup
        print(
            f"warning: failed to start managed calmd ({message}); falling back",
            file=sys.stderr,
        )
        debug_log(f"managed start failed: {message}")

    # Launch daemon as detached background process using the same Python env.
    cmd = [sys.executable, "-m", "calmd"]
    if "CALMD_SOCKET" in os.environ:
        cmd.extend(["--socket", os.environ["CALMD_SOCKET"]])
    env = os.environ.copy()
    if skip_warmup:
        env["CALMD_SKIP_WARMUP"] = "1"

    subprocess.Popen(
        cmd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    debug_log(
        f"unmanaged start launched cmd={cmd!r} elapsed_ms={int((time.monotonic() - started_at) * 1000)}"
    )
    return False


def daemon_is_running() -> bool:
    health = _check_daemon_health()
    return health is not None


def offload_daemon() -> int:
    if not daemon_is_running():
        print("calmd is not running", file=sys.stderr)
        return 0

    try:
        response = make_request(
            {"mode": "control", "action": "offload"}, ensure_running=False
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    message = response.get("message", "calmd offloaded")
    if response.get("status") == "error":
        print(f"error: {message}", file=sys.stderr)
        return 1
    print(message)
    return 0


def stop_unmanaged_daemon(force: bool) -> int:
    config = load_calm_cli_config()
    if not daemon_is_running():
        print("calmd is not running", file=sys.stderr)
        return 0

    if force:
        return _send_shutdown_request(force=True)

    status = _send_shutdown_request(force=False)
    if status != 0:
        return status

    deadline = time.time() + config.shutdown_timeout_secs
    while time.time() < deadline:
        if not daemon_is_running():
            print("calmd stopped")
            return 0
        time.sleep(0.05)

    print("calmd did not stop gracefully; forcing shutdown", file=sys.stderr)
    status = _send_shutdown_request(force=True)
    if status != 0:
        return status

    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not daemon_is_running():
            print("calmd stopped")
            return 0
        time.sleep(0.05)

    print("error: calmd is still running after forced shutdown", file=sys.stderr)
    return 1


def terminate_daemon(force: bool) -> int:
    service, _loaded = managed_service_status()
    if service is not None:
        status, message = stop_service()
        if status != 0:
            print(f"error: {message}", file=sys.stderr)
            return 1
        print(message)
        return 0
    print(
        "error: custom calmd LaunchAgent is not installed; `calm -d stop` only manages the LaunchAgent",
        file=sys.stderr,
    )
    return 1


def _send_shutdown_request(force: bool) -> int:
    try:
        response = make_request(
            {"mode": "control", "action": "shutdown", "force": force},
            ensure_running=False,
        )
    except Exception as exc:
        if force and not daemon_is_running():
            print("calmd stopped")
            return 0
        print(f"error: {exc}", file=sys.stderr)
        return 1

    message = response.get("message", "calmd stopping")
    if response.get("status") == "error":
        print(f"error: {message}", file=sys.stderr)
        return 1
    print(message)
    return 0


def handle_daemon_action(action: str, force: bool) -> int:
    if action == "install":
        status, message = install_service()
        print(message, file=sys.stderr if status != 0 else sys.stdout)
        return status
    if action == "uninstall":
        status, message = uninstall_service()
        print(message, file=sys.stderr if status != 0 else sys.stdout)
        return status
    if action == "start":
        if find_homebrew_service() is not None:
            print(
                "error: homebrew service detected; use `brew services` instead",
                file=sys.stderr,
            )
            return 1
        service = find_custom_service()
        if service is None:
            print(
                "error: custom calmd LaunchAgent is not installed; run `calm -d install` first",
                file=sys.stderr,
            )
            return 1
        if daemon_is_running() and managed_service_status()[1] is False:
            print(
                "stopping unmanaged calmd before starting LaunchAgent-managed daemon",
                file=sys.stderr,
            )
            status = stop_unmanaged_daemon(force=force)
            if status != 0:
                return status
        status, message = start_service(skip_warmup=False, service=service)
        print(message, file=sys.stderr if status != 0 else sys.stdout)
        return status
    if action == "stop":
        return terminate_daemon(force=force)
    if action == "offload":
        return offload_daemon()
    print(f"error: unsupported daemon action: {action}", file=sys.stderr)
    return 1


def main() -> int:
    args = parse_args()
    if args.daemon and args.query:
        print("error: cannot combine query with -d/--daemon", file=sys.stderr)
        return 1
    if not args.daemon and not args.query:
        print("error: query is required", file=sys.stderr)
        return 1
    if not ensure_supported_runtime("calm"):
        return 1

    if args.daemon:
        return handle_daemon_action(args.daemon, force=args.force)

    stdin_text = detect_stdin()
    mode = "analysis" if stdin_text is not None else "command"
    notify_if_daemon_offloaded()

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
        print(
            f"error: calmd status={response.get('status')}: {response.get('message', '')}",
            file=sys.stderr,
        )
        return 1

    if response.get("type") != "command":
        print("error: invalid daemon response", file=sys.stderr)
        return 1

    command = response.get("command", "").strip()
    runnable = bool(response.get("runnable", False))

    if not command:
        print("No command generated.", file=sys.stderr)
        return 1

    # In a piped chain, we only want the clean output on stdout.
    print(command)

    if not runnable:
        return 0

    if is_dangerous(command) and not args.force:
        print("Refusing dangerous command without --force", file=sys.stderr)
        return 1

    should_run = args.yolo
    # Only prompt if stdout is a terminal (so we don't corrupt the pipe)
    # AND stdin is a terminal (so we can actually read the user's y/n).
    if not should_run and sys.stdout.isatty() and sys.stdin.isatty():
        try:
            answer = input("\nRun this command? [y/N] ").strip().lower()
            should_run = answer in {"y", "yes"}
        except EOFError:
            pass

    if should_run:
        return execute_command(command)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
