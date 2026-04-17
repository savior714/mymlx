# 2026-04-17 Stack Upgrade Inventory Checklist

## 1. 목적

`docs/specs/stack_upgrade_enforcement_guide.md`를 기준으로 현재 `mlx-server` 저장소의 정합성을 점검하고, 전환 항목을 `즉시 적용 / 예외 등록 / 보류`로 분류한다.

본 문서는 코드 변경 지시서가 아니라, **전환 우선순위와 승인 게이트를 정의하는 실행 체크리스트**다.

---

## 2. Inventory (현황)

### 2.1 현재 확인된 상태

- Python 도구체인: `uv`, `ruff`, `ty` 사용 중 (`pyproject.toml`, `verify.sh`)
- 웹 프레임워크: `Starlette` 기반 (`src/mlx_server/app.py`)
- 스크립트 실행: `bash` 기반 (`run.sh`, `run_models.sh`, `verify.sh`)
- Task Runner: `Justfile` 없음
- 프런트엔드 스택 파일: `package.json`, `vite.config.*` 등 없음
- Docker/Compose 파일: 없음
- DB(PostgreSQL) 신호: 없음

### 2.2 가이드 대비 핵심 갭

1. `zsh/bash -> Nushell` 전환 요구와 현재 `bash` 스크립트 불일치
2. `make -> just` 전환 요구와 `Justfile` 부재
3. `FastAPI + SQLModel` 강제 요구와 현재 `Starlette + 비DB` 구조 충돌
4. `CI stack enforcement`(denylist 탐지 실패 처리) 미구현

---

## 3. Compatibility (호환성/리스크)

### 3.1 즉시 적용 가능 (저위험)

- [x] **Stack Audit 스크립트 도입**
  - 범위: denylist 파일/패턴 탐지 (`Makefile`, `Dockerfile`, `vite.config.*`, `postgres://`, `#!/bin/zsh` 등)
  - 리스크: 낮음 (검사성 로직)
  - 완료 기준: 로컬/CI에서 audit 실행 시 위반 항목이 명확히 실패 처리됨

- [x] **`Justfile` 단일 진입점 도입**
  - 범위: `lint`, `typecheck`, `test`, `ci`, `audit:stack`
  - 리스크: 낮음 (기존 명령 래핑)
  - 완료 기준: 팀 표준 명령을 `just ci`로 실행 가능

- [x] **예외 레지스트리 문서 신설**
  - 범위: 가이드 강제 항목 중 프로젝트 특성상 즉시 미적용 항목을 기한 포함 등록
  - 리스크: 낮음
  - 완료 기준: 예외마다 `유지 이유/제거 목표일/대체 진행률` 존재

### 3.2 예외 등록 후 유지 (중위험)

- [ ] **`Starlette` 유지 예외**
  - 가이드 요구: `FastAPI`
  - 현재: Starlette 중심 아키텍처로 API 프록시 안정 운영 중
  - 리스크: 즉시 전환 시 라우팅/미들웨어/테스트 회귀 가능성
  - 정책: 명시적 예외로 등록 후 주기 재평가

- [ ] **`SQLModel` 비적용 예외**
  - 가이드 요구: `SQLModel`
  - 현재: DB 영속 계층이 핵심 요구사항이 아님
  - 리스크: 불필요한 구조 도입 시 복잡도 증가
  - 정책: DB 도입 스펙 승인 전까지 예외 유지

- [ ] **`pyx` 비적용 예외**
  - 가이드 요구: 실행/스크립팅 `pyx`
  - 현재: `uv run` 중심 실행 경로
  - 리스크: 전환 이득 불명확, 운영 문서 재작성 비용 발생
  - 정책: 실측 이득 확인 전 예외 유지

### 3.3 보류 (고위험, 별도 의사결정 필요)

- [ ] **`bash -> nushell` 전면 전환**
  - 영향: `run.sh`, `run_models.sh`, `verify.sh`, 보조 스크립트 전반
  - 선행조건: 팀 NuShell 운영 합의, CI/로컬 호환성 점검, 회귀 테스트
  - 승인 게이트: 운영자/개발자 온보딩 절차까지 Nu 기준 검증 완료

- [ ] **`Starlette -> FastAPI` 전환 검토**
  - 영향: 앱 엔트리/라우팅/예외 처리/테스트 재작성 가능성
  - 선행조건: 성능/생산성/호환성 이점이 정량적으로 입증될 것
  - 승인 게이트: API 호환성 회귀 테스트 100% 통과 + 성능 저하 없음

---

## 4. Execution (실행 순서)

### Phase 1 (즉시, 1~2일)

1. Stack Audit 검사 스크립트 추가
2. `Justfile` 추가 및 기존 검증 명령 매핑
3. 예외 레지스트리 문서 생성 (`Starlette`, `SQLModel`, `pyx`, `bash`)

### Phase 2 (단기, 1~2주)

1. CI에 `audit:stack` 게이트 연결
2. 예외 항목 만료일/재검토 주기 확정
3. 문서(`README`, 운영 가이드)에서 표준 실행 경로 일치화

### Phase 3 (중기, 30~90일)

1. `bash -> nushell` 전환 PoC (핵심 스크립트 1개)
2. `Starlette -> FastAPI` 전환 타당성 검토서 작성
3. 보류 항목의 유지/전환 최종 의사결정

---

## 5. Verification (검증 체크리스트)

- [x] `just ci` 기준으로 lint/typecheck/test가 통과한다.
- [x] `just audit-stack`에서 denylist 위반 시 실패한다.
- [x] 예외 항목이 문서화되어 있고 제거 목표일이 존재한다.
- [x] 신규 PR에서 allowlist 외 기술 유입 시 CI가 차단한다.
- [x] 운영 문서가 실제 실행 경로와 일치한다.

---

## 6. 최종 결정 필요 항목 (Owner 승인)

- [ ] 이 저장소에서 `FastAPI + SQLModel`을 강제 표준으로 적용할지, 프로젝트 범위 예외로 둘지 결정
- [ ] `bash -> nushell` 전면 전환의 시행 시점(즉시/차기 분기/미적용) 결정
- [ ] `pyx` 도입의 실익 검증 방식(벤치마크/운영성/학습비용) 결정

의사결정 전까지는 본 체크리스트의 `즉시 적용` 항목을 우선 실행하고, `예외 등록`으로 정책 충돌을 관리한다.
