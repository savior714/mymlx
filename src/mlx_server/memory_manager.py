import logging
from typing import Any
import mlx.core as mx

logger = logging.getLogger(__name__)

class MemoryPressureManager:
    """Monitors Metal memory usage and defined pressure states.

    headroom_ratio keeps a gap between cache occupancy and the soft limit
    so that prompt-processing KV computation has room to run without
    triggering eviction mid-inference.
    """

    def __init__(
        self,
        soft_limit_ratio: float = 0.85,
        hard_limit_ratio: float = 0.95,
        headroom_ratio: float = 0.80,
    ):
        self.soft_limit_ratio = soft_limit_ratio
        self.hard_limit_ratio = hard_limit_ratio
        self.headroom_ratio = headroom_ratio
        self.total_limit = mx.device_info()["max_recommended_working_set_size"]

    def set_total_limit(self, limit_bytes: int):
        self.total_limit = limit_bytes

    def get_usage_ratio(self) -> float:
        return mx.get_active_memory() / self.total_limit

    def get_current_state(self) -> str:
        """Returns HEALTHY, WARNING (Soft), or CRITICAL (Hard)."""
        ratio = self.get_usage_ratio()
        if ratio >= self.hard_limit_ratio:
            return "CRITICAL"
        if ratio >= self.soft_limit_ratio:
            return "WARNING"
        return "HEALTHY"

    def needs_headroom(self) -> bool:
        """True when usage exceeds the proactive headroom target."""
        return self.get_usage_ratio() > self.headroom_ratio

    def get_stats(self) -> dict:
        active = mx.get_active_memory()
        return {
            "active_gb": active / (1024**3),
            "total_gb": self.total_limit / (1024**3),
            "ratio": active / self.total_limit,
            "headroom_ratio": self.headroom_ratio,
            "state": self.get_current_state(),
        }

def initialize_metal_infrastructure(mlx_args: Any) -> float:
    """Wire Metal limits and return the resolved wired limit in bytes."""
    if not mx.metal.is_available():
        return 0.0

    device_info = mx.device_info()
    logger.info(
        "Metal Device: %s (Memory: %.2f GB, Recommended Wired: %.2f GB, Max Buffer: %.2f GB)",
        device_info["device_name"],
        device_info["memory_size"] / 1024**3,
        device_info["max_recommended_working_set_size"] / 1024**3,
        device_info["max_buffer_length"] / 1024**3,
    )

    # Wired Limit
    if hasattr(mlx_args, "metal_memory_limit") and mlx_args.metal_memory_limit is not None:
        wired_limit = mlx_args.metal_memory_limit
        logger.info("Using custom Metal wired limit: %.2f GB", wired_limit / 1024**3)
    else:
        wired_limit = device_info["max_recommended_working_set_size"]
        logger.info("Using device's recommended Metal wired limit: %.2f GB", wired_limit / 1024**3)
    mx.set_wired_limit(wired_limit)

    # Cache Limit
    if hasattr(mlx_args, "metal_cache_limit") and mlx_args.metal_cache_limit is not None:
        logger.info("Using custom Metal cache limit: %.2f GB", mlx_args.metal_cache_limit / 1024**3)
        mx.set_cache_limit(mlx_args.metal_cache_limit)
    
    return float(wired_limit)
