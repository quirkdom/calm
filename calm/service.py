from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from calm.config import load_calm_cli_config

CUSTOM_LAUNCHD_LABEL = "com.quirkdom.calmd"
HOMEBREW_LAUNCHD_LABEL = "homebrew.mxcl.calmd"
CUSTOM_PLIST_PATH = Path("~/Library/LaunchAgents/com.quirkdom.calmd.plist").expanduser()
HOMEBREW_PLIST_PATH = Path(
    "~/Library/LaunchAgents/homebrew.mxcl.calmd.plist"
).expanduser()
LOG_DIR = Path("~/Library/Logs/calmd").expanduser()
DEBUG_ENV_VAR = "CALM_DEBUG_DAEMON"
SKIP_WARMUP_ENV_VAR = "CALMD_SKIP_WARMUP"


@dataclass(frozen=True, slots=True)
class ManagedService:
    label: str
    plist_path: Path
    source: str


def find_custom_service() -> ManagedService | None:
    if CUSTOM_PLIST_PATH.exists() or _launchctl_service_exists(CUSTOM_LAUNCHD_LABEL):
        return ManagedService(
            label=CUSTOM_LAUNCHD_LABEL,
            plist_path=CUSTOM_PLIST_PATH,
            source="launchd",
        )
    return None


def find_homebrew_service() -> ManagedService | None:
    if HOMEBREW_PLIST_PATH.exists() or _launchctl_service_exists(
        HOMEBREW_LAUNCHD_LABEL
    ):
        return ManagedService(
            label=HOMEBREW_LAUNCHD_LABEL,
            plist_path=HOMEBREW_PLIST_PATH,
            source="homebrew",
        )
    return None


def find_managed_service() -> ManagedService | None:
    return find_homebrew_service() or find_custom_service()


def install_service() -> tuple[int, str]:
    if find_homebrew_service() is not None:
        return 1, "homebrew service detected; use `brew services` instead"

    CUSTOM_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if _launchctl_service_exists(CUSTOM_LAUNCHD_LABEL):
        _bootout_service(
            ManagedService(CUSTOM_LAUNCHD_LABEL, CUSTOM_PLIST_PATH, "launchd")
        )

    config = load_calm_cli_config()
    plist = {
        "Label": CUSTOM_LAUNCHD_LABEL,
        "ProgramArguments": _resolve_calmd_program_arguments(),
        "RunAtLoad": True,
        "WorkingDirectory": str(Path.home()),
        "StandardOutPath": str(LOG_DIR / "calmd.stdout.log"),
        "StandardErrorPath": str(LOG_DIR / "calmd.stderr.log"),
        "EnvironmentVariables": {
            "CALMD_SOCKET": str(config.socket_path),
        },
    }

    with CUSTOM_PLIST_PATH.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=True)

    return 0, f"installed launchd service at {CUSTOM_PLIST_PATH}"


def uninstall_service() -> tuple[int, str]:
    service = find_custom_service()
    removed_paths: list[str] = []

    if service is not None:
        _bootout_service(service)

    if CUSTOM_PLIST_PATH.exists():
        CUSTOM_PLIST_PATH.unlink()
        removed_paths.append(str(CUSTOM_PLIST_PATH))

    if not removed_paths:
        return 0, "custom calmd LaunchAgent is not installed"
    return 0, "removed service definition(s): " + ", ".join(removed_paths)


def start_service(
    skip_warmup: bool = False,
    service: ManagedService | None = None,
) -> tuple[int, str]:
    service = service or find_custom_service()
    if service is None:
        return 1, "custom calmd LaunchAgent is not installed"

    debug_log(
        f"managed service detected: label={service.label} source={service.source}"
    )
    if skip_warmup:
        set_skip_warmup_env()
    service_exists = _launchctl_service_exists(service.label)
    debug_log(f"launchctl service exists={service_exists} label={service.label}")
    if not service_exists:
        bootstrap = _run_launchctl(
            ["bootstrap", _launchd_domain(), str(service.plist_path)],
            check=False,
        )
        if bootstrap.returncode != 0 and not _launchctl_service_exists(service.label):
            stderr = bootstrap.stderr.strip() or bootstrap.stdout.strip()
            return 1, stderr or f"failed to bootstrap {service.label}"
        debug_log(
            "bootstrap loaded service; skipping kickstart because RunAtLoad starts it"
        )
        return 0, f"started calmd via {service.source}"

    kickstart = _run_launchctl(
        ["kickstart", "-k", f"{_launchd_domain()}/{service.label}"],
        check=False,
    )
    if kickstart.returncode != 0:
        stderr = kickstart.stderr.strip() or kickstart.stdout.strip()
        return 1, stderr or f"failed to start {service.label}"

    return 0, f"started calmd via {service.source}"


