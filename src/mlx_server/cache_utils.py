import hashlib
import logging
import struct
import threading
from typing import Any, List, Optional

from mlx_lm.models.cache import LRUPromptCache, trim_prompt_cache, can_trim_prompt_cache, KVCache


logger = logging.getLogger(__name__)

def _tuples_to_kvcache(kv_tuples: list) -> list:
    """swap_in 결과 (k, v) 튜플 리스트를 KVCache 객체 리스트로 변환.

    _deserialize_kv_state 는 ``[(k, v) | None, ...]`` 형태의 리스트를 반환하는데,
    LRUPromptCache.insert_cache 내부는 ``c.nbytes`` 속성을 기대하므로
    각 항목을 KVCache 객체로 감싸서 반환한다.

    이미 ``nbytes`` 속성을 가진 객체(KVCache 등)는 변환 없이 그대로 반환한다.
    """
    result = []
    for item in kv_tuples:
        if item is None:
            result.append(KVCache())
            continue

        if hasattr(item, "nbytes"):
            result.append(item)
            continue

        kv = KVCache()
        kv.keys, kv.values = item
        kv.offset = item[0].shape[2]
        result.append(kv)
    return result

_priority_context = threading.local()


def set_priority(priority: int | None):
    _priority_context.priority = priority

def get_priority() -> int | None:
    return getattr(_priority_context, "priority", None)

class TokenHasher:
    """Utility to hash token sequences for cache indexing.

    Uses binary packing (struct) instead of str join for ~5x faster
    serialization, and prefers xxhash (XXH3) when available.
    """

    _has_xxhash = None

    @classmethod
    def _init_xxhash(cls):
        if cls._has_xxhash is None:
            try:
                import xxhash
                cls._xxhash = xxhash
                cls._has_xxhash = True
                logger.debug("Hardware-accelerated hashing enabled (XXH3)")
            except ImportError:
                cls._has_xxhash = False

    @classmethod
    def _pack_tokens(cls, tokens: List[int]) -> bytes:
        return struct.pack(f"<{len(tokens)}i", *tokens)

    @classmethod
    def hash_tokens(cls, tokens: List[int]) -> str:
        """Create a hash of a list of token IDs (XXH3 if available, else SHA-256)."""
        cls._init_xxhash()
        raw = cls._pack_tokens(tokens)
        if cls._has_xxhash:
            return cls._xxhash.xxh3_64_hexdigest(raw)
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def hash_tokens_at_indices(
        cls, tokens: List[int], indices: List[int],
    ) -> List[tuple[int, str]]:
        """Hash multiple token prefixes efficiently using binary packing.

        Each prefix is hashed independently (same result as hash_tokens) to
        keep insert/lookup consistent.  The binary pack is ~5x faster than
        str-join for the serialization step.

        Returns [(index, hex_digest), ...] including len(tokens) as the
        last entry.
        """
        cls._init_xxhash()
        result: list[tuple[int, str]] = []
        sorted_indices = sorted(set(indices) | {len(tokens)})

        full_packed = cls._pack_tokens(tokens)
        item_size = 4  # struct 'i' = 4 bytes

        if cls._has_xxhash:
            for idx in sorted_indices:
                digest = cls._xxhash.xxh3_64_hexdigest(full_packed[:idx * item_size])
                result.append((idx, digest))
        else:
            for idx in sorted_indices:
                digest = hashlib.sha256(full_packed[:idx * item_size]).hexdigest()
                result.append((idx, digest))

        return result

class SafeguardPromptCache(LRUPromptCache):
    """
    Prevents IndexError in mlx-lm 0.31.2 BatchGenerator by ensuring
    at least one token remains in 'rest' (not cached).
    """
    def fetch_nearest_cache(self, model: Any, tokens: List[int]) -> tuple[Optional[Any], List[int]]:
        cache, rest = super().fetch_nearest_cache(model, tokens)
        if cache is not None and not rest and tokens:
            # Bug prevention for mlx-lm 0.31.2: Ensure at least one token is in 'rest'
            # to avoid empty segments in BatchGenerator.
            if can_trim_prompt_cache(cache):
                trim_prompt_cache(cache, 1)
                logger.info("🛡️ Safeguard: Trimmed 1 cached token to avoid mlx-lm BatchGenerator crash")
                return cache, tokens[-1:]
        return cache, rest


# Re-exports (late imports avoid circular deps with advanced_prompt_cache).
from mlx_server.cache_index import CacheKey, KVPage  # noqa: E402, F401
from mlx_server.cache_persistent import PersistentCacheLayer  # noqa: E402, F401
from mlx_server.advanced_prompt_cache import AdvancedPromptCache  # noqa: E402, F401
from mlx_server.memory_manager import MemoryPressureManager  # noqa: E402, F401

