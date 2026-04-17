"""Embedded `mlx_lm.server` HTTP stack on a localhost port (for proxying)."""

from __future__ import annotations

import functools
import json
import logging
import re
import threading
from argparse import Namespace
from dataclasses import dataclass

from mlx_server.cache_utils import AdvancedPromptCache, SafeguardPromptCache, set_priority
from mlx_server.memory_manager import initialize_metal_infrastructure
import mlx_lm.server as _mlx_server_mod
from mlx_lm.server import (
    APIHandler,
    ModelProvider,
    ResponseGenerator,
    ThreadingHTTPServer,
    get_system_fingerprint,
)

logger = logging.getLogger(__name__)


_GEMMA4_HYPHEN_CALL_RE = re.compile(r"call:([A-Za-z0-9_-]+)(\{.*\})", re.DOTALL)
_GEMMA4_THOUGHT_TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*<\|\"\|>\s*")
_LOOSE_BOOL_INT_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>true|false|-?\d+)\b"
)
_LOOSE_STRING_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<q>\"|')(?P<value>.*?)(?P=q)\s*(?=,|$)",
    re.DOTALL,
)
_LOOSE_ANGLE_QUOTE_STRING_RE = re.compile(
    r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*<\|"\|>(?P<value>.*?)<\|"\|>\s*(?=,|$)',
    re.DOTALL,
)
_LOOSE_THOUGHT_RE = re.compile(
    r"thought\s*:\s*(?P<value>.*?)(?=,\s*(?:nextThoughtNeeded|thoughtNumber|totalThoughts)\s*:|\s*}$)",
    re.DOTALL,
)


def _normalize_gemma4_args(args_str: str) -> str:
    """Normalize common malformed Gemma-style argument fragments."""
    normalized = _GEMMA4_THOUGHT_TOKEN_RE.sub(r"\1:", args_str)
    normalized = normalized.replace('<|"|>', '"')
    return normalized


def _normalize_tool_arguments(arguments: dict) -> dict:
    """Normalize parsed tool argument aliases without changing semantics."""
    if "needsMoreThoughts" in arguments:
        if "nextThoughtNeeded" not in arguments:
            arguments["nextThoughtNeeded"] = arguments["needsMoreThoughts"]
        arguments.pop("needsMoreThoughts", None)
    return arguments


def _parse_loose_tool_arguments(args_str: str) -> dict | None:
    """Best-effort parser for malformed pseudo-JSON argument payloads.

    Some models emit unquoted multiline text (mostly in `thought`) which breaks
    strict JSON conversion. Recover primitive fields and keep `thought` as text.
    """
    body = args_str.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]

    parsed: dict[str, object] = {}

    thought_match = _LOOSE_THOUGHT_RE.search(body)
    if thought_match:
        thought_raw = thought_match.group("value").strip()
        thought_clean = thought_raw.replace('<|"|>', '"').strip().strip('"')
        if thought_clean:
            parsed["thought"] = thought_clean

    for m in _LOOSE_BOOL_INT_RE.finditer(body):
        key = m.group("key")
        if key in parsed:
            # Keep first occurrence when malformed output duplicates keys.
            continue
        value_str = m.group("value")
        if value_str in ("true", "false"):
            parsed[key] = value_str == "true"
        else:
            try:
                parsed[key] = int(value_str)
            except ValueError:
                continue

    for m in _LOOSE_STRING_RE.finditer(body):
        key = m.group("key")
        if key in parsed:
            continue
        value = m.group("value").replace('<|"|>', '"').strip()
        if value != "":
            parsed[key] = value

    for m in _LOOSE_ANGLE_QUOTE_STRING_RE.finditer(body):
        key = m.group("key")
        if key in parsed:
            continue
        value = m.group("value").strip()
        if value != "":
            parsed[key] = value

    if isinstance(parsed.get("thought"), str) and parsed["thought"].strip() == "":
        parsed.pop("thought", None)

    return _normalize_tool_arguments(parsed) if parsed else None


