# Knowledge: 캐시 시스템 심층 감사 결과 (2026-04-15)

## §1. 메타 정보
- **Last Verified**: 2026-04-15
- **Source**: `cache_utils.py` + `backend.py` + `proxy.py` 코드 리뷰 + 런타임 데이터 분석
- **Author**: AI Pair-Programmer
- **Created**: 2026-04-15
- **Tags**: #cache #audit #ssd-swap #memory-leak #thread-safety

## §2. 감사 배경
SSD Swap 직렬화 버그(`KeyError: 'layer_0_k'`) 수정 후, 전체 캐시 시스템의 잠재 이슈를 사전 식별하기 위해 심층 감사를 수행함.
- **현 상태**: SSD 캐시 **280GB / 169파일** 누적, 디스크 잔여 572GB

## §3. 발견 이슈 요약 (11건)

### P0 — 즉시 해결 필요 (3건)
| # | 이슈 | 핵심 원인 | 플랜 |
|---|------|----------|------|
| 1 | 디스크 캐시 무한 증가 | `PersistentCacheLayer`에 GC/LRU 정책 없음 | `20260415_fix_disk_cache_gc.md` |
| 2 | metadata 메모리 누수 | `block_metadata["tokens"]`에 전체 토큰 저장 + PURGED 미정리 | `20260415_fix_metadata_leak.md` |
| 3 | Resurrection nbytes 크래시 | swap_in → `(k,v)` 튜플 반환 vs `insert_cache`의 `c.nbytes` 호출 | `20260415_fix_resurrection_type.md` |

### P1 — 높음 (4건)
| # | 이슈 | 핵심 원인 | 플랜 |
|---|------|----------|------|
| 4 | Thread Safety 부재 | `block_metadata`/`vram_pool` 무락 동시 접근 | `20260415_fix_thread_safety.md` |
| 5 | evacuate 정렬 반전 | `reverse=True`로 `last_used` 최근 것이 먼저 삭제 | `20260415_fix_evacuate_sort.md` |
| 6 | CRITICAL 스왑 불가 | WARNING에서만 swap-to-disk, CRITICAL은 즉시 PURGE | `20260415_fix_critical_swap.md` |
| 7 | async 마킹 타이밍 | 비동기 스왑 시작 즉시 `location="DISK"` 마킹 | `20260415_fix_async_location.md` |

### P2 — 보통 (4건)
| # | 이슈 | 비고 |
|---|------|------|
| 8 | `hash_to_tokens` ↔ `metadata["tokens"]` 중복 | #2 해결 시 함께 |
| 9 | `import re` 반복 호출 | 모듈 레벨 이동 |
| 10 | CI 환경 Metal API 호출 에러 | guard 추가 |
| 11 | 캐시 통계에 SSD 사용량 누락 | #1 해결 시 함께 |

## §4. 권장 조치 순서
1. **#3** → Resurrection 크래시 방지 (swap_in 성공 시 즉시 터짐)
2. **#1** → 280GB 디스크 정리 + GC 도입
3. **#5** → 정렬 부호 수정 (1줄 수정)
4. **#7** → async 마킹 타이밍
5. **#4** → Thread Lock
6. **#6** → CRITICAL 스왑
7. **#2** → metadata 경량화

## §5. 프로젝트 적용
- **적용 위치**: `src/mlx_server/cache_utils.py`
- **관련 플랜**: `docs/plans/20260415_fix_*.md` (7건)
- **관련 문서**: `docs/knowledge/ssd_swap_serialization_fix.md`, `docs/knowledge/advanced_cache_strategy.md`
