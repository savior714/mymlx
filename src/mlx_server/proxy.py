"""HTTP proxy from Starlette to the embedded MLX `ThreadingHTTPServer`."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from mlx_server.inference_audit import (
    InferenceAuditTrail,
    effective_inference_params,
    prompt_stats_for_body,
    resolve_request_id,
    server_runtime_snapshot,
)
from mlx_server.request_transformer import MlxRequestTransformer

if TYPE_CHECKING:
    from mlx_server.backend import MlxBackend

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

def _forward_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in request.headers.items():
        if name.lower() in ("host", "connection", "content-length"):
            continue
        out[name] = value
    return out


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in headers.items():
        if name.lower() in _HOP_BY_HOP:
            continue
        out[name] = value
    return out


def _log_inference_audit_complete(
    audit: InferenceAuditTrail | None,
    audit_ctx: dict[str, Any] | None,
    *,
    upstream_status: int | None,
    outcome: str,
    usage: dict[str, int] | None = None,
) -> None:
    if audit is None or audit_ctx is None or not audit.enabled:
        # Update tracker even if file logging is disabled
        if usage:
            _dummy = InferenceAuditTrail(None, None)
            stats = _dummy.log_complete(
                request_id="",
                path="",
                model_resolved=None,
                upstream_status=None,
                outcome="",
                effective={},
                prompt_stats={},
                server_runtime={},
                priority=None,
                usage=usage,
            )
            if stats and stats.get("should_report"):
                _metrics_log.info(
                    f"[SUMMARY] Total Requests: {stats['total_requests']} | "
                    f"Avg Tokens: {stats['avg_prompt_tokens']} prompt, {stats['avg_completion_tokens']} completion"
                )
        return
    stats = audit.log_complete(
        request_id=audit_ctx["request_id"],
        path=audit_ctx["path"],
        model_resolved=audit_ctx["model_resolved"],
        upstream_status=upstream_status,
        outcome=outcome,
        effective=audit_ctx["effective"],
        prompt_stats=audit_ctx["prompt_stats"],
        server_runtime=audit_ctx["server_runtime"],
        priority=audit_ctx["priority"],
        usage=usage,
    )
    if stats and stats.get("should_report"):
        _metrics_log.info(
            f"[SUMMARY] Total Requests: {stats['total_requests']} | "
            f"Avg Tokens: {stats['avg_prompt_tokens']} prompt, {stats['avg_completion_tokens']} completion"
        )


def _prepare_inference_audit(
    request: Request,
    path: str,
    data: dict,
    backend: MlxBackend,
) -> tuple[InferenceAuditTrail | None, dict[str, Any] | None]:
    audit: InferenceAuditTrail | None = getattr(request.app.state, "inference_audit", None)
    if not audit or not audit.enabled:
        return audit, None

    rid = resolve_request_id(request)
    eff = effective_inference_params(data, backend.mlx_args)
    pstats = prompt_stats_for_body(path, data)
    srv = server_runtime_snapshot(backend.mlx_args)
    pri = data.get("priority")
    pri_out = int(pri) if isinstance(pri, int) else None
    mr = data.get("model")
    model_str = str(mr) if mr is not None else None
    
    audit.write_snapshot(
        request_id=rid,
        path=path,
        model_resolved=model_str,
        effective=eff,
        prompt_stats=pstats,
        server_runtime=srv,
        priority=pri_out,
    )
    
    ctx = {
        "request_id": rid,
        "path": path,
        "model_resolved": model_str,
        "effective": eff,
        "prompt_stats": pstats,
        "server_runtime": srv,
        "priority": pri_out,
    }
    return audit, ctx


_metrics_log = logging.getLogger("mlx_server.metrics")

_SSE_CONTENT_PROBE = '"content":'
_SSE_USAGE_PROBE = '"completion_tokens":'


def _log_request_metrics(
    *,
    prompt_tokens: int | None,
    completion_tokens: int,
    ttft: float | None,
    total_time: float,
) -> None:
    gen_time = total_time - (ttft if ttft is not None else 0)
    tps = completion_tokens / gen_time if gen_time > 0 else 0.0

    parts = [f"{completion_tokens} tokens", f"{tps:.1f} t/s"]

    if prompt_tokens is not None and ttft is not None and ttft > 0:
        pps = prompt_tokens / ttft
        parts.append(f"{pps:.1f} pp/s")

    if prompt_tokens is not None:
        parts.append(f"{prompt_tokens} prompt")

    if ttft is not None:
        parts.append(f"{ttft:.2f}s TTFT")

    parts.append(f"{total_time:.1f}s total")
    _metrics_log.info("    ".join(parts))


# Backward compatibility for internal helpers used by tests
_normalize_chat_messages_for_mlx = MlxRequestTransformer.normalize_chat_messages
_normalize_prompt_payload = MlxRequestTransformer.normalize_prompt_payload


async def proxy_to_mlx(
    request: Request,
    backend: MlxBackend,
    client: httpx.AsyncClient,
) -> Response:
    path = request.url.path
    if path == "/v1/embeddings":
        return JSONResponse(
            {
                "error": {
                    "message": "mlx-server does not support embeddings. Use /v1/chat/completions or /v1/completions.",
                    "type": "unsupported_endpoint",
                    "param": None,
                    "code": "embeddings_not_supported",
                }
            },
            status_code=501,
        )
    if path.startswith("/v1/mlx/"):
        return Response("Not Found", status_code=404)

    target = f"{backend.base_url}{path}"
    q = request.url.query
    if q:
        target = f"{target}?{q}"
    
    body = await request.body()
    headers = _forward_request_headers(request)
    audit: InferenceAuditTrail | None = None
    audit_ctx: dict[str, Any] | None = None
    start_time = time.monotonic()

    inference_paths = ("/v1/chat/completions", "/v1/completions", "/chat/completions")
    is_inference = path in inference_paths and request.method == "POST"
    if is_inference:
        data: dict | None = None
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = None
        else:
            if isinstance(parsed, dict):
                data = parsed

        if data is not None:
            MlxRequestTransformer.transform(
                path, data, backend.mlx_args, backend.model_provider.model_key
            )
            if data.get("stream"):
                so = data.setdefault("stream_options", {})
                if isinstance(so, dict):
                    so.setdefault("include_usage", True)

            # Audit Snapshot (non-blocking — queued to background)
            audit, audit_ctx = _prepare_inference_audit(request, path, data, backend)

            # Direct inference path — call ResponseGenerator in-process
            from mlx_server.direct_inference import handle_direct_inference
            return await handle_direct_inference(request, backend, data)

    try:
        req = client.build_request(request.method, target, headers=headers, content=body)
        stream = await client.send(req, stream=True)
    except httpx.RequestError as e:
        _log_inference_audit_complete(
            audit, audit_ctx, upstream_status=None, outcome="transport_error"
        )
        return Response(f"Upstream MLX error: {e}", status_code=502)

    resp_headers = _filter_response_headers(stream.headers)

    if stream.status_code >= 400:
        try:
            raw_error = await stream.aread()
        except httpx.HTTPError as e:
            logging.getLogger(__name__).error(
                "Failed to read upstream error body (%s): %s",
                stream.status_code,
                e,
            )
            raw_error = b""
        finally:
            await stream.aclose()

        if raw_error:
            try:
                err_data = json.loads(raw_error)
                logging.getLogger(__name__).error(
                    "Upstream MLX error (%s): %s",
                    stream.status_code,
                    err_data,
                )
            except Exception:
                logging.getLogger(__name__).error(
                    "Upstream MLX error (%s): %s",
                    stream.status_code,
                    raw_error.decode(errors="replace"),
                )
        else:
            logging.getLogger(__name__).error(
                "Upstream MLX error (%s): empty body",
                stream.status_code,
            )

        _log_inference_audit_complete(
            audit,
            audit_ctx,
            upstream_status=stream.status_code,
            outcome="upstream_error",
        )
        return Response(
            content=raw_error or b"Not Found",
            status_code=stream.status_code,
            headers=resp_headers,
        )

    ct = resp_headers.get("content-type", "").lower()
    is_sse = "text/event-stream" in ct
    if is_sse:
        resp_headers.setdefault("Cache-Control", "no-cache")
        resp_headers["X-Accel-Buffering"] = "no"

    async def body_iter():
        interrupted = False
        t_first_token: float | None = None
        token_count = 0
        prompt_toks: int | None = None
        compl_toks: int | None = None
        usage_data: dict | None = None
        non_sse_buf = bytearray() if (is_inference and not is_sse) else None

        try:
            async for chunk in stream.aiter_raw():
                if is_inference:
                    if is_sse:
                        try:
                            text = chunk.decode("utf-8", errors="replace")
                            for line in text.split("\n"):
                                stripped = line.strip()
                                if not stripped.startswith("data: ") or stripped == "data: [DONE]":
                                    continue
                                payload = stripped[6:]
                                if _SSE_CONTENT_PROBE in payload:
                                    token_count += 1
                                    if t_first_token is None:
                                        t_first_token = time.monotonic()
                                if _SSE_USAGE_PROBE in payload:
                                    try:
                                        evt = json.loads(payload)
                                        u = evt.get("usage")
                                        if isinstance(u, dict) and u.get("completion_tokens"):
                                            usage_data = u
                                    except (json.JSONDecodeError, ValueError):
                                        pass
                        except Exception:
                            pass
                    elif non_sse_buf is not None:
                        non_sse_buf.extend(chunk)
                yield chunk
        except httpx.HTTPError as e:
            interrupted = True
            logging.getLogger(__name__).warning("Upstream stream interrupted: %s", e)
        finally:
            await stream.aclose()

            if is_inference:
                total_elapsed = time.monotonic() - start_time
                ttft = (t_first_token - start_time) if t_first_token is not None else None
                compl_toks = token_count

                if usage_data:
                    prompt_toks = usage_data.get("prompt_tokens")
                    ct_val = usage_data.get("completion_tokens")
                    if ct_val:
                        compl_toks = ct_val
                elif non_sse_buf:
                    try:
                        resp_body = json.loads(non_sse_buf)
                        u = resp_body.get("usage")
                        if isinstance(u, dict):
                            prompt_toks = u.get("prompt_tokens")
                            compl_toks = u.get("completion_tokens", 0)
                    except (json.JSONDecodeError, ValueError):
                        pass

                if compl_toks or prompt_toks:
                    _log_request_metrics(
                        prompt_tokens=prompt_toks,
                        completion_tokens=compl_toks or 0,
                        ttft=ttft,
                        total_time=total_elapsed,
                    )

            outcome = "stream_interrupted" if interrupted else "success"
            _log_inference_audit_complete(
                audit,
                audit_ctx,
                upstream_status=stream.status_code,
                outcome=outcome,
                usage={"prompt_tokens": prompt_toks, "completion_tokens": compl_toks}
                if (prompt_toks or compl_toks)
                else None,
            )

    return StreamingResponse(
        body_iter(),
        status_code=stream.status_code,
        headers=resp_headers,
    )


async def run_load(
    backend: MlxBackend,
    *,
    model: str,
    adapter_path: str | None,
    draft_model: str | None,
) -> None:
    mp = backend.model_provider

    def _load() -> None:
        mp.load(
            model,
            adapter_path=adapter_path,
            draft_model_path=draft_model,
        )

    await asyncio.to_thread(_load)


async def run_unload(backend: MlxBackend) -> None:
    """Clear the active model and release Metal memory."""
    import mlx.core as mx

    mp = backend.model_provider
    prompt_cache = backend.prompt_cache

    def _unload() -> None:
        # Release references
        mp.model = None
        mp.tokenizer = None
        mp.model_key = None
        if hasattr(mp, "draft_model"):
            mp.draft_model = None

        # Clear prompt cache entries to free retained KV tensors.
        clear_fn = getattr(prompt_cache, "clear", None)
        if callable(clear_fn):
            clear_fn()

        if mx.metal.is_available():
            mx.clear_cache()

    await asyncio.to_thread(_unload)
