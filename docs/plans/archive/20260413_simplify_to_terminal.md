# [Plan] 웹 UI 제거 및 터미널 중심의 헤드리스 API 서버로의 전환

## 1. 개요
현재 `mlx-server`는 Starlette 기반의 HTTP 서버를 통해 OpenAI 호환 API와 함께 브라우저 기반의 웹 UI(`/ui`)를 제공하고 있습니다. 사용자의 요청에 따라 복잡한 웹 UI 관련 기능을 모두 제거하고, 터미널 환경에서 최소한의 기능(API 서버 및 향후 CLI 입출력)만 지원하는 구조로 단순화합니다.

## 2. 변경 사항 요약

### 2.1 UI 관련 자산 제거
- [x] `src/mlx_server/static/` 디렉토리 및 `index.html` 삭제
- [x] `src/mlx_server/app.py`에서 `/ui` 관련 라우트, `RedirectResponse`, `StaticFiles` 설정 제거

### 2.2 API 서버 단순화 (Headless 전환)
- [x] `src/mlx_server/app.py`에서 UI 전용 API(`/v1/mlx/finder/*`) 제거
- [x] `src/mlx_server/app.py`에서 `local` 모델 목록 조회는 CLI에서도 유용할 수 있으므로 유지하되, UI 친화적인 필드 정리
- [x] 서버 기동 시 출력되는 로그에서 UI 접속 안내(`http://.../ui/`) 제거

### 2.3 CLI 개선
- [x] `mlx-server serve` 명령어의 도움말 및 로그 메시지에서 웹 UI 언급 삭제
- [ ] (향후 과제) 터미널 내에서 직접 추론 결과물을 볼 수 있는 `chat` 명령어 추가 기반 마련

### 2.4 명세 및 문서 업데이트
- [x] `specs/ui.md`: 사용 중단(Deprecated/Removed) 표시
- [x] `docs/CRITICAL_LOGIC.md`: UI 제거 및 헤드리스 아키텍처 채택 기록
- [x] `README.md`: 웹 UI 관련 설명 제거 및 API 서버 중심으로 설명 수정

## 3. 구현 단계 (Tasks)

1.  **[Doc]** `docs/CRITICAL_LOGIC.md`에 UI 제거 결정 기록
2.  **[File]** UI 파일 및 디렉토리 삭제 (`src/mlx_server/static/`)
3.  **[Code]** `src/mlx_server/app.py` 리팩토링 (UI 라우트 및 macOS 전용 Finder API 제거)
4.  **[Code]** `src/mlx_server/cli.py` 리팩토링 (로그 및 도움말 수정)
5.  **[Spec]** `specs/ui.md` 업데이트 (Deprecated 안내)
6.  **[Doc]** `README.md` 업데이트
7.  **[Test]** `uv run pytest`로 기존 API 기능 유지 확인

## 4. 수용 기준 (AC)
- `http://localhost:port/ui/` 접속 시 404가 발생하거나 더 이상 페이지가 로드되지 않음.
- API 서버(`status`, `load`, `unload`, `proxy`)는 여전히 정상 동작함.
- 서버 로그 및 도움말에서 웹 UI에 대한 언급이 없음.
