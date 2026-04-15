"""HTTP proxy from Starlette to the embedded MLX `ThreadingHTTPServer`."""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
) -> None:
    if audit is None or audit_ctx is None or not audit.enabled:
        return
    audit.log_complete(
        request_id=audit_ctx["request_id"],
        path=audit_ctx["path"],
        model_resolved=audit_ctx["model_resolved"],
        upstream_status=upstream_status,
        outcome=outcome,
        effective=audit_ctx["effective"],
        prompt_stats=audit_ctx["prompt_stats"],
        server_runtime=audit_ctx["server_runtime"],
        priority=audit_ctx["priority"],
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


from mlx_server.request_transformer import MlxRequestTransformer

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

    inference_paths = ("/v1/chat/completions", "/v1/completions", "/chat/completions")
    if path in inference_paths and request.method == "POST":
        data: dict | None = None
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = None
        else:
            if isinstance(parsed, dict):
                data = parsed

        if data is not None:
            # Shift payload mutation to transformer
            mutated = MlxRequestTransformer.transform(
                path, data, backend.mlx_args, backend.model_provider.model_key
            )
            
            priority = data.get("priority")
            if priority is not None:
                headers["X-MLX-Priority"] = str(priority)

            # Audit Snapshot
            audit, audit_ctx = _prepare_inference_audit(request, path, data, backend)

            if mutated:
                body = json.dumps(data).encode("utf-8")

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

    # SSE handling
    ct = resp_headers.get("content-type", "").lower()
    if "text/event-stream" in ct:
        resp_headers.setdefault("Cache-Control", "no-cache")
        resp_headers["X-Accel-Buffering"] = "no"

    async def body_iter():
        interrupted = False
        try:
            async for chunk in stream.aiter_raw():
                yield chunk
        except httpx.HTTPError as e:
            interrupted = True
            logging.getLogger(__name__).warning("Upstream stream interrupted: %s", e)
        finally:
            await stream.aclose()
            outcome = "stream_interrupted" if interrupted else "success"
            _log_inference_audit_complete(
                audit,
                audit_ctx,
                upstream_status=stream.status_code,
                outcome=outcome,
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
