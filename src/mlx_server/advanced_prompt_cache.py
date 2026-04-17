"""LRU 2.0 AdvancedPromptCache — 우선순위·메모리 압박·비동기 디스크 스왑."""

import logging
import threading
import time
from collections import Counter
from typing import Any, List, Optional

import mlx.core as mx

from mlx_server.advanced_prompt_cache_eviction import AdvancedPromptCacheEvictionMixin
from mlx_server.cache_persistent import PersistentCacheLayer
from mlx_server.cache_utils import (
    SafeguardPromptCache,
    TokenHasher,
    get_priority,
    _tuples_to_kvcache,
)
from mlx_server.cache_index import CacheIndex, CacheKey, KVPage
from mlx_server.memory_manager import MemoryPressureManager

logger = logging.getLogger(__name__)


class AdvancedPromptCache(AdvancedPromptCacheEvictionMixin, SafeguardPromptCache):
    """
    LRU 2.0: Extends AdvancedPromptCache with Priority-based Hierarchy,
    Memory Pressure Awareness, and Async Disk Swap.
    """

    _MAINTENANCE_INTERVAL = 5.0  # background check interval (seconds)
    _LAZY_SWAP_BASE = 60.0       # base idle threshold for WARNING eviction
    _LAZY_SWAP_MIN = 3.0         # minimum idle threshold under high pressure

    _SSD_WRITE_THRESHOLD = 4  # minimum cache hits before persisting to SSD
    _SSD_WRITE_THRESHOLD_MIN = 1
    _SSD_WRITE_THRESHOLD_MAX = 4

    # Dynamic Cooldown Thresholds (Deep Research 기반)
    _VRAM_PRESSURE_THRESHOLD = 0.85
    _COOLDOWN_NORMAL = 60.0    # User reading/thinking time
    _COOLDOWN_PRESSURE = 5.0   # Aggressive reclamation under pressure

    def __init__(
        self,
        page_size: int = 128,
        max_memory_gb: float = None,
        disk_cache_limit: int = None,
        model_id: str = "default",
        tokenizer_version: str = "1.0",
        quantization: str = "none",
        *args,
        **kwargs,
    ):
        self.cache_grace_seconds = float(kwargs.pop("cache_grace_seconds", 15.0))
        self.cache_observability = bool(kwargs.pop("cache_observability", False))
        self.cache_headroom_ratio = float(kwargs.pop("cache_headroom_ratio", 0.80))
        super().__init__(*args, **kwargs)
        self.page_size = page_size
        
        # Environment context for I4 (Strictness)
        self.model_id = model_id
        self.tokenizer_version = tokenizer_version
        self.quantization = str(quantization)
        
        # Metadata and Indexing decoupled into CacheIndex
        self.index = CacheIndex()

        self.pressure_manager = MemoryPressureManager(headroom_ratio=self.cache_headroom_ratio)
        if max_memory_gb:
            self.pressure_manager.set_total_limit(int(max_memory_gb * 1024**3))

        persistent_kwargs = {}
        if disk_cache_limit is not None:
            persistent_kwargs["max_disk_bytes"] = disk_cache_limit
        self.persistent_layer = PersistentCacheLayer(**persistent_kwargs)
        
        # Legacy lock — still used for some coordination, though index has its own
        self._cache_lock = threading.Lock()

        self._last_inference_time: float = 0.0

        # Explicit inference-active tracking to prevent Metal encoder contention.
        # Event is SET when no inference is running (safe for background GPU work).
        self._inference_event = threading.Event()
        self._inference_event.set()
        self._active_inference_count = 0
        self._active_inference_lock = threading.Lock()

        # Global GPU Lock for all Metal-touching background/foreground coordination.
        # This prevents 'Completed handler provided after commit call' SIGABRTs
        # when background disk I/O (save_safetensors) collides with inference.
        self._metal_lock = threading.Lock()

        self._maintenance_stop = threading.Event()
        self._maintenance_thread = threading.Thread(
            target=self._background_maintenance,
            name="cache-maintenance",
            daemon=True,
        )
        self._maintenance_thread.start()
        self._stats_lock = threading.Lock()
        self._event_counters: Counter[str] = Counter()
        self._matched_token_total = 0
        self._match_events = 0
        self._last_miss_reason = "none"
        self._last_dynamic_threshold_update = time.time()
        logger.info(f"LRU 2.0 Cache Manager initialized (PageSize: {page_size})")

    # Compatibility properties for legacy tests and internal logic
    @property
    def block_metadata(self):
        return self.index.block_metadata

    @property
    def hash_to_tokens(self):
        return self.index.hash_to_tokens

    @property
    def vram_pool(self):
        return self.index.vram_pool

    @property
    def hit_counts(self):
        return self.index.hit_counts

    # ------------------------------------------------------------------
    # Background maintenance — proactive eviction during idle periods
    # ------------------------------------------------------------------

    def _mark_inference_start(self) -> None:
        with self._active_inference_lock:
            self._active_inference_count += 1
            self._inference_event.clear()
        self._last_inference_time = time.time()

    def _mark_inference_end(self) -> None:
        self._last_inference_time = time.time()
        with self._active_inference_lock:
            self._active_inference_count = max(0, self._active_inference_count - 1)
            if self._active_inference_count == 0:
                self._inference_event.set()

    def _get_current_cooldown(self) -> float:
        """Calculate dynamic cooldown based on current memory pressure."""
        ratio = self.pressure_manager.get_usage_ratio()
        if ratio >= self._VRAM_PRESSURE_THRESHOLD:
            return self._COOLDOWN_PRESSURE
        return self._COOLDOWN_NORMAL

    def _is_inference_active(self) -> bool:
        """True if inference is explicitly running OR was active recently."""
        if not self._inference_event.is_set():
            return True
        # Never observed inference → treat as idle without consulting pressure.
        # This avoids consuming get_usage_ratio() side effects in tests that
        # simulate pressure transitions for eviction loops.
        if self._last_inference_time <= 0:
            return False
        cooldown = self._get_current_cooldown()
        return (time.time() - self._last_inference_time) < cooldown

    def _background_maintenance(self):
        """Periodically check memory and evict proactively to maintain headroom."""
        while not self._maintenance_stop.wait(self._MAINTENANCE_INTERVAL):
            try:
                if self._is_inference_active():
                    continue
                if self.pressure_manager.needs_headroom():
                    self._proactive_evict()
            except Exception:
                logger.exception("Background maintenance error")

    def _proactive_evict(self):
        """Evict lowest-value blocks until usage drops below headroom target."""
        # Proactive eviction must be conservative: never touch GPU/SSD while inference is active.
        # Also, avoid repeatedly calling get_usage_ratio() via _is_inference_active() inside the loop;
        # tests may mock get_usage_ratio() with finite side effects.
        if not self._inference_event.is_set():
            return
        if self._last_inference_time > 0 and (time.time() - self._last_inference_time) < self._COOLDOWN_NORMAL:
            return

        target = self.pressure_manager.headroom_ratio
        evicted = 0
        
        # Get candidates sorted by value (prio, age)
        candidates = self.index.get_eviction_candidates()

        ratio = self.pressure_manager.get_usage_ratio()
        for page in candidates:
            if ratio <= target:
                break
            if not self._inference_event.is_set():
                logger.debug("Proactive eviction aborted: inference became active")
                break
            
            if page is None or page.location != "VRAM":
                continue
                
            kv_state = page.kv_tensor
            if not kv_state:
                continue

            # Re-check immediately before GPU-touching save_safetensors call
            if not self._inference_event.is_set():
                logger.debug("Proactive eviction aborted pre-write: inference became active")
                break

            try:
                kv_dict = PersistentCacheLayer._serialize_kv_state(kv_state)
                if kv_dict:
                    # Final guard: if inference started during serialization, put it back
                    if not self._inference_event.is_set():
                        logger.debug("Proactive eviction aborted pre-SSD: inference became active")
                        break
                    self.persistent_layer._write_to_ssd(
                        self.persistent_layer.cache_dir / f"{page.page_id}.safetensors",
                        kv_dict,
                    )
                    page.location = "DISK"
                    page.kv_tensor = None
                else:
                    page.location = "PURGED"
                    page.kv_tensor = None
                evicted += 1
                ratio = self.pressure_manager.get_usage_ratio()
            except Exception as e:
                logger.error(f"❌ Proactive swap failed for {page.page_id[:8]}: {e}")
                page.location = "VRAM"
                page.kv_tensor = kv_state

        if evicted:
            logger.info(
                f"🧹 Proactive eviction: swapped {evicted} block(s), "
                f"usage {self.pressure_manager.get_usage_ratio():.1%}"
            )

    def stop_maintenance(self):
        """Stop the background maintenance thread (for clean shutdown)."""
        self._maintenance_stop.set()
        self._maintenance_thread.join(timeout=3.0)
        self.persistent_layer.shutdown(wait=False, cancel_futures=True)

    def _get_block_indices(self, tokens: List[int]) -> List[int]:
        """Find structural boundaries for block creation (Anchors + Fixed Pages)."""
        indices = set()
        for i in range(self.page_size, len(tokens) + 1, self.page_size):
            indices.add(i)

        common_anchors = {
            151644, 151645, 151655, # Qwen
            128006, 128007, 128009, # Llama 3
            1, 2, 32000, 32001,
            198, 271, 628,
        }

        last_idx = 0
        min_gap = max(16, self.page_size // 4)
        for i, t in enumerate(tokens):
            if t in common_anchors:
                idx = i + 1
                if idx - last_idx >= min_gap:
                    indices.add(idx)
                    last_idx = idx
        return sorted(list(indices))

    def _record_event(self, event_name: str, amount: int = 1) -> None:
        with self._stats_lock:
            self._event_counters[event_name] += amount

    def _record_match(self, matched_tokens: int) -> None:
        with self._stats_lock:
            self._match_events += 1
            self._matched_token_total += matched_tokens

    def _set_last_miss_reason(self, reason: str) -> None:
        with self._stats_lock:
            self._last_miss_reason = reason

    def _update_dynamic_ssd_threshold(self) -> None:
        """Dynamically tune SSD threshold based on memory pressure."""
        now = time.time()
        if now - self._last_dynamic_threshold_update < 2.0:
            return
        self._last_dynamic_threshold_update = now

        ratio = self.pressure_manager.get_usage_ratio()
        new_threshold = self._SSD_WRITE_THRESHOLD
        if ratio >= self.pressure_manager.soft_limit_ratio:
            new_threshold = min(self._SSD_WRITE_THRESHOLD_MAX, self._SSD_WRITE_THRESHOLD + 1)
        elif ratio <= self.pressure_manager.headroom_ratio:
            new_threshold = max(self._SSD_WRITE_THRESHOLD_MIN, self._SSD_WRITE_THRESHOLD - 1)

        if new_threshold != self._SSD_WRITE_THRESHOLD:
            self._SSD_WRITE_THRESHOLD = new_threshold
            if self.cache_observability:
                logger.info("🔧 Dynamic SSD threshold: %d", self._SSD_WRITE_THRESHOLD)

    def insert_cache(self, model: Any, tokens: List[int], prompt_cache: List[Any], priority: int = None, **kwargs):
        """Insert cache with priority and trigger eviction if needed."""
        self._mark_inference_end()

        if priority is None:
            priority = get_priority()
        if priority is None:
            priority = 2

        self.evacuate_if_needed()
        self._update_dynamic_ssd_threshold()

        super().insert_cache(model, tokens, prompt_cache, **kwargs)

        if tokens:
            prefix_hash = TokenHasher.hash_tokens(tokens)
            key = self._make_cache_key(prefix_hash)
            
            # Wrap as KVPage (I5)
            import uuid
            page = KVPage(
                page_id=str(uuid.uuid4()),
                tokens=tokens,
                kv_tensor=prompt_cache,
                priority=priority,
                depth=kwargs.get("depth", 0)
            )
            self.index.register_block(key, [page])

    def warm_up(self, model: Any, token_hash: str):
        """Proactively load a cache from disk to VRAM/mmap."""
        meta = self.index.get_metadata(token_hash)
        if meta and meta["location"] == "DISK":
            with self.index.lock:
                tokens = self.index.hash_to_tokens.get(token_hash)
            if not tokens:
                return False
            logger.info(f"🔥 Warming up cache {token_hash[:8]}")
            kv_state = self.persistent_layer.swap_in(token_hash)
            if kv_state:
                kv_state = _tuples_to_kvcache(kv_state)
                super().insert_cache(model, tokens, kv_state)
                self.index.move_to_vram(token_hash, kv_state)
                return True
        return False

    def fetch_nearest_cache(self, model: Any, tokens: List[int]) -> tuple[Optional[Any], List[int]]:
        """Integrated block matching with LRU 2.0 metadata updates and Swap-in."""
        self._mark_inference_start()
        key, matched_len = self.find_best_blocks(tokens)

        if key:
            pages = self.index.lookup(key)
            if pages is None:
                self._record_event("metadata_missing")
                self._set_last_miss_reason("metadata_missing")
                return super().fetch_nearest_cache(model, tokens)

            # TODO: Handle multi-page recombination if needed
            page = pages[0]
            location = page.location

            if location == "DISK":
                self._record_event("disk_resurrection")
                logger.info(f"🔄 Cache Resurrect: Swapping in {key.prefix_chain_hash[:8]} from Disk (mmap)")
                cached_tokens = page.tokens
                if not cached_tokens:
                    logger.error(f"❌ Resurrection skipped: tokens missing for {key.prefix_chain_hash[:8]}")
                    return None, tokens
                
                with self._metal_lock:
                    kv_state = self.persistent_layer.swap_in(key.prefix_chain_hash)
                    if kv_state:
                        kv_state = _tuples_to_kvcache(kv_state)
                        # Materialize immediately under lock to ensure Metal consistency
                        mx.eval(*[k.keys for k in kv_state if k.keys is not None])
                        mx.eval(*[k.values for k in kv_state if k.values is not None])
                        
                    if kv_state:
                        super().insert_cache(model, cached_tokens, kv_state)
                        page.location = "VRAM"
                        page.kv_tensor = kv_state
                    else:
                        logger.error(f"❌ Resurrection failed for {key.prefix_chain_hash[:8]}")
                        return None, tokens

            res_cache, res_rest = super().fetch_nearest_cache(model, tokens[:matched_len])
            if res_cache is not None:
                full_rest = res_rest + tokens[matched_len:]
                actual_matched = len(tokens) - len(full_rest)
                if matched_len == len(tokens):
                    self._record_event("full_hash_hit")
                else:
                    self._record_event("paged_hash_hit")
                self._record_match(actual_matched)
                prio = getattr(page, "priority", "?")
                logger.info(
                    "💾 LRU 2.0 Hit: %d tokens (hash: %s, prio: %s)",
                    actual_matched,
                    key.prefix_chain_hash[:8],
                    prio,
                )
                return res_cache, full_rest

            self._record_event("fetch_hit_failed")
            self._set_last_miss_reason("fetch_hit_failed")
            return super().fetch_nearest_cache(model, tokens)

        self._record_event("paged_hash_miss")
        self._set_last_miss_reason("paged_hash_miss")
        return super().fetch_nearest_cache(model, tokens)

    def _make_cache_key(self, prefix_hash: str) -> CacheKey:
        return CacheKey(
            model_id=self.model_id,
            tokenizer_version=self.tokenizer_version,
            quantization=self.quantization,
            prefix_chain_hash=prefix_hash
        )

    def find_best_blocks(self, tokens: List[int]) -> tuple[Optional[CacheKey], int]:
        """Find the longest match using single-pass incremental hashing.

        Notes
        -----
        - 전체 시퀀스 해시는 `TokenHasher.hash_tokens()`를 우선 사용한다.
          (테스트/호환성 측면에서 full-hash 경로를 보장)
        - 그 다음 블록 인덱스 기반 해시(`hash_tokens_at_indices`)로 longest prefix를 탐색한다.
        """
        if not tokens:
            return None, 0

        # 1) Full sequence hash first (compat/test-friendly)
        full_digest = TokenHasher.hash_tokens(tokens)
        full_key = self._make_cache_key(full_digest)
        with self.index.lock:
            if full_key in self.index.key_to_pages:
                return full_key, len(tokens)

        # 2) Fallback: incremental prefix hashing at structural indices
        indices = self._get_block_indices(tokens)
        pairs = TokenHasher.hash_tokens_at_indices(tokens, indices)
        for idx, digest in reversed(pairs):
            key = self._make_cache_key(digest)
            with self.index.lock:
                if key in self.index.key_to_pages:
                    return key, idx
        return None, 0

    def get_cache_stats(self) -> dict[str, Any]:
        stats = super().get_cache_stats() if hasattr(super(), "get_cache_stats") else {}
        
        with self.index.lock:
            vram_pages = [p for p in self.index.pages.values() if p.location == "VRAM"]
            disk_pages = [p for p in self.index.pages.values() if p.location == "DISK"]
            purged_pages = [p for p in self.index.pages.values() if p.location == "PURGED"]
            
            total_hits = sum(p.reuse_count for p in self.index.pages.values())
            hot_blocks = sum(1 for p in self.index.pages.values() if p.reuse_count >= self._SSD_WRITE_THRESHOLD)

        with self._stats_lock:
            events = dict(self._event_counters)
            match_events = self._match_events
            matched_total = self._matched_token_total
            last_miss_reason = self._last_miss_reason

        full_hits = events.get("full_hash_hit", 0)
        paged_hits = events.get("paged_hash_hit", 0)
        misses = events.get("paged_hash_miss", 0)
        total_decisions = full_hits + paged_hits + misses
        avg_matched = (matched_total / match_events) if match_events else 0.0
        
        stats.update({
            "model_id": self.model_id,
            "quantization": self.quantization,
            "total_indexed_keys": len(self.index.key_to_pages),
            "vram_count": len(vram_pages),
            "disk_count": len(disk_pages),
            "purged_count": len(purged_pages),
            "total_cache_hits": total_hits,
            "hot_blocks": hot_blocks,
            "ssd_write_threshold": self._SSD_WRITE_THRESHOLD,
            "cache_grace_seconds": self.cache_grace_seconds,
            "cache_observability": self.cache_observability,
            "cache_headroom_ratio": self.cache_headroom_ratio,
            "full_hit_rate": (full_hits / total_decisions) if total_decisions else 0.0,
            "paged_hit_rate": (paged_hits / total_decisions) if total_decisions else 0.0,
            "avg_matched_tokens": avg_matched,
            "miss_reason_counts": {
                "full_hash_miss": events.get("full_hash_miss", 0),
                "paged_hash_miss": events.get("paged_hash_miss", 0),
                "metadata_missing": events.get("metadata_missing", 0),
                "fetch_hit_failed": events.get("fetch_hit_failed", 0),
                "purged_recently": events.get("purged_recently", 0),
            },
            "eviction_reason_counts": {
                "evicted_to_disk": events.get("evicted_to_disk", 0),
                "purged_cold": events.get("purged_cold", 0),
                "purged_critical": events.get("purged_critical", 0),
                "eviction_under_inference": events.get("eviction_under_inference", 0),
            },
            "last_miss_reason": last_miss_reason,
            "memory_pressure": self.pressure_manager.get_stats(),
            "disk_cache": self.persistent_layer.get_disk_stats(),
            "dynamic_cooldown": {
                "current_mode": "Pressure (5s)" if self.pressure_manager.get_usage_ratio() >= self._VRAM_PRESSURE_THRESHOLD else "Normal (60s)",
                "last_inference_time": self._last_inference_time,
                "idle_seconds": time.time() - self._last_inference_time if self._last_inference_time > 0 else 0,
            }
        })
        return stats

    def clear(self):
        super().clear()
        self.index.clear()
