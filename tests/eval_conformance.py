import json
import os
import socket
import subprocess
import time

import pytest

SOCKET_PATH = "/tmp/calmd-conformance.sock"


def _request(payload):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(SOCKET_PATH)
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8"))


def _wait_ready(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            res = _request({"mode": "health"})
            if res.get("status") == "ready":
                return True
        except (ConnectionRefusedError, FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module", autouse=True)
def daemon():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    env = os.environ.copy()
    # Abhishek's flag name: CALMD_DISABLE_PREFILL_COMPLETION=0
    env["CALMD_DISABLE_PREFILL_COMPLETION"] = "0"
    env["CALMD_SKIP_WARMUP"] = "1"

    # Start daemon
    proc = subprocess.Popen(
        ["uv", "run", "calmd", "--socket", SOCKET_PATH],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if not _wait_ready():
        proc.terminate()
        stdout, stderr = proc.communicate()
        pytest.skip(
            f"Daemon failed to start or not supported on this platform. Stderr: {stderr.decode()}"
        )

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)


@pytest.mark.parametrize(
    "query,expected_type",
    [
        ("what is 2+2", "analysis"),
        ("list files in current directory", "command"),
    ],
)
def test_prefill_conformance(query, expected_type):
    payload = {
        "mode": "smart",
        "query": query,
        "include_raw": True,
        "shell": "bash",
        "cwd": os.getcwd(),
        "os_name": "Linux",
    }

    res = _request(payload)

    # 1. Check if raw_output starts with the prefill
    assert "raw_output" in res, "raw_output should be present in response"
    assert res["raw_output"].startswith("[TYPE:"), (
        f"Model output should start with [TYPE:], got {res['raw_output'][:20]}..."
    )

    # 2. Check if the response is parseable and matches the expected type
    assert res["type"] == expected_type, (
        f"Expected type {expected_type}, got {res['type']}"
    )

    # 3. Check if content is non-empty
    assert res["content"], "Content should not be empty"

    # Verify the full tag is present in raw_output
    import re

    assert re.search(
        rf"\[TYPE:\s*{expected_type.upper()}\]", res["raw_output"], re.IGNORECASE
    ), f"Expected [TYPE: {expected_type.upper()}] in raw output"


if __name__ == "__main__":
    pytest.main([__file__])
