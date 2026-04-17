# mlx-server — 프로젝트 규칙 (운영·스택 SSOT)

## 문서 메타 (Version SSOT)

| 항목 | 내용 |
|------|------|
| **Last Verified** | 2026-04-17 |
| **Python** | `>=3.12` (`pyproject.toml`) |
| **Min Supported** | SDD·`AGENTS.md` 가드레일 준수 |
| **Reference** | `README.md`, `AGENTS.md`, `specs/`, `docs/specs/tech_multi_agent_tooling.md`, `docs/CRITICAL_LOGIC.md` |

---

## 1. 프로젝트 목표

**공개 HTTP(Starlette/Uvicorn)** 로 OpenAI 스타일 API·모델 로드 엔드포인트를 제공하고, **MLX 추론은 `mlx_lm.server`의 루프백(`ThreadingHTTPServer`)으로 프록시**한다. 두 레이어의 책임을 분리하며, 동작·API·설정의 근거는 **`specs/`**에 둔다.

---

## 2. 기술 스택 (Tech Stack)

| 영역 | 선택 |
|------|------|
| 패키지 매니저 | **`uv`** (`pyproject.toml`, `uv.lock`) |
| HTTP 프레임워크 | **Starlette**, **Uvicorn** |
| MLX 추론 엔진 | **`mlx-lm`** (`mlx_lm.server` — 별도 스레드/루프백) |
| HTTP 클라이언트 | **httpx** (프록시·헬스 체크 등) |
| 설정 관리 | **PyYAML** + CLI·환경 변수 (우선순위: `specs/model_lifecycle.md`) |
| 테스트 프레임워크 | **pytest** (`tests/`) |
| 정적 분석 (dev) | **ruff** (lint), **ty** (타입 검사; 경고는 기본적으로 실패로 처리하지 않음) |

**플랫폼:** Apple Silicon + MLX 최적화. Windows/Linux 전용 가정은 두지 않는다.

---

## 3. 문서 SSOT 경계 (Documentation SSOT)

프로젝트 문서의 역할을 엄격히 분리하여 지식의 중복을 방지하고 신뢰성을 유지한다.

- **`PROJECT_RULES.md` (본 문서)**: "항상 지켜야 하는 규칙", "운영 프로토콜", "도구 사용 원칙" 등 **지속 규범**의 SSOT.
- **`docs/specs/` (요구사항/계약 SSOT)**: 기능·도메인·API의 **요구사항, 인터페이스, 수용 기준(AC)** 명세. 구현 전 선행 업데이트 필수(**SDD**).
- **`docs/CRITICAL_LOGIC.md` (결정/불변 SSOT)**: "왜 그렇게 했는지"에 대한 **핵심 설계 결정(대안/채택 이유)** 및 회귀 시 치명적인 **불변 정책** 기록.
- **`docs/memory/` (세션 지식 SSOT)**: 진행 상황, 작업 맥락 등 **세션성 정보** 저장.
  - **`MEMORY.md` (인덱스)**: **500라인 제한**. 링크와 최소 메타만 유지. **Anti-Drift**: 본문에 요약/기술 메모 작성 금지.
- **`docs/knowledge/` (외부 지식 자산)**: 웹 검색 결과 및 외부 기술 레퍼런스 자산화.

---

## 4. 디렉토리 역할 (Directory Structure)

| 경로 | 역할 |
|------|------|
| `src/mlx_server/` | `app.py`(엔트리), `handlers.py`(라우팅), `proxy.py`(프록시), `backend.py`(엔진), `request_transformer.py`(변환), `model_resolver.py`(검색), `memory_manager.py`(메모리) |
| `specs/` | API 호환성, 모델 수명주기, UI 계약 등 도메인 명세 |
| `docs/` | 프로젝트 지식 SSOT (specs, memory, CRITICAL_LOGIC 등) |
| `tests/` | pytest 테스트 스위트 |
| `scripts/` | 운영 및 검증 보조 스크립트 |

---

## 5. 아키텍처 및 API 규칙

