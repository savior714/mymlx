"""Unit tests for inference audit helpers (no MLX)."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from mlx_server.inference_audit import (
    InferenceAuditTrail,
    effective_inference_params,
    prompt_stats_for_body,
    resolve_snapshot_path,
)


def test_effective_inference_params_merges_like_server() -> None:
    ns = Namespace(
        num_draft_tokens=3,
        max_tokens=512,
        temp=0.0,
        top_p=1.0,
        top_k=0,
        min_p=0.0,
    )
    body = {"max_tokens": 128, "temperature": 0.7}
    eff = effective_inference_params(body, ns)
    assert eff["max_tokens"] == 128
    assert eff["temperature"] == 0.7
    assert eff["top_p"] == 1.0


def test_effective_max_completion_tokens() -> None:
    ns = Namespace(
        num_draft_tokens=3,
        max_tokens=512,
        temp=0.0,
        top_p=1.0,
        top_k=0,
        min_p=0.0,
    )
    body = {"max_completion_tokens": 64}
    eff = effective_inference_params(body, ns)
    assert eff["max_tokens"] == 64


def test_prompt_stats_chat() -> None:
    body = {
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        ]
    }
    st = prompt_stats_for_body("/v1/chat/completions", body)
    assert st["message_count"] == 2
    assert st["prompt_chars"] == len("hello") + len("ok")


def test_prompt_stats_completions() -> None:
    body = {"prompt": "abc"}
    st = prompt_stats_for_body("/v1/completions", body)
    assert st["prompt_chars"] == 3


def test_resolve_snapshot_path_auto() -> None:
    p = resolve_snapshot_path("/tmp/logs/audit.jsonl", None)
    assert p is not None
    assert p.name == "audit_last_request.json"


def test_resolve_snapshot_explicit() -> None:
    p = resolve_snapshot_path("/tmp/a.jsonl", "/other/snap.json")
    assert str(p) == "/other/snap.json"


def test_audit_jsonl(tmp_path: Path) -> None:
    logf = tmp_path / "a.jsonl"
    trail = InferenceAuditTrail(audit_log_path=logf, snapshot_path=None)
    trail.log_complete(
        request_id="r1",
        path="/v1/chat/completions",
        model_resolved="/m",
        upstream_status=200,
        outcome="success",
        effective={"max_tokens": 1},
        prompt_stats={"message_count": 1, "prompt_chars": 2},
        server_runtime={"decode_concurrency": 32},
        priority=None,
    )
    line = logf.read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["schema"] == "mlx_server.inference_audit.v1"
    assert rec["outcome"] == "success"
    assert rec["request_id"] == "r1"


def test_audit_from_namespace_snapshot_only() -> None:
    d = _mlx_ns_min()
    d["audit_log_path"] = None
    d["audit_snapshot_path"] = "/tmp/x_last.json"
    t = InferenceAuditTrail.from_namespace(Namespace(**d))
    assert t.audit_log_path is None
    assert t.snapshot_path == Path("/tmp/x_last.json")


def _mlx_ns_min() -> dict:
    from mlx_server.config import _mlx_defaults

    return _mlx_defaults()


def test_audit_from_namespace_auto_snapshot() -> None:
    d = _mlx_ns_min()
    d["audit_log_path"] = str(Path("/tmp/logs/audit.jsonl"))
    d["audit_snapshot_path"] = None
    t = InferenceAuditTrail.from_namespace(Namespace(**d))
    assert t.snapshot_path is not None
    assert "last_request" in t.snapshot_path.name
