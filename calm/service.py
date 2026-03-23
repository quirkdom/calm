from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from calm.config import load_calm_cli_config

CUSTOM_LAUNCHD_LABEL = "com.quirkdom.calmd"
HOMEBREW_FORMULA_NAME = "calm"
HOMEBREW_LAUNCHD_LABEL = "homebrew.mxcl.calm"
CUSTOM_PLIST_PATH = Path("~/Library/LaunchAgents/com.quirkdom.calmd.plist").expanduser()
HOMEBREW_PLIST_CANDIDATES = (
    Path(f"/opt/homebrew/opt/{HOMEBREW_FORMULA_NAME}/{HOMEBREW_LAUNCHD_LABEL}.plist"),
    Path(f"/usr/local/opt/{HOMEBREW_FORMULA_NAME}/{HOMEBREW_LAUNCHD_LABEL}.plist"),
)
LOG_DIR = Path("~/Library/Logs/calmd").expanduser()
DEBUG_ENV_VAR = "CALM_DEBUG_DAEMON"
SKIP_WARMUP_ENV_VAR = "CALMD_SKIP_WARMUP"


@dataclass(frozen=True, slots=True)
class ManagedService:
    label: str
    plist_path: Path
    source: str
    name: str | None = None


def find_custom_service() -> ManagedService | None:
    if CUSTOM_PLIST_PATH.exists() or _launchctl_service_exists(CUSTOM_LAUNCHD_LABEL):
        return ManagedService(
            label=CUSTOM_LAUNCHD_LABEL,
            plist_path=CUSTOM_PLIST_PATH,
            source="launchd",
        )
    return None


def find_homebrew_service() -> ManagedService | None:
    service = _find_homebrew_service_via_plist()
    if service is not None:
        return service
    return _find_homebrew_service_via_launchctl()


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

    if service.source == "homebrew":
        return _start_homebrew_service(service, register=not skip_warmup)

    service_exists = _launchctl_service_exists(service.label)
    debug_log(f"launchctl service exists={service_exists} label={service.label}")
    if not service_exists:
        debug_log(
            f"starting launchd service via bootstrap label={service.label} plist={service.plist_path}"
        )
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

    debug_log(f"starting launchd service via kickstart label={service.label}")
    kickstart = _run_launchctl(
        ["kickstart", "-kp", f"{_launchd_domain()}/{service.label}"],
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


def _find_homebrew_service_via_plist() -> ManagedService | None:
    for plist_path in HOMEBREW_PLIST_CANDIDATES:
        if not plist_path.exists():
            continue
        return ManagedService(
            label=_label_from_plist(plist_path) or HOMEBREW_LAUNCHD_LABEL,
            plist_path=plist_path,
            source="homebrew",
            name=HOMEBREW_FORMULA_NAME,
        )
    return None


def _find_homebrew_service_via_launchctl() -> ManagedService | None:
    plist_path = _default_homebrew_plist_path()
    if plist_path.exists() or _launchctl_service_exists(HOMEBREW_LAUNCHD_LABEL):
        return ManagedService(
            label=HOMEBREW_LAUNCHD_LABEL,
            plist_path=plist_path,
            source="homebrew",
            name=HOMEBREW_FORMULA_NAME,
        )
    return None


def _default_homebrew_plist_path() -> Path:
    return HOMEBREW_PLIST_CANDIDATES[0]


def _label_from_plist(plist_path: Path) -> str | None:
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    label = plist.get("Label")
    return label if isinstance(label, str) and label else None


def _start_homebrew_service(
    service: ManagedService, register: bool
) -> tuple[int, str]:
    brew_name = service.name or HOMEBREW_FORMULA_NAME
    subcommand = "start" if register else "run"
    debug_log(
        f"starting homebrew service via `brew services {subcommand}` formula={brew_name}"
    )
    result = _run_brew(["services", subcommand, brew_name], check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        return 1, stderr or f"failed to {subcommand} Homebrew service {brew_name}"
    mode = "login service" if register else "on-demand run"
    return 0, f"started calmd via {service.source} ({mode})"


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


@cache
def _fallback_brew_executable() -> str | None:
    for candidate in (
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def _run_brew(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    started_at = time.monotonic()
    debug_log(f"brew start: {' '.join(args)}")
    command = ["brew", *args]
    try:
        result = subprocess.run(
            command,
            check=check,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        brew = _fallback_brew_executable()
        if brew is None:
            return subprocess.CompletedProcess(
                args=command,
                returncode=127,
                stdout="",
                stderr="brew not found",
            )
        result = subprocess.run(
            [brew, *args],
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
        f"brew done: {' '.join(args)} rc={result.returncode} elapsed_ms={elapsed_ms}{suffix}"
    )
    return result
