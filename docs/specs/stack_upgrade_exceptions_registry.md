# Stack Upgrade Exceptions Registry

## 목적

`docs/policies/stack_upgrade_exceptions_policy.md`의 관리 원칙에 따라, 현재 저장소의 비허용 스택 예외를 기한 기반으로 추적한다.

## 공통 필드

- 비허용 기술명
- 유지 이유
- 제거 목표일
- 대체 진행률
- 다음 재검토일
- 오너

## 활성 예외 목록

### EXC-001: Starlette 유지

- 비허용 기술명: `Starlette` (가이드 요구: `FastAPI`)
- 유지 이유: 현재 API 프록시 라우팅/미들웨어 경로가 Starlette 기준으로 안정 운영 중이며 즉시 전환 시 회귀 리스크가 큼
- 제거 목표일: 2026-07-31
- 대체 진행률: 10% (전환 타당성 검토 범위 정의 완료)
- 다음 재검토일: 2026-05-15
- 오너: Platform

### EXC-002: SQLModel 비적용

- 비허용 기술명: `SQLModel`
- 유지 이유: 현재 서비스 요구사항에 DB 영속 계층이 핵심이 아니며 도입 시 복잡도만 증가
- 제거 목표일: 2026-08-31
- 대체 진행률: 0% (DB 도입 스펙 미승인)
- 다음 재검토일: 2026-05-15
- 오너: Platform

### EXC-003: pyx 비적용

- 비허용 기술명: `pyx`
- 유지 이유: `uv run` 기반 실행 체계가 이미 정착되어 있고 전환 이득이 정량화되지 않음
- 제거 목표일: 2026-09-30
- 대체 진행률: 0% (벤치마크 계획 전)
- 다음 재검토일: 2026-05-15
- 오너: Platform

### EXC-004: bash 스크립트 유지

- 비허용 기술명: `bash` (가이드 요구: `Nushell`)
- 유지 이유: 운영 스크립트가 bash에 맞춰 검증되어 있으며 팀 공통 NuShell 온보딩/CI 호환성 검토가 선행되어야 함
- 제거 목표일: 2026-08-15
- 대체 진행률: 5% (대상 스크립트 인벤토리 완료)
- 다음 재검토일: 2026-05-15
- 오너: Platform

## 참조

- 정책 본문: `docs/policies/stack_upgrade_exceptions_policy.md`
- 관련 정책: `docs/policies/stack_upgrade_enforcement_policy.md`
