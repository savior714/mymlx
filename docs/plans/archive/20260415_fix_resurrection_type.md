# [Plan] P0-#3: Resurrection 후 tuple→KVCache 타입 변환

- **심각도**: 🔴 P0 (즉시 크래시)
- **상태**: [x] 완료
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #3
- **의존**: 없음 (독립 수정 가능)

---

## 1. 문제

`PersistentCacheLayer.swap_in()`은 `(k, v)` 튜플 리스트를 반환하지만,
`LRUPromptCache.insert_cache()`는 내부에서 `sum(c.nbytes for c in prompt_cache)`를 호출한다.

```python
# LRUPromptCache.insert_cache 내부 (mlx-lm)
entry = LRUPromptCache.CacheEntry(
    prompt_cache, sum(c.nbytes for c in prompt_cache), cache_type
)
```

튜플 `(mx.array, mx.array)`에는 `.nbytes` 속성이 없으므로 `AttributeError` 발생.

## 2. 영향 범위

- `fetch_nearest_cache()` → swap_in 성공 → `super().insert_cache()` 호출 시
- `warm_up()` → swap_in 성공 → `super().insert_cache()` 호출 시

## 3. 해결 방안

### 3.1 변환 함수 추가
```python
from mlx_lm.models.cache import KVCache

def _tuples_to_kvcache(kv_tuples: list) -> list:
    """swap_in 결과(튜플 리스트)를 KVCache 객체 리스트로 변환."""
    result = []
    for item in kv_tuples:
        if item is None:
            kv = KVCache()
            result.append(kv)
        else:
            kv = KVCache()
            kv.keys, kv.values = item
            kv.offset = item[0].shape[2]
            result.append(kv)
    return result
```

### 3.2 적용 위치
- `fetch_nearest_cache()` L334: `kv_state = _tuples_to_kvcache(kv_state)` 추가
- `warm_up()` L314: 동일하게 변환 적용

## 4. 검증
- [x] 기존 테스트 통과 (`test_lru2_cache.py`) — 12/12 pass
- [x] Resurrection 시나리오 테스트 추가 (nbytes 접근 확인) — `TestTuplesToKVCache` (5개)
- [x] `./verify.sh` 통과 — 전체 22/22 pass
