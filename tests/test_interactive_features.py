import unittest
from unittest.mock import MagicMock, patch

import calm.cli


class TestInteractiveFeatures(unittest.TestCase):
    @patch("subprocess.Popen")
    def test_copy_to_clipboard(self, mock_popen):
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"", b"")
        mock_popen.return_value = mock_process

        result = calm.cli.copy_to_clipboard("test command")
        self.assertTrue(result)
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["pbcopy"])

    @patch("subprocess.run")
    def test_edit_command_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        # We need to mock Path.read_text to return the "edited" command
        with patch("calm.cli.Path.read_text") as mock_read:
            mock_read.return_value = "edited command"
            result = calm.cli.edit_command("original command")
            self.assertEqual(result, "edited command")

    @patch("subprocess.run")
    def test_edit_command_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = calm.cli.edit_command("original command")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
