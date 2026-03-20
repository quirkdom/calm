import pytest

from tests.conftest import run_calm


@pytest.mark.parametrize(
    "query,expected_in_out",
    [
        ("what is 2+2", "4"),
        ("list files", "ls"),
    ],
)
def test_prefill_conformance(query, expected_in_out, verbose_runs):
    stdout, stderr, code, cmd_str = run_calm(
        query, env={"CALMD_DISABLE_PREFILL_COMPLETION": "0"}
    )
    # This evaluation is meant to be run on supported platforms.
    # On other platforms, it will fail with the "not supported" message,
    # which we can check for to avoid accidental failures.
    if "currently supports only macOS on Apple Silicon" in stderr:
        pytest.skip("Skipping test on unsupported platform")

    if verbose_runs:
        print(f"COMMAND: {cmd_str}\nSTDOUT: {stdout}\nSTDERR: {stderr}\nCODE: {code}")

    assert code == 0
    assert expected_in_out.lower() in stdout.lower()


if __name__ == "__main__":
    pytest.main([__file__])
