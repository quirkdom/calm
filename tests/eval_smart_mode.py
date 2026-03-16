import shlex
import subprocess

import pytest


@pytest.fixture
def verbose_runs(request):
    # Enable if the custom flag is set OR if pytest verbosity is at least 2 (-vv)
    return request.config.getoption("verbose") >= 2


def run_calm(query, stdin=None, args=None):
    cmd = ["uv", "run", "calm"]
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
    return stdout.strip(), stderr.strip(), process.returncode, shlex.join(cmd)


@pytest.fixture(scope="session", autouse=True)
def setup_daemon():
    # Ensure any existing daemon is stopped so tests start clean
    subprocess.run(["pkill", "-f", "calmd"], capture_output=True)
    yield
    subprocess.run(["pkill", "-f", "calmd"], capture_output=True)


def verify_smart_mode(test_case, verbose_runs=False):
    """Common logic for running calm and asserting results."""
    stdout, stderr, code, cmd_str = run_calm(
        test_case["query"], stdin=test_case.get("stdin"), args=test_case.get("args")
    )

    if verbose_runs:
        print(f"COMMAND: {cmd_str}\nSTDOUT: {stdout}\nSTDERR: {stderr}\nCODE: {code}")

    assert test_case["expects"](stdout, stderr, code), (
        f"COMMAND: {cmd_str}\nSTDOUT: {stdout}\nSTDERR: {stderr}\nCODE: {code}"
    )


def case_ids(test_case):
    return test_case["name"]


class TestAnalysisPriority:
    """CASE 1: Prioritize ANALYSIS when STDIN is present"""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "Line counting with stdin",
                "query": "how many lines are here?",
                "stdin": "line 1\nline 2\nline 3",
                "expects": lambda out, err, code: code == 0 and "3" in out,
            },
            {
                "name": "Extracting JSON with stdin",
                "query": "what is the value of 'version'?",
                "stdin": '{"name": "test", "version": "1.2.3"}',
                "expects": lambda out, err, code: code == 0 and "1.2.3" in out,
            },
            {
                "name": "Finding error in logs with stdin",
                "query": "extract the error message",
                "stdin": "INFO: success\nERROR: database connection failed\nDEBUG: retrying",
                "expects": lambda out, err, code: (
                    code == 0 and "database connection failed" in out
                ),
            },
        ],
        ids=case_ids,
    )
    def test_analysis(self, test_case, verbose_runs):
        verify_smart_mode(test_case, verbose_runs)


class TestCommandPreference:
    """CASE 2: COMMAND preference when NO STDIN is present"""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "Disk usage command",
                "query": "show me the size of all folders here",
                "expects": lambda out, err, code: code == 0 and "du" in out,
            },
            {
                "name": "Process finding command",
                "query": "find the process using port 8080",
                "expects": lambda out, err, code: code == 0 and "lsof" in out,
            },
        ],
        ids=case_ids,
    )
    def test_commands(self, test_case, verbose_runs):
        verify_smart_mode(test_case, verbose_runs)


class TestGuardrails:
    """CASE 3: Guardrails (-c and -a)"""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "Analysis allowed with -a hint",
                "query": "list files",
                "args": ["-a"],
                "expects": lambda out, err, code: code == 0 and len(out) > 0,
            },
            {
                "name": "Strict guardrail: Analysis rejected by -c",
                "query": "what is 2+2",
                "args": ["-c"],
                "expects": lambda out, err, code: (
                    code != 0 and "no command generated" in err.lower()
                ),
            },
            {
                "name": "Strict guardrail: Command rejected by -a",
                "query": "install git",
                "args": ["-a"],
                "expects": lambda out, err, code: (
                    (code == 0 and "git" in out.lower())
                    or (code != 0 and "no analysis generated" in err.lower())
                ),
            },
        ],
        ids=case_ids,
    )
    def test_flags(self, test_case, verbose_runs):
        verify_smart_mode(test_case, verbose_runs)


class TestPipedOutput:
    """CASE 4: Piped output (conciseness)"""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "Clean output for piping",
                "query": "suggest a random filename with .txt extension",
                "expects": lambda out, err, code: (
                    code == 0 and ".txt" in out and "\n" not in out.strip()
                ),
            },
        ],
        ids=case_ids,
    )
    def test_piping(self, test_case, verbose_runs):
        verify_smart_mode(test_case, verbose_runs)


class TestMultilineOutput:
    """CASE 5: Multiline output"""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "Multiline analysis answer",
                "query": "how to install git?",
                "args": ["-a"],
                "expects": lambda out, err, code: (
                    code == 0
                    and (
                        "brew install git" in out
                        or ("install git" in out and "homebrew" in out)
                        or ("installer" in out and "git-scm.com" in out)
                    )
                ),
            },
        ],
        ids=case_ids,
    )
    def test_multiline(self, test_case, verbose_runs):
        verify_smart_mode(test_case, verbose_runs)
