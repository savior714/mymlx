# [Plan] P1-#4: Thread Safety — Lock 도입

- **심각도**: 🟠 P1 (동시 요청 크래시)
- **상태**: [x] 완료 (2026-04-15)
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #4
- **의존**: 없음

---

## 1. 문제

`mlx_lm.server`는 `ThreadingHTTPServer`를 사용하므로 동시 요청이 **별도 스레드**에서 처리됨.
`AdvancedPromptCache`의 `block_metadata`, `vram_pool`, `hash_to_tokens`가 **락 없이 접근**됨.

### 발생 가능한 시나리오
1. **Thread A**: `evacuate_if_needed()` → `vram_pool.pop(h)`
2. **Thread B**: `fetch_nearest_cache()` → `vram_pool[h]` 접근 → `KeyError` or `None`
3. **Thread C**: `insert_cache()` → `block_metadata[h] = {...}` (iteration 중 dict 크기 변경)

## 2. 해결 방안

### 2.1 AdvancedPromptCache에 Lock 추가
```python
def __init__(self, ...):
    ...
    self._cache_lock = threading.Lock()
```

### 2.2 보호 대상 메서드
- `insert_cache()` — 전체를 lock
- `fetch_nearest_cache()` — metadata/vram_pool 접근 구간
- `evacuate_if_needed()` — candidates 리스트 빌드 + 순회

### 2.3 주의사항
- Lock 범위를 **최소화**하여 추론 성능에 영향 없도록 함
- `super().insert_cache()`는 부모가 자체 동기화를 할 수 있으므로, 우리 딕셔너리 접근만 보호
- Deadlock 방지: 단일 Lock, 중첩 없음

## 3. 검증
- [ ] 동시 요청 시뮬레이션 테스트
- [ ] 기존 테스트 통과
