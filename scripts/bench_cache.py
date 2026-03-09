from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class RequestError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark calmd prefix-cache impact")
    parser.add_argument(
        "--rounds",
        type=int,
        default=10,
        help="number of times to run each request sample per mode",
    )
    parser.add_argument(
        "--socket",
        default="/tmp/calmd-bench.sock",
        help="unix socket path for benchmark daemon",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="optional model path to pass to calmd",
    )
    parser.add_argument(
        "--skip-daemon-warmup",
        action="store_true",
        help="set CALMD_SKIP_WARMUP=1 for both cache-on and cache-off runs",
    )
    parser.add_argument(
        "--log-dir",
        default="/tmp",
        help="directory to write daemon benchmark logs",
    )
    return parser.parse_args()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "mean": round(statistics.mean(values), 2),
        "p50": round(_percentile(values, 0.50), 2),
        "p95": round(_percentile(values, 0.95), 2),
    }


def _recv_line(client: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        chunk = client.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def _request(socket_path: str, payload: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        raw = _recv_line(client)
    if not raw:
        raise RequestError("empty response from daemon")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequestError(f"invalid JSON from daemon: {raw[:160]!r}") from exc


def _request_retry(
    socket_path: str, payload: dict[str, Any], retries: int = 3, delay_s: float = 0.05
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            return _request(socket_path, payload)
        except (OSError, RequestError) as exc:
            last_exc = exc
            time.sleep(delay_s)
    if last_exc is None:
        raise RequestError("request failed without exception details")
    raise RequestError(str(last_exc))


def _wait_ready(
    socket_path: str,
    proc: subprocess.Popen[str],
    log_path: Path,
    timeout_s: float = 600.0,
) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"calmd exited early with code {proc.returncode}. "
                f"See log: {log_path}\n{_tail_file(log_path)}"
            )
        try:
            response = _request(socket_path, {"mode": "health"})
            if response.get("status") == "ready":
                return
            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "daemon initialization failed"))
        except (OSError, RequestError):
            pass
        time.sleep(0.1)
    raise TimeoutError(f"calmd did not become ready within {int(timeout_s)}s")


def _start_daemon(
    *,
    socket_path: str,
    model_path: str | None,
    disable_prefix_cache: bool,
    skip_warmup: bool,
    log_path: Path,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["CALMD_SOCKET"] = socket_path
    env["CALMD_DISABLE_PREFIX_CACHE"] = "1" if disable_prefix_cache else "0"
    env["CALMD_SKIP_WARMUP"] = "1" if skip_warmup else "0"
    cmd = [sys.executable, "-m", "calmd", "--socket", socket_path]
    if model_path:
        cmd.extend(["--model-path", model_path])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log_file,
        text=True,
    )
    log_file.close()
    return proc


def _stop_daemon(proc: subprocess.Popen[str], socket_path: str) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    try:
        Path(socket_path).unlink(missing_ok=True)
    except OSError:
        pass


def _tail_file(path: Path, max_lines: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(unable to read daemon log)"
    if not lines:
        return "(daemon log is empty)"
    tail = lines[-max_lines:]
    return "\n".join(tail)


def _run_benchmark(socket_path: str, rounds: int) -> dict[str, dict[str, list[float]]]:
    command_samples = [
        "show files bigger than 200MB in current directory",
        "find what is listening on port 5432",
        "how to extract backup.tar.gz",
        "top 5 memory processes",
    ]
    analysis_samples = [
        ("alpha\nbeta\ngamma", "how many lines are there"),
        ("service up\nservice down\nservice up", "which status appears most"),
        ("PID CPU MEM\n1 10 20\n2 20 10", "which pid has highest cpu"),
        ("error: timeout\nok: done\nerror: disk", "how many errors"),
    ]

    result = {
        "command": {"e2e_ms": [], "inference_ms": []},
        "analysis": {"e2e_ms": [], "inference_ms": []},
    }

    for _ in range(rounds):
        for query in command_samples:
            payload = {
                "mode": "command",
                "query": query,
                "history": "git status",
                "shell": "zsh",
                "cwd": os.getcwd(),
                "os_name": os.uname().sysname,
                "include_metrics": True,
            }
            started = time.perf_counter()
            response = _request_retry(socket_path, payload)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            result["command"]["e2e_ms"].append(elapsed_ms)
            inference_ms = (response.get("metrics") or {}).get("inference_ms")
            if isinstance(inference_ms, (int, float)):
                result["command"]["inference_ms"].append(float(inference_ms))

        for stdin_text, query in analysis_samples:
            payload = {
                "mode": "analysis",
                "query": query,
                "stdin": stdin_text,
                "include_metrics": True,
            }
            started = time.perf_counter()
            response = _request_retry(socket_path, payload)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            result["analysis"]["e2e_ms"].append(elapsed_ms)
            inference_ms = (response.get("metrics") or {}).get("inference_ms")
            if isinstance(inference_ms, (int, float)):
                result["analysis"]["inference_ms"].append(float(inference_ms))
    return result


def _fmt_delta(old: float, new: float) -> str:
    if old <= 0:
        return "n/a"
    delta = old - new
    pct = (delta / old) * 100.0
    return f"{delta:.2f} ms ({pct:.1f}%)"


def _print_summary(cache_off: dict[str, dict[str, list[float]]], cache_on: dict[str, dict[str, list[float]]]) -> None:
    print("\n== Summary (cache-off baseline -> cache-on) ==")
    for mode in ("command", "analysis"):
        print(f"\n[{mode}]")
        for metric in ("e2e_ms", "inference_ms"):
            off = _summarize(cache_off[mode][metric])
            on = _summarize(cache_on[mode][metric])
            print(f"{metric}:")
            print(f"  off mean/p50/p95: {off['mean']:.2f} / {off['p50']:.2f} / {off['p95']:.2f}")
            print(f"   on mean/p50/p95: {on['mean']:.2f} / {on['p50']:.2f} / {on['p95']:.2f}")
            print(f"  improvement mean: {_fmt_delta(off['mean'], on['mean'])}")
            print(f"  improvement  p50: {_fmt_delta(off['p50'], on['p50'])}")
            print(f"  improvement  p95: {_fmt_delta(off['p95'], on['p95'])}")


def main() -> int:
    args = parse_args()
    socket_path = str(Path(args.socket).expanduser())
    Path(socket_path).unlink(missing_ok=True)

    log_dir = Path(args.log_dir).expanduser()
    off_log = log_dir / "calmd-bench-cache-off.log"
    on_log = log_dir / "calmd-bench-cache-on.log"

    print("Running cache-off benchmark...")
    off_proc = _start_daemon(
        socket_path=socket_path,
        model_path=args.model_path,
        disable_prefix_cache=True,
        skip_warmup=args.skip_daemon_warmup,
        log_path=off_log,
    )
    try:
        _wait_ready(socket_path, off_proc, off_log)
        cache_off = _run_benchmark(socket_path, args.rounds)
    finally:
        _stop_daemon(off_proc, socket_path)

    print("Running cache-on benchmark...")
    on_proc = _start_daemon(
        socket_path=socket_path,
        model_path=args.model_path,
        disable_prefix_cache=False,
        skip_warmup=args.skip_daemon_warmup,
        log_path=on_log,
    )
    try:
        _wait_ready(socket_path, on_proc, on_log)
        cache_on = _run_benchmark(socket_path, args.rounds)
    finally:
        _stop_daemon(on_proc, socket_path)

    _print_summary(cache_off, cache_on)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
