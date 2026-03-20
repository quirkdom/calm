from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

AVAILABLE_FEATURES = ("prefix-cache", "warmup", "prefill")


class RequestError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark calmd daemon performance")
    parser.add_argument(
        "-x",
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
        "-m",
        "--model-path",
        default=None,
        help="optional model path to pass to calmd",
    )
    parser.add_argument(
        "--log-dir",
        default="benchmarks/logs",
        help="directory to write timestamped benchmark report logs",
    )
    parser.add_argument(
        "--enable-longtail",
        action="store_true",
        help="include longtail analysis samples using calmd/daemon.py code blob",
    )
    parser.add_argument(
        "--control",
        default=None,
        help="comma-separated features for control run",
    )
    parser.add_argument(
        "--experiment",
        default=None,
        help="comma-separated features for experiment run",
    )
    return parser.parse_args()


def _parse_feature_set(raw: str | None, label: str) -> set[str]:
    if raw is None:
        return set()
    out = {part.strip() for part in raw.split(",") if part.strip()}
    unknown = sorted(out.difference(AVAILABLE_FEATURES))
    if unknown:
        raise ValueError(
            f"{label} has unknown feature(s): {', '.join(unknown)}. "
            f"Available: {', '.join(AVAILABLE_FEATURES)}"
        )
    return out


def _feature_summary(features: set[str]) -> str:
    if not features:
        return "(none)"
    return ",".join(sorted(features))


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
    proc: subprocess.Popen[bytes],
    timeout_s: float = 600.0,
) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"calmd exited early with code {proc.returncode}")
        try:
            response = _request(socket_path, {"mode": "health"})
            if response.get("status") == "ready":
                return
            if response.get("status") == "error":
                raise RuntimeError(
                    response.get("message", "daemon initialization failed")
                )
        except (OSError, RequestError):
            pass
        time.sleep(0.1)
    raise TimeoutError(f"calmd did not become ready within {int(timeout_s)}s")


def _start_daemon(
    *,
    socket_path: str,
    model_path: str | None,
    features: set[str],
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["CALMD_SOCKET"] = socket_path
    env["CALMD_DISABLE_PREFIX_CACHE"] = "0" if "prefix-cache" in features else "1"
    env["CALMD_SKIP_WARMUP"] = "0" if "warmup" in features else "1"
    env["CALMD_PREFILL_COMPLETION"] = "1" if "prefill" in features else "0"
    cmd = [sys.executable, "-m", "calmd", "--socket", socket_path]
    if model_path:
        cmd.extend(["--model-path", model_path])
    return subprocess.Popen(cmd, env=env)


def _stop_daemon(proc: subprocess.Popen[bytes], socket_path: str) -> None:
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


def _run_benchmark(
    socket_path: str, rounds: int, enable_longtail: bool
) -> dict[str, dict[str, list[float]]]:
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
    if enable_longtail:
        analysis_samples.extend(_longtail_analysis_samples())

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


def _longtail_analysis_samples() -> list[tuple[str, str]]:
    code_blob = _load_code_blob(min_lines=200, max_lines=260)
    return [
        (
            code_blob,
            "Summarize the daemon lifecycle stages and when requests are accepted.",
        ),
        (
            code_blob,
            "List two potential failure paths and how the daemon reports them.",
        ),
    ]


def _load_code_blob(min_lines: int, max_lines: int) -> str:
    path = Path("calmd/daemon.py")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < min_lines:
        raise RuntimeError(
            f"{path} has only {len(lines)} lines; expected at least {min_lines}"
        )
    return "\n".join(lines[:max_lines])


def _fmt_delta(old: float, new: float) -> str:
    if old <= 0:
        return "n/a"
    delta = old - new
    pct = (delta / old) * 100.0
    return f"{delta:.2f} ms ({pct:.1f}%)"


def _build_summary_lines(
    control: dict[str, dict[str, list[float]]],
    experiment: dict[str, dict[str, list[float]]],
    control_features: set[str],
    experiment_features: set[str],
) -> list[str]:
    lines: list[str] = []
    lines.append("== Summary (control baseline -> experiment) ==")
    lines.append(f"control.features: {_feature_summary(control_features)}")
    lines.append(f"experiment.features: {_feature_summary(experiment_features)}")
    for mode in ("command", "analysis"):
        lines.append("")
        lines.append(f"[{mode}]")
        for metric in ("e2e_ms", "inference_ms"):
            off = _summarize(control[mode][metric])
            on = _summarize(experiment[mode][metric])
            lines.append(f"{metric}:")
            lines.append(
                f"  control mean/p50/p95: {off['mean']:.2f} / {off['p50']:.2f} / {off['p95']:.2f}"
            )
            lines.append(
                f"  experiment mean/p50/p95: {on['mean']:.2f} / {on['p50']:.2f} / {on['p95']:.2f}"
            )
            lines.append(f"  improvement mean: {_fmt_delta(off['mean'], on['mean'])}")
            lines.append(f"  improvement  p50: {_fmt_delta(off['p50'], on['p50'])}")
            lines.append(f"  improvement  p95: {_fmt_delta(off['p95'], on['p95'])}")
    return lines


def _write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_no_feature_warning() -> None:
    print("No feature sets provided; benchmark did not run.")
    print(f"Available features: {', '.join(AVAILABLE_FEATURES)}")
    print("Use:")
    print("  --control=prefix-cache --experiment=prefix-cache,warmup")
    print("Any side omitted means empty feature set for that side.")


def main() -> int:
    args = parse_args()
    if args.control is None and args.experiment is None:
        _print_no_feature_warning()
        return 0

    control_features = _parse_feature_set(args.control, "control")
    experiment_features = _parse_feature_set(args.experiment, "experiment")

    socket_path = str(Path(args.socket).expanduser())
    Path(socket_path).unlink(missing_ok=True)

    run_ts = dt.datetime.now().astimezone()
    run_id = run_ts.strftime("%Y%m%d-%H%M%S")
    log_dir = Path(args.log_dir).expanduser()
    report_log = log_dir / f"{run_id}.report.log"

    print(
        f"Running control benchmark (features={_feature_summary(control_features)})..."
    )
    control_proc = _start_daemon(
        socket_path=socket_path,
        model_path=args.model_path,
        features=control_features,
    )
    try:
        _wait_ready(socket_path, control_proc)
        control_result = _run_benchmark(
            socket_path, rounds=args.rounds, enable_longtail=args.enable_longtail
        )
    finally:
        _stop_daemon(control_proc, socket_path)

    print(
        f"Running experiment benchmark (features={_feature_summary(experiment_features)})..."
    )
    experiment_proc = _start_daemon(
        socket_path=socket_path,
        model_path=args.model_path,
        features=experiment_features,
    )
    try:
        _wait_ready(socket_path, experiment_proc)
        experiment_result = _run_benchmark(
            socket_path, rounds=args.rounds, enable_longtail=args.enable_longtail
        )
    finally:
        _stop_daemon(experiment_proc, socket_path)

    lines = [
        f"timestamp: {run_ts.isoformat()}",
        f"rounds: {args.rounds}",
        f"model_path: {args.model_path or '(default)'}",
        f"enable_longtail: {args.enable_longtail}",
        f"control.features: {_feature_summary(control_features)}",
        f"experiment.features: {_feature_summary(experiment_features)}",
        "",
    ]
    summary_lines = _build_summary_lines(
        control_result,
        experiment_result,
        control_features=control_features,
        experiment_features=experiment_features,
    )
    lines.extend(summary_lines)
    print("\n" + "\n".join(summary_lines))
    _write_report(report_log, lines)
    print(f"\nWrote benchmark report: {report_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
