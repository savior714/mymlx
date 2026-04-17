"""Starlette app: MLX proxy and model lifecycle extension routes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route

from mlx_server.backend import MlxBackend
from mlx_server.handlers import (
    cache_stats_route,
    load_route,
    local_models_route,
    mcp_config_route,
    proxy_route,
    remote_models_route,
    status_route,
    unload_route,
)
from mlx_server.inference_audit import InferenceAuditTrail

logger = logging.getLogger(__name__)


def build_app(backend: MlxBackend) -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        app.state.backend = backend
        app.state.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(86400.0, connect=60.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        app.state.inference_audit = InferenceAuditTrail.from_namespace(backend.mlx_args)
        yield
        await app.state.http_client.aclose()
        backend.shutdown()

    routes = [
        Route("/v1/mlx/status", status_route, methods=["GET"]),
        Route("/v1/mlx/cache/stats", cache_stats_route, methods=["GET"]),
        Route("/v1/mlx/models/local", local_models_route, methods=["GET"]),
        Route("/v1/mlx/models/remote", remote_models_route, methods=["GET"]),
        Route("/v1/mlx/models/load", load_route, methods=["POST"]),
        Route("/v1/mlx/models/unload", unload_route, methods=["POST"]),
        Route("/v1/mlx/mcp-config", mcp_config_route, methods=["GET"]),
        Route(
            "/{path:path}",
            proxy_route,
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
        ),
    ]

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app
