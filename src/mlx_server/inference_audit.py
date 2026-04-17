"""Structured inference audit (JSONL + optional last-request snapshot).

All disk I/O is offloaded to a single background writer thread so that
audit never blocks the inference hot-path.
"""

from __future__ import annotations

import atexit
import json
import logging
import queue
import threading
import uuid
from argparse import Namespace
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, TypedDict

from starlette.requests import Request


class TokenUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int


class TokenStats(TypedDict):
    avg_prompt_tokens: float
    avg_completion_tokens: float
    total_requests: int
    should_report: bool

SCHEMA_V1 = "mlx_server.inference_audit.v1"

logger = logging.getLogger(__name__)


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
    repetition_penalty = body.get("repetition_penalty", mlx_args.repetition_penalty)
    repetition_context_size = body.get(
        "repetition_context_size", mlx_args.repetition_context_size
    )
    presence_penalty = body.get("presence_penalty", mlx_args.presence_penalty)
    presence_context_size = body.get(
        "presence_context_size", mlx_args.presence_context_size
    )
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
        "draft_model": getattr(mlx_args, "draft_model", None),
        "num_draft_tokens": getattr(mlx_args, "num_draft_tokens", None),
    }


_SENTINEL = object()


class _AuditWriter:
    """Single background thread that drains a queue of write tasks."""

    def __init__(self) -> None:
        self._q: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._flush_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="audit-writer", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            task = self._q.get()
            if task is _SENTINEL:
                self._flush_event.set()
                break
            if task is self._flush_event:
                self._flush_event.set()
                continue
            try:
                task()
            except Exception:
                logger.debug("Audit write error", exc_info=True)

    def submit(self, fn: Any) -> None:
        self._q.put(fn)

    def flush(self, timeout: float = 5.0) -> None:
        """Block until all previously submitted tasks have been processed."""
        self._flush_event.clear()
        self._q.put(self._flush_event)
        self._flush_event.wait(timeout)

    def shutdown(self) -> None:
        self._q.put(_SENTINEL)
        self._thread.join(timeout=3.0)


_writer = _AuditWriter()
atexit.register(_writer.shutdown)


class TokenStatsTracker:
    """Thread-safe tracker for cumulative token usage."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_requests = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    def update(self, prompt: int | None, completion: int | None) -> TokenStats:
        with self._lock:
            self._total_requests += 1
            if prompt is not None:
                self._total_prompt_tokens += prompt
            if completion is not None:
                self._total_completion_tokens += completion

            avg_p = (
                self._total_prompt_tokens / self._total_requests
                if self._total_requests > 0
                else 0.0
            )
            avg_c = (
                self._total_completion_tokens / self._total_requests
                if self._total_requests > 0
                else 0.0
            )

            return {
                "avg_prompt_tokens": round(avg_p, 2),
                "avg_completion_tokens": round(avg_c, 2),
                "total_requests": self._total_requests,
            }

    def get_stats(self) -> TokenStats:
        with self._lock:
            avg_p = (
                self._total_prompt_tokens / self._total_requests
                if self._total_requests > 0
                else 0.0
            )
            avg_c = (
                self._total_completion_tokens / self._total_requests
                if self._total_requests > 0
                else 0.0
            )
            return {
                "avg_prompt_tokens": round(avg_p, 2),
                "avg_completion_tokens": round(avg_c, 2),
                "total_requests": self._total_requests,
            }


_stats_tracker = TokenStatsTracker()


def get_global_token_stats() -> TokenStats:
    """Return cumulative token usage averages."""
    return _stats_tracker.get_stats()


@dataclass
class InferenceAuditTrail:
    """Append JSONL and/or overwrite crash snapshot per request.

    All file I/O is submitted to a background writer thread so callers
    never block on disk.
    """

    audit_log_path: Path | None
    snapshot_path: Path | None
    _dirs_ensured: ClassVar[set[Path]] = set()

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

    def _ensure_parent(self, p: Path) -> None:
        parent = p.parent
        if parent not in self._dirs_ensured:
            parent.mkdir(parents=True, exist_ok=True)
            self._dirs_ensured.add(parent)

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
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        dest = self.snapshot_path
        self._ensure_parent(dest)

        def _write():
            dest.write_text(text + "\n", encoding="utf-8")

        _writer.submit(_write)

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
        usage: TokenUsage | None = None,
    ) -> TokenStats | None:
        if self.audit_log_path is None:
            if usage:
                return _stats_tracker.update(usage.get("prompt_tokens"), usage.get("completion_tokens"))
            return None

        avg_stats = (
            _stats_tracker.update(usage.get("prompt_tokens"), usage.get("completion_tokens"))
            if usage
            else _stats_tracker.get_stats()
        )

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
            "usage": usage,
            "avg_usage": avg_stats,
            "server_runtime": server_runtime,
            "priority": priority,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        dest = self.audit_log_path
        self._ensure_parent(dest)

        def _append():
            with dest.open("a", encoding="utf-8") as fh:
                fh.write(line)

        _writer.submit(_append)
        return avg_stats

    @staticmethod
    def flush(timeout: float = 5.0) -> None:
        """Wait for all pending audit writes to complete (for testing)."""
        _writer.flush(timeout)
