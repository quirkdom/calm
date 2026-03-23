from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

from calm import service


def test_find_homebrew_service_prefers_fast_plist_path(
    monkeypatch, tmp_path: Path
) -> None:
    plist_path = tmp_path / "homebrew.mxcl.calm.plist"
    plist_path.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>Label</key><string>homebrew.mxcl.calm</string></dict></plist>'
    )

    monkeypatch.setattr(service, "HOMEBREW_PLIST_CANDIDATES", (plist_path,))
    monkeypatch.setattr(
        service,
        "_run_brew",
        lambda args, check=False: (_ for _ in ()).throw(
            AssertionError("brew should not be called")
        ),
    )

    managed = service.find_homebrew_service()

    assert managed is not None
    assert managed.plist_path == plist_path
    assert managed.label == "homebrew.mxcl.calm"


def test_find_homebrew_service_skips_brew_probe_without_plist(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "HOMEBREW_PLIST_CANDIDATES",
        (Path("/definitely/missing/homebrew.mxcl.calm.plist"),),
    )
    monkeypatch.setattr(
        service,
        "_run_brew",
        lambda args, check=False: (_ for _ in ()).throw(
            AssertionError("brew should not be called")
        ),
    )
    monkeypatch.setattr(service, "_launchctl_service_exists", lambda label: False)

    managed = service.find_homebrew_service()

    assert managed is None


def test_start_service_uses_brew_run_for_auto_started_homebrew_service(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run_brew(
        args: list[str], check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args=["brew", *args],
            returncode=0,
            stdout="Service `calm` already started, use `brew services restart calm` to restart.",
            stderr="",
        )

    monkeypatch.setattr(service, "_run_brew", fake_run_brew)

    managed = service.ManagedService(
        label="homebrew.mxcl.calm",
        plist_path=Path("/opt/homebrew/opt/calm/homebrew.mxcl.calm.plist"),
        source="homebrew",
        name="calm",
    )

    status, message = service.start_service(skip_warmup=True, service=managed)

    assert status == 0
    assert message == "started calmd via homebrew (on-demand run)"
    assert calls == [["services", "run", "calm"]]


def test_start_service_uses_brew_start_for_registered_homebrew_service(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run_brew(
        args: list[str], check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(
            args=["brew", *args],
            returncode=0,
            stdout="Successfully started `calm` (label: homebrew.mxcl.calm)",
            stderr="",
        )

    monkeypatch.setattr(service, "_run_brew", fake_run_brew)

    managed = service.ManagedService(
        label="homebrew.mxcl.calm",
        plist_path=Path("/opt/homebrew/opt/calm/homebrew.mxcl.calm.plist"),
        source="homebrew",
        name="calm",
    )

    status, message = service.start_service(skip_warmup=False, service=managed)

    assert status == 0
    assert message == "started calmd via homebrew (login service)"
    assert calls == [["services", "start", "calm"]]


def test_install_service_refuses_when_homebrew_service_registered(monkeypatch) -> None:
    managed = service.ManagedService(
        label="homebrew.mxcl.calm",
        plist_path=Path("/opt/homebrew/opt/calm/homebrew.mxcl.calm.plist"),
        source="homebrew",
        name="calm",
    )
    monkeypatch.setattr(service, "find_homebrew_service", lambda: managed)

    status, message = service.install_service()

    assert status == 1
    assert message == "homebrew service detected; use `brew services` instead"


def test_run_brew_uses_brew_from_path_first(monkeypatch) -> None:
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=["brew", "services", "run", "calm"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
    )
    monkeypatch.setattr(service.subprocess, "run", run)

    result = service._run_brew(["services", "run", "calm"])

    assert result.returncode == 0
    assert run.call_count == 1
    assert run.call_args.args[0] == ["brew", "services", "run", "calm"]


def test_run_brew_falls_back_to_cached_known_path(monkeypatch) -> None:
    service._fallback_brew_executable.cache_clear()
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str], check: bool, text: bool, capture_output: bool
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[0] == "brew":
            raise FileNotFoundError("brew")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    monkeypatch.setattr(
        service.Path, "exists", lambda self: str(self) == "/opt/homebrew/bin/brew"
    )

    result_one = service._run_brew(["services", "run", "calm"])
    result_two = service._run_brew(["services", "start", "calm"])

    assert result_one.returncode == 0
    assert result_two.returncode == 0
    assert calls == [
        ["brew", "services", "run", "calm"],
        ["/opt/homebrew/bin/brew", "services", "run", "calm"],
        ["brew", "services", "start", "calm"],
        ["/opt/homebrew/bin/brew", "services", "start", "calm"],
    ]
