"""Merge defaults, environment, YAML, and CLI for `serve`."""

from __future__ import annotations

import argparse
import json
import os
from argparse import Namespace
from pathlib import Path
from typing import Any

import yaml

from mlx_lm.utils import _parse_size

_ENV_PREFIX = "MLX_SERVER_"


def _mlx_defaults() -> dict[str, Any]:
    return {
        "model": None,
        "adapter_path": None,
        "local_models_root": "~/Desktop/models",
        "allowed_origins": ["*"],
        "draft_model": None,
        "num_draft_tokens": 3,
        "trust_remote_code": False,
        "log_level": "INFO",
        "chat_template": "",
        "use_default_chat_template": False,
        "temp": 0.0,
        "top_p": 1.0,
        "top_k": 0,
        "min_p": 0.0,
        "repetition_penalty": 0.0,
        "repetition_context_size": 20,
        "presence_penalty": 0.0,
        "presence_context_size": 20,
        "max_tokens": 512,
        "chat_template_args": {},
        "decode_concurrency": 32,
        "prompt_concurrency": 8,
        "prefill_step_size": 2048,
        "prompt_cache_size": 10,
        "prompt_cache_bytes": None,
        "advanced_cache": True,
        "page_size": 128,
        "pipeline": False,
        "metal_memory_limit": None,
        "metal_cache_limit": None,
        "disk_cache_limit": None,
        "kv_bits": None,
        "kv_group_size": 64,
        "cache_grace_seconds": 15.0,
        "prompt_normalization": False,
        "cache_observability": False,
        "cache_headroom_ratio": 0.80,
        "audit_log_path": None,
        "audit_snapshot_path": None,
        "tool_choice_default": "auto",
        "mcp_config_path": None,
        "host": "127.0.0.1",
        "port": 0,
    }


def _env_mlx_overrides() -> dict[str, Any]:
    o: dict[str, Any] = {}
    env = os.environ
    if v := env.get(f"{_ENV_PREFIX}MODEL"):
        o["model"] = v
    if v := env.get(f"{_ENV_PREFIX}ADAPTER_PATH"):
        o["adapter_path"] = v
    if v := env.get(f"{_ENV_PREFIX}LOCAL_MODELS_ROOT"):
        o["local_models_root"] = v
    if v := env.get(f"{_ENV_PREFIX}DRAFT_MODEL"):
        o["draft_model"] = v
    if v := env.get(f"{_ENV_PREFIX}ALLOWED_ORIGINS"):
        o["allowed_origins"] = v.split(",")
    if v := env.get(f"{_ENV_PREFIX}TRUST_REMOTE_CODE"):
        o["trust_remote_code"] = v.lower() in ("1", "true", "yes")
    if v := env.get(f"{_ENV_PREFIX}LOG_LEVEL"):
        o["log_level"] = v
    if v := env.get(f"{_ENV_PREFIX}CHAT_TEMPLATE"):
        o["chat_template"] = v
    if v := env.get(f"{_ENV_PREFIX}USE_DEFAULT_CHAT_TEMPLATE"):
        o["use_default_chat_template"] = v.lower() in ("1", "true", "yes")
    if v := env.get(f"{_ENV_PREFIX}TEMP"):
        o["temp"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}TOP_P"):
        o["top_p"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}TOP_K"):
        o["top_k"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}MIN_P"):
        o["min_p"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}REPETITION_PENALTY"):
        o["repetition_penalty"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}REPETITION_CONTEXT_SIZE"):
        o["repetition_context_size"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}PRESENCE_PENALTY"):
        o["presence_penalty"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}PRESENCE_CONTEXT_SIZE"):
        o["presence_context_size"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}MAX_TOKENS"):
        o["max_tokens"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}CHAT_TEMPLATE_ARGS"):
        o["chat_template_args"] = json.loads(v)
    if v := env.get(f"{_ENV_PREFIX}DECODE_CONCURRENCY"):
        o["decode_concurrency"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}PROMPT_CONCURRENCY"):
        o["prompt_concurrency"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}PREFILL_STEP_SIZE"):
        o["prefill_step_size"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}PROMPT_CACHE_SIZE"):
        o["prompt_cache_size"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}PROMPT_CACHE_BYTES"):
        o["prompt_cache_bytes"] = _parse_size(v)
    if v := env.get(f"{_ENV_PREFIX}ADVANCED_CACHE"):
        o["advanced_cache"] = v.lower() in ("1", "true", "yes")
    if v := env.get(f"{_ENV_PREFIX}PAGE_SIZE"):
        o["page_size"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}PIPELINE"):
        o["pipeline"] = v.lower() in ("1", "true", "yes")
    if v := env.get(f"{_ENV_PREFIX}NUM_DRAFT_TOKENS"):
        o["num_draft_tokens"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}METAL_MEMORY_LIMIT"):
        o["metal_memory_limit"] = _parse_size(v)
    if v := env.get(f"{_ENV_PREFIX}METAL_CACHE_LIMIT"):
        o["metal_cache_limit"] = _parse_size(v)
    if v := env.get(f"{_ENV_PREFIX}DISK_CACHE_LIMIT"):
        o["disk_cache_limit"] = _parse_size(v)
    if v := env.get(f"{_ENV_PREFIX}KV_BITS"):
        o["kv_bits"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}KV_GROUP_SIZE"):
        o["kv_group_size"] = int(v)
    if v := env.get(f"{_ENV_PREFIX}CACHE_GRACE_SECONDS"):
        o["cache_grace_seconds"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}PROMPT_NORMALIZATION"):
        o["prompt_normalization"] = v.lower() in ("1", "true", "yes")
    if v := env.get(f"{_ENV_PREFIX}CACHE_OBSERVABILITY"):
        o["cache_observability"] = v.lower() in ("1", "true", "yes")
    if v := env.get(f"{_ENV_PREFIX}CACHE_HEADROOM_RATIO"):
        o["cache_headroom_ratio"] = float(v)
    if v := env.get(f"{_ENV_PREFIX}AUDIT_LOG_PATH"):
        o["audit_log_path"] = v
    if v := env.get(f"{_ENV_PREFIX}AUDIT_SNAPSHOT_PATH"):
        o["audit_snapshot_path"] = v
    if v := env.get(f"{_ENV_PREFIX}TOOL_CHOICE_DEFAULT"):
        if v in ("auto", "none", "required"):
            o["tool_choice_default"] = v
    if v := env.get(f"{_ENV_PREFIX}MCP_CONFIG_PATH"):
        o["mcp_config_path"] = v
    return o


