"""Embedded `mlx_lm.server` HTTP stack on a localhost port (for proxying)."""

from __future__ import annotations

import functools
import logging
import threading
from argparse import Namespace
from dataclasses import dataclass

from mlx_server.cache_utils import AdvancedPromptCache, SafeguardPromptCache, set_priority
from mlx_server.memory_manager import initialize_metal_infrastructure
import mlx_lm.server as _mlx_server_mod
from mlx_lm.server import (
    APIHandler,
    ModelProvider,
    ResponseGenerator,
    ThreadingHTTPServer,
    get_system_fingerprint,
)

logger = logging.getLogger(__name__)

# ... (PriorityAwareAPIHandler stays here as it's coupled with APIHandler) ...
class PriorityAwareAPIHandler(APIHandler):
    """
    Extends APIHandler to extract priority from headers and make it
    available to the cache manager via thread-local storage.
    """
    def handle(self):
        # Reset priority for this thread
        set_priority(None)
        super().handle()

    def parse_request(self) -> bool:
        if super().parse_request():
            # Extract priority from custom header
            p_header = self.headers.get("X-MLX-Priority")
            if p_header:
                try:
                    p_val = int(p_header)
                    set_priority(p_val)
                    logger.debug(f"Request priority set to {p_val}")
                except (ValueError, TypeError):
                    pass
            return True
        return False

@dataclass
class MlxBackend:
    """Holds the MLX generation stack and the internal HTTP server thread."""

    mlx_args: Namespace
    response_generator: ResponseGenerator
    prompt_cache: AdvancedPromptCache
    base_url: str
    _thread: threading.Thread
    _httpd: ThreadingHTTPServer

    @property
    def model_provider(self) -> ModelProvider:
        return self.response_generator.model_provider

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self.response_generator.stop_and_join()
        if hasattr(self.prompt_cache, "stop_maintenance"):
            self.prompt_cache.stop_maintenance()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)


def _run_httpd(
    host: str,
    port: int,
    response_generator: ResponseGenerator,
    ready: threading.Event,
    holder: list,
) -> None:
    import socket

    server_address = (host, port)
    infos = socket.getaddrinfo(
        *server_address, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )
    ThreadingHTTPServer.address_family, _, _, _, server_address = next(iter(infos))
    httpd = ThreadingHTTPServer(
        server_address,
        lambda *args, **kwargs: PriorityAwareAPIHandler(
            response_generator,
            system_fingerprint=get_system_fingerprint(),
            *args,
            **kwargs,
        ),
    )
    holder.append(httpd)
    actual_host, actual_port = httpd.server_address[:2]
    logger.info("MLX internal httpd bound to %s:%s", actual_host, actual_port)
    logger.info(
        "mlx_lm.server is not recommended for production as it only implements "
        "basic security checks."
    )
    ready.set()
    try:
        httpd.serve_forever()
    except Exception:
        logger.exception("MLX internal httpd stopped")
    finally:
        response_generator.stop_and_join()


def _patch_kv_quantization(kv_bits: int, kv_group_size: int = 64) -> None:
    """Inject kv_bits into mlx_lm.server's stream_generate calls.

    The upstream server module does not forward kv_bits to stream_generate,
    so we wrap the function at the module level before ResponseGenerator is
    created.
    """
    original = _mlx_server_mod.stream_generate

    @functools.wraps(original)
    def _wrapped(*args, **kwargs):
        kwargs.setdefault("kv_bits", kv_bits)
        kwargs.setdefault("kv_group_size", kv_group_size)
        return original(*args, **kwargs)

    _mlx_server_mod.stream_generate = _wrapped
    logger.info(
        "KV cache quantization enabled: kv_bits=%d, kv_group_size=%d",
        kv_bits,
        kv_group_size,
    )


def start_backend(mlx_args: Namespace) -> MlxBackend:
    """Wire Metal limits, build ModelProvider + ResponseGenerator, start internal httpd."""
    wired_limit = initialize_metal_infrastructure(mlx_args)

    kv_bits = getattr(mlx_args, "kv_bits", None)
    if kv_bits is not None:
        _patch_kv_quantization(kv_bits, getattr(mlx_args, "kv_group_size", 64))

    model_provider = ModelProvider(mlx_args)

    cache_kwargs = {"max_size": mlx_args.prompt_cache_size}
    if mlx_args.prompt_cache_bytes is not None:
        cache_kwargs["max_bytes"] = mlx_args.prompt_cache_bytes
        logger.info("Prompt cache limit: %.2f GB", mlx_args.prompt_cache_bytes / 1024**3)
    
    if getattr(mlx_args, "advanced_cache", True):
        # Extract model_id from path or identity
        m_path = getattr(mlx_args, "model", "default")
        model_id = m_path.split("/")[-1] if "/" in m_path else m_path
        
        prompt_cache = AdvancedPromptCache(
            page_size=mlx_args.page_size,
            max_memory_gb=wired_limit / 1024**3,
            disk_cache_limit=getattr(mlx_args, "disk_cache_limit", None),
            model_id=model_id,
            quantization=f"{getattr(mlx_args, 'kv_bits', 'none')}bit",
            cache_grace_seconds=getattr(mlx_args, "cache_grace_seconds", 15.0),
            cache_observability=getattr(mlx_args, "cache_observability", False),
            cache_headroom_ratio=getattr(mlx_args, "cache_headroom_ratio", 0.80),
            **cache_kwargs
        )
    else:
        prompt_cache = SafeguardPromptCache(**cache_kwargs)
        logger.info("Using standard SafeguardPromptCache (Advanced Cache disabled)")
    response_generator = ResponseGenerator(model_provider, prompt_cache)

    ready = threading.Event()
    holder: list = []
    host, port = "127.0.0.1", 0
    thread = threading.Thread(
        target=_run_httpd,
        args=(host, port, response_generator, ready, holder),
        name="mlx-internal-httpd",
        daemon=True,
    )
    thread.start()
    if not ready.wait(timeout=120):
        raise RuntimeError("MLX internal httpd failed to bind")

    httpd = holder[0]
    _, actual_port = httpd.server_address[:2]
    base_url = f"http://127.0.0.1:{actual_port}"

    return MlxBackend(
        mlx_args=mlx_args,
        response_generator=response_generator,
        prompt_cache=prompt_cache,
        base_url=base_url,
        _thread=thread,
        _httpd=httpd,
    )
