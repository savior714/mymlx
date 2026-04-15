# [Plan] P1-#6: CRITICAL 상태에서도 디스크 스왑 시도

- **심각도**: 🟠 P1 (캐시 영구 손실)
- **상태**: [x] 완료 (2026-04-15)
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #6
- **의존**: #7 (async 마킹 수정) 선행 권장

---

## 1. 문제

`evacuate_if_needed()` L386-420:
- `WARNING`: swap-to-disk 후 VRAM 해제 ✅
- `CRITICAL`: **스왑 없이 즉시 PURGE** → 캐시 영구 손실 ❌

WARNING을 거치지 않고 바로 CRITICAL에 진입하면 모든 캐시 데이터가 구제 불능.

## 2. 해결 방안

```python
elif state == "CRITICAL":
    kv_state = self.vram_pool.pop(h, None)
    if kv_state:
        # 스왑 시도 (sync — CRITICAL은 빠른 해제가 우선)
        try:
            kv_dict = PersistentCacheLayer._serialize_kv_state(kv_state)
            if kv_dict:
                mx.eval(*kv_dict.values())
                self.persistent_layer._write_to_ssd(
                    self.persistent_layer.cache_dir / f"{h}.safetensors", kv_dict
                )
                meta["location"] = "DISK"
                logger.info(f"📦 CRITICAL Swap: {h[:8]} (P{meta['priority']}) -> SSD")
            else:
                meta["location"] = "PURGED"
        except Exception:
            meta["location"] = "PURGED"
            logger.warning(f"🔥 CRITICAL Purge (swap failed): {h[:8]}")
```

### 핵심 원칙
- CRITICAL에서는 **async가 아닌 sync** 스왑 (즉시 VRAM 해제 필요)
- 스왑 실패 시에만 PURGE로 폴백
- Lazy Swap threshold는 CRITICAL에서 무시

## 3. 검증
- [ ] CRITICAL 진입 시 스왑 시도 확인
- [ ] 스왑 실패 시 PURGE 폴백 확인
- [ ] 기존 테스트 통과
