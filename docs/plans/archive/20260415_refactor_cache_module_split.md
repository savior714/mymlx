# [Plan] 20260415_refactor_cache_module_split.md

- **목표**: `AdvancedPromptCache` 관련 코드가 500라인을 초과하거나 임계치에 도달함에 따라, 로직을 기능별로 분리하여 관리 효율성을 높이고 프로젝트 가드레일을 준수함.
- **현재 상태**:
    - `src/mlx_server/advanced_prompt_cache.py`: 504라인 (500라인 초과)
    - `src/mlx_server/cache_utils.py`: 70라인 (AdvancedPromptCache를 여기서 분리하라는 요청이나, 이미 물리적으로는 분리되어 있음. 단, `advanced_prompt_cache.py` 자체가 커진 상태)

---

## 1. 리팩터링 전략

### 1.1 `MemoryPressureManager` 분리
- **대상**: `MemoryPressureManager` 클래스 및 관련 로직.
- **목적지**: `src/mlx_server/memory_manager.py` (신규)
- **이유**: 메모리 압박 관리 로직은 캐시뿐만 아니라 다른 모듈에서도 참조될 수 있는 인프라적 성격이 강함.

### 1.2 유틸리티 로직 이동
- **대상**: `_tuples_to_kvcache` 함수.
- **목적지**: `src/mlx_server/cache_utils.py`
- **이유**: 단순 타입 변환 유틸리티이므로 유틸리티 모듈로 이동하여 코어 로직의 부피를 줄임.

### 1.3 `AdvancedPromptCache` 최적화
- **결과**: `advanced_prompt_cache.py`에는 `AdvancedPromptCache` 클래스만 남기거나 꼭 필요한 로직만 유지.
- **기대 효과**: 파일 크기가 ~400라인 수준으로 감소하여 500라인 가드레일 준수.

---

## 2. 세부 작업 단계 (SDD)

### Step 1: `src/mlx_server/memory_manager.py` 생성
- `mlx.core` 및 `logging` 의존성 포함.
- `MemoryPressureManager` 클래스 이동.

### Step 2: `src/mlx_server/cache_utils.py` 업데이트
- `_tuples_to_kvcache` 이동 및 `KVCache` 임포트 추가.

### Step 3: `src/mlx_server/advanced_prompt_cache.py` 업데이트
- 상단 임포트 정리 (신규 모듈로부터 `MemoryPressureManager`, `_tuples_to_kvcache` 임포트).
- 이동된 로직 삭제.

### Step 4: 의존성 확인
- `src/mlx_server/backend.py`, `src/mlx_server/app.py` 등에서 기존 `AdvancedPromptCache` 또는 `MemoryPressureManager`를 참조하는 경로가 올바른지 확인. (현재는 `cache_utils`를 통해 프록시 임포트 중이므로 `cache_utils.py`만 잘 수정하면 됨)

---

## 3. 검증 계획

- [ ] **라인 수 검증**: 모든 파일이 500라인 이하인지 확인.
- [ ] **정적 분석**: `ruff` 또는 `flake8` (설정된 경우) 실행.
- [ ] **통합 테스트**: `./verify.sh` 실행하여 캐시 동작 및 메모리 관리 동작 확인.
- [ ] **스모크 테스트**: 서버 기동 및 기본 추론 테스트.

---

## 4. 리스크 및 후속
- **순환 참조**: `cache_utils` ↔ `advanced_prompt_cache` 간 순환 참조 발생 주의.
- **임포트 경로**: `cache_utils.py`에서 `advanced_prompt_cache`를 임포트하고, `advanced_prompt_cache`에서 `cache_utils`를 임포트하는 기존 구조가 있으므로, 핵심 로직 이동 시 이 관계를 끊거나 정리해야 함.
