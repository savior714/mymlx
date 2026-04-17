"""Unit tests for malformed tool-call recovery helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_backend_with_stubs() -> types.ModuleType:
    cache_utils = types.ModuleType("mlx_server.cache_utils")
    cache_utils.AdvancedPromptCache = object
    cache_utils.SafeguardPromptCache = object
    cache_utils.set_priority = lambda *_args, **_kwargs: None

    memory_manager = types.ModuleType("mlx_server.memory_manager")
    memory_manager.initialize_metal_infrastructure = lambda _args: 0

    mlx_lm_server = types.ModuleType("mlx_lm.server")
    mlx_lm_server.APIHandler = object
    mlx_lm_server.ModelProvider = object
    mlx_lm_server.ResponseGenerator = object
    mlx_lm_server.ThreadingHTTPServer = object
    mlx_lm_server.get_system_fingerprint = lambda: "fp"
    mlx_lm_server.stream_generate = lambda *args, **kwargs: iter(())
    mlx_lm_pkg = types.ModuleType("mlx_lm")
    mlx_lm_pkg.server = mlx_lm_server
    tool_parsers_pkg = types.ModuleType("mlx_lm.tool_parsers")

    fake_gemma4 = types.ModuleType("mlx_lm.tool_parsers.gemma4")
    fake_gemma4._gemma4_args_to_json = (
        lambda arg_str: (
            '{"thought":"ok","thoughtNumber":2,'
            '"totalThoughts":12,"nextThoughtNeeded":true,"needsMoreThoughts":false}'
        )
    )

    sys.modules["mlx_server.cache_utils"] = cache_utils
    sys.modules["mlx_server.memory_manager"] = memory_manager
    sys.modules["mlx_lm"] = mlx_lm_pkg
    sys.modules["mlx_lm.server"] = mlx_lm_server
    sys.modules["mlx_lm.tool_parsers"] = tool_parsers_pkg
    sys.modules["mlx_lm.tool_parsers.gemma4"] = fake_gemma4

    backend_path = Path(__file__).resolve().parents[1] / "src/mlx_server/backend.py"
    spec = importlib.util.spec_from_file_location("backend_under_test", backend_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_hyphenated_tool_call_normalizes_malformed_tokens() -> None:
    backend = _load_backend_with_stubs()
    parsed = backend._parse_hyphenated_tool_call(
        'call:mcp--sequentialthinking--sequentialthinking'
        '{thought<|"|>ok<|"|>,thoughtNumber:2,totalThoughts:12,nextThoughtNeeded:true,needsMoreThoughts:false}'
    )

    assert parsed is not None
    assert parsed["name"] == "mcp--sequentialthinking--sequentialthinking"
    assert parsed["arguments"]["nextThoughtNeeded"] is True
    assert "needsMoreThoughts" not in parsed["arguments"]


def test_parse_hyphenated_tool_call_recovers_angle_quoted_strings() -> None:
    backend = _load_backend_with_stubs()
    # Force fallback path (gemma4 converter may succeed for other cases).
    sys.modules["mlx_lm.tool_parsers.gemma4"]._gemma4_args_to_json = lambda _s: "{"  # type: ignore[attr-defined]
    parsed = backend._parse_hyphenated_tool_call(
        "call:mcp--serena--read_file{relative_path:<|\"|>frontend/package.json<|\"|>}"
    )

    assert parsed is not None
    assert parsed["name"] == "mcp--serena--read_file"
    assert parsed["arguments"]["relative_path"] == "frontend/package.json"
