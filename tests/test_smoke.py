"""Smoke tests against a real embedded mlx_lm backend (requires MLX, Apple silicon)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mlx_server.app import build_app
from mlx_server.backend import start_backend
from mlx_server.config import _mlx_defaults


@pytest.fixture
def client() -> TestClient:
    ns = Namespace(**_mlx_defaults())
    backend = start_backend(ns)
    app = build_app(backend)
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc
    backend.shutdown()


def test_health_proxy(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_mlx_status(client: TestClient) -> None:
    r = client.get("/v1/mlx/status")
    assert r.status_code == 200
    data = r.json()
    assert "model_key" in data
    assert "cli_default_model" in data


def test_local_models_list(client: TestClient, tmp_path: Path) -> None:
    from urllib.parse import quote
    (tmp_path / "sub-a").mkdir()
    (tmp_path / "sub-a" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sub-b").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    r = client.get(f"/v1/mlx/models/local?root={quote(str(tmp_path))}")
    assert r.status_code == 200
    data = r.json()
    assert data["root"] == str(tmp_path.resolve())
    names = {e["name"]: e for e in data["entries"]}
    assert "sub-a" in names and names["sub-a"]["likely_mlx_model"] is True
    assert "sub-b" in names and names["sub-b"]["likely_mlx_model"] is False
    assert "file.txt" not in names


def test_proxy_post_allowed(client: TestClient) -> None:
    # We want to ensure it's not a 405 (Method Not Allowed)
    # 502/404 are acceptable since we don't have a real model loaded in smoke tests usually
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code != 405


def test_embeddings_explicitly_unsupported(client: TestClient) -> None:
    r = client.post("/v1/embeddings", json={"input": "hello", "model": "any"})
    assert r.status_code == 501
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == "embeddings_not_supported"
