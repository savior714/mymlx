"""Argument parser aligned with `mlx_lm.server` (mlx-lm 0.31.x)."""

from __future__ import annotations

import argparse
import json

from mlx_lm.utils import _parse_size


def add_mlx_server_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        type=str,
        help="The path to the MLX model weights, tokenizer, and config",
    )
    parser.add_argument(
        "--adapter-path",
        type=str,
        help="Optional path for the trained adapter weights and config.",
    )
    parser.add_argument(
        "--allowed-origins",
        type=lambda x: x.split(","),
        default="*",
        help="Allowed origins (default: *)",
    )
    parser.add_argument(
        "--draft-model",
        type=str,
        help="A model to be used for speculative decoding.",
        default=None,
    )
    parser.add_argument(
        "--num-draft-tokens",
        type=int,
        help="Number of tokens to draft when using speculative decoding.",
        default=3,
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Enable trusting remote code for tokenizer",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--chat-template",
        type=str,
        default="",
        help="Specify a chat template for the tokenizer",
        required=False,
    )
    parser.add_argument(
        "--use-default-chat-template",
        action="store_true",
        help="Use the default chat template",
    )
    parser.add_argument(
        "--temp",
        type=float,
        default=0.0,
        help="Default sampling temperature (default: 0.0)",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=1.0,
        help="Default nucleus sampling top-p (default: 1.0)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Default top-k sampling (default: 0, disables top-k)",
    )
    parser.add_argument(
        "--min-p",
        type=float,
        default=0.0,
        help="Default min-p sampling (default: 0.0, disables min-p)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="Default maximum number of tokens to generate (default: 512)",
    )
    parser.add_argument(
        "--chat-template-args",
        type=json.loads,
        help=(
            "A JSON formatted string of arguments for the tokenizer's "
            "apply_chat_template, e.g. '{\"enable_thinking\":false}'"
        ),
        default="{}",
    )
    parser.add_argument(
        "--decode-concurrency",
        type=int,
        default=32,
        help="When a request is batchable then decode that many requests in parallel",
    )
    parser.add_argument(
        "--prompt-concurrency",
        type=int,
        default=8,
        help="When a request is batchable then process that many prompts in parallel",
    )
    parser.add_argument(
        "--prefill-step-size",
        type=int,
        default=2048,
        help="Step size for prefill processing (default: 2048)",
    )
    parser.add_argument(
        "--prompt-cache-size",
        type=int,
        default=10,
        help="Maximum number of distinct KV caches to hold in the prompt cache",
    )
    parser.add_argument(
        "--prompt-cache-bytes",
        type=_parse_size,
        metavar="SIZE",
        help=(
            "Upper bound on total KV-cache memory for the LRU prompt cache. "
            "Give a number with a unit: 24GB, 512MB, 16KB. "
            "If you write only digits, they count as bytes (24 = 24 bytes, not 24 GB). "
            "Leave unset for no byte cap (only --prompt-cache-size applies)."
        ),
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Use pipelining instead of tensor parallelism",
    )
    parser.add_argument(
        "--metal-memory-limit",
        type=_parse_size,
        metavar="SIZE",
        help=(
            "Metal wired (working-set) memory ceiling for MLX on Apple Silicon. "
            "Examples: 96GB, 100GB. "
            "Digits without a suffix are bytes, not gigabytes (96 alone is 96 bytes). "
            "If you omit this flag, the device-recommended wired limit is used."
        ),
    )
    parser.add_argument(
        "--metal-cache-limit",
        type=_parse_size,
        metavar="SIZE",
        help=(
            "Cap for Metal’s cache pool so large allocations can evict cache and free GPU memory. "
            "Examples: 8GB, 16GB. "
            "Digits without a suffix are bytes, not gigabytes. "
            "Omit this flag to keep MLX default cache behavior."
        ),
    )
    parser.add_argument(
        "--advanced-cache",
        action="store_true",
        default=True,
        help="Enable advanced content-based hashing and logical paging for KV cache",
    )
    parser.add_argument(
        "--no-advanced-cache",
        action="store_false",
        dest="advanced_cache",
        help="Disable advanced cache management",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=128,
        help="Page size for virtualized block management (default: 128)",
    )
    parser.add_argument(
        "--disk-cache-limit",
        type=_parse_size,
        metavar="SIZE",
        default=None,
        help=(
            "Maximum total disk space for the KV cache swap directory. "
            "Give a number with a unit: 50GB, 20GB, 100GB. "
            "Digits without a suffix are bytes. "
            "Defaults to 50 GB if not specified. "
            "On startup and after each write, old files are removed LRU-first to stay under the limit."
        ),
    )
    parser.add_argument(
        "--kv-bits",
        type=int,
        default=None,
        choices=[4, 8],
        help=(
            "Number of bits for KV cache quantization (4 or 8). "
            "Reduces VRAM usage by 2-4x with minimal quality loss. "
            "Omit to keep full-precision KV cache."
        ),
    )
    parser.add_argument(
        "--kv-group-size",
        type=int,
        default=64,
        help="Group size for KV cache quantization (default: 64).",
    )
    parser.add_argument(
        "--cache-grace-seconds",
        type=float,
        default=15.0,
        help=(
            "Minimum age in seconds before a cold block (hits=0) can be purged. "
            "Helps reduce immediate re-computation after eviction."
        ),
    )
    parser.add_argument(
        "--prompt-normalization",
        action="store_true",
        default=False,
        help=(
            "Enable prompt normalization (whitespace/newline cleanup) before proxying "
            "to improve cache key stability."
        ),
    )
    parser.add_argument(
        "--cache-observability",
        action="store_true",
        default=False,
        help="Enable detailed cache observability logs and counters.",
    )
    parser.add_argument(
        "--cache-headroom-ratio",
        type=float,
        default=0.80,
        help=(
            "Target memory usage ratio after eviction. "
            "For example 0.80 means keep usage under 80%% when pressure occurs."
        ),
    )
    parser.add_argument(
        "--audit-log-path",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Append-only JSONL for inference audit (effective params, no prompt text). "
            "See docs/specs/inference_audit_log.md."
        ),
    )
    parser.add_argument(
        "--audit-snapshot-path",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Overwrite each request: last inference metadata for crash post-mortem. "
            "Default: next to --audit-log-path as {stem}_last_request.json when set."
        ),
    )
