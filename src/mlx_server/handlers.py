"""Route handlers for the MLX server API."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mlx_server.backend import MlxBackend
from mlx_server.model_resolver import resolve_model_path, search_huggingface_models
from mlx_server.proxy import proxy_to_mlx, run_load, run_unload

logger = logging.getLogger(__name__)

def _list_local_model_dirs(root: str) -> tuple[Path, list[dict[str, Any]]]:
    """List direct child directories under root (for local UI picker)."""
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ValueError(f"디렉터리가 없거나 경로가 아닙니다: {root}")
    entries: list[dict[str, Any]] = []
    for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "mtime": child.stat().st_mtime,
                "likely_mlx_model": (child / "config.json").is_file(),
            }
        )
    return base, entries

async def status_route(request: Request) -> JSONResponse:
    backend: MlxBackend = request.app.state.backend
    mp = backend.model_provider
    key = mp.model_key
    return JSONResponse(
        {
            "model_key": list(key) if key else None,
            "cli_default_model": backend.mlx_args.model,
        }
    )

async def load_route(request: Request) -> JSONResponse:
    backend: MlxBackend = request.app.state.backend
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        return JSONResponse({"detail": f"Invalid JSON: {e}"}, status_code=400)
    
    model = body.get("model")
    if not model or not isinstance(model, str):
        return JSONResponse(
            {"detail": '"model" must be a non-empty string'},
            status_code=400,
        )
    
    adapter_path = body.get("adapter_path")
    if adapter_path is not None and not isinstance(adapter_path, str):
        return JSONResponse(
            {"detail": "adapter_path must be a string or null"},
            status_code=400,
        )
    
    draft_model = body.get("draft_model")
    if draft_model is not None and not isinstance(draft_model, str):
        return JSONResponse(
            {"detail": "draft_model must be a string or null"},
            status_code=400,
        )

    # Resolve model path (Desktop models root prioritized)
    model = resolve_model_path(model, backend.mlx_args.local_models_root)

    try:
        await run_load(
            backend,
            model=model,
            adapter_path=adapter_path,
            draft_model=draft_model,
        )
    except Exception as e:
        logger.exception("Model load failed")
        msg = str(e)
        if "Repository Not Found" in msg and "/" not in model:
            msg = (
                f"모델을 찾을 수 없습니다: '{model}'. Hugging Face 모델은 "
                f"'조직/모델명' (예: Qwen/{model}) 형식이 필요합니다. "
                f"로컬 경로일 경우 절대 경로인지 확인하세요. (오류: {msg})"
            )
        return JSONResponse({"detail": msg}, status_code=500)
    
    key = backend.model_provider.model_key
    return JSONResponse({"status": "ok", "model_key": list(key) if key else None})

async def unload_route(request: Request) -> JSONResponse:
    backend: MlxBackend = request.app.state.backend
    try:
        await run_unload(backend)
    except Exception as e:
        logger.exception("Model unload failed")
        return JSONResponse({"detail": str(e)}, status_code=500)
    return JSONResponse({"status": "ok", "message": "Model unloaded"})

async def cache_stats_route(request: Request) -> JSONResponse:
    backend: MlxBackend = request.app.state.backend
    cache = backend.prompt_cache
    get_stats = getattr(cache, "get_cache_stats", None)
    if not callable(get_stats):
        return JSONResponse(
            {
                "advanced_cache": False,
                "detail": "Cache stats are available only when advanced cache is enabled.",
            },
            status_code=200,
        )

    try:
        stats = get_stats()
    except Exception as e:
        logger.exception("cache stats collection failed")
        return JSONResponse({"detail": str(e)}, status_code=500)

    return JSONResponse(
        {
            "advanced_cache": True,
            "stats": stats,
        }
    )

async def local_models_route(request: Request) -> JSONResponse:
    backend: MlxBackend = request.app.state.backend
    root = request.query_params.get("root")
    if not root or not root.strip():
        root = backend.mlx_args.local_models_root
        
    try:
        resolved, entries = _list_local_model_dirs(root.strip())
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    except OSError as e:
        logger.exception("local models list failed")
        return JSONResponse({"detail": str(e)}, status_code=400)
    return JSONResponse({"root": str(resolved), "entries": entries})

async def remote_models_route(request: Request) -> JSONResponse:
    # Query param processing doesn't strictly need backend, but keeping same pattern
    query = request.query_params.get("q", "").strip()
    if not query:
        return JSONResponse({"results": []})
    try:
        results = await asyncio.to_thread(search_huggingface_models, query)
    except Exception as e:
        logger.exception("remote search failed")
        return JSONResponse({"detail": str(e)}, status_code=500)
    return JSONResponse({"results": results})

async def proxy_route(request: Request) -> Response:
    backend: MlxBackend = request.app.state.backend
    client: httpx.AsyncClient = request.app.state.http_client
    return await proxy_to_mlx(request, backend, client)
