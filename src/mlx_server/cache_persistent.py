"""PersistentCacheLayer — KV 캐시 SSD 오프로드 및 디스크 GC 관리."""

import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List, Optional

import mlx.core as mx

logger = logging.getLogger(__name__)


class PersistentCacheLayer:
    """Handles offloading cache blocks to SSD and loading them via mmap.

    Disk GC 정책
    -----------
    - ``max_disk_bytes`` 한도 초과 시 mtime 기준 가장 오래된 .safetensors 파일부터 삭제(LRU).
    - 서버 시작 시 1회 GC 실행 → 이전 실행에서 누적된 파일 정리.
    - ``_write_to_ssd()`` 성공 직후 GC 실행 → 실시간 한도 유지.
    """

    _DEFAULT_DISK_LIMIT = 50 * 1024 ** 3  # 50 GB

    def __init__(self, cache_dir: str = ".cache/mlx_server/kv", max_disk_bytes: int = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_disk_bytes: int = (
            max_disk_bytes if max_disk_bytes is not None else self._DEFAULT_DISK_LIMIT
        )
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.last_write_time: dict[str, float] = {}
        self.write_cooldown = 1.0  # 동일 블록에 대한 스왑 쿨다운 (초)
        logger.info(
            "Persistent Cache Layer initialized at %s (disk limit: %.1f GB)",
            self.cache_dir.absolute(),
            self.max_disk_bytes / 1024 ** 3,
        )
        # 서버 시작 시 1회 GC — 이전 실행에서 누적된 파일 정리
        self._enforce_disk_limit()

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_kv_state(kv_state: Any) -> dict:
        """KV 캐시 상태를 safetensors 저장용 dict로 직렬화.

        layer is None 이거나 KVCache.keys is None인 레이어를 건너뛰므로,
        인덱스가 비연속적(non-contiguous)일 수 있다.
        swap_in 시 반드시 _deserialize_kv_state로 복원해야 한다.
        """
        kv_dict = {}
        for i, layer in enumerate(kv_state):
            if layer is None:
                continue
            # Handle both KVCache objects (with keys/values attr) and legacy tuples
            if hasattr(layer, "keys") and hasattr(layer, "values"):
                if layer.keys is None:
                    continue  # 초기화되지 않은 빈 KVCache 레이어 skip
                kv_dict[f"layer_{i}_k"] = layer.keys
                kv_dict[f"layer_{i}_v"] = layer.values
            elif isinstance(layer, (list, tuple)) and len(layer) >= 2:
                if layer[0] is None:
                    continue
                kv_dict[f"layer_{i}_k"] = layer[0]
                kv_dict[f"layer_{i}_v"] = layer[1]
        return kv_dict

    @staticmethod
    def _deserialize_kv_state(kv_dict: dict) -> List[tuple]:
        """safetensors dict에서 KV 캐시 리스트를 복원.

        비연속 인덱스(gaps)를 올바르게 처리한다.
        예: layer_2_k, layer_5_k 만 있으면 → [None, None, (k2,v2), None, None, (k5,v5)]
        """
        layer_indices: set[int] = set()
        for key in kv_dict:
            m = re.match(r"layer_(\d+)_[kv]", key)
            if m:
                layer_indices.add(int(m.group(1)))

        if not layer_indices:
            return []

        max_idx = max(layer_indices)
        kv_state: list = [None] * (max_idx + 1)
        for i in sorted(layer_indices):
            k_key = f"layer_{i}_k"
            v_key = f"layer_{i}_v"
            if k_key in kv_dict and v_key in kv_dict:
                kv_state[i] = (kv_dict[k_key], kv_dict[v_key])
            else:
                logger.warning("⚠️ Incomplete layer %d in swap file (missing k or v)", i)
        return kv_state

    # ------------------------------------------------------------------
    # Disk GC
    # ------------------------------------------------------------------

    def _enforce_disk_limit(self) -> None:
        """디스크 사용량이 한도를 초과하면 mtime 기준 가장 오래된 파일부터 삭제(LRU)."""
        try:
            files = sorted(
                self.cache_dir.glob("*.safetensors"),
                key=lambda f: f.stat().st_mtime,
            )
            total = sum(f.stat().st_size for f in files)
            while total > self.max_disk_bytes and files:
                victim = files.pop(0)
                victim_size = victim.stat().st_size
                victim.unlink()
                total -= victim_size
                logger.info(
                    "🗑️ Disk GC: Removed %s (%.1f MB)", victim.name, victim_size / 1024 ** 2
                )
        except OSError as e:
            logger.warning("⚠️ Disk GC error: %s", e)

    def get_disk_stats(self) -> dict:
        """현재 디스크 캐시 사용량 통계 반환."""
        try:
            files = list(self.cache_dir.glob("*.safetensors"))
            total_bytes = sum(f.stat().st_size for f in files)
            return {
                "ssd_files": len(files),
                "ssd_bytes": total_bytes,
                "ssd_gb": total_bytes / 1024 ** 3,
                "ssd_limit_gb": self.max_disk_bytes / 1024 ** 3,
                "ssd_usage_ratio": total_bytes / self.max_disk_bytes if self.max_disk_bytes else 0.0,
            }
        except OSError:
            return {
                "ssd_files": 0,
                "ssd_bytes": 0,
                "ssd_gb": 0.0,
                "ssd_limit_gb": self.max_disk_bytes / 1024 ** 3,
                "ssd_usage_ratio": 0.0,
            }

    # ------------------------------------------------------------------
    # Swap I/O
    # ------------------------------------------------------------------

    async def swap_out_async(self, block_hash: str, kv_state: Any) -> None:
        """Asynchronously save KV state to disk."""
        path = self.cache_dir / f"{block_hash}.safetensors"
        loop = asyncio.get_running_loop()

        kv_dict = self._serialize_kv_state(kv_state)
        if not kv_dict:
            logger.debug("🛑 Swap skipped (empty KV state) for %s", block_hash[:8])
            return

        # Ensure tensors are materialized before background write
        mx.eval(*kv_dict.values())

        # SSD protection: Check cooldown
        now = time.time()
        if block_hash in self.last_write_time:
            if now - self.last_write_time[block_hash] < self.write_cooldown:
                logger.debug("🛑 Swap skipped (cooldown active) for %s", block_hash[:8])
                return

        await loop.run_in_executor(self.executor, self._write_to_ssd, path, kv_dict)
        self.last_write_time[block_hash] = now

    def _write_to_ssd(self, path: Path, kv_dict: dict) -> None:
        try:
            if kv_dict:
                mx.save_safetensors(str(path), kv_dict)
                logger.debug("💾 Swapped out to %s", path.name)
                # 쓰기 성공 직후 GC — 한도 초과 시 가장 오래된 파일 삭제
                self._enforce_disk_limit()
        except Exception as e:
            logger.error("❌ Failed to swap out cache: %s", e)

    def swap_in(self, block_hash: str) -> Optional[List[tuple]]:
        """Load KV state from disk using mmap."""
        path = self.cache_dir / f"{block_hash}.safetensors"
        if not path.exists():
            logger.warning("⚠️ Swap file not found: %s", path.name)
            return None

        try:
            # mx.load uses mmap internally for .safetensors
            kv_dict = mx.load(str(path))

            # Reconstruct mlx-lm style cache (비연속 인덱스 안전 처리)
            kv_state = self._deserialize_kv_state(kv_dict)

            if not kv_state:
                logger.warning("⚠️ Empty KV state loaded from %s", path.name)
                return None

            non_null = len([x for x in kv_state if x])
            logger.debug("📂 Swapped in from %s (mmap, %d layers)", path.name, non_null)
            return kv_state
        except Exception as e:
            logger.error("❌ Failed to swap in cache: %s", e)
            # 손상된 파일 정리
            try:
                path.unlink(missing_ok=True)
                logger.info("🗑️ Removed corrupted swap file: %s", path.name)
            except OSError:
                pass
            return None

    def purge(self, block_hash: str) -> None:
        path = self.cache_dir / f"{block_hash}.safetensors"
        if path.exists():
            path.unlink()
