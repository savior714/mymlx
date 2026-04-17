# Stack Upgrade Enforcement Policy (Portable)

## 목적

허용 스택(allowlist)과 비허용 스택(denylist) 기준으로 기술 스택 전환을 관리하는 포터블 정책 템플릿이다.

## 적용 범위

- 이 문서는 범용 템플릿이며, 저장소별 실제 런타임 계약은 아래 SSOT를 우선한다.
  - `PROJECT_RULES.md`
  - `docs/specs/api_compat.md`
  - `docs/specs/model_lifecycle.md`

## 핵심 정책

- allowlist 외 신규 기술 도입 금지
- denylist 신호 탐지 시 전환 계획 수립
- `Inventory -> Compatibility -> Execution -> Verification` 단계 준수
- CI에서 비허용 스택 유입 차단

## 비고

세부 전환 플레이북, 자동 탐지 규칙, 단계별 완료 기준은 팀 운영 정책으로 확장 관리한다.