def _env_listen() -> tuple[str | None, int | None]:
    h = os.environ.get(f"{_ENV_PREFIX}LISTEN_HOST")
    p = os.environ.get(f"{_ENV_PREFIX}LISTEN_PORT")
    return h, int(p) if p is not None else None


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")
    return data


def _apply_yaml_mlx(d: dict[str, Any], config_path: Path) -> None:
    y = _load_yaml(config_path)
    mlx = y.get("mlx")
    if isinstance(mlx, dict):
        d.update(mlx)
    if "model" in y:
        d["model"] = y["model"]
    for k in ("adapter_path", "draft_model"):
        if k in y:
            d[k] = y[k]


def merged_mlx_namespace(
    *,
    config_path: Path | None,
    serve_parser: argparse.ArgumentParser,
    cli: Namespace,
) -> Namespace:
    """Precedence: defaults < env < yaml < CLI (only args that differ from parser defaults)."""
    d = _mlx_defaults()
    d.update(_env_mlx_overrides())
    if config_path is not None:
        _apply_yaml_mlx(d, config_path)

    empty = serve_parser.parse_args([])
    for k in _mlx_defaults():
        if getattr(cli, k, None) != getattr(empty, k, None):
            d[k] = getattr(cli, k)

    return Namespace(**d)


def resolve_listen(
    *,
    config_path: Path | None,
    cli_host: str | None,
    cli_port: int | None,
) -> tuple[str, int]:
    """Resolve listen host/port: default < env < yaml < explicit CLI (non-None)."""
    host, port = "127.0.0.1", 8080
    eh, ep = _env_listen()
    if eh is not None:
        host = eh
    if ep is not None:
        port = ep
    if config_path is not None:
        y = _load_yaml(config_path)
        listen = y.get("listen") or {}
        if "host" in listen:
            host = str(listen["host"])
        if "port" in listen:
            port = int(listen["port"])
    if cli_host is not None:
        host = cli_host
    if cli_port is not None:
        port = cli_port
    return host, port
