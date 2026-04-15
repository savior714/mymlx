# [Plan] P1-#5: evacuate 정렬 로직 last_used 부호 수정

- **심각도**: 🟠 P1 (캐시 효율 저하)
- **상태**: [x] 완료 (2026-04-15)
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #5
- **의존**: 없음 (1줄 수정)

---

## 1. 문제

```python
# 현재 (L376-380)
candidates = sorted(
    [...],
    key=lambda h: (self.block_metadata[h]["priority"], self.block_metadata[h]["last_used"]),
    reverse=True
)
```

`reverse=True`이므로:
- `priority`: 높은 숫자(P3 Ephemeral) 우선 → ✅ 올바름
- `last_used`: 높은 timestamp(최근) 우선 → ❌ **LRU 반대** (최근 사용된 것이 먼저 삭제)

## 2. 수정

```python
key=lambda h: (self.block_metadata[h]["priority"], -self.block_metadata[h]["last_used"])
```

`last_used`에 `-` 부호를 추가하여, `reverse=True` 시 **오래된 것(작은 timestamp → 큰 음수)이 먼저** 선택되도록 함.

## 3. 검증
- [ ] P3이 P1보다 먼저 삭제 확인
- [ ] 같은 priority 내에서 오래된 것이 먼저 삭제 확인
- [ ] 기존 테스트 통과
