import os
import shlex
import subprocess

import pytest


@pytest.fixture(scope="module")
def verbose_runs(request):
    # Enable if the custom flag is set OR if pytest verbosity is at least 2 (-vv)
    return request.config.get_verbosity() >= 2


@pytest.fixture(scope="session", autouse=True)
def setup_daemon(request):
    # Check if we're running any eval tests
    is_eval_test = False
    try:
        # Access the test items that will be run
        if hasattr(request, "session") and hasattr(request.session, "items"):
            for item in request.session.items:
                # Check if the test is from an eval file
                if "eval_" in str(item.fspath):
                    is_eval_test = True
                    break
    except Exception:
        # If we can't determine, default to running setup (safe behavior)
        is_eval_test = True

    # Only run daemon setup if we're running eval tests
    if is_eval_test:
        # Ensure any existing daemon is stopped so tests start clean
        subprocess.run(["pkill", "-f", "calmd"], capture_output=True)
        yield
        subprocess.run(["pkill", "-f", "calmd"], capture_output=True)
    else:
        # Not running eval tests - just yield without doing anything
        yield


def run_calm(query, args=None, stdin=None, env=None):
    """Run calm command and return (stdout, stderr, returncode, command_string)."""
    cmd = ["uv", "run", "calm"]
    if args:
        cmd.extend(args)
    cmd.append(query)

    # Prepare environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=run_env,
    )
    stdout, stderr = process.communicate(input=stdin)
    return stdout.strip(), stderr.strip(), process.returncode, shlex.join(cmd)