def _parse_hyphenated_tool_call(tool_text: str) -> dict | None:
    """Best-effort parser for Gemma-style tool calls with hyphenated names."""
    m = _GEMMA4_HYPHEN_CALL_RE.search(tool_text)
    if not m:
        return None

    func_name = m.group(1)
    args_str = m.group(2)
    try:
        # Reuse upstream converter for Gemma4 pseudo-JSON format.
        from mlx_lm.tool_parsers.gemma4 import _gemma4_args_to_json

        normalized_args = _normalize_gemma4_args(args_str)
        arguments = json.loads(_gemma4_args_to_json(normalized_args))
        if isinstance(arguments, dict):
            arguments = _normalize_tool_arguments(arguments)
        else:
            return None
    except Exception:
        arguments = _parse_loose_tool_arguments(args_str)
        if not isinstance(arguments, dict):
            return None
    return {"name": func_name, "arguments": arguments}

# ... (PriorityAwareAPIHandler stays here as it's coupled with APIHandler) ...
class PriorityAwareAPIHandler(APIHandler):
    """
    Extends APIHandler to extract priority from headers and make it
    available to the cache manager via thread-local storage.
    """
    def handle(self):
        # Reset priority for this thread
        set_priority(None)
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected (or shutdown in progress) during streaming write.
            # Avoid noisy traceback for expected network tear-down scenarios.
            logger.info("Client connection closed while streaming response")

    def parse_request(self) -> bool:
        if super().parse_request():
            # Extract priority from custom header
            p_header = self.headers.get("X-MLX-Priority")
            if p_header:
                try:
                    p_val = int(p_header)
                    set_priority(p_val)
                    logger.debug(f"Request priority set to {p_val}")
                except (ValueError, TypeError):
                    pass
            return True
        return False

@dataclass
class MlxBackend:
    """Holds the MLX generation stack and the internal HTTP server thread."""

    mlx_args: Namespace
    response_generator: ResponseGenerator
    prompt_cache: AdvancedPromptCache
    base_url: str
    _thread: threading.Thread
    _httpd: ThreadingHTTPServer

    @property
    def model_provider(self) -> ModelProvider:
        return self.response_generator.model_provider

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self.response_generator.stop_and_join()
        if hasattr(self.prompt_cache, "stop_maintenance"):
            self.prompt_cache.stop_maintenance()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)


def _run_httpd(
    host: str,
    port: int,
    response_generator: ResponseGenerator,
    ready: threading.Event,
    holder: list,
) -> None:
    import socket

    server_address = (host, port)
    infos = socket.getaddrinfo(
        *server_address, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )
    ThreadingHTTPServer.address_family, _, _, _, server_address = next(iter(infos))
    httpd = ThreadingHTTPServer(
        server_address,
        lambda *args, **kwargs: PriorityAwareAPIHandler(
            response_generator,
            system_fingerprint=get_system_fingerprint(),
            *args,
            **kwargs,
        ),
    )
    holder.append(httpd)
    actual_host, actual_port = httpd.server_address[:2]
    logger.info("MLX internal httpd bound to %s:%s", actual_host, actual_port)
    logger.info(
        "mlx_lm.server is not recommended for production as it only implements "
        "basic security checks."
    )
    ready.set()
    try:
        httpd.serve_forever()
    except Exception:
        logger.exception("MLX internal httpd stopped")
    finally:
        response_generator.stop_and_join()


