from __future__ import annotations

import platform
import sys

SUPPORTED_SYSTEM = "Darwin"
SUPPORTED_MACHINES = {"arm64", "arm64e"}


def is_supported_runtime() -> bool:
    return (
        platform.system() == SUPPORTED_SYSTEM
        and platform.machine() in SUPPORTED_MACHINES
    )


def unsupported_runtime_message(tool_name: str) -> str:
    system = platform.system() or "unknown"
    machine = platform.machine() or "unknown"
    return (
        f"{tool_name} currently supports only macOS on Apple Silicon "
        f"(detected {system} {machine})"
    )


def ensure_supported_runtime(tool_name: str) -> bool:
    if is_supported_runtime():
        return True
    print(f"error: {unsupported_runtime_message(tool_name)}", file=sys.stderr)
    return False
