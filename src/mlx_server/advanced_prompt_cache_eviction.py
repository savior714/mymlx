"""AdvancedPromptCache의 메모리 압박·SSD 스왑·배치 eviction 로직 (믹스인)."""

import logging
import time

import mlx.core as mx

from mlx_server.cache_persistent import PersistentCacheLayer
from mlx_server.cache_index import KVPage

logger = logging.getLogger(__name__)


class AdvancedPromptCacheEvictionMixin:
    """`AdvancedPromptCache`용 eviction / 디스크 오프로드 메서드."""

    async def _swap_and_mark_async(self, page: KVPage):
        """async 스왑 완료 후 location을 DISK로 마킹. 실패 시 VRAM으로 롤백."""
        try:
            await self.persistent_layer.swap_out_async(page.page_id, page.kv_tensor)
            page.location = "DISK"
            page.kv_tensor = None
        except Exception as e:
            logger.error(f"❌ Async swap failed for {page.page_id[:8]}: {e}")
            page.location = "VRAM"

    def _swap_sync(self, page: KVPage, kv_dict: dict):
        """sync 스왑 후 location을 DISK로 마킹. 실패 시 VRAM으로 롤백."""
        try:
            with self._metal_lock:
                self.persistent_layer._write_to_ssd(
                    self.persistent_layer.cache_dir / f"{page.page_id}.safetensors",
                    kv_dict
                )
            page.location = "DISK"
            page.kv_tensor = None
        except Exception as e:
            logger.error(f"❌ Sync swap failed for {page.page_id[:8]}: {e}")
            page.location = "VRAM"

    def _dynamic_lazy_threshold(self) -> float:
        """Scale idle threshold down as memory pressure increases."""
        ratio = self.pressure_manager.get_usage_ratio()
        pm = self.pressure_manager
        span = pm.soft_limit_ratio - pm.headroom_ratio
        if span <= 0:
            return getattr(self, "_LAZY_SWAP_MIN", 3.0)
        t = max(0.0, min(1.0, (ratio - pm.headroom_ratio) / span))
        base = getattr(self, "_LAZY_SWAP_BASE", 30.0)
        min_val = getattr(self, "_LAZY_SWAP_MIN", 3.0)
        return base * (1 - t) + min_val * t

    def _should_persist_to_ssd(self, page: KVPage) -> bool:
        """True if the block has been reused enough to warrant SSD persistence."""
        return page.reuse_count >= getattr(self, "_SSD_WRITE_THRESHOLD", 2)

    def _evict_to_ssd(self, page: KVPage) -> None:
        """Serialize and write a block to SSD (WARNING path — sync only)."""
        if not self._inference_event.is_set():
            logger.debug(f"🛑 Eviction aborted (inference active) for {page.page_id[:8]}")
            return

        kv_state = page.kv_tensor
        kv_dict = PersistentCacheLayer._serialize_kv_state(kv_state)
        if not kv_dict:
            logger.debug(f"🛑 Eviction skipped (empty KV) for {page.page_id[:8]}")
            return

        # Final check before GPU-touching write
        if not self._inference_event.is_set():
            logger.debug(f"🛑 Eviction aborted pre-write (inference active) for {page.page_id[:8]}")
            return

        page.location = "SWAPPING"
        self._swap_sync(page, kv_dict)

    def evacuate_if_needed(self):
        """Check memory pressure and batch-evict with hysteresis."""
        state = self.pressure_manager.get_current_state()
        if state == "HEALTHY":
            return

        target_ratio = self.pressure_manager.headroom_ratio
        logger.warning(
            f"⚠️ Memory Pressure Detected: {state} "
            f"(usage {self.pressure_manager.get_usage_ratio():.1%}, "
            f"target {target_ratio:.0%})"
        )

        with self.index.lock:
            candidates = self.index.get_eviction_candidates()

        evicted = 0
        self._update_dynamic_ssd_threshold()
        
        for page in candidates:
            if self.pressure_manager.get_usage_ratio() <= target_ratio:
                break

            if page.location != "VRAM" or page.priority == 0:
                continue

            now = time.time()

            if state == "WARNING":
                threshold = self._dynamic_lazy_threshold()
                idle_time = now - page.last_access
                if idle_time < threshold:
                    continue

                if page.kv_tensor:
                    block_age = now - page.last_access
                    if page.reuse_count == 0 and block_age < getattr(self, "cache_grace_seconds", 15.0):
                        self._record_event("purged_recently")
                        continue
                    
                    other_inference = not self._inference_event.is_set()
                    if self._should_persist_to_ssd(page) and not other_inference:
                        logger.info(f"📦 Evicting {page.page_id[:8]} (P{page.priority}) -> SSD")
                        try:
                            self._evict_to_ssd(page)
                            self._record_event("evicted_to_disk")
                        except Exception as e:
                            logger.error(f"❌ Swap failed for {page.page_id[:8]}: {e}")
                            page.location = "VRAM"
                    else:
                        if other_inference:
                            self._record_event("eviction_under_inference")
                            continue
                        page.location = "PURGED"
                        page.kv_tensor = None
                        self._record_event("purged_cold")
                    evicted += 1

            elif state == "CRITICAL":
                if page.kv_tensor:
                    gpu_safe = self._inference_event.is_set() and not self._is_inference_active()
                    if gpu_safe and self._should_persist_to_ssd(page):
                        try:
                            with self._metal_lock:
                                kv_dict = PersistentCacheLayer._serialize_kv_state(page.kv_tensor)
                                if kv_dict:
                                    self.persistent_layer._write_to_ssd(
                                        self.persistent_layer.cache_dir / f"{page.page_id}.safetensors",
                                        kv_dict
                                    )
                                    page.location = "DISK"
                                    page.kv_tensor = None
                                    self._record_event("evicted_to_disk")
                                    logger.info(f"📦 CRITICAL Swap: {page.page_id[:8]} (P{page.priority}) -> SSD")
                                else:
                                    page.location = "PURGED"
                                    page.kv_tensor = None
                                    self._record_event("purged_critical")
                        except Exception as e:
                            page.location = "PURGED"
                            page.kv_tensor = None
                            self._record_event("purged_critical")
                            logger.warning(f"🔥 CRITICAL Purge (swap failed): {page.page_id[:8]} — {e}")
                    else:
                        page.location = "PURGED"
                        page.kv_tensor = None
                        self._record_event("purged_critical")
                evicted += 1

        if evicted:
            logger.info(
                f"🧹 Batch eviction: freed {evicted} block(s), "
                f"usage {self.pressure_manager.get_usage_ratio():.1%}"
            )

        if state == "CRITICAL":
            with self._metal_lock:
                mx.clear_cache()

        self._cleanup_purged_metadata()

    def _cleanup_purged_metadata(self, max_age: float = 300.0):
        """300초 이상 PURGED 상태인 메타데이터 제거."""
        now = time.time()
        with self.index.lock:
            to_remove_ids = [
                pid for pid, p in self.index.pages.items()
                if p.location == "PURGED" and now - p.last_access > max_age
            ]
            for pid in to_remove_ids:
                del self.index.pages[pid]
        if to_remove_ids:
            logger.info(f"🧹 Purged metadata GC: removed {len(to_remove_ids)} stale entries")
