# [Plan] P1-#7: async 스왑 location 마킹 타이밍 수정

- **심각도**: 🟠 P1 (유령 DISK 엔트리)
- **상태**: [x] 완료 (2026-04-15)
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #7
- **의존**: 없음

---

## 1. 문제

`evacuate_if_needed()` L406-416:
```python
loop.create_task(self.persistent_layer.swap_out_async(h, kv_state))
# ↑ 비동기 시작만 함
meta["location"] = "DISK"  # ← 완료 전 마킹!
```

- 비동기 스왑이 쿨다운/IO 에러로 실패해도 `location`은 이미 `"DISK"`
- 이후 swap_in 시 파일이 존재하지 않아 Resurrection 실패 → 캐시 유실

## 2. 해결 방안

### 방안 A: 중간 상태 도입 (추천)
```python
meta["location"] = "SWAPPING"  # 새 상태

async def _swap_and_mark(self, h, kv_state, meta):
    try:
        await self.persistent_layer.swap_out_async(h, kv_state)
        meta["location"] = "DISK"
    except Exception:
        meta["location"] = "VRAM"  # 롤백
        self.vram_pool[h] = kv_state  # VRAM에 복원
```

### 방안 B: sync-only로 단순화
async 경로를 제거하고 sync fallback만 사용. 이미 `mx.eval()`로 텐서 물질화 후이므로
`_write_to_ssd()`는 IO만 수행하여 충분히 빠름.

## 3. 검증
- [ ] async 스왑 실패 시 location이 DISK가 아닌지 확인
- [ ] 기존 테스트 통과
