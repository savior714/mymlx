# [Plan] 20260415_refactor_core_architecture

- **목표**: 비즈니스 로직(모델 변환, 요청 정규화)과 인프라(HTTP 프록시, 메모리 관리)를 분리하여 코드 가독성 및 유지보수성 향상.
- **가드레일**: 모든 수정 파일은 500라인 미만 유지, SDD 아키텍처 준수.

---

## 1. 단계별 작업 계획

### Phase 1: 도메인/인프라 유틸리티 분리 (`backend.py` 정리) [DONE]
- **대상**: 모델 검색(HF), 로컬 경로 해석, Metal 메모리 초기화.
- **작업**:
    - `src/mlx_server/model_resolver.py` 신설: `search_huggingface_models`, `resolve_model_path` 이관. [DONE]
    - `src/mlx_server/memory_manager.py` 확장: `backend.py`의 `mx.set_wired_limit` 및 초기 로깅 로직을 `initialize_metal_infrastructure()`로 캡슐화. [DONE]
    - 미사용 임포트(`mx`, `resolve_model_path`) 및 레거시 의존성 정리. [DONE]

### Phase 2: 요청 파이프라인 정규화 (`proxy.py` 정리) [DONE]
- **대상**: 프롬프트 정규화, 채팅 메시지 변환, 모델명 매핑 로직.
- **작업**:
    - `src/mlx_server/request_transformer.py` 신설: `_normalize_prompt_payload`, `_normalize_chat_messages_for_mlx` 이관. [DONE]
    - `proxy_to_mlx` 함수 내의 복잡한 `if data is not None` 블록을 `MlxRequestTransformer` 클래스로 캡슐화하여 위임. [DONE]

### Phase 3: 라우트 핸들러 독립화 (`app.py` 정리) [DONE]
- **대상**: `load_route`, `unload_route`, `cache_stats_route` 등 인라인 핸들러.
- **작업**:
    - `src/mlx_server/handlers.py` 신설: 모든 핸들러를 독립 함수로 추출하여 `build_app`은 라우팅 정의에만 집중하도록 변경. [DONE]
    - `backend` 객체를 핸들러의 인자로 전달하거나 의존성 주입 패턴 사용. [DONE]

### Phase 4: 캐시 엔진 메타데이터 분리 (`advanced_prompt_cache.py` 정리) [DONE]
- **대상**: 블록 인덱싱 및 메타데이터 딕셔너리 관리.
- **작업**:
    - `src/mlx_server/cache_index.py` 신설: `block_metadata`, `hash_to_tokens`를 관리하는 `CacheIndex` 클래스 이관. [DONE]
    - `AdvancedPromptCache`는 교체 정책(LRU) 및 물리적 스왑 흐름 제어에만 집중. [DONE]

---

## 2. SDD 명세 업데이트 (Prior to implementation)
- `docs/specs/` 내 아키텍처 다이어그램 또는 모듈 정의 업데이트 필요 여부 검토. (현재 구조는 구현상의 정리이므로 계약 변경은 없음)

---

## 3. 검증 계획 (Verification)
- [ ] **정적 분석**: 파일별 라인 수 확인 (All < 500 lines).
- [ ] **유닛 테스트**: 분리된 `model_resolver` 및 `request_transformer`의 독립 테스트.
- [ ] **통합 테스트**: `./verify.sh` 실행하여 전체 추론 파이프라인 정상 동작 확인.
- [ ] **스모크 테스트**: CLI를 통한 모델 로드/언로드 및 `/v1/chat/completions` API 프록시 동작 확인.

---

## 4. 리스크 및 후속
- **순환 참조**: `backend` ↔ `handlers` 간 순환 참조 방지 (인터페이스/추상화 활용).
- **성능 영향**: 로직 분리로 인한 약간의 오버헤드 검증 (무시할 수 있는 수준 예상).
