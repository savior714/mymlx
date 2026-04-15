# Advanced Prompt Cache 전략 (Full-Sequence & Paged)

- **작성일**: 2026-04-14
- **대상**: mlx-server v0.1.0 이상
- **태그**: #cache #prompt-cache #hashing #optimization

## 1. 개요 (Background)
`mlx-lm`의 기본 캐시 모델은 토큰 단위의 Trie 구조를 사용하여 최장 접두사(Longest Prefix)를 찾습니다. 하지만 서버 재시작 시 인메모리 Trie가 소실되고, 대규모 컨텍스트 환경에서 매번 Trie를 검색하는 비용을 최적화하기 위해 해시 기반의 **AdvancedPromptCache**를 도입했습니다.

## 2. 핵심 아키텍처 (Key Architecture)

### 2.1 2단계 하이브리드 매칭 (Hybrid Matching)
1.  **Full Sequence Hash (L0)**: 입력된 전체 프롬프트의 해시를 먼저 확인합니다. 반복적인 요청(Identical Request)에 대해 TTFT를 즉각적으로(Safeguard 제외 0토큰) 단축합니다.
2.  **Logical Paging (L1)**: 프롬프트를 고정 크기(기본 128 토큰) 블록으로 나누어 각 블록의 누적 해시를 인덱싱합니다. 이를 통해 서로 다른 프롬프트 간에도 공통된 블록(예: 같은 시스템 프롬프트나 RAG 문서)을 재사용할 수 있습니다.

### 2.2 Safeguard 통합 (Safeguard Integration)
`mlx-lm 0.31.2` 이상의 `BatchGenerator`에서 발생하는 `IndexError`를 방지하기 위해, 캐시 히트 시에도 항상 **마지막 1개 토큰을 연산 대상(`rest`)으로 남겨두는** 세이프가드 로직을 포함합니다.
- **로직**: `Matched - 1` 토큰을 캐시에서 로드하고, 마지막 1개 토큰 + 캐시되지 않은 뒷부분(`tail`)을 모델에 전달.

## 3. 해결된 문제 (Problem Solved)

### 3.1 Partial-Hit Loop (부분 히트 루프)
- **현상**: 프롬프트가 페이지 크기(128)의 배수가 아닐 경우, 전체 해시 체크가 없으면 마지막 페이지 경계 이후의 토큰들이 매 요청마다 반복해서 연산되는 현상.
- **해결**: 매칭 전 전체 프롬프트 해시를 우선 검사함으로써, 비-페이지-정렬(Non-page-aligned) 꼬리 부분(`tail`)까지 완벽하게 캐싱 처리함.

## 4. 구현 가이드 (Implementation Details)
- **Hash Algorithm**: `hashlib.sha256` (Apple Silicon 하드웨어 가속 활용).
- **Storage**: `self.hash_to_tokens`(전체/블록 해시 매핑) 및 `self.block_pool`(페이지 단위 인덱스).
- **Integration**: `src/mlx_server/cache_utils.py`의 `AdvancedPromptCache` 클래스 참고.

## 4.1 운영 관측 포인트 (2026-04-15 업데이트)
- **Cache Stats API**: `GET /v1/mlx/cache/stats`
  - `full_hit_rate`, `paged_hit_rate`, `avg_matched_tokens`
  - `miss_reason_counts` (`full_hash_miss`, `paged_hash_miss`, `metadata_missing`, `fetch_hit_failed`, `purged_recently`)
  - `evicted_to_disk`, `purged_cold`, `purged_critical`, `eviction_under_inference` 관련 카운터
- **Grace Window**: `cache_grace_seconds` 동안 `hits=0` 블록을 즉시 PURGE하지 않음.
- **Dynamic Threshold**: `_SSD_WRITE_THRESHOLD`를 메모리 압박 비율에 따라 동적으로 조정.
- **Prompt Normalization (옵션)**: 공백/개행 정규화로 동일 의미 프롬프트의 캐시 키 변동을 감소.

## 5. 기대 효과
- **TTFT 개선**: 반복 요청 시 연산량을 99% 이상 절감.
- **Resource Efficiency**: VRAM 점유를 예측 가능하게 관리하며, 중복된 KV-Cache 생성을 억제함.
