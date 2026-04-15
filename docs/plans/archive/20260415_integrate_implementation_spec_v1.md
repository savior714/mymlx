# Plan: Advanced Cache Manager Implementation Spec v1.0 Integration [DONE]

사용자가 제공한 **Implementation Spec v1.0**을 바탕으로 `docs/specs/advanced_cache_manager.md`를 실제 구현이 즉시 가능한 수준으로 고도화하고, 프로젝트의 핵심 불변식(Invariants)을 동기화합니다.

## 1. 주요 업데이트 항목 (Implementation V1.0)

### 1.1 불변식(Non-Negotiable Invariants) 정의
- **I1. Tail Integrity**: `reconstructed_input == cached_prefix + original_tail` 보장.
- **I2. Page Immutability**: 모든 KV Page는 Immutable하며 수정 시 CoW 강제.
- **I3. Full-Hit Safety**: Full-hit 시 최소 1개 토큰을 runtime prefill로 분리하거나 safe-path 처리.
- **I4. Cache Key Strictness**: 모델/설정별 캐시 격리.
- **I5. Refcount Consistency**: 정확한 참조 카운트 기반의 메모리 회수.

### 1.2 상세 자료구조 및 함수 시그니처 명세
- `CacheKey`, `KVPage`, `BlockTable`, `CacheIndex` 클래스 정의(Pseudo-code).
- `fetch`, `reconstruct`, `handle_full_hit`, `ensure_writable`, `insert` 등 핵심 파이프라인 로직 명문화.

### 1.3 메모리 및 스왑 관리 로직 구체화
- **Watermarks**: Soft Limit (80%), Hard Limit (95%).
- **Eviction Score**: `priority`, `refcount`, `recency`를 결합한 점수 공식.
- **Disk Swap**: `safetensors` + `mmap` 기반의 Zero-copy 로드 및 체크섬/버전 검증 로직.

### 1.4 실패 모드(Failure Modes) 및 쓰레드 모델
- **OOM Guard**: Hard Limit 초과 시 503 HTTP 에러 유도.
- **Robustness**: 디스크 로드 실패 및 해시 충돌(Mismatch) 대응 경로.
- **Threading**: Main(Inference) vs Maintenance(Background) 쓰레드 역할 분담.

## 2. 작업 순서

1.  **`docs/specs/advanced_cache_manager.md` 재작성**: 사용자가 제공한 템플릿을 기반으로 명세서 전면 개정.
2.  **`docs/CRITICAL_LOGIC.md` 업데이트**: 핵심 불변식(I1~I5) 및 실패 모드 결정 사항 기록.
3.  **검증**: 명세서 내 로직의 기술적 정합성 검토.

## 3. 예상 변경 내용

- **Section 1~13**: 사용자가 제안한 기술 설계 문서의 구조를 그대로 수용하여 보완.
- **Invariant Section**: 프로젝트 루트 레벨의 불변 정책으로 승격.
