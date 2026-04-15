from __future__ import annotations

from argparse import Namespace

from starlette.testclient import TestClient

from mlx_server.app import build_app
from mlx_server.config import _mlx_defaults


class _DummyModelProvider:
    model_key = None


class _DummyCache:
    def get_cache_stats(self) -> dict:
        return {
            "full_hit_rate": 0.5,
            "paged_hit_rate": 0.25,
            "miss_reason_counts": {"paged_hash_miss": 2},
        }


class _DummyBackend:
    def __init__(self, *, prompt_cache) -> None:
        self.prompt_cache = prompt_cache
        self.model_provider = _DummyModelProvider()
        self.mlx_args = Namespace(**_mlx_defaults())
        self.base_url = "http://127.0.0.1:9"

    def shutdown(self) -> None:
        return


def test_cache_stats_route_returns_stats() -> None:
    backend = _DummyBackend(prompt_cache=_DummyCache())
    app = build_app(backend)
    with TestClient(app, raise_server_exceptions=True) as client:
        r = client.get("/v1/mlx/cache/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["advanced_cache"] is True
    assert "stats" in data
    assert data["stats"]["full_hit_rate"] == 0.5


def test_cache_stats_route_when_unavailable() -> None:
    backend = _DummyBackend(prompt_cache=object())
    app = build_app(backend)
    with TestClient(app, raise_server_exceptions=True) as client:
        r = client.get("/v1/mlx/cache/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["advanced_cache"] is False
