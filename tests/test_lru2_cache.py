import time
import unittest
from unittest.mock import MagicMock, patch
import mlx.core as mx
from mlx_lm.models.cache import KVCache
from mlx_server.cache_utils import (
    AdvancedPromptCache,
    MemoryPressureManager,
    PersistentCacheLayer,
    _tuples_to_kvcache,
    KVPage
)

class TestLRU2Cache(unittest.TestCase):
    def setUp(self):
        # Mock MLX Metal behavior
        self.mx_patcher = patch("mlx.core.get_active_memory")
        self.mock_get_mem = self.mx_patcher.start()
        self.mock_get_mem.return_value = 10 * 1024**3 # 10GB default
        
        self.device_patcher = patch("mlx.core.device_info")
        self.mock_device_info = self.device_patcher.start()
        self.mock_device_info.return_value = {"max_recommended_working_set_size": 100 * 1024**3}
        
    def tearDown(self):
        self.mx_patcher.stop()
        self.device_patcher.stop()

    def test_memory_pressure_states(self):
        mgr = MemoryPressureManager(soft_limit_ratio=0.8, hard_limit_ratio=0.9)
        mgr.set_total_limit(100 * 1024**3) # 100GB
        
        # Healthy
        self.mock_get_mem.return_value = 50 * 1024**3
        self.assertEqual(mgr.get_current_state(), "HEALTHY")
        
        # Warning
        self.mock_get_mem.return_value = 85 * 1024**3
        self.assertEqual(mgr.get_current_state(), "WARNING")
        
        # Critical
        self.mock_get_mem.return_value = 95 * 1024**3
        self.assertEqual(mgr.get_current_state(), "CRITICAL")

    def test_priority_eviction_order(self):
        cache = AdvancedPromptCache(max_memory_gb=100)
        cache._LAZY_SWAP_MIN = 0
        cache._LAZY_SWAP_BASE = 0
        
        def create_mock_kv():
            m = MagicMock()
            m.nbytes = 1024
            m.is_trimmable.return_value = True
            m.keys = mx.array([0.0])
            m.values = mx.array([0.0])
            return m
            
        dummy_state = [create_mock_kv()]
        
        # P0: Pinned
        cache.insert_cache(None, [1, 2], dummy_state, priority=0)
        # P1: High
        cache.insert_cache(None, [3, 4], [create_mock_kv()], priority=1)
        # P2: Normal
        cache.insert_cache(None, [5, 6], [create_mock_kv()], priority=2)
        # P3: Ephemeral
        cache.insert_cache(None, [7, 8], [create_mock_kv()], priority=3)
        
        # Mark blocks as "hot" so they go to SSD instead of PURGE
        for page in cache.index.pages.values():
            page.reuse_count = 5
        
        # Trigger Warning Pressure (85GB)
        self.mock_get_mem.return_value = 85 * 1024**3
        
        cache.evacuate_if_needed()
        
        # Check if P3 was swapped
        key, matched_len = cache.find_best_blocks([7, 8])
        page = cache.index.key_to_pages[key][0]
        self.assertEqual(page.location, "DISK")

    def test_kvpage_tokens_preserved(self):
        """insert_cache 후 KVPage에 tokens가 올바르게 보존되어야 한다."""
        cache = AdvancedPromptCache(max_memory_gb=100)

        def create_mock_kv():
            m = MagicMock()
            m.nbytes = 1024
            m.is_trimmable.return_value = True
            m.keys = mx.array([0.0])
            m.values = mx.array([0.0])
            return m

        tokens = [10, 20, 30]
        cache.insert_cache(None, tokens, [create_mock_kv()], priority=2)

        self.assertEqual(len(cache.index.pages), 1)
        page = list(cache.index.pages.values())[0]
        self.assertEqual(page.tokens, tokens, "tokens should be preserved in KVPage")

    def test_cleanup_purged_metadata(self):
        """PURGED 상태인 메타데이터 정리 검증."""
        cache = AdvancedPromptCache(max_memory_gb=100)
        
        # stale
        p1 = KVPage(page_id="p1", tokens=[1, 2], priority=2)
        p1.location = "PURGED"
        p1.last_access = time.time() - 400
        cache.index.pages["p1"] = p1
        
        # recent
        p2 = KVPage(page_id="p2", tokens=[3, 4], priority=2)
        p2.location = "PURGED"
        p2.last_access = time.time() - 100
        cache.index.pages["p2"] = p2

        cache._cleanup_purged_metadata(max_age=300)

        self.assertNotIn("p1", cache.index.pages)
        self.assertIn("p2", cache.index.pages)

    def test_resurrection_from_disk(self):
        cache = AdvancedPromptCache(max_memory_gb=100)
        tokens = [1, 2, 3]
        h = "test_hash"
        
        def create_mock_kv():
            m = MagicMock()
            m.nbytes = 1024
            m.is_trimmable.return_value = True
            m.keys = mx.array([0.1])
            m.values = mx.array([0.2])
            return m
            
        dummy_state = [create_mock_kv()]
        
        with patch("mlx_server.cache_utils.TokenHasher.hash_tokens", return_value=h):
            cache.insert_cache(None, tokens, dummy_state, priority=2)
            key = cache._make_cache_key(h)
            page = cache.index.key_to_pages[key][0]
            
            # Manually simulate on disk
            page.location = "DISK"
            page.kv_tensor = None
            
            with patch.object(cache.persistent_layer, "swap_in", return_value=dummy_state) as mock_load:
                with patch("mlx_lm.models.cache.LRUPromptCache.fetch_nearest_cache", return_value=(dummy_state, [])):
                    c, r = cache.fetch_nearest_cache(None, tokens)
                    self.assertIsNotNone(c)
                    self.assertEqual(page.location, "VRAM")
                    mock_load.assert_called_once()

    def test_evacuate_sort_lru_order(self):
        """같은 priority라면 오래된 블록이 먼저 삭제되어야 한다."""
        cache = AdvancedPromptCache(max_memory_gb=100)
        cache._LAZY_SWAP_MIN = 0
        cache._LAZY_SWAP_BASE = 0

        def create_mock_kv():
            m = MagicMock()
            m.nbytes = 1024
            m.is_trimmable.return_value = True
            m.keys = mx.array([0.0])
            m.values = mx.array([0.0])
            return m

        base = time.time()
        h_old = "old_page"
        h_new = "new_page"

        for h, offset in [(h_old, -200), (h_new, -10)]:
            page = KVPage(page_id=h, tokens=[1, 2], priority=2)
            page.location = "VRAM"
            page.last_access = base + offset
            page.kv_tensor = [create_mock_kv()]
            page.reuse_count = 5
            cache.index.register_block(cache._make_cache_key(h), [page])

        # Mock: initial state is WARNING, usage drops after 1 eviction
        ratio_calls = [0]
        def ratio_side_effect():
            ratio_calls[0] += 1
            return 0.85 if ratio_calls[0] <= 2 else 0.60
        cache.pressure_manager.get_usage_ratio = ratio_side_effect
        
        cache.pressure_manager.get_current_state = MagicMock(return_value="WARNING")

        cache.evacuate_if_needed()

        self.assertIn(cache.index.pages[h_old].location, {"DISK", "SWAPPING"})
        self.assertEqual(cache.index.pages[h_new].location, "VRAM")

