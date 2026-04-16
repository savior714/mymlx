import time
import unittest
from unittest.mock import MagicMock, patch
from mlx_server.advanced_prompt_cache import AdvancedPromptCache

class TestDynamicCooldown(unittest.TestCase):
    def setUp(self):
        self.mx_patcher = patch("mlx.core.get_active_memory", return_value=10 * 1024**3)
        self.mx_patcher.start()
        self.device_patcher = patch("mlx.core.device_info", return_value={"max_recommended_working_set_size": 100 * 1024**3})
        self.device_patcher.start()

    def tearDown(self):
        self.mx_patcher.stop()
        self.device_patcher.stop()

    def test_dynamic_cooldown_modes(self):
        cache = AdvancedPromptCache(max_memory_gb=100)
        
        # 1. Normal Mode (Usage < 85%)
        cache.pressure_manager.get_usage_ratio = MagicMock(return_value=0.50)
        self.assertEqual(cache._get_current_cooldown(), 60.0)
        
        # 2. Pressure Mode (Usage >= 85%)
        cache.pressure_manager.get_usage_ratio = MagicMock(return_value=0.90)
        self.assertEqual(cache._get_current_cooldown(), 5.0)

    def test_inference_active_with_dynamic_cooldown(self):
        cache = AdvancedPromptCache(max_memory_gb=100)
        cache._inference_event.set() # Not running
        
        # Normal mode: 60s cooldown
        cache.pressure_manager.get_usage_ratio = MagicMock(return_value=0.50)
        cache._last_inference_time = time.time() - 30.0 # 30s ago
        self.assertTrue(cache._is_inference_active(), "Should be active (within 60s)")
        
        # Pressure mode: 5s cooldown
        cache.pressure_manager.get_usage_ratio = MagicMock(return_value=0.90)
        self.assertFalse(cache._is_inference_active(), "Should NOT be active (past 5s)")

if __name__ == "__main__":
    unittest.main()