### 5.1 네임스페이스 및 프록시
- **신규 API**는 `/v1/mlx/*` 네임스페이스를 우선 고려한다.
- `mlx-lm` 업스트림 코드를 직접 수정하기보다, **래퍼 및 프록시 레이어**에서 문제를 해결하는 것을 지향한다.

### 5.2 SDD (Spec-Driven Design)
- 모든 기능 및 호환성 변경은 구현 전에 `docs/specs/` 또는 `specs/` 하위 명세를 선행 업데이트한다.
- 라이브러리(Starlette, MLX-LM 등)의 공식 문서와 프로젝트 명세를 항상 교차 확인한다.

---

## 6. 개발 및 운영 프로토콜 (Standard Protocols)

### 6.1 파일 읽기 및 경로 검증 (File & Path Protocol)
- **File-Read-Once**: `read_file` 사용 시 `offset/limit`을 통한 분할 읽기를 금지하고, 단일 호출로 전체 맥락을 파악한다.
- **Path Verification**: 파일 수정 전 `list_files`로 존재 여부를 확인하며, 모든 경로는 **프로젝트 루트 기준 상대 경로(Full Relative Path)**를 사용한다.
- **MCP-First**: `AGENTS.md`, `PROJECT_RULES.md` 등 핵심 규칙 파일 접근 시 `mcp--filesystem--read_text_file` 도구를 우선 사용한다.

### 6.2 Pre-Guard (코드 작성 전 자가 검증)
- **Starlette 라우팅 순서**: 정적 경로(Static Route)를 동적 경로(Path Parameter)보다 항상 상단에 배치하여 오매칭을 방지한다.
- **레이어 분리**: `proxy.py`나 `backend.py`의 인프라 로직과 `app.py`의 인터페이스 로직을 명확히 구분한다.

### 6.3 리팩터링 가드레일
- 단일 소스 파일이 **500라인을 초과**하면 즉시 하위 모듈로 분리한다.

---

## 7. 검증 프로토콜 (Verification)

### 7.1 단계별 검증
- 모든 코드 변경 후에는 저장소 루트에서 **`./verify.sh`**를 실행하여 안정성을 증명한다(순서: **`uv run ruff`** → **`uv run ty`** → **`uv run pytest`**; 앞 단계 실패 시 이후 단계는 생략).
- 결과 요약은 **`verify-last-result.json`**을 읽는다. 실패 시 단계별 로그는 **`verify-ruff-failures.txt`** / **`verify-ty-failures.txt`** / **`verify-pytest-failures.txt`** 중 해당 파일을 본다.

### 7.2 완료 보고 (Verify Report)
사용자에게 보고 시 아래 항목을 포함한다:
- **변경 파일**: 수정/생성된 파일 목록
- **테스트 결과**: 실행 범위 및 pytest 성공 여부
- **리스크/후속**: 잔여 과제 및 다음 세션 가이드

---

## 8. 도구 실패 및 루프 방지 (Self-Correction)

- **Loop Prevention**: 동일 인자로 무분별한 재시도를 금지한다.
- **Error Analysis**: 에러 메시지를 기술적으로 해석하여 원인을 분석하고, 동일 오류가 **2회 지속 시 전략 변경**, **3회 지속 시 즉시 중단 및 보고**한다.

---

## 9. 웹 검색 정책 (Web Search Policy)

- **MCP-First Search**: 웹 검색 시 `mcp--ddg-search--search` 및 `fetch_content` 도구를 자동으로 사용한다.
- **Latest Doc Protocol**: 신규 라이브러리 도입 시 프로젝트 명세와 공식 문서를 교차 확인하며, 검색 결과는 `docs/knowledge/`에 자산화한다.

---

## 10. 문서 인코딩 및 안전 관리
- 모든 문서는 **UTF-8 (BOM 없음)**을 유지한다.
- 셸 리다이렉션(`>`)을 통한 파일 생성을 금지하며, 반드시 에이전트 전용 `write_to_file` 도구를 사용하여 인코딩 오염(Mojibake)을 방지한다.

