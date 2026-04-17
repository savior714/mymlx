"""Payload transformation and normalization for MLX inference requests."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_whitespace_re = re.compile(r"[ \t]+")
_newline_re = re.compile(r"\n{3,}")

class MlxRequestTransformer:
    """Handles mutation and normalization of OpenAI-style requests for MLX."""

    @staticmethod
    def ensure_chat_messages(data: dict) -> bool:
        """Ensure chat/completions payload uses OpenAI-style `messages`."""
        messages = data.get("messages")
        if isinstance(messages, list):
            return False

        prompt = data.get("prompt")
        if not isinstance(prompt, str):
            return False

        data["messages"] = [{"role": "user", "content": prompt}]
        data.pop("prompt", None)
        return True

    @staticmethod
    def normalize_chat_messages(data: dict) -> int:
        """Make chat `messages` compatible with `mlx_lm.server.process_message_content`.

        Returns the number of messages whose content was converted (list -> string).
        """
        messages = data.get("messages")
        if not isinstance(messages, list):
            return 0
        converted = 0
        total_dropped = 0
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            text_parts: list[str] = []
            dropped_here = 0
            for fragment in content:
                if isinstance(fragment, dict) and fragment.get("type") == "text":
                    text_parts.append(str(fragment.get("text", "")))
                else:
                    dropped_here += 1
            total_dropped += dropped_here
            msg["content"] = "".join(text_parts)
            converted += 1
        
        if total_dropped:
            logger.warning(
                "Stripped %d non-text message content part(s) for MLX (text-only upstream)",
                total_dropped,
            )
        return converted

    @staticmethod
    def normalize_prompt_payload(data: dict) -> tuple[int, int]:
        """Normalize textual prompt payload for cache-key stability."""
        before = 0
        after = 0

        def _normalize_text(s: str) -> str:
            cleaned = _whitespace_re.sub(" ", s).strip()
            return _newline_re.sub("\n\n", cleaned)

        prompt = data.get("prompt")
        if isinstance(prompt, str):
            before += len(prompt)
            normalized = _normalize_text(prompt)
            after += len(normalized)
            data["prompt"] = normalized

        messages = data.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if isinstance(content, str):
                    before += len(content)
                    normalized = _normalize_text(content)
                    after += len(normalized)
                    msg["content"] = normalized
        return before, after

    @staticmethod
    def transform(
        path: str,
        data: dict,
        backend_args: Any,
        active_model_key: tuple[str, ...] | None,
    ) -> bool:
        """Perform all necessary mutations on the request data. Returns True if mutated."""
        from mlx_server.model_resolver import _resolve_model_cached
        
        mutated = False
        
        # 1. Model Resolution
        if not data.get("model"):
            if active_model_key and active_model_key[0]:
                data["model"] = active_model_key[0]
                mutated = True

        model_name = data.get("model")
        if model_name and isinstance(model_name, str):
            resolved = _resolve_model_cached(model_name, backend_args.local_models_root)
            if resolved != model_name:
                data["model"] = resolved
                mutated = True

        # 2. Chat Normalization
        if path in ("/v1/chat/completions", "/chat/completions"):
            if MlxRequestTransformer.ensure_chat_messages(data):
                mutated = True
            if MlxRequestTransformer.normalize_chat_messages(data):
                mutated = True

        # 3. Tool Choice Default
        if path in ("/v1/chat/completions", "/chat/completions"):
            if "tools" in data and "tool_choice" not in data:
                tc_default = getattr(backend_args, "tool_choice_default", "auto")
                if tc_default and tc_default != "auto":
                    data["tool_choice"] = tc_default
                    mutated = True

        # 4. Prompt Normalization
        if getattr(backend_args, "prompt_normalization", False):
            pre_len, post_len = MlxRequestTransformer.normalize_prompt_payload(data)
            if pre_len != post_len:
                logger.info(
                    "Prompt normalization applied: before=%d, after=%d",
                    pre_len,
                    post_len,
                )
                mutated = True
        
        return mutated
