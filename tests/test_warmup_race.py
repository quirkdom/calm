import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SOCKET_PATH = Path("~/.cache/calmd/test_warmup_reactive.sock").expanduser()


def check_health() -> dict | None:
    if not SOCKET_PATH.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(SOCKET_PATH))
            client.sendall((json.dumps({"mode": "health"}) + "\n").encode("utf-8"))
            raw = client.recv(4096).decode("utf-8").strip()
            return json.loads(raw)
    except Exception as _:
        return None


def test_warmup_skip_on_poll():
    """
    Test that the daemon skips warmup simply because a client is polling health.
    """
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Start daemon WITHOUT skip_warmup env
    proc = subprocess.Popen(
        [sys.executable, "-m", "calmd", "--socket", str(SOCKET_PATH)],
        env={**os.environ, "CALMD_SKIP_WARMUP": "0"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Poll health immediately - this signal should trigger skip_warmup in the daemon
        deadline = time.time() + 30
        status_seen = None
        while time.time() < deadline:
            health = check_health()
            if health:
                status_seen = health.get("status")
                # Once it's ready, we can stop
                if status_seen == "ready":
                    break
                # If it reached warming_up, then we failed to skip
                if status_seen == "warming_up":
                    break
            time.sleep(0.1)

        assert status_seen == "ready", (
            f"Daemon should have skipped warmup due to polling (status: {status_seen})"
        )

        health = check_health()
        assert health is not None
        assert health.get("warmup_status") == "skipped"

    finally:
        proc.terminate()
        proc.wait()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()


def test_warmup_happens_no_client():
    """
    Test that if NO client polls, the daemon eventually enters warming_up.
    """
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    proc = subprocess.Popen(
        [sys.executable, "-m", "calmd", "--socket", str(SOCKET_PATH)],
        env={**os.environ, "CALMD_SKIP_WARMUP": "0"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Wait until model is loaded (we can check socket exists)
        deadline = time.time() + 20
        while not SOCKET_PATH.exists() and time.time() < deadline:
            time.sleep(0.1)

        # Wait for model load + 3s grace period + some buffer
        # We DON'T poll health here to avoid triggering the skip
        time.sleep(15)

        health = check_health()
        assert health is not None
        # NOW we check. It should have started warming up by now.
        assert health.get("status") in ("warming_up", "ready")
        if health.get("status") == "ready":
            # If it's already ready, it must have finished warmup
            assert health.get("warmup_status") == "done"
        else:
            assert health.get("status") == "warming_up"
            assert health.get("warmup_status") == "in_progress"

    finally:
        proc.terminate()
        proc.wait()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()


def test_on_demand_warmup_skip_via_query():
    """
    Test that a real request triggers an on-demand warmup skip if the daemon is currently in the 'warming_up' state.
    """
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    # Start WITHOUT skip_warmup
    proc = subprocess.Popen(
        [sys.executable, "-m", "calmd", "--socket", str(SOCKET_PATH)],
        env={**os.environ, "CALMD_SKIP_WARMUP": "0"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Wait for model to load and enter warming_up
        # We poll rarely to avoid triggering skip too early during load
        deadline = time.time() + 30
        warming_up_reached = False
        while time.time() < deadline:
            time.sleep(5)  # Wait long enough for grace period to expire
            health = check_health()
            if health and health.get("status") == "warming_up":
                warming_up_reached = True
                break
            if (
                health
                and health.get("status") == "ready"
                and health.get("warmup_status") == "done"
            ):
                pytest.skip("Test was too slow: daemon already finished warmup")

        if not warming_up_reached:
            pytest.skip("Timed out waiting for daemon to enter warming_up state")

        # Now send a real query which should trigger on-demand skip (marking status as skipped)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30.0)
            client.connect(str(SOCKET_PATH))
            payload = {"mode": "smart", "query": "say hi"}
            client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            raw = client.recv(4096).decode("utf-8").strip()
            response = json.loads(raw)

        assert response.get("type") in ("analysis", "command")

        health = check_health()
        assert health is not None
        assert health.get("status") == "ready"
        # Since the query came in, even if warmup was 'in_progress' or 'done',
        # our logic in _wait_until_ready sets it to skipped if it wasn't already ready.
        # Actually, if it was 'done', it stays 'done'.
        # But if it was 'warming_up' (ready=False), it becomes 'skipped'.
        assert health.get("warmup_status") == "skipped"

    finally:
        proc.terminate()
        proc.wait()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