class TestMemoryHeadroomAndProactiveEviction(unittest.TestCase):
    def setUp(self):
        self.mx_patcher = patch("mlx.core.get_active_memory")
        self.mock_get_mem = self.mx_patcher.start()
        self.mock_get_mem.return_value = 10 * 1024**3
        self.device_patcher = patch("mlx.core.device_info")
        self.mock_device_info = self.device_patcher.start()
        self.mock_device_info.return_value = {"max_recommended_working_set_size": 100 * 1024**3}

    def tearDown(self):
        self.mx_patcher.stop()
        self.device_patcher.stop()

    def test_needs_headroom(self):
        mgr = MemoryPressureManager(headroom_ratio=0.65)
        mgr.set_total_limit(100 * 1024**3)
        self.mock_get_mem.return_value = 70 * 1024**3
        self.assertTrue(mgr.needs_headroom())

    def test_proactive_evict(self):
        cache = AdvancedPromptCache(max_memory_gb=100)
        cache._last_inference_time = 0.0

        def create_mock_kv():
            m = MagicMock()
            m.nbytes = 1024
            m.keys = mx.array([0.0])
            m.values = mx.array([0.0])
            return m

        page = KVPage(page_id="p1", tokens=[1, 2], priority=2)
        page.location = "VRAM"
        page.last_access = time.time() - 60
        page.kv_tensor = [create_mock_kv()]
        page.reuse_count = 5
        cache.index.register_block(cache._make_cache_key("h1"), [page])

        hr = cache.pressure_manager.headroom_ratio
        cache.pressure_manager.get_usage_ratio = MagicMock(side_effect=[hr + 0.05, hr + 0.05, hr - 0.1])

        with patch.object(cache.persistent_layer, "_write_to_ssd"):
            cache._proactive_evict()

        self.assertEqual(page.location, "DISK")

class TestPersistentCacheLayerSerialization(unittest.TestCase):
    def test_serialization_roundtrip(self):
        kv_state = [None] * 2
        kv_state[1] = (mx.array([1.0]), mx.array([2.0]))
        kv_dict = PersistentCacheLayer._serialize_kv_state(kv_state)
        self.assertIn("layer_1_k", kv_dict)
        result = PersistentCacheLayer._deserialize_kv_state(kv_dict)
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[1])

class TestTuplesToKVCache(unittest.TestCase):
    def test_conversion(self):
        raw = [(mx.zeros((1, 1, 4, 8)), mx.zeros((1, 1, 4, 8)))]
        converted = _tuples_to_kvcache(raw)
        self.assertIsInstance(converted[0], KVCache)
        self.assertEqual(converted[0].offset, 4)

if __name__ == "__main__":
    unittest.main()
