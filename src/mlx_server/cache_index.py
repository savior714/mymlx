import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class CacheKey:
    """Environment-aware cache key for strict isolation (I4)."""
    model_id: str
    tokenizer_version: str
    quantization: str      # e.g. "4bit", "8bit", "none"
    prefix_chain_hash: str # Merkle root slash chain hash of tokens
    dtype: str = "float16"

@dataclass
class KVPage:
    """Atomic storage unit for KV cache with refcounting and scoring."""
    page_id: str
    tokens: List[int]
    kv_tensor: Any = None       # MLX Array or list of arrays
    
    # Metadata for I2, I5
    refcount: int = 1
    generation: int = 0
    location: str = "VRAM" # "VRAM", "DISK", "PURGED"
    
    # Scoring factors
    priority: int = 2
    last_access: float = field(default_factory=time.time)
    reuse_count: int = 0
    depth: int = 0

class CacheIndex:
    """Manages the indexing of prompt cache blocks using Environment-aware keys."""

    def __init__(self):
        # NOTE: CacheIndex methods may call each other while holding the lock.
        # Use a re-entrant lock to avoid self-deadlock (e.g., get_eviction_candidates -> get_vram_pages).
        self.lock = threading.RLock()
        # Key: CacheKey -> Value: List[KVPage]
        self.key_to_pages: Dict[CacheKey, List[KVPage]] = {}
        # page_id -> KVPage (Flat access for global management)
        self.pages: Dict[str, KVPage] = {}
        
        # Legacy mappings for compatibility during transition
        self.hash_to_tokens: dict[str, List[int]] = {}
        self.hit_counts: dict[str, int] = {}

    def register_block(
        self,
        key: CacheKey,
        pages: List[KVPage],
    ):
        with self.lock:
            self.key_to_pages[key] = pages
            for page in pages:
                self.pages[page.page_id] = page
            # Legacy sync
            self.hash_to_tokens[key.prefix_chain_hash] = [t for p in pages for t in p.tokens]

    def lookup(self, key: CacheKey) -> Optional[List[KVPage]]:
        with self.lock:
            pages = self.key_to_pages.get(key)
            if pages:
                for page in pages:
                    page.last_access = time.time()
                    page.reuse_count += 1
                return pages
            return None

    def get_vram_pages(self) -> List[KVPage]:
        with self.lock:
            return [p for p in self.pages.values() if p.location == "VRAM"]

    def get_eviction_candidates(self) -> List[KVPage]:
        """Returns VRAM pages sorted by eviction score (lower score = evict first)."""
        with self.lock:
            candidates = self.get_vram_pages()
            # Multi-factor scoring logic could be here or in manager
            return sorted(candidates, key=self._compute_score)

    def _compute_score(self, page: KVPage) -> float:
        # Simplistic implementation matching the spec
        now = time.time()
        base = page.priority * 100
        recency = 100 / (1 + (now - page.last_access)) # Simple decay
        reuse = page.reuse_count * 50
        depth = page.depth * 5
        return base + recency + reuse + depth

    def clear(self):
        with self.lock:
            self.key_to_pages.clear()
            self.pages.clear()
            self.hash_to_tokens.clear()
            self.hit_counts.clear()
