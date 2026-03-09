from __future__ import annotations

import copy
import json
import os
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
    system_prompt: str
    user_prompt: str = ""
    prompt_cache: Any | None = None
    system_tokens: tuple[int, ...] = ()


class MLXBackend(InferenceBackend):
    def __init__(self) -> None:
        self.model: Module | None = None
        self.tokenizer: TokenizerWrapper | None = None
        self._generate_fn: Callable[..., str] | None = None
        self._generate_step_fn: Callable[..., Any] | None = None
        self._make_prompt_cache_fn: Callable[..., Any] | None = None
        self.last_metrics: dict[str, Any] = {}
        self._is_qwen35_model = False
        self._disable_prefix_cache = (
            os.environ.get("CALMD_DISABLE_PREFIX_CACHE", "0") == "1"
        )

    def load_model(self, model_path: str) -> None:
        from mlx_lm import generate, load  # type: ignore
        from mlx_lm.generate import generate_step  # type: ignore
        from mlx_lm.models.cache import make_prompt_cache  # type: ignore

        # With default load params we expect a 2-tuple: (model, tokenizer).
        self.model, self.tokenizer = cast(
            tuple[Module, TokenizerWrapper], load(model_path)
        )
        self._generate_fn = generate
        self._generate_step_fn = generate_step
        self._make_prompt_cache_fn = make_prompt_cache
        self._is_qwen35_model = _is_qwen35_model(model_path)

    def build_base_state(self, system_prompt: str) -> PromptState:
        if self._disable_prefix_cache:
            return PromptState(system_prompt=system_prompt)

        try:
            system_tokens = self._render_chat_tokens(
                system_prompt=system_prompt,
                user_prompt="",
                add_generation_prompt=False,
            )
            prompt_cache = self._prefill_prompt_cache(system_tokens)
        except Exception:
            # Some chat templates reject system-only inputs. Use a tiny synthetic
            # user turn to still prefill cache and warm up model load.
            try:
                system_tokens = self._render_chat_tokens(
                    system_prompt=system_prompt,
                    user_prompt="x",
                    add_generation_prompt=False,
                )
                prompt_cache = self._prefill_prompt_cache(system_tokens)
            except Exception:
                # If templating/prefill still fails, preserve startup by falling
                # back to an uncached base state.
                system_tokens = []
                prompt_cache = None
        return PromptState(
            system_prompt=system_prompt,
            user_prompt="",
            prompt_cache=prompt_cache,
            system_tokens=tuple(system_tokens),
        )

    def clone_state(self, state: PromptState) -> PromptState:
        return copy.deepcopy(state)

    def prefill(self, state: PromptState, tokens: str) -> None:
        state.user_prompt += tokens

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

        full_tokens = self._render_chat_tokens(
            system_prompt=state.system_prompt,
            user_prompt=state.user_prompt,
            add_generation_prompt=True,
        )

        started = time.perf_counter()
        prompt_cache = state.prompt_cache
        system_tokens = list(state.system_tokens)
        prefix_len = (
            0
            if self._disable_prefix_cache
            else _common_prefix_len(system_tokens, full_tokens)
        )
        if not self._disable_prefix_cache and prompt_cache is not None and prefix_len > 0:
            cache_for_request = prompt_cache
            if prefix_len < len(system_tokens):
                cache_for_request = self._trimmed_cache_copy(
                    prompt_cache, system_tokens, prefix_len
                )
            output = generate_fn(
                self.model,
                self.tokenizer,
                prompt=full_tokens[prefix_len:],
                prompt_cache=cache_for_request,
                verbose=verbose,
                **base_kwargs,
            )
        else:
            output = generate_fn(
                self.model,
                self.tokenizer,
                prompt=full_tokens,
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

    def _render_chat_tokens(
        self, system_prompt: str, user_prompt: str, add_generation_prompt: bool
    ) -> list[int]:
        if self.tokenizer is None:
            raise RuntimeError("Model is not loaded")
        apply_chat_template = getattr(self.tokenizer, "apply_chat_template", None)

        if callable(apply_chat_template):
            messages = [{"role": "system", "content": system_prompt}]
            if user_prompt:
                messages.append({"role": "user", "content": user_prompt})

            template_kwargs: dict[str, Any] = {
                "tokenize": True,
                "add_generation_prompt": add_generation_prompt,
            }
            if self._is_qwen35_model:
                template_kwargs["enable_thinking"] = False

            rendered = apply_chat_template(messages, **template_kwargs)
            if hasattr(rendered, "tolist"):
                return [int(token) for token in cast(list[int], rendered.tolist())]
            return [int(token) for token in cast(list[int], rendered)]

        raw_prompt = f"{system_prompt}\n\n{user_prompt}".strip()
        return cast(list[int], self.tokenizer.encode(raw_prompt))

    def _prefill_prompt_cache(self, prompt_tokens: list[int]) -> Any | None:
        if (
            self.model is None
            or self._generate_step_fn is None
            or self._make_prompt_cache_fn is None
        ):
            return None

        if not prompt_tokens:
            return None

        prompt_cache = self._make_prompt_cache_fn(self.model)
        for _ in self._generate_step_fn(
            mx.array(prompt_tokens),
            self.model,
            max_tokens=0,
            prompt_cache=prompt_cache,
        ):
            pass
        return prompt_cache

    def _trimmed_cache_copy(
        self, prompt_cache: Any, cached_tokens: list[int], target_prefix_len: int
    ) -> Any:
        from mlx_lm.models.cache import can_trim_prompt_cache, trim_prompt_cache  # type: ignore

        cache_copy = copy.deepcopy(prompt_cache)
        if (
            target_prefix_len < len(cached_tokens)
            and can_trim_prompt_cache(cache_copy)
        ):
            trim_prompt_cache(cache_copy, len(cached_tokens) - target_prefix_len)
        return cache_copy


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
        return PromptState(system_prompt=system_prompt)

    def clone_state(self, state: PromptState) -> PromptState:
        return PromptState(
            system_prompt=state.system_prompt,
            user_prompt=state.user_prompt,
        )

    def prefill(self, state: PromptState, tokens: str) -> None:
        state.user_prompt += tokens

    def generate_completion(self, state: PromptState, params: dict[str, Any]) -> str:
        _ = params
        prompt = f"{state.system_prompt}\n\n{state.user_prompt}"
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


def _common_prefix_len(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    idx = 0
    while idx < n and a[idx] == b[idx]:
        idx += 1
    return idx
