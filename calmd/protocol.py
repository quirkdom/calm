from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["command", "analysis"]


@dataclass(slots=True)
class Request:
    query: str
    mode: Mode
    stdin: str | None = None
    history: str | None = None
    shell: str | None = None
    cwd: str | None = None
    os_name: str | None = None


@dataclass(slots=True)
class CommandResponse:
    type: Literal["command"]
    command: str
    runnable: bool


@dataclass(slots=True)
class AnalysisResponse:
    type: Literal["analysis"]
    answer: str
