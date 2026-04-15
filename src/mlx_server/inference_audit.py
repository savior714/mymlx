"""Structured inference audit (JSONL + optional last-request snapshot)."""

from __future__ import annotations

import json
import threading
import uuid
from argparse import Namespace
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from starlette.requests import Request

SCHEMA_V1 = "mlx_server.inference_audit.v1"


def resolve_request_id(request: Request) -> str:
    for key in ("x-request-id", "x-correlation-id", "x-trace-id"):
        raw = request.headers.get(key)
        if raw and raw.strip():
            return raw.strip()
    return str(uuid.uuid4())


def resolve_snapshot_path(audit_log_path: str | None, explicit_snapshot: str | None) -> Path | None:
    if explicit_snapshot:
        return Path(explicit_snapshot)
    if audit_log_path:
        p = Path(audit_log_path)
        return p.parent / f"{p.stem}_last_request.json"
    return None


def prompt_stats_for_body(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Aggregate sizes only; no prompt text."""
    if path in ("/v1/chat/completions", "/chat/completions"):
        messages = body.get("messages")
        if not isinstance(messages, list):
            return {"message_count": 0, "prompt_chars": 0}
        total = 0
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                total += len(content)
            elif isinstance(content, list):
                for fragment in content:
                    if isinstance(fragment, dict) and fragment.get("type") == "text":
                        total += len(str(fragment.get("text", "")))
        return {"message_count": len(messages), "prompt_chars": total}
    if path == "/v1/completions":
        prompt = body.get("prompt")
        if isinstance(prompt, str):
            return {"message_count": 1, "prompt_chars": len(prompt)}
        if isinstance(prompt, list):
            joined = len("".join(str(x) for x in prompt))
            return {"message_count": len(prompt), "prompt_chars": joined}
        return {"message_count": 0, "prompt_chars": 0}
    return {"message_count": 0, "prompt_chars": 0}


def effective_inference_params(body: dict[str, Any], mlx_args: Namespace) -> dict[str, Any]:
    """Mirror mlx_lm.server APIHandler request parsing (subset used for tuning)."""
    stream = body.get("stream", False)
    num_draft_tokens = body.get("num_draft_tokens", mlx_args.num_draft_tokens)
    max_tokens = body.get("max_completion_tokens", None)
    if max_tokens is None:
        max_tokens = body.get("max_tokens", mlx_args.max_tokens)
    temperature = body.get("temperature", mlx_args.temp)
    top_p = body.get("top_p", mlx_args.top_p)
    top_k = body.get("top_k", mlx_args.top_k)
    min_p = body.get("min_p", mlx_args.min_p)
    repetition_penalty = body.get("repetition_penalty", 0.0)
    repetition_context_size = body.get("repetition_context_size", 20)
    presence_penalty = body.get("presence_penalty", 0.0)
    presence_context_size = body.get("presence_context_size", 20)
    frequency_penalty = body.get("frequency_penalty", 0.0)
    frequency_context_size = body.get("frequency_context_size", 20)
    seed = body.get("seed", None)
    return {
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "min_p": min_p,
        "num_draft_tokens": num_draft_tokens,
        "repetition_penalty": repetition_penalty,
        "repetition_context_size": repetition_context_size,
        "presence_penalty": presence_penalty,
        "presence_context_size": presence_context_size,
        "frequency_penalty": frequency_penalty,
        "frequency_context_size": frequency_context_size,
        "seed": seed,
    }


def server_runtime_snapshot(mlx_args: Namespace) -> dict[str, Any]:
    return {
        "decode_concurrency": getattr(mlx_args, "decode_concurrency", None),
        "prompt_concurrency": getattr(mlx_args, "prompt_concurrency", None),
        "prefill_step_size": getattr(mlx_args, "prefill_step_size", None),
        "prompt_cache_size": getattr(mlx_args, "prompt_cache_size", None),
        "kv_bits": getattr(mlx_args, "kv_bits", None),
        "kv_group_size": getattr(mlx_args, "kv_group_size", None),
        "metal_memory_limit": getattr(mlx_args, "metal_memory_limit", None),
        "metal_cache_limit": getattr(mlx_args, "metal_cache_limit", None),
        "advanced_cache": getattr(mlx_args, "advanced_cache", None),
    }


@dataclass
class InferenceAuditTrail:
    """Append JSONL and/or overwrite crash snapshot per request."""

    audit_log_path: Path | None
    snapshot_path: Path | None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.audit_log_path is not None or self.snapshot_path is not None

    @classmethod
    def from_namespace(cls, mlx_args: Namespace) -> InferenceAuditTrail:
        log_raw = getattr(mlx_args, "audit_log_path", None)
        snap_raw = getattr(mlx_args, "audit_snapshot_path", None)
        log_path = Path(log_raw).expanduser() if log_raw else None
        snap_resolved = resolve_snapshot_path(log_raw, snap_raw)
        return cls(audit_log_path=log_path, snapshot_path=snap_resolved)

    def write_snapshot(
        self,
        *,
        request_id: str,
        path: str,
        model_resolved: str | None,
        effective: dict[str, Any],
        prompt_stats: dict[str, Any],
        server_runtime: dict[str, Any],
        priority: int | None,
    ) -> None:
        if self.snapshot_path is None:
            return
        payload = {
            "schema": SCHEMA_V1,
            "event": "inference_start",
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "request_id": request_id,
            "path": path,
            "model_resolved": model_resolved,
            "priority": priority,
            "effective": effective,
            "prompt_stats": prompt_stats,
            "server_runtime": server_runtime,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        path_obj = self.snapshot_path
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            path_obj.write_text(text + "\n", encoding="utf-8")

    def log_complete(
        self,
        *,
        request_id: str,
        path: str,
        model_resolved: str | None,
        upstream_status: int | None,
        outcome: str,
        effective: dict[str, Any],
        prompt_stats: dict[str, Any],
        server_runtime: dict[str, Any],
        priority: int | None,
    ) -> None:
        if self.audit_log_path is None:
            return
        record = {
            "schema": SCHEMA_V1,
            "event": "inference_complete",
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "request_id": request_id,
            "path": path,
            "model_resolved": model_resolved,
            "upstream_status": upstream_status,
            "outcome": outcome,
            "effective": effective,
            "prompt_stats": prompt_stats,
            "server_runtime": server_runtime,
            "priority": priority,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        dest = self.audit_log_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with dest.open("a", encoding="utf-8") as fh:
                fh.write(line)
