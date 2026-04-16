"""Unit tests for speculative decoding configuration flow (no MLX hardware required)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from mlx_server.config import _mlx_defaults, merged_mlx_namespace
from mlx_server.inference_audit import effective_inference_params, server_runtime_snapshot


def _make_ns(**overrides) -> Namespace:
    d = _mlx_defaults()
    d.update(overrides)
    return Namespace(**d)


class TestSpeculativeDefaults:
    def test_draft_model_default_is_none(self) -> None:
        defaults = _mlx_defaults()
        assert defaults["draft_model"] is None

    def test_num_draft_tokens_default_is_3(self) -> None:
        defaults = _mlx_defaults()
        assert defaults["num_draft_tokens"] == 3


class TestEffectiveInferenceParams:
    def test_num_draft_tokens_from_cli(self) -> None:
        ns = _make_ns(num_draft_tokens=16)
        body: dict = {}
        eff = effective_inference_params(body, ns)
        assert eff["num_draft_tokens"] == 16

    def test_num_draft_tokens_request_override(self) -> None:
        ns = _make_ns(num_draft_tokens=3)
        body = {"num_draft_tokens": 20}
        eff = effective_inference_params(body, ns)
        assert eff["num_draft_tokens"] == 20

    def test_num_draft_tokens_zero_allowed(self) -> None:
        ns = _make_ns(num_draft_tokens=3)
        body = {"num_draft_tokens": 0}
        eff = effective_inference_params(body, ns)
        assert eff["num_draft_tokens"] == 0


class TestServerRuntimeSnapshot:
    def test_includes_draft_model(self) -> None:
        ns = _make_ns(draft_model="/models/draft-1B")
        snap = server_runtime_snapshot(ns)
        assert snap["draft_model"] == "/models/draft-1B"

    def test_includes_num_draft_tokens(self) -> None:
        ns = _make_ns(num_draft_tokens=16)
        snap = server_runtime_snapshot(ns)
        assert snap["num_draft_tokens"] == 16

    def test_draft_model_none_when_absent(self) -> None:
        ns = _make_ns()
        snap = server_runtime_snapshot(ns)
        assert snap["draft_model"] is None


class TestMergedNamespace:
    def test_cli_draft_model_propagates(self) -> None:
        import argparse
        from mlx_server.mlx_parser import add_mlx_server_arguments

        parser = argparse.ArgumentParser()
        add_mlx_server_arguments(parser)
        cli = parser.parse_args(["--draft-model", "/models/draft", "--num-draft-tokens", "12"])
        ns = merged_mlx_namespace(config_path=None, serve_parser=parser, cli=cli)
        assert ns.draft_model == "/models/draft"
        assert ns.num_draft_tokens == 12

    def test_yaml_draft_model(self, tmp_path: Path) -> None:
        import argparse

        import yaml

        from mlx_server.mlx_parser import add_mlx_server_arguments

        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump({"draft_model": "/yaml/draft", "mlx": {"num_draft_tokens": 8}}),
            encoding="utf-8",
        )
        parser = argparse.ArgumentParser()
        add_mlx_server_arguments(parser)
        cli = parser.parse_args([])
        ns = merged_mlx_namespace(config_path=cfg, serve_parser=parser, cli=cli)
        assert ns.draft_model == "/yaml/draft"
        assert ns.num_draft_tokens == 8

    def test_cli_overrides_yaml(self, tmp_path: Path) -> None:
        import argparse

        import yaml

        from mlx_server.mlx_parser import add_mlx_server_arguments

        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump({"draft_model": "/yaml/draft", "mlx": {"num_draft_tokens": 8}}),
            encoding="utf-8",
        )
        parser = argparse.ArgumentParser()
        add_mlx_server_arguments(parser)
        cli = parser.parse_args(["--num-draft-tokens", "20"])
        ns = merged_mlx_namespace(config_path=cfg, serve_parser=parser, cli=cli)
        assert ns.draft_model == "/yaml/draft"
        assert ns.num_draft_tokens == 20
