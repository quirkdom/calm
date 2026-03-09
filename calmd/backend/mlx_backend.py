from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, cast

import mlx.core as mx
from mlx.nn import Module
from mlx_lm.tokenizer_utils import TokenizerWrapper

from .interface import InferenceBackend


@dataclass(slots=True)
class PromptState:
    base_prompt: str
    prompt: str
    prompt_cache: Any | None = None
    rendered_suffix: str = ""


class MLXBackend(InferenceBackend):
    def __init__(self) -> None:
        self.model: Module | None = None
        self.tokenizer: TokenizerWrapper | None = None
        self._generate_fn: Callable[..., str] | None = None
        self._generate_step_fn: Callable[..., Any] | None = None
        self.last_metrics: dict[str, Any] = {}
        self._is_qwen35_model = False

    def load_model(self, model_path: str) -> None:
        from mlx_lm import generate, load  # type: ignore
        from mlx_lm.generate import generate_step  # type: ignore

        # With default load params we expect a 2-tuple: (model, tokenizer).
        self.model, self.tokenizer = cast(
            tuple[Module, TokenizerWrapper], load(model_path)
        )
        self._generate_fn = generate
        self._generate_step_fn = generate_step
        self._is_qwen35_model = _is_qwen35_model(model_path)

    def build_base_state(self, system_prompt: str) -> PromptState:
        if (
            self.model is None
            or self.tokenizer is None
            or self._generate_step_fn is None
        ):
            raise RuntimeError("Model is not loaded")

        base_prompt = f"{system_prompt}\n\n"
        prefill_text = base_prompt
        rendered_suffix = ""
        add_special_tokens = True

        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)
        if self._is_qwen35_model and callable(apply_chat_template):
            marker = "<calm_query_suffix_marker>"
            rendered = apply_chat_template(
                [{"role": "user", "content": f"{base_prompt}{marker}"}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            if isinstance(rendered, str) and marker in rendered:
                marker_idx = rendered.index(marker)
                prefill_text = rendered[:marker_idx]
                rendered_suffix = rendered[marker_idx + len(marker) :]
                add_special_tokens = False

        prefill_tokens = self.tokenizer.encode(
            prefill_text, add_special_tokens=add_special_tokens
        )
        prompt_cache = self._prefill_prompt_cache(prefill_tokens)
        return PromptState(
            base_prompt=base_prompt,
            prompt="",
            prompt_cache=prompt_cache,
            rendered_suffix=rendered_suffix,
        )

    def clone_state(self, state: PromptState) -> PromptState:
        return copy.deepcopy(state)

    def prefill(self, state: PromptState, tokens: str) -> None:
        state.prompt += tokens

    def generate_completion(self, state: PromptState, params: dict[str, Any]) -> str:
        if self.model is None or self.tokenizer is None or self._generate_fn is None:
            raise RuntimeError("Model is not loaded")

        max_tokens = int(params.get("max_tokens", 96))
        sampler = _make_sampler_from_params(params)
        stop_sequences = _normalize_stop_sequences(params.get("stop"))
        verbose = bool(params.get("verbose", False))
        base_kwargs: dict[str, Any] = {
            "max_tokens": max_tokens,
        }
        if sampler is not None:
            base_kwargs["sampler"] = sampler

        generate_fn = self._generate_fn
        if generate_fn is None:
            raise RuntimeError("Model is not loaded")
        started = time.perf_counter()
        if state.prompt_cache is not None:
            continuation = f"{state.prompt}{state.rendered_suffix}"
            prompt = self.tokenizer.encode(continuation, add_special_tokens=False)
            output = generate_fn(
                self.model,
                self.tokenizer,
                prompt=prompt,
                prompt_cache=state.prompt_cache,
                verbose=verbose,
                **base_kwargs,
            )
        else:
            prompt = self._build_prompt(f"{state.base_prompt}{state.prompt}")
            output = generate_fn(
                self.model,
                self.tokenizer,
                prompt=prompt,
                verbose=verbose,
                **base_kwargs,
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        self.last_metrics = {
            "inference_ms": elapsed_ms,
            "model_family": "qwen3.5" if self._is_qwen35_model else "other",
            "thinking_disabled": self._is_qwen35_model,
        }
        truncated, _ = _truncate_at_stop(output, stop_sequences)
        return truncated

    def _build_prompt(self, raw_prompt: str) -> str:
        if not self._is_qwen35_model or self.tokenizer is None:
            return raw_prompt
        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)
        if not callable(apply_chat_template):
            return raw_prompt

        # For Qwen 3.5, disable thinking directly via chat templating.
        messages = [{"role": "user", "content": raw_prompt}]
        try:
            rendered = apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        except Exception:
            return raw_prompt
        return raw_prompt

    def _prefill_prompt_cache(self, prompt_tokens: list[int]) -> list[Any]:
        if self.model is None or self._generate_step_fn is None:
            raise RuntimeError("Model is not loaded")
        from mlx_lm.models.cache import make_prompt_cache  # type: ignore

        prompt_cache = make_prompt_cache(self.model)
        token_array = mx.array(prompt_tokens)
        for _ in self._generate_step_fn(
            token_array,
            self.model,
            max_tokens=0,
            prompt_cache=prompt_cache,
        ):
            pass
        return prompt_cache


def _normalize_stop_sequences(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            out.append(item)
    return out


def _truncate_at_stop(text: str, stop_sequences: list[str]) -> tuple[str, bool]:
    if not text or not stop_sequences:
        return text, False
    stop_positions = [text.find(stop) for stop in stop_sequences if stop in text]
    if not stop_positions:
        return text, False
    return text[: min(stop_positions)], True


def _make_sampler_from_params(params: dict[str, Any]) -> Any:
    from mlx_lm.sample_utils import make_sampler  # type: ignore

    temp = float(params.get("temperature", 0.3))
    top_p = float(params.get("top_p", 1.0))
    top_k = int(params.get("top_k", 0))
    min_p = float(params.get("min_p", 0.0))
    return make_sampler(
        temp=temp,
        top_p=top_p,
        top_k=top_k,
        min_p=min_p,
    )


def _is_qwen35_model(model_path: str) -> bool:
    normalized = model_path.lower().replace("-", "").replace("_", "")
    return "qwen3.5" in model_path.lower() or "qwen35" in normalized


class RuleBasedFallbackBackend(InferenceBackend):
    """Used only when mlx_lm is unavailable in the runtime environment."""

    def load_model(self, model_path: str) -> None:
        _ = model_path

    def build_base_state(self, system_prompt: str) -> PromptState:
        return PromptState(base_prompt=f"{system_prompt}\n\n", prompt="")

    def clone_state(self, state: PromptState) -> PromptState:
        return PromptState(
            base_prompt=state.base_prompt,
            prompt=state.prompt,
            prompt_cache=None,
            rendered_suffix=state.rendered_suffix,
        )

    def prefill(self, state: PromptState, tokens: str) -> None:
        state.prompt += tokens

    def generate_completion(self, state: PromptState, params: dict[str, Any]) -> str:
        _ = params
        prompt = f"{state.base_prompt}{state.prompt}"
        query_match = re.search(
            r"User request:\n(.+?)\n\nAnswer:$", prompt, flags=re.DOTALL
        )
        if query_match:
            query = query_match.group(1).strip().lower()
            cmd = self._guess_command(query)
            return json.dumps({"command": cmd, "analysis": None, "runnable": bool(cmd)})

        analysis_q = re.search(r"Question:\n(.+?)\n\nAnswer:$", prompt, flags=re.DOTALL)
        if analysis_q:
            q = analysis_q.group(1).strip()
            return json.dumps(
                {"command": None, "analysis": f"Based on input: {q}", "runnable": False}
            )

        return json.dumps({"command": None, "analysis": "No result", "runnable": False})

    def _guess_command(self, query: str) -> str | None:
        if "port" in query:
            port = re.search(r"(\d{2,5})", query)
            if port:
                return f"lsof -i :{port.group(1)}"
        if "larger" in query or "large file" in query:
            return "find . -type f -size +1G"
        if "tar.gz" in query or "extract" in query:
            return "tar -xzf archive.tar.gz"
        if "memory" in query:
            return "ps aux | sort -nrk 4 | head -n 5"
        return None
