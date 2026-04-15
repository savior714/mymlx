# Plan: Advanced Cache Manager Specification Enhancement [DONE]

사용자 피드백을 반영하여 `docs/specs/advanced_cache_manager.md`를 실제 `mlx-lm` 및 `vLLM`의 선진 사례에 맞게 고도화합니다.

## 1. 주요 업데이트 항목

### 1.1 캐시 키 메타데이터 강화 (Metadata-rich Cache Key)
- 단순 토큰 시퀀스 해시에서 탈피하여 환경 정보를 포함한 복합 키 설계.
- 포함 요소: `model_id`, `tokenizer_version`, `chat_template`, `special_tokens`, `quantization/dtype`, `rope_scaling`, `system_prompt_version`.

### 1.2 블록 레벨 해싱 및 프리픽스 체인 (Block-level Hashing & Prefix Chain)
- 누적 전체 해싱 대신 **Block-level Hash + Prefix Hash Chain** 방식 도입.
- 이점: 부분 재사용(Partial Reuse), 부분 축출(Partial Eviction), CoW 관리 효율화.

### 1.3 3계층 아키텍처 분리 (3-Layer Architecture)
- **Index Layer**: 해시, 메타데이터, 우선순위, 위치, 참조 카운트 관리.
- **Runtime Layer**: VRAM 블록 할당/해제, CoW, LRU/점수화.
- **Persistence Layer**: Disk Swap (mmap, safetensors), 체크섬, 버전 관리.

### 1.4 CoW 및 참조 카운트 도입 (CoW with Refcount & Generation)
- 공유 페이지의 불변성(Immutability) 보장.
- 페이지 단위 참조 카운트(Ref-count) 및 세대 번호(Generation) 관리로 동시성 안전 보장.

### 1.5 점수 기반 동적 축출 (Score-based Eviction)
- 고정 등급(P0~P3) 대신 다차원 점수 모델 도입.
- `score = f(priority, recency, reuse_count, recovery_cost, block_depth)`.

### 1.6 메모리 압박 실패 모드 정의 (Memory Pressure Failure Modes)
- **Soft Limit**: 신규 캐시 억제, 비동기 스왑 후보 등록.
- **Hard Limit**: 신규 요청 차단(503/429), 즉각적 축출.
- **OOM Guard**: Fail-fast 경로 정의 및 HTTP 에러 변환 가드.

### 1.7 불변성(Invariants) 및 명시적 테스트 고정
- **Tail Integrity**: `cached_prefix + original_tail == reconstructed_input`.
- **Full-hit Handling**: 예외 경로 처리를 통한 `BatchGenerator` 인덱스 에러 방지.
- **Data Integrity**: Disk Swap 시 Checksum + Versioning 강제.

## 2. 작업 순서

1.  **`docs/specs/advanced_cache_manager.md` 업데이트**: 위 항목들을 상세히 기술하여 명세서 수정.
2.  **`docs/CRITICAL_LOGIC.md` 업데이트**: 설계 결정 사항(Architecture, Invariants) 반영.
3.  **검증**: 명세서 간의 정합성 확인.

## 3. 예상 변경 내용 (Summary of Changes)

- **Section 2**: 해시 매커니즘을 블록 단위 및 메타데이터 포함 방식으로 전면 개정.
- **Section 3**: CoW 로직에 참조 카운트 필드 추가.
- **Section 7**: 불변성(Invariants) 섹션 강화 및 Full-hit 처리 경로 구체화.
- **Section 9**: 점수 기반 축출 알고리즘 및 메모리 실패 모드 추가.
- **Section 10**: 3계층 아키텍처에 따른 모듈 역할 재정의.
