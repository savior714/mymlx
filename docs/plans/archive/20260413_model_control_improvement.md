# 구현 계획: 모델 로딩 제어 UI 개선 및 언로드 기능 추가

## 1. 개요
사용자가 모델 로드 여부를 명확히 인지하고, 필요 시 메모리에서 모델을 내릴 수 있도록 UI와 API를 개선합니다.

## 2. 목표
- 모델 선택 시 '로드' 버튼의 가시성 확보 및 직관적인 UX 제공.
- 명시적인 **모델 언로드(Unload)** API 및 UI 버튼 추가.
- 상단 배너를 통해 현재 활성 모델 상태를 상시 노출.

## 3. 상세 작업 내용

### 3.1. 스펙(Spec) 업데이트
- `specs/model_lifecycle.md`: `POST /v1/mlx/models/unload` 엔드포인트 정의 추가.
- `specs/ui.md`: 로드/언로드 버튼 배치 및 상태 표시 요구사항 최신화.

### 3.2. 백엔드(Backend) 구현
- `src/mlx_server/proxy.py`: `run_unload` 함수 추가 (ModelProvider의 모델을 해제).
- `src/mlx_server/app.py`: `/v1/mlx/models/unload` 라우트 추가.

### 3.3. 프론트엔드(Frontend) 개선
- `src/mlx_server/static/index.html`:
    - 모델 카드 내부에 '즉시 로드' 아이콘/버튼 추가.
    - 활성 모델 정보 영역에 **[언로드]** 버튼 추가.
    - 로드 중 상태를 더 명확히 표시.

## 4. 검증 계획
- [ ] `POST /v1/mlx/models/unload` 호출 후 `GET /v1/mlx/status`에서 모델이 비어있는지 확인.
- [ ] UI에서 모델 선택 후 로드 버튼이 즉시 반응하는지 확인.
- [ ] 언로드 버튼 클릭 후 메모리 상태 및 UI 배지 변화 확인.
- [ ] `uv run pytest`를 통한 기존 기능 회귀 테스트.

## 5. 일정
1. 스펙 수정 (즉시)
2. 백엔드 구현
3. 프론트엔드 구현
4. 최종 검증 및 보고
