"""CLI entry: `mlx-server serve`."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from mlx_server.app import build_app
from mlx_server.backend import start_backend
from mlx_server.config import merged_mlx_namespace, resolve_listen
from mlx_server.mlx_parser import add_mlx_server_arguments


def _build_serve_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        add_help=False,
        description="MLX HTTP server (mlx-lm + Starlette wrapper).",
    )
    p.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="YAML config (mlx block, optional listen block).",
    )
    p.add_argument(
        "--listen-host",
        type=str,
        default=None,
        help="Bind address for the public HTTP server (overrides env/yaml if set).",
    )
    p.add_argument(
        "--listen-port",
        type=int,
        default=None,
        help="Bind port for the public HTTP server (overrides env/yaml if set).",
    )
    add_mlx_server_arguments(p)
    return p


def main() -> None:
    root = argparse.ArgumentParser(prog="mlx-server")
    sub = root.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser(
        "serve",
        parents=[_build_serve_parser()],
        help="Run OpenAI-compatible API server (headless, proxied mlx_lm.server).",
    )

    args = root.parse_args()
    if args.command != "serve":
        raise SystemExit(2)

    mlx_ns = merged_mlx_namespace(
        config_path=args.config,
        serve_parser=serve_p,
        cli=args,
    )

    # 1. Resolve startup model if provided
    if mlx_ns.model:
        from mlx_server.model_resolver import resolve_model_path
        mlx_ns.model = resolve_model_path(mlx_ns.model, mlx_ns.local_models_root)

    host, port = resolve_listen(
        config_path=args.config,
        cli_host=args.listen_host,
        cli_port=args.listen_port,
    )

    logging.basicConfig(
        level=getattr(logging, mlx_ns.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # Suppress verbose token-by-token debug noise from upstream mlx_lm.server.
    # Keep at least INFO even when global log level is DEBUG.
    logging.getLogger("mlx_lm.server").setLevel(logging.INFO)
    # Reduce transport-level debug spam from HTTP client internals.
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)

    backend = start_backend(mlx_ns)
    app = build_app(backend)
    logging.info("MLX API server at http://%s:%s/ (Headless)", host, port)
    uvicorn.run(app, host=host, port=port, log_level=mlx_ns.log_level.lower())


if __name__ == "__main__":
    main()
