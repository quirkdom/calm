from pathlib import Path

from calm import cli


def test_read_recent_history_commands_prefers_current_shell_and_skips_calm(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("SHELL", "/opt/homebrew/bin/fish")

    fish_dir = tmp_path / ".local" / "share" / "fish"
    fish_dir.mkdir(parents=True)
    (fish_dir / "fish_history").write_text(
        "\n".join(
            [
                "- cmd: ls",
                "  when: 1",
                "- cmd: uv run calm \"what changed\"",
                "  when: 2",
                "- cmd: git status",
                "  when: 3",
                "- cmd: pytest -q",
                "  when: 4",
            ]
        ),
        encoding="utf-8",
    )

    commands = cli.read_recent_history_commands(limit=3)

    assert commands == ["pytest -q", "git status", "ls"]


def test_format_history_context_includes_last_and_recent_commands(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    (tmp_path / ".zsh_history").write_text(
        "\n".join(
            [
                ": 1:0;pwd",
                ": 2:0;git status",
                ": 3:0;ls -la",
            ]
        ),
        encoding="utf-8",
    )

    history = cli.format_history_context(limit=5)

    assert history == (
        "Last Command:\nls -la\n\n"
        "Last 3 Commands:\n"
        "1. ls -la\n"
        "2. git status\n"
        "3. pwd"
    )


def test_parse_bash_history_ignores_timestamp_lines() -> None:
    assert cli._parse_bash_history("#1712345678") is None
    assert cli._parse_bash_history("git status") == "git status"