def _patch_tool_call_formatter() -> None:
    """Patch ToolCallFormatter.__call__ to handle malformed tool calls gracefully.

    The Gemma4 (and other) tool parsers raise ValueError when the model output
    contains a tool call marker (<|tool_call>) but the content does not match
    the expected pattern (e.g. empty call or wrong format). Without this patch
    the socket-server thread crashes and the client receives a connection reset.
    With this patch we log a warning and return an empty list so the response
    is delivered cleanly with finish_reason="tool_calls" and tool_calls=[].
    """
    try:
        import mlx_lm.server as _srv

        original_call = _srv.ToolCallFormatter.__call__

        def _safe_call(self, tool_calls):  # type: ignore[override]
            try:
                return original_call(self, tool_calls)
            except ValueError as exc:
                if tool_calls:
                    recovered: list[dict] = []
                    for raw in tool_calls:
                        parsed = _parse_hyphenated_tool_call(raw)
                        if parsed is None:
                            recovered = []
                            break
                        recovered.append(self._format(parsed))
                    if recovered:
                        logger.info(
                            "Recovered malformed tool call via hyphen parser: %d call(s)",
                            len(recovered),
                        )
                        return recovered
                logger.warning(
                    "Tool call parsing failed (malformed model output): %s. "
                    "Returning empty tool_calls. Raw segments: %r",
                    exc,
                    tool_calls[:3] if tool_calls else [],
                )
                return []

        _srv.ToolCallFormatter.__call__ = _safe_call
        logger.info("Tool call formatter: error-handling patch applied")
    except (ImportError, AttributeError):
        logger.debug("Tool call formatter patch skipped (ToolCallFormatter not found)")


def _patch_speculative_observability() -> None:
    """Wrap stream_generate to log speculative decoding acceptance rate.

    The upstream server discards ``GenerationResponse.from_draft`` in its
    HTTP path, so we capture it here at the module level to provide
    per-request observability via INFO logs.
    """
    original = _mlx_server_mod.stream_generate

    @functools.wraps(original)
    def _wrapped(*args, **kwargs):
        draft_model = kwargs.get("draft_model")
        if draft_model is None:
            yield from original(*args, **kwargs)
            return

        accepted = 0
        total = 0
        num_draft = kwargs.get("num_draft_tokens", 3)
        for gen in original(*args, **kwargs):
            total += 1
            if gen.from_draft:
                accepted += 1
            yield gen

        if total > 0:
            rate = accepted / total
            logger.info(
                "Speculative decoding stats: %d/%d tokens accepted "
                "(α=%.2f), draft_tokens_per_step=%d",
                accepted,
                total,
                rate,
                num_draft,
            )

    _mlx_server_mod.stream_generate = _wrapped
    logger.info("Speculative decoding observability enabled")


def _patch_kv_quantization(kv_bits: int, kv_group_size: int = 64) -> None:
    """Inject kv_bits into mlx_lm.server's stream_generate calls.

    The upstream server module does not forward kv_bits to stream_generate,
    so we wrap the function at the module level before ResponseGenerator is
    created.
    """
    original = _mlx_server_mod.stream_generate

    @functools.wraps(original)
    def _wrapped(*args, **kwargs):
        kwargs.setdefault("kv_bits", kv_bits)
        kwargs.setdefault("kv_group_size", kv_group_size)
        return original(*args, **kwargs)

    _mlx_server_mod.stream_generate = _wrapped
    logger.info(
        "KV cache quantization enabled: kv_bits=%d, kv_group_size=%d",
        kv_bits,
        kv_group_size,
    )


def _check_speculative_compat(model_provider: ModelProvider) -> bool:
    """Return True if the loaded model's cache supports speculative decoding.

    Speculative decoding requires every layer cache to be trimmable.
    Hybrid architectures (SSM/recurrent layers) use ArraysCache which is
    not trimmable, making them incompatible.
    """
    from mlx_lm.models.cache import make_prompt_cache, can_trim_prompt_cache

    try:
        model = model_provider.model
        if model is None:
            return True
        test_cache = make_prompt_cache(model)
        return can_trim_prompt_cache(test_cache)
    except Exception:
        logger.debug("Could not verify speculative decoding compatibility", exc_info=True)
        return True


