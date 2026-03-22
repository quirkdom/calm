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
                '- cmd: uv run calm "what changed"',
                "  when: 2",
                "- cmd: git status",
                "  when: 3",
                "- cmd: pytest -q",
                "  when: 4",
                "- cmd: ls | calm 'summarize'",
                "  when: 5",
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
        "Last Command:\nls -la\n\nLast 3 Commands:\n1. ls -la\n2. git status\n3. pwd"
    )


def test_parse_bash_history_ignores_timestamp_lines() -> None:
    assert cli._parse_bash_history("#1712345678") is None
    assert cli._parse_bash_history("git status") == "git status"


def test_looks_like_calm_invocation_comprehensive():
    # Basic
    assert cli._looks_like_calm_invocation("calm 'test'") is True
    assert cli._looks_like_calm_invocation("calmd --status") is True

    # Piped
    assert cli._looks_like_calm_invocation("ls | calm 'summarize'") is True
    assert cli._looks_like_calm_invocation("calm 'search' | grep 'foo'") is True

    # Full path
    assert cli._looks_like_calm_invocation("/usr/local/bin/calm 'hello'") is True

    # Malformed
    assert cli._looks_like_calm_invocation("calm 'unbalanced quote") is True

    # Env vars and sudo
    assert cli._looks_like_calm_invocation("DEBUG=1 calm 'test'") is True
    assert cli._looks_like_calm_invocation("sudo calm 'test'") is True
    assert cli._looks_like_calm_invocation("FOO=bar sudo DEBUG=1 /usr/bin/calmd") is True

    # Wrappers
    assert cli._looks_like_calm_invocation("python3 -m calm 'test'") is True
    assert cli._looks_like_calm_invocation("uv run calm 'test'") is True
    assert cli._looks_like_calm_invocation("uv run /path/to/calmd") is True
    assert cli._looks_like_calm_invocation("uv tool run calm -h") is True
    assert cli._looks_like_calm_invocation("uvx --from calm-cli calm -h") is True
    assert cli._looks_like_calm_invocation("pipx run --spec calm-cli calm -h") is True

    # Not calm
    assert cli._looks_like_calm_invocation("git commit -m 'fixed calm bug'") is False
    assert cli._looks_like_calm_invocation("grep 'calm' file.txt") is False
    assert cli._looks_like_calm_invocation("echo calm") is False
