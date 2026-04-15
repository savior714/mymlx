# [Plan] P0-#2: block_metadata 메모리 누수 해소

- **심각도**: 🔴 P0 (장시간 운영 시 OOM)
- **상태**: [x] 완료 (2026-04-15)
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #2
- **의존**: #3 (Resurrection 타입 수정) 선행 권장

---

## 1. 문제

### 1.1 tokens 전체 저장
```python
self.block_metadata[h] = {
    "tokens": tokens,  # ← 10만 토큰 = 수 MB
    ...
}
```
Resurrection/warm_up에서 `meta["tokens"]`를 사용하지만, 전체 토큰이 VRAM 메타에 들어갈 필요 없음.

### 1.2 PURGED 미정리
블록이 PURGED 상태가 되어도 metadata가 계속 남아있음.

### 1.3 hash_to_tokens 중복 (P2 #8)
`hash_to_tokens[h] = tokens`와 `block_metadata[h]["tokens"] = tokens`가 동일 리스트를 2중 참조.

## 2. 해결 방안

### 2.1 metadata 경량화
```python
self.block_metadata[h] = {
    "len": len(tokens),
    "token_hash": h,           # 해시만 저장
    "priority": priority,
    "location": "VRAM",
    "last_used": time.time()
}
```
- `tokens` 전체는 `hash_to_tokens`에만 유지
- DISK/PURGED 상태에서 tokens가 필요하면 `hash_to_tokens`에서 조회

### 2.2 PURGED 메타 정리
```python
def _cleanup_purged_metadata(self, max_age=300):
    """300초 이상 PURGED 상태인 메타데이터 제거."""
    now = time.time()
    to_remove = [
        h for h, m in self.block_metadata.items()
        if m["location"] == "PURGED" and now - m["last_used"] > max_age
    ]
    for h in to_remove:
        del self.block_metadata[h]
        self.hash_to_tokens.pop(h, None)
```

### 2.3 호출 시점
- `evacuate_if_needed()` 끝에서 주기적으로 호출
- 또는 `insert_cache()` 시 10회마다 1회 트리거

## 3. 검증
- [x] metadata에 tokens 직접 접근하는 코드가 없는지 확인
- [x] PURGED 정리 후 메모리 감소 확인 (test_cleanup_purged_metadata_removes_stale)
- [x] 기존 테스트 통과 + warm_up/resurrection 정상 동작 (23/23 passed)
