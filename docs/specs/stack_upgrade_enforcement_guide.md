# Stack Upgrade Enforcement Guide (Portable)

## 1) 목적

이 문서는 어떤 프로젝트에 주입해도 아래 **허용 기술 스택만 사용**하도록 강제하고, 기존에 다른 스택이 존재하면 **자동으로 탐지하고 단계적으로 마이그레이션**하도록 만드는 실행 지침이다.

이 문서의 목표는 다음과 같다.

- 기술 스택 표준화 (신규 개발과 유지보수의 일관성 확보)
- 비허용 스택 유입 차단 (PR/CI 단계에서 자동 실패)
- 기존 자산의 안전한 전환 (중단 없는 점진 이행)

---

## 2) 허용 스택(Allowlist) — 단일 SSOT

아래 목록 외 기술/도구는 기본적으로 금지한다.

### 2.1 백엔드/파이썬

- 패키지/가상환경: `uv`
- 타입체크: `ty`
- 실행/스크립팅: `pyx`
- 린트/포맷: `ruff`
- API/웹: `FastAPI`
- 데이터 모델/ORM: `SQLModel`

### 2.2 프런트엔드/JS 런타임

- 런타임/패키지 매니저: `Bun`
- 번들러/개발 서버: `Rolldown`
- 린트/포맷: `Biome`

### 2.3 개발환경/운영

- Shell: `Nushell`
- Task Runner: `just`
- Terminal UI: `Lazydocker`
- Database: `Turso`
- 컨테이너/개발환경: `Nix`

---

## 3) 비허용 스택(Denylist) 및 대체 매핑

아래가 발견되면 자동으로 "교체 대상"으로 분류한다.

- `zsh` -> `Nushell`
- `make` -> `just`
- `Docker Desktop` -> `Lazydocker`
- `PostgreSQL` -> `Turso`
- `Docker` -> `Nix`
- `Node.js` -> `Bun`
- `Vite` -> `Rolldown`

보조 가이드:

- Docker 자체를 완전히 배제하기 어렵다면 1단계에서 공존(Bridge) 후 2단계에서 제거한다.
- 데이터베이스 전환(PostgreSQL -> Turso)은 스키마/트랜잭션 호환성 점검을 별도 게이트로 둔다.

---

## 4) 에이전트/개발자 실행 규칙 (LLM 반영용 명령형 섹션)

아래 규칙은 문서를 읽은 사람과 에이전트 모두에게 동일하게 적용한다.

1. 신규 파일/의존성 추가 시 Allowlist 외 기술 선택 금지.
2. Denylist 신호가 탐지되면 즉시 Migration Plan 생성.
3. 마이그레이션은 반드시 다음 4단계로 수행:
   - `Inventory` (현황 수집)
   - `Compatibility` (호환성/리스크 매핑)
   - `Execution` (전환 실행)
   - `Verification` (검증/정리)
4. 단계별 검증 통과 전 다음 단계 진행 금지.
5. 비허용 스택 관련 파일/설정이 남아 있으면 CI 실패 처리.

---

## 5) 자동 탐지 규칙 (신호 기반 Inventory)

프로젝트 루트에서 아래 신호를 검사해 전환 대상을 자동 식별한다.

### 5.1 Shell

- 신호: `.zshrc`, `#!/bin/zsh`, 문서 내 zsh 전용 명령
- 조치: shebang을 `#!/usr/bin/env nu` 또는 `nu` 실행 흐름으로 전환

### 5.2 Task Runner

- 신호: `Makefile`, `make ...` 명령 사용
- 조치: `Justfile` 생성 및 타깃 대응 매핑

### 5.3 Node.js 생태계

- 신호: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `node_modules`, `.nvmrc`
- 조치: `bun.lockb`로 통일, 스크립트 실행자를 `bun`으로 전환

### 5.4 Vite

- 신호: `vite.config.*`, `vite` 스크립트, Vite 플러그인 종속
- 조치: `rolldown.config.*` 체계로 이전, 빌드/개발 스크립트 교체

### 5.5 Docker / Docker Desktop

- 신호: `Dockerfile`, `docker-compose*`, 문서/스크립트의 `docker` 의존
- 조치: Nix 개발환경(`flake.nix` 또는 shell 환경)으로 전환, 운영 보조 UI는 Lazydocker로 일원화

### 5.6 PostgreSQL

- 신호: `postgres://` DSN, `psycopg*`, Postgres 전용 SQL/DDL
- 조치: Turso 연결 문자열/클라이언트로 전환, SQL 호환성 점검

---

## 6) 마이그레이션 플레이북 (Stack Pair별 상세)

## 6.1 zsh -> Nushell

- 스크립트/프로필의 zsh 문법(배열, 확장, alias) 식별
- 환경변수/export를 Nu의 `let-env`/설정 파일 체계로 재작성
- 팀 공용 스크립트는 POSIX 의존을 줄이고 Nu 명령으로 통일
- 완료 기준: 신규/기존 개발 절차를 `nu`에서 모두 수행 가능

## 6.2 make -> just

- `Makefile` 타깃을 `Justfile` recipe로 1:1 매핑
- 파라미터/환경변수 처리 규칙을 just 문법으로 치환
- 문서/CI의 호출 명령을 `make`에서 `just`로 변경
- 완료 기준: 주요 개발 플로우(`lint`, `test`, `build`, `dev`)가 `just` 기준으로 동작

