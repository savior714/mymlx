"""Direct-call inference path — bypasses the internal ThreadingHTTPServer.

Constructs ``CompletionRequest`` / ``GenerationArguments`` from the parsed
JSON body and invokes ``ResponseGenerator.generate()`` in-process, avoiding
the localhost HTTP round-trip entirely.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Iterator

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from mlx_lm.server import (
    CompletionRequest,
    GenerationArguments,
    LogitsProcessorArguments,
    ModelDescription,
    SamplingArguments,
    ToolCallFormatter,
    get_system_fingerprint,
)

if TYPE_CHECKING:
    from mlx_server.backend import MlxBackend

logger = logging.getLogger(__name__)


def _build_gen_args(
    data: dict[str, Any],
    mlx_args: Any,
) -> tuple[CompletionRequest, GenerationArguments, dict[str, Any]]:
    """Build upstream dataclass instances from the OpenAI-style body."""
    path_model = data.get("model") or "default_model"
    draft = data.get("draft_model") or "default_model"
    adapter = data.get("adapters") or data.get("adapter_path") or None
    model_desc = ModelDescription(model=path_model, draft=draft, adapter=adapter)

    temp = float(data.get("temperature", mlx_args.temp))
    sampling = SamplingArguments(
        temperature=temp,
        top_p=float(data.get("top_p", mlx_args.top_p)),
        top_k=int(data.get("top_k", mlx_args.top_k)),
        min_p=float(data.get("min_p", mlx_args.min_p)),
        xtc_probability=float(data.get("xtc_probability", 0.0)),
        xtc_threshold=float(data.get("xtc_threshold", 0.0)),
    )

    logits = LogitsProcessorArguments(
        logit_bias=data.get("logit_bias"),
        repetition_penalty=float(
            data.get("repetition_penalty", mlx_args.repetition_penalty)
        ),
        repetition_context_size=int(
            data.get("repetition_context_size", mlx_args.repetition_context_size)
        ),
        presence_penalty=float(
            data.get("presence_penalty", mlx_args.presence_penalty)
        ),
        presence_context_size=int(
            data.get("presence_context_size", mlx_args.presence_context_size)
        ),
        frequency_penalty=float(data.get("frequency_penalty", 0.0)),
        frequency_context_size=int(data.get("frequency_context_size", 20)),
    )

    max_tokens = data.get("max_completion_tokens")
    if max_tokens is None:
        max_tokens = data.get("max_tokens", mlx_args.max_tokens)

    stop = data.get("stop") or []
    if isinstance(stop, str):
        stop = [stop]

    gen_args = GenerationArguments(
        model=model_desc,
        sampling=sampling,
        logits=logits,
        stop_words=stop,
        max_tokens=int(max_tokens),
        num_draft_tokens=int(data.get("num_draft_tokens", mlx_args.num_draft_tokens)),
        logprobs=bool(data.get("logprobs", False)),
        top_logprobs=int(data.get("top_logprobs", 0)),
        seed=data.get("seed"),
        chat_template_kwargs=getattr(mlx_args, "chat_template_kwargs", None),
    )

    messages = data.get("messages")
    if messages is not None:
        req = CompletionRequest(
            request_type="chat",
            prompt="",
            messages=messages,
            tools=data.get("tools"),
            role_mapping=data.get("role_mapping"),
        )
    else:
        req = CompletionRequest(
            request_type="text",
            prompt=data.get("prompt", ""),
            messages=[],
            tools=None,
            role_mapping=None,
        )

    stream_opts = data.get("stream_options") or {}
    meta: dict[str, Any] = {
        "stream": bool(data.get("stream", False)),
        "include_usage": stream_opts.get("include_usage", False),
        "request_model": path_model,
        "is_chat": messages is not None,
    }
    return req, gen_args, meta


def _make_chunk(
    request_id: str,
    model: str,
    created: int,
    fingerprint: str,
    *,
    is_chat: bool,
    text: str = "",
    finish_reason: str | None = None,
    reasoning_text: str = "",
    tool_calls: list | None = None,
) -> dict:
    choice: dict[str, Any] = {"index": 0, "finish_reason": finish_reason}
    if is_chat:
        delta: dict[str, Any] = {"role": "assistant"}
        if text:
            delta["content"] = text
        if reasoning_text:
            delta["reasoning"] = reasoning_text
        if tool_calls:
            delta["tool_calls"] = tool_calls
        choice["delta"] = delta
        obj_type = "chat.completion.chunk"
    else:
        choice["text"] = text
        obj_type = "text_completion"
    return {
        "id": request_id,
        "system_fingerprint": fingerprint,
        "object": obj_type,
        "model": model,
        "created": created,
        "choices": [choice],
    }


def _make_full_response(
    request_id: str,
    model: str,
    created: int,
    fingerprint: str,
    *,
    is_chat: bool,
    text: str,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
    prompt_cache_count: int,
    reasoning_text: str = "",
    tool_calls: list | None = None,
) -> dict:
    choice: dict[str, Any] = {"index": 0, "finish_reason": finish_reason}
    if is_chat:
        msg: dict[str, Any] = {"role": "assistant"}
        if text:
            msg["content"] = text
        if reasoning_text:
            msg["reasoning"] = reasoning_text
        if tool_calls:
            msg["tool_calls"] = tool_calls
        choice["message"] = msg
        obj_type = "chat.completion"
    else:
        choice["text"] = text
        obj_type = "text_completion"

    usage: dict[str, Any] = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if prompt_cache_count >= 0:
        usage["prompt_tokens_details"] = {"cached_tokens": prompt_cache_count}

    return {
        "id": request_id,
        "system_fingerprint": fingerprint,
        "object": obj_type,
        "model": model,
        "created": created,
        "choices": [choice],
        "usage": usage,
    }


def _run_generation_sync(
    backend: MlxBackend,
    req: CompletionRequest,
    gen_args: GenerationArguments,
    meta: dict[str, Any],
) -> Iterator[bytes]:
    """Synchronous generator that yields SSE bytes or a single JSON body."""
    rg = backend.response_generator
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    fingerprint = get_system_fingerprint()
    created = int(time.time())
    is_chat = meta["is_chat"]
    model_name = meta["request_model"]
    do_stream = meta["stream"]

    ctx, response = rg.generate(req, gen_args)

    tool_formatter = ToolCallFormatter(ctx.tool_parser, req.tools, do_stream)

    prev_state = None
    finish_reason: str | None = "stop"
    reasoning_text = ""
    made_tool_call = False
    tool_text = ""
    tool_calls: list[str] = []
    text = ""
    tokens: list[int] = []

    try:
        for gen in response:
            if gen.state == "reasoning":
                reasoning_text += gen.text
            elif gen.state == "tool":
                tool_text += gen.text
            elif gen.state == "normal":
                if prev_state == "tool":
                    tool_calls.append(tool_text)
                    tool_text = ""
                    made_tool_call = True
                text += gen.text

            tokens.append(gen.token)

            if (
                do_stream
                and gen.state != "tool"
                and (text or tool_calls or reasoning_text)
            ):
                chunk = _make_chunk(
                    request_id, model_name, created, fingerprint,
                    is_chat=is_chat,
                    text=text,
                    reasoning_text=reasoning_text,
                    tool_calls=tool_formatter(tool_calls) if tool_calls else None,
                )
                yield f"data: {json.dumps(chunk)}\n\n".encode()
                reasoning_text = ""
                text = ""
                tool_calls = []

            if gen.finish_reason is not None:
                finish_reason = gen.finish_reason

            prev_state = gen.state

        if prev_state == "tool" and tool_text:
            tool_calls.append(tool_text)
            made_tool_call = True

        if finish_reason == "stop" and made_tool_call:
            finish_reason = "tool_calls"

        formatted_tc = tool_formatter(tool_calls) if tool_calls else None

        if do_stream:
            final = _make_chunk(
                request_id, model_name, created, fingerprint,
                is_chat=is_chat,
                text=text,
                finish_reason=finish_reason,
                reasoning_text=reasoning_text,
                tool_calls=formatted_tc,
            )
            yield f"data: {json.dumps(final)}\n\n".encode()

            if meta["include_usage"]:
                usage_resp = {
                    "id": request_id,
                    "system_fingerprint": fingerprint,
                    "object": "chat.completion",
                    "model": model_name,
                    "created": created,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": len(ctx.prompt),
                        "completion_tokens": len(tokens),
                        "total_tokens": len(ctx.prompt) + len(tokens),
                    },
                }
                pcc = ctx.prompt_cache_count
                if pcc is not None and pcc >= 0:
                    usage_resp["usage"]["prompt_tokens_details"] = {
                        "cached_tokens": pcc,
                    }
                yield f"data: {json.dumps(usage_resp)}\n\n".encode()

            yield b"data: [DONE]\n\n"
        else:
            body = _make_full_response(
                request_id, model_name, created, fingerprint,
                is_chat=is_chat,
                text=text,
                finish_reason=finish_reason or "stop",
                prompt_tokens=len(ctx.prompt),
                completion_tokens=len(tokens),
                prompt_cache_count=ctx.prompt_cache_count or 0,
                reasoning_text=reasoning_text,
                tool_calls=formatted_tc,
            )
            yield json.dumps(body).encode()
    finally:
        ctx.stop()


async def handle_direct_inference(
    request: Request,
    backend: MlxBackend,
    data: dict[str, Any],
) -> Response:
    """Entry point called from the proxy layer for inference requests."""
    try:
        req, gen_args, meta = _build_gen_args(data, backend.mlx_args)
    except Exception as e:
        logger.warning("Failed to build generation args: %s", e)
        return JSONResponse({"error": {"message": str(e)}}, status_code=400)

    do_stream = meta["stream"]

    if do_stream:
        try:
            sync_gen = _run_generation_sync(backend, req, gen_args, meta)
        except Exception as e:
            logger.error("Direct inference init error: %s", e)
            return JSONResponse(
                {"error": {"message": str(e), "type": "server_error"}},
                status_code=500,
            )

        async def _stream():
            loop = asyncio.get_running_loop()
            gen = sync_gen
            try:
                while True:
                    chunk = await loop.run_in_executor(None, next, gen, None)
                    if chunk is None:
                        break
                    yield chunk
            except StopIteration:
                pass
            except Exception as e:
                logger.error("Direct inference stream error: %s", e)

        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(_stream(), headers=headers)
    else:
        try:
            def _sync():
                return b"".join(_run_generation_sync(backend, req, gen_args, meta))

            body = await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("Direct inference error: %s", e)
            return JSONResponse(
                {"error": {"message": str(e), "type": "server_error"}},
                status_code=500,
            )
        return Response(
            content=body,
            media_type="application/json",
        )
