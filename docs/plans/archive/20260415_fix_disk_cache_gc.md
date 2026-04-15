# [Plan] P0-#1: 디스크 캐시 무한 증가 방지 (GC 도입)

- **심각도**: 🔴 P0 (디스크 풀 위험)
- **상태**: [x] 완료
- **관련 감사**: `docs/knowledge/cache_system_audit_20260415.md` #1
- **의존**: 없음

---

## 1. 문제

`PersistentCacheLayer`에 디스크 캐시 삭제/GC 정책이 없어, evict된 블록이 `.safetensors`로 **무한 누적**됨.
- 현 상태: **280GB / 169파일**

## 2. 해결 방안

### 2.1 `max_disk_cache_bytes` 한도 설정
```python
def __init__(self, cache_dir="...", max_disk_bytes=50 * 1024**3):  # 50GB 기본
    self.max_disk_bytes = max_disk_bytes
```

### 2.2 디스크 LRU Eviction
```python
def _enforce_disk_limit(self):
    """디스크 사용량이 한도를 초과하면 가장 오래된 파일부터 삭제."""
    files = sorted(self.cache_dir.glob("*.safetensors"), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    while total > self.max_disk_bytes and files:
        victim = files.pop(0)
        total -= victim.stat().st_size
        victim.unlink()
        logger.info(f"🗑️ Disk GC: Removed {victim.name}")
```

### 2.3 호출 시점
- `_write_to_ssd()` 성공 직후
- 서버 시작 시 1회

### 2.4 CLI 옵션 추가
- `--disk-cache-limit` (기본: 50GB)
- 기존 `cli.py`의 argparse에 추가

## 3. 검증
- [x] 한도 초과 시 가장 오래된 파일 삭제 확인 (TestDiskCacheGC 통과)
- [x] 기존 테스트 통과 (25/25 passed)
- [x] `config.py` disk_cache_limit 기본값 및 MLX_SERVER_DISK_CACHE_LIMIT env var 추가

## 4. P2 #11 함께 해결
- `get_cache_stats()`에 SSD 사용량(bytes, 파일 수) 추가