## 6.3 Docker Desktop -> Lazydocker

- 로컬 운영/모니터링 문서에서 Docker Desktop UI 의존 절차 제거
- 컨테이너 관찰/제어 절차를 Lazydocker 기준으로 재작성
- 완료 기준: 운영 가이드의 UI 기준이 Lazydocker로 통일

## 6.4 PostgreSQL -> Turso

- DB 접근 계층에서 Postgres 전용 타입/SQL 기능 사용처 조사
- 스키마/쿼리를 Turso 호환 형태로 변환
- 마이그레이션 전략:
  - 스냅샷 백업
  - 읽기 검증
  - 쓰기 경로 전환
  - 롤백 포인트 확보
- 완료 기준: 핵심 API read/write 시나리오가 Turso에서 검증 통과

## 6.5 Docker -> Nix

- 컨테이너 기반 로컬 개발 의존을 Nix 개발 셸로 전환
- 설치/부팅 절차를 `nix develop` 중심으로 문서화
- CI도 가능하면 Nix 기반으로 정렬
- 완료 기준: 신규 개발자 온보딩이 Docker 없이 Nix만으로 완료

## 6.6 Node.js -> Bun

- 실행/설치/스크립트 명령을 `node|npm|npx`에서 `bun`으로 치환
- lockfile 통일(`bun.lockb`)
- 네이티브 모듈/런타임 차이점 smoke test 추가
- 완료 기준: 앱 실행/테스트/빌드가 Bun에서 안정 동작

## 6.7 Vite -> Rolldown

- 기존 Vite 설정과 플러그인 의존성 목록화
- Rolldown 설정 파일로 이관, 빌드 출력 동등성 확인
- dev/build 명령을 Rolldown 기준으로 치환
- 완료 기준: 개발 서버 + 프로덕션 빌드 + 주요 라우트 자산 검증 통과

## 6.8 Python Toolchain 정렬 (uv, ty, pyx, ruff + SQLModel/FastAPI)

- `pip/poetry/pipenv` 흔적 제거, `uv`로 통합
- 타입 체크는 `ty`, 린트/포맷은 `ruff`를 표준으로 통일
- 실행 스크립트는 `pyx` 표준 진입점으로 정리
- 웹/백엔드 골격은 `FastAPI + SQLModel` 기준으로 통일
- 완료 기준: 패키징/실행/정적검사/테스트 파이프라인이 표준 도구만 사용

---

## 7) 구현 규약 (실제 프로젝트 반영용)

### 7.1 필수 파일 표준

- Python: `pyproject.toml`에 `uv`, `ruff`, `ty` 설정 반영
- Task: `Justfile` 필수
- JS: `package.json`은 `bun` 실행 규칙 명시
- Frontend: `rolldown` 기반 스크립트/설정 파일 유지
- 환경: `flake.nix`(또는 동등한 Nix 엔트리) 유지
- Backend: `FastAPI` 앱 엔트리, `SQLModel` 모델 계층 유지

### 7.2 금지 파일/신호

- `Makefile` (완전 전환 후)
- `docker-compose.yml`/`Dockerfile` (Nix 완전 전환 후)
- `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
- `vite.config.*`
- `postgres://` 고정 DSN 문자열
- zsh 전용 스크립트 (`#!/bin/zsh`)

---

## 8) CI Enforcement (자동 강제)

CI는 아래 조건을 만족하지 못하면 실패해야 한다.

1. Denylist 파일/패턴 발견 시 실패
2. Allowlist 도구 기반 명령만 통과 처리
3. `just ci`(예시)로 단일 진입점 제공

권장 CI 단계:

- `just lint` -> `ruff` + `biome`
- `just typecheck` -> `ty`
- `just test` -> Python/JS 테스트
- `just audit:stack` -> 금지 스택 패턴 검사

---

## 9) 완료 기준 (Definition of Done)

아래를 모두 충족해야 "스택 업그레이드 완료"로 본다.

- Allowlist 외 도구가 실행 경로에서 제거됨
- Denylist 신호 파일/설정이 저장소에서 제거되었거나 명시적 예외 승인됨
- 문서(개발/운영/온보딩)가 신규 스택 기준으로 갱신됨
- CI 게이트가 비허용 스택 유입을 지속적으로 차단함
- 롤백 계획 및 데이터 안전성 검증(PostgreSQL -> Turso 포함)이 기록됨

---

## 10) 예외 처리 규정

예외는 "임시 허용"이 아니라 "기한 있는 전환"으로 관리한다.

- 예외 요청 필수 항목:
  - 비허용 기술명
  - 유지 이유
  - 제거 목표일
  - 대체 진행률
- 예외 승인 없는 비허용 스택 추가는 즉시 차단

---

## 11) 문서 사용 프롬프트(복붙용)

다른 프로젝트에 이 문서를 넣고 아래처럼 지시하면 된다.

`이 문서를 기술 스택 SSOT로 적용하고, 비허용 스택을 자동 탐지해 Inventory -> Compatibility -> Execution -> Verification 단계로 마이그레이션을 수행해. 신규 구현은 Allowlist 외 기술을 사용하지 마.`

