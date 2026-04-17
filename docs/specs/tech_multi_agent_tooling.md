# Multi-Agent Tooling Guidelines (범용 도구 사용 SSOT)

## 문서 메타 (Version SSOT)
- **Last Verified**: 2026-04-17
- **Purpose**: 여러 에이전트(Antigravity, Roo Code, Cursor) 공통 도구 사용 정책 및 가이드
- **Reference**: `AGENTS.md`, `PROJECT_RULES.md`

## 문서 경계(SSOT)
- **규칙/운영**: `PROJECT_RULES.md`
- **결정/핵심 불변**: `docs/CRITICAL_LOGIC.md`
- **요구사항/계약**: `docs/specs/`
- **세션 지식**: `docs/memory/`

---

## 개요

본 문서는 **Google Antigravity**, **VS Code (Roo Code/Cline)**, **Cursor AI** 등 멀티 에이전트 환경에서 동일한 프로젝트를 개발할 때, 도구 사용의 일관성을 유지하고 SSOT(Single Source of Truth)를 보호하기 위한 가이드라인을 제공합니다.

---

## 에이전트별 최적화 및 도구 매핑

### 1. 도구 매핑 테이블 (공통 기능)

| 기능 유형 | Antigravity | Roo Code (VS Code) | Cursor AI | 공통 MCP (권장) |
|-----------|-------------|--------------------|-----------|------------------|
| **파일 읽기** | `view_file` | `read_file` | `ReadFile` | `user-serena`/`user-filesystem` 읽기 도구 |
| **파일 수정** | `replace_file_content` | `apply_diff` | `ApplyPatch`/편집 도구 | 서버별 편집 도구 |
| **파일 생성** | `write_to_file` | `write_to_file` | 파일 생성 도구 | 서버별 쓰기 도구 |
| **경로 확인** | `list_dir` | `list_files` | `Glob`/디렉터리 조회 | `list_directory` 계열 |
| **터미널** | `run_command` | `execute_command` | `Shell` | `execute_command` 계열 |

### 2. 에이전트별 특이사항

#### Google Antigravity
- **특징**: 강력한 Sequential Thinking 기반 설계 분석 수행.
- **팁**: `view_file` 시 800라인 제한이 있으므로, 큰 파일은 `grep_search`로 먼저 탐색하십시오.

#### VS Code - Roo Code (with Qwen 35B Local)
- **모델**: **Qwen 2.5/3.5 35B** 등의 로컬 모델 활용.
- **최적화**: 로컬 모델의 컨텍스트 한계를 고려하여, 한 번에 읽는 파일 범위를 최소화하고 태스크를 원자적(Atomic)으로 쪼개어 작업하십시오.
- **설정**: `.roo-code.json` (로컬 전용) 을 통해 도구 제어 가능.

#### Cursor AI
- **특징**: 'Composer' 모드를 통한 다중 파일 동시 수정 지원.
- **설정**: `.cursor/mcp.json`에 MCP 서버를 등록하여 모든 에이전트와 동일한 도구 셋을 공유하십시오.

---

## 공통 MCP 도구 사용 규약

에이전트 간의 도구 불일치를 줄이기 위해, 가능한 경우 **`.mcp.json`**에 정의된 공통 MCP 서버를 사용합니다.

1. **`user-ddg-mcp-search`**: 웹 검색(DuckDuckGo). 모든 에이전트에서 동일한 검색 소스를 사용합니다.
2. **`user-sequentialthinking`**: 설계/분석 작업 전 사고 단계를 문서화합니다.
3. **`user-filesystem` / `user-serena`**: 파일 탐색 및 코드 컨텍스트 분석의 공통 기반으로 사용합니다.

### 2.1 필수 강제 규칙 (실행 규약)

1. **Sequential Thinking Mandatory**: 작업 시작 전에 `sequentialthinking`을 반드시 실행하고, 최소 10단계 분석을 수행합니다.
2. **Path Verification**: 수정 전 반드시 경로 존재를 검증합니다.
3. **SSOT 우선 반영**: 규칙 변경은 `PROJECT_RULES.md`, 요구사항/계약 변경은 `docs/specs/`, 핵심 결정은 `docs/CRITICAL_LOGIC.md`에 반영합니다.
4. **Verify 필수**: 코드 변경 시 보고 전에 `./verify.sh` 결과를 기준으로 검증 상태를 기록합니다.

---

## 멀티 에이전트 작업 주의사항

1. **파일 락(File Lock)**: 여러 에이전트가 동시에 같은 파일을 수정하지 않도록 세션을 관리하십시오.
2. **상태 동기화**: 한 에이전트가 작업을 마친 후에는 반드시 `MEMORY.md` 및 `project_changelog_*.md`를 업데이트하여 다른 에이전트가 변경 사항을 즉시 알 수 있게 하십시오.
3. **경로 정규화**: `ENOENT` 방지를 위해 프로젝트 루트 기준 경로 규칙을 일관되게 사용하십시오.
4. **동시 수정 방지**: 대규모 변경 전 대상 파일을 명시적으로 선언하고, 완료 후 즉시 해제합니다.
5. **충돌 우선순위**: 규칙 충돌 시 `AGENTS.md`와 `PROJECT_RULES.md`를 최우선으로 따릅니다.

---

## 관련 문서
- [`AGENTS.md`](../../AGENTS.md) - 에이전트 행동 지침
- [`PROJECT_RULES.md`](../../PROJECT_RULES.md) - 프로젝트 운영 규칙
- [`docs/knowledge/mcp_configuration.md`](../../knowledge/mcp_configuration.md) - MCP 서버 상세 설정
