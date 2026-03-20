import os
import subprocess

import pytest


def run_calm(query, args=None):
    cmd = ["uv", "run", "calm"]
    if args:
        cmd.extend(args)
    cmd.append(query)

    env = os.environ.copy()
    env["CALMD_PREFILL_COMPLETION"] = "1"

    process = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate()
    return stdout.strip(), stderr.strip(), process.returncode

@pytest.fixture(scope="session", autouse=True)
def setup_daemon():
    # Ensure any existing daemon is stopped so tests start clean
    subprocess.run(["pkill", "-f", "calmd"], capture_output=True)
    yield
    subprocess.run(["pkill", "-f", "calmd"], capture_output=True)

@pytest.mark.parametrize("query,expected_in_out", [
    ("what is 2+2", "4"),
    ("list files", "ls"),
])
def test_prefill_conformance(query, expected_in_out):
    stdout, stderr, code = run_calm(query)
    # This evaluation is meant to be run on supported platforms.
    # On other platforms, it will fail with the "not supported" message,
    # which we can check for to avoid accidental failures.
    if "currently supports only macOS on Apple Silicon" in stderr:
        pytest.skip("Skipping test on unsupported platform")

    assert code == 0
    assert expected_in_out.lower() in stdout.lower()

if __name__ == "__main__":
    pytest.main([__file__])