def _patch_inference_tracking(rg: ResponseGenerator, pc: AdvancedPromptCache) -> None:
    """Wrap ResponseGenerator.generate to track long-running inference sessions."""
    original_generate = rg.generate

    def _wrapped_generate(*args, **kwargs):
        pc._mark_inference_start()
        ctx, response = original_generate(*args, **kwargs)

        def _response_wrapper():
            try:
                yield from response
            finally:
                pc._mark_inference_end()

        return ctx, _response_wrapper()

    rg.generate = _wrapped_generate
    logger.info("Inference tracking patch applied to ResponseGenerator")


def start_backend(mlx_args: Namespace) -> MlxBackend:
    """Wire Metal limits, build ModelProvider + ResponseGenerator, start internal httpd."""
    _patch_tool_call_formatter()

    wired_limit = initialize_metal_infrastructure(mlx_args)

    kv_bits = getattr(mlx_args, "kv_bits", None)
    if kv_bits is not None:
        _patch_kv_quantization(kv_bits, getattr(mlx_args, "kv_group_size", 64))

    draft_requested = getattr(mlx_args, "draft_model", None) is not None

    if draft_requested:
        _patch_speculative_observability()

    model_provider = ModelProvider(mlx_args)

    if draft_requested and not _check_speculative_compat(model_provider):
        logger.warning(
            "⚠ --draft-model speculative decoding disabled: this model uses "
            "non-trimmable cache layers (ArraysCache). Hybrid models like "
            "Qwen3.5/Qwen3-Next support native MTP speculative decoding "
            "(--mtp flag, requires mlx-lm with MTP support) instead of "
            "--draft-model. Falling back to standard generation."
        )
        mlx_args.draft_model = None
        model_provider.draft_model = None

    cache_kwargs = {"max_size": mlx_args.prompt_cache_size}
    if mlx_args.prompt_cache_bytes is not None:
        cache_kwargs["max_bytes"] = mlx_args.prompt_cache_bytes
        logger.info("Prompt cache limit: %.2f GB", mlx_args.prompt_cache_bytes / 1024**3)
    
    if getattr(mlx_args, "advanced_cache", True):
        # Extract model_id from path or identity
        m_path = getattr(mlx_args, "model", None) or "default"
        model_id = m_path.split("/")[-1] if "/" in m_path else m_path
        
        prompt_cache = AdvancedPromptCache(
            page_size=mlx_args.page_size,
            max_memory_gb=wired_limit / 1024**3,
            disk_cache_limit=getattr(mlx_args, "disk_cache_limit", None),
            model_id=model_id,
            quantization=f"{getattr(mlx_args, 'kv_bits', 'none')}bit",
            cache_grace_seconds=getattr(mlx_args, "cache_grace_seconds", 15.0),
            cache_observability=getattr(mlx_args, "cache_observability", False),
            cache_headroom_ratio=getattr(mlx_args, "cache_headroom_ratio", 0.80),
            **cache_kwargs
        )
    else:
        prompt_cache = SafeguardPromptCache(**cache_kwargs)
        logger.info("Using standard SafeguardPromptCache (Advanced Cache disabled)")
    
    response_generator = ResponseGenerator(model_provider, prompt_cache)
    
    # Apply inference tracking if using AdvancedPromptCache
    if isinstance(prompt_cache, AdvancedPromptCache):
        _patch_inference_tracking(response_generator, prompt_cache)

    ready = threading.Event()
    holder: list = []
    host, port = "127.0.0.1", 0
    thread = threading.Thread(
        target=_run_httpd,
        args=(host, port, response_generator, ready, holder),
        name="mlx-internal-httpd",
        daemon=True,
    )
    thread.start()
    if not ready.wait(timeout=120):
        raise RuntimeError("MLX internal httpd failed to bind")

    httpd = holder[0]
    _, actual_port = httpd.server_address[:2]
    base_url = f"http://127.0.0.1:{actual_port}"

    return MlxBackend(
        mlx_args=mlx_args,
        response_generator=response_generator,
        prompt_cache=prompt_cache,
        base_url=base_url,
        _thread=thread,
        _httpd=httpd,
    )
