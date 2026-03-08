from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class InferenceBackend(ABC):
    @abstractmethod
    def load_model(self, model_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_base_state(self, system_prompt: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def clone_state(self, state: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def prefill(self, state: Any, tokens: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def generate_completion(self, state: Any, params: dict[str, Any]) -> str:
        raise NotImplementedError
