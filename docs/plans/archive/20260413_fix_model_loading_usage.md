# 구현 계획: 모델 로딩 연동 및 프록시 강화

## 1. 개요
사용자가 `/v1/mlx/models/load`를 통해 모델을 로드했음에도 불구하고, `/v1/chat/completions` 호출 시 `model` 필드가 누락되면 `mlx_lm.server`에서 "A model path has to be given..." 에러가 발생하는 문제를 해결합니다.

## 2. 목표
- 모델 로드 후 별도의 `model` 필드 지정 없이도 채팅 기능을 사용할 수 있도록 개선.
- 프록시(Proxy)에서 현재 활성 모델 정보를 지능적으로 관리 및 주입.
- UI와 백엔드 간의 모델 상태 동기화 강화.

## 3. 상세 작업 내용

### 3.1. [Spec] 명세 업데이트
- `specs/api_compat.md`: 프록시의 `model` 필드 자동 주입 동작을 명시.
- `specs/model_lifecycle.md`: 명시적 로드(`load`)가 완료된 모델이 기본 모델(Default)로 동작함을 명시.

### 3.2. [Backend] 프록시 로직 강화 (`src/mlx_server/proxy.py`)
- `proxy_to_mlx` 함수 수정:
    - 요청이 `/v1/chat/completions` 또는 `/v1/completions`인 경우 JSON 바디를 검사.
    - `model` 필드가 누락되었거나 `null`인 경우, `backend.model_provider.model_key[0]` 값을 주입.
    - 수정된 바디로 업스트림 요청 수행.

### 3.3. [Frontend] UI 연동 보완 (`src/mlx_server/static/index.html`)
- `btnSend.onclick` 핸들러 수정:
    - `fetch("/v1/chat/completions")` 호출 시 `body`에 `model: state.loadedModelKey[0]` 필드 추가.
    - 모델이 로드되지 않은 상태에서 전송 방지 로직 강화.

### 3.4. [Cleanup] `docs/memory/MEMORY.md` 갱신
- 발견된 이슈 및 해결 방안 기록.

## 4. 검증 계획 (Verification)
- [ ] **자동 검증**: `curl`을 사용하여 `model` 필드 없이 `/v1/chat/completions` 요청 시 성공 여부 확인.
- [ ] **UI 검증**: 모델 로드 후 채팅창에 입력 시 정상 응답 확인.
- [ ] **에러 케이스**: 모델이 전혀 로드되지 않았을 때의 에러 응답이 "No model loaded" 등으로 명확한지 확인.
- [ ] **회귀 테스트**: `uv run pytest` (기존 기능 영향도 확인).

## 5. 단계별 실행 (SDD)
1. 명세(`specs/`) 수정 및 자산화.
2. `proxy.py` 백엔드 로직 수정.
3. `index.html` 프론트엔드 연동 수정.
4. 최종 통합 테스트 및 리포트 작성.
