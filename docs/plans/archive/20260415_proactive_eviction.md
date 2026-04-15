# [Plan] Proactive Eviction & Inference Headroom

- **심각도**: 🟡 P1 (추론 중 stall → 체감 성능 저하)
- **상태**: [x] 완료 (2026-04-15)
- **관련**: 캐시 시스템 감사 `docs/knowledge/cache_system_audit_20260415.md`

---

## 1. 문제

### 1.1 Reactive Eviction
- `evacuate_if_needed()`가 `insert_cache()` 호출 시점(추론 중)에만 실행됨
- 요청 사이 유휴 시간(30초+)에는 아무 정리도 하지 않아, 캐시가 21.55GB까지 누적

### 1.2 추론 중 Stall
- `mx.eval(*kv_dict.values())` + safetensors 쓰기가 추론 스레드를 동기적으로 블록
- 프롬프트 처리 중 eviction 발생 → 수 초간 멈춤

### 1.3 Lazy Swap 고정 임계값
- WARNING 상태에서 `lazy_swap_threshold = 30초` 고정
- 최근 사용된 블록은 모두 스킵 → soft limit 직전에서 아무것도 evict 못 함

## 2. 해결

### 2.1 Inference Headroom (`headroom_ratio=0.65`)
```python
class MemoryPressureManager:
    def needs_headroom(self) -> bool:
        return self.get_usage_ratio() > self.headroom_ratio
```
- 캐시는 VRAM의 65%까지만, 나머지 15%는 추론용 여유

### 2.2 Background Maintenance Thread
```python
def _background_maintenance(self):
    while not self._maintenance_stop.wait(5.0):
        if self.pressure_manager.needs_headroom() and self.vram_pool:
            self._proactive_evict()
```
- 5초 간격으로 체크, 유휴 시 proactive eviction

### 2.3 Dynamic Lazy Threshold
```python
def _dynamic_lazy_threshold(self) -> float:
    # headroom(65%) → 30초, soft_limit(80%) → 3초, 선형 보간
    t = (ratio - headroom) / (soft - headroom)
    return BASE * (1 - t) + MIN * t
```

## 3. 검증
- [x] 기존 테스트 호환성 유지 (lazy_swap_threshold → 클래스 상수 전환)
- [x] 신규 테스트 7개 추가 (headroom, proactive, dynamic, shutdown)
- [x] 전체 38/38 통과
