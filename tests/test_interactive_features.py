from unittest.mock import MagicMock, patch

import calm.cli


@patch("subprocess.Popen")
def test_copy_to_clipboard(mock_popen):
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"", b"")
    mock_popen.return_value = mock_process

    command_text = "test command"
    result = calm.cli.copy_to_clipboard(command_text)
    assert result is True

    mock_popen.assert_called_once()
    args, _ = mock_popen.call_args
    assert args[0] == ["pbcopy"]

    mock_process.communicate.assert_called_once_with(input=command_text.encode("utf-8"))


@patch("subprocess.run")
def test_edit_command_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0)

    # We need to mock Path.read_text to return the "edited" command
    with patch("calm.cli.Path.read_text") as mock_read:
        mock_read.return_value = "edited command"
        result = calm.cli.edit_command("original command")
        assert result == "edited command"


@patch("subprocess.run")
def test_edit_command_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    result = calm.cli.edit_command("original command")
    assert result is None
