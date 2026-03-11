from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["command", "analysis", "control"]
ControlAction = Literal["offload", "shutdown"]


@dataclass(slots=True)
class Request:
    query: str | None
    mode: Mode
    stdin: str | None = None
    history: str | None = None
    shell: str | None = None
    cwd: str | None = None
    os_name: str | None = None
    action: ControlAction | None = None
    force: bool = False


@dataclass(slots=True)
class CommandResponse:
    type: Literal["command"]
    command: str
    runnable: bool


@dataclass(slots=True)
class AnalysisResponse:
    type: Literal["analysis"]
    answer: str
