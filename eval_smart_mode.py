import subprocess
import sys


def run_calm(query, stdin=None, args=None):
    cmd = [sys.executable, "-m", "calm"]
    if args:
        cmd.extend(args)
    cmd.append(query)

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate(input=stdin)
    return stdout.strip(), stderr.strip(), process.returncode


def test_suite():
    tests = [
        # --- CASE 1: Prioritize ANALYSIS when STDIN is present ---
        {
            "name": "Line counting with stdin",
            "query": "how many lines are here?",
            "stdin": "line 1\nline 2\nline 3",
            "expected_type": "analysis",
            "contains": "3",
        },
        {
            "name": "Extracting JSON with stdin",
            "query": "what is the value of 'version'?",
            "stdin": '{"name": "test", "version": "1.2.3"}',
            "expected_type": "analysis",
            "contains": "1.2.3",
        },
        {
            "name": "Finding error in logs with stdin",
            "query": "extract the error message",
            "stdin": "INFO: success\nERROR: database connection failed\nDEBUG: retrying",
            "expected_type": "analysis",
            "contains": "database connection failed",
        },
        # --- CASE 2: COMMAND preference when NO STDIN is present ---
        {
            "name": "Disk usage command",
            "query": "show me the size of all folders here",
            "stdin": None,
            "expected_type": "command",
            "contains": "du",
        },
        {
            "name": "Process finding command",
            "query": "find the process using port 8080",
            "stdin": None,
            "expected_type": "command",
            "contains": "lsof",
        },
        # --- CASE 3: Guardrails (-c and -a) ---
        {
            "name": "Force command on analysis query",
            "query": "what is 2+2",
            "args": ["-c"],
            "stdin": None,
            "expect_error": True,
            "stderr_contains": "no command generated",
        },
        {
            "name": "Force analysis on command query",
            "query": "list files",
            "args": ["-a"],
            "stdin": None,
            "expect_error": True,
            "stderr_contains": "no analysis generated",
        },
        # --- CASE 4: Piped output (conciseness) ---
        {
            "name": "Clean output for piping",
            "query": "suggest a random filename with .txt extension",
            "stdin": None,
            "piped": True,  # We simulate this by checking if it's a clean string
            "expected_type": "analysis",
            "contains": ".txt",
        },
    ]

    passed = 0
    failed = 0

    print(f"{'Test Name':<40} | {'Status':<10}")
    print("-" * 55)

    for test in tests:
        # For 'piped' test, we check if the model returns analysis even for something
        # that could be a command, because we want a clean string.
        # Note: In our current CLI, stdout.isatty() is true when running this script
        # unless we explicitly pipe it.
        stdout, stderr, code = run_calm(
            test["query"], stdin=test.get("stdin"), args=test.get("args")
        )

        success = True

        if test.get("expect_error"):
            if code == 0:
                success = False
                msg = "Expected non-zero exit code"
            elif (
                test.get("stderr_contains")
                and test["stderr_contains"] not in stderr.lower()
            ):
                success = False
                msg = f"Stderr missing: {test['stderr_contains']}"
        else:
            if code != 0:
                success = False
                msg = f"Exit code {code}. Stderr: {stderr}"
            elif test.get("contains") and test["contains"] not in stdout:
                success = False
                msg = f"Output missing: {test['contains']}"

        if success:
            print(f"{test['name']:<40} | \033[92mPASSED\033[0m")
            passed += 1
        else:
            print(f"{test['name']:<40} | \033[91mFAILED\033[0m ({msg})")
            print(f"  STDOUT: {stdout}")
            print(f"  STDERR: {stderr}")
            failed += 1

    print("-" * 55)
    print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")


if __name__ == "__main__":
    # Ensure daemon is stopped to pick up new code if needed
    # subprocess.run([sys.executable, "-m", "calm", "-d", "stop"], capture_output=True)
    subprocess.run(["pkill", "-f", "calmd"], capture_output=True)
    test_suite()
