from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

DEFAULT_SOCKET_PATH = "~/.cache/calmd/socket"
DEFAULT_WAIT_TIMEOUT_SECS = 300
DEFAULT_SHUTDOWN_TIMEOUT_SECS = 2
DEFAULT_MODEL_PATH = "mlx-community/Qwen3.5-9B-OptiQ-4bit"
FAST_MODEL_PATH = "mlx-community/Qwen3.5-4B-OptiQ-4bit"
DEFAULT_VERBOSE = False
DEFAULT_SKIP_WARMUP = False
DEFAULT_IDLE_OFFLOAD_SECS = 450  # 7 mins 30 secs
DEFAULT_DISABLE_PREFIX_CACHE = False
DEFAULT_MAX_KV_SIZE = 4096
DEFAULT_PREFILL_COMPLETION = True

CONFIG_PATH = Path("~/.config/calm/config.toml").expanduser()


@dataclass(frozen=True, slots=True)
class CalmCLIConfig:
    socket_path: Path
    wait_timeout_secs: float
    shutdown_timeout_secs: float


@dataclass(frozen=True, slots=True)
class CalmdConfig:
    socket_path: Path
    model_path: str
    use_fast_model: bool
    verbose: bool
    skip_warmup: bool
    idle_offload_secs: int
    disable_prefix_cache: bool
    max_kv_size: int
    prefill_completion: bool


def ensure_default_config_file() -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_render_default_config(), encoding="utf-8")
    return CONFIG_PATH


def load_calm_cli_config() -> CalmCLIConfig:
    data = _load_config_file()
    return CalmCLIConfig(
        socket_path=Path(
            _resolve_config_value(
                env_var="CALMD_SOCKET",
                raw_value=_lookup(data, "common", "socket_path"),
                default=DEFAULT_SOCKET_PATH,
                parser=_parse_str,
            )
        ).expanduser(),
        wait_timeout_secs=_resolve_config_value(
            env_var="CALMD_WAIT_TIMEOUT_SECS",
            raw_value=_lookup(data, "cli", "wait_timeout_secs"),
            default=DEFAULT_WAIT_TIMEOUT_SECS,
            parser=_parse_float,
        ),
        shutdown_timeout_secs=_resolve_config_value(
            env_var="CALMD_SHUTDOWN_TIMEOUT",
            raw_value=_lookup(data, "cli", "shutdown_timeout_secs"),
            default=DEFAULT_SHUTDOWN_TIMEOUT_SECS,
            parser=_parse_float,
        ),
    )


def load_calmd_config() -> CalmdConfig:
    data = _load_config_file()
    return CalmdConfig(
        socket_path=Path(
            _resolve_config_value(
                env_var="CALMD_SOCKET",
                raw_value=_lookup(data, "common", "socket_path"),
                default=DEFAULT_SOCKET_PATH,
                parser=_parse_str,
            )
        ).expanduser(),
        model_path=_resolve_config_value(
            env_var="CALMD_MODEL_PATH",
            raw_value=_lookup(data, "daemon", "model_path"),
            default=DEFAULT_MODEL_PATH,
            parser=_parse_str,
        ),
        use_fast_model=_resolve_config_value(
            env_var="CALMD_FAST_MODEL",
            raw_value=_lookup(data, "daemon", "use_fast_model"),
            default=False,
            parser=_parse_bool,
        ),
        verbose=_resolve_config_value(
            env_var="CALMD_VERBOSE",
            raw_value=_lookup(data, "daemon", "verbose"),
            default=DEFAULT_VERBOSE,
            parser=_parse_bool,
        ),
        skip_warmup=_resolve_config_value(
            env_var="CALMD_SKIP_WARMUP",
            raw_value=_lookup(data, "daemon", "skip_warmup"),
            default=DEFAULT_SKIP_WARMUP,
            parser=_parse_bool,
        ),
        idle_offload_secs=_resolve_config_value(
            env_var="CALMD_IDLE_OFFLOAD_SECS",
            raw_value=_lookup(data, "daemon", "idle_offload_secs"),
            default=DEFAULT_IDLE_OFFLOAD_SECS,
            parser=_parse_int,
        ),
        disable_prefix_cache=_resolve_config_value(
            env_var="CALMD_DISABLE_PREFIX_CACHE",
            raw_value=_lookup(data, "backend", "disable_prefix_cache"),
            default=DEFAULT_DISABLE_PREFIX_CACHE,
            parser=_parse_bool,
        ),
        max_kv_size=_resolve_config_value(
            env_var="CALMD_MAX_KV_SIZE",
            raw_value=_lookup(data, "backend", "max_kv_size"),
            default=DEFAULT_MAX_KV_SIZE,
            parser=_parse_int,
        ),
        prefill_completion=_resolve_config_value(
            env_var="CALMD_PREFILL_COMPLETION",
            raw_value=_lookup(data, "backend", "prefill_completion"),
            default=DEFAULT_PREFILL_COMPLETION,
            parser=_parse_bool,
        ),
    )


def _load_config_file() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("rb") as handle:
        data = tomllib.load(handle)
    return data if isinstance(data, dict) else {}


def _resolve_config_value(
    *,
    env_var: str,
    raw_value: Any,
    default: Any,
    parser: Callable[[Any], Any],
) -> Any:
    if env_var in os.environ:
        return parser(os.environ[env_var])
    if raw_value is not None:
        return parser(raw_value)
    return default


def _lookup(data: dict[str, Any], section: str, key: str) -> Any:
    raw_section = data.get(section)
    if not isinstance(raw_section, dict):
        return None
    return raw_section.get(key)


def _parse_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"expected string, got {type(value).__name__}")


def _parse_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(f"expected integer, got {type(value).__name__}")


def _parse_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("expected float, got bool")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise ValueError(f"expected float, got {type(value).__name__}")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"expected boolean, got {value!r}")


def _render_default_config() -> str:
    return f"""# calm configuration
# Precedence per key: CLI flag > environment variable > config file > code default.

[common]
socket_path = "{DEFAULT_SOCKET_PATH}"

[cli]
wait_timeout_secs = {int(DEFAULT_WAIT_TIMEOUT_SECS)}
shutdown_timeout_secs = {int(DEFAULT_SHUTDOWN_TIMEOUT_SECS)}

[daemon]
model_path = "{DEFAULT_MODEL_PATH}"
use_fast_model = false
verbose = false
skip_warmup = false
idle_offload_secs = {DEFAULT_IDLE_OFFLOAD_SECS}

[backend]
disable_prefix_cache = false
max_kv_size = {DEFAULT_MAX_KV_SIZE}
prefill_completion = true
"""