def stop_service() -> tuple[int, str]:
    service = find_custom_service()
    if service is None:
        return 1, "custom calmd LaunchAgent is not installed"
    return _bootout_service(service)


def managed_service_status() -> tuple[ManagedService | None, bool]:
    service = find_custom_service()
    if service is None:
        return None, False
    return service, _launchctl_service_exists(service.label)


def _bootout_service(service: ManagedService) -> tuple[int, str]:
    commands = [
        ["bootout", _launchd_domain(), f"{_launchd_domain()}/{service.label}"],
        ["bootout", _launchd_domain(), str(service.plist_path)],
    ]
    last_error = ""
    for command in commands:
        result = _run_launchctl(command, check=False)
        if result.returncode == 0:
            return 0, f"stopped calmd via {service.source}"
        last_error = result.stderr.strip() or result.stdout.strip()
    if not _launchctl_service_exists(service.label):
        return 0, f"stopped calmd via {service.source}"
    return 1, last_error or f"failed to stop {service.label}"


def _resolve_calmd_program_arguments() -> list[str]:
    candidates = []
    which_path = shutil.which("calmd")
    if which_path:
        candidates.append([which_path])

    argv0 = Path(sys.argv[0]).expanduser().resolve()
    if argv0.name == "calm":
        candidates.append([str(argv0.with_name("calmd"))])

    candidates.append([str(Path(sys.executable).resolve().with_name("calmd"))])
    candidates.append([sys.executable, "-m", "calmd"])

    for candidate in candidates:
        if len(candidate) > 1:
            return [str(Path(candidate[0]).expanduser().resolve()), *candidate[1:]]
        executable = Path(candidate[0]).expanduser()
        if executable.exists():
            return [str(executable.resolve())]

    return [str(Path(sys.executable).expanduser().resolve()), "-m", "calmd"]


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl_service_exists(label: str) -> bool:
    result = _run_launchctl(
        ["print", f"{_launchd_domain()}/{label}"],
        check=False,
    )
    return result.returncode == 0


def debug_enabled() -> bool:
    value = os.environ.get(DEBUG_ENV_VAR, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def debug_log(message: str) -> None:
    if not debug_enabled():
        return
    print(f"[calm debug] {message}", file=sys.stderr, flush=True)


def _set_launchd_env(name: str, value: str) -> None:
    debug_log(f"launchctl setenv {name}={value}")
    _run_launchctl(["setenv", name, value], check=False)


def _unset_launchd_env(name: str) -> None:
    debug_log(f"launchctl unsetenv {name}")
    _run_launchctl(["unsetenv", name], check=False)


def set_skip_warmup_env() -> None:
    _set_launchd_env(SKIP_WARMUP_ENV_VAR, "1")


def unset_skip_warmup_env() -> None:
    _unset_launchd_env(SKIP_WARMUP_ENV_VAR)


def _run_launchctl(
    args: list[str], check: bool = False
) -> subprocess.CompletedProcess[str]:
    started_at = time.monotonic()
    debug_log(f"launchctl start: {' '.join(args)}")
    result = subprocess.run(
        ["launchctl", *args],
        check=check,
        text=True,
        capture_output=True,
    )
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    detail = stderr or stdout
    suffix = f" output={detail!r}" if detail else ""
    debug_log(
        f"launchctl done: {' '.join(args)} rc={result.returncode} elapsed_ms={elapsed_ms}{suffix}"
    )
    return result
