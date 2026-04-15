# 추론 감사 로그 (Inference Audit Log)

## 목적

크래시·OOM·업스트림 오류 이후 **다음 세션에서 샘플링·길이·동시성 등 옵션을 조정**할 수 있도록, 프롬프트 본문 없이 **구조화된 메타데이터**를 남긴다.

## 활성화

| 구성 | 설명 |
|------|------|
| CLI `--audit-log-path` | JSONL 파일 경로(추가 전용). 한 줄에 JSON 객체 하나. |
| CLI `--audit-snapshot-path` | 명시 스냅샷 경로. 생략 시 `--audit-log-path`가 있으면 동일 디렉터리에 `{stem}_last_request.json` 자동 생성. |
| 환경 변수 | `MLX_SERVER_AUDIT_LOG_PATH`, `MLX_SERVER_AUDIT_SNAPSHOT_PATH` |

둘 다 비활성화면 감사 기록을 쓰지 않는다.

## 상관 ID

다음 HTTP 헤더가 있으면 `request_id`로 사용한다(우선순위 순).

- `X-Request-ID`
- `X-Correlation-ID`
- `X-Trace-ID`

없으면 서버가 UUID를 생성한다.

## 스냅샷 파일 (`*_last_request.json`)

각 추론 요청 **시작 시** 덮어쓴다. 프로세스가 비정상 종료되어도 **마지막 요청의 유효 파라미터**를 남기기 위함이다. 민감 정보(프롬프트 텍스트)는 포함하지 않는다.

## JSONL 스키마 (`mlx_server.inference_audit.v1`)

각 레코드는 UTF-8 한 줄 JSON이다.

| 필드 | 설명 |
|------|------|
| `schema` | 고정: `mlx_server.inference_audit.v1` |
| `event` | `inference_complete` |
| `ts` | ISO8601 UTC 타임스탬프 |
| `request_id` | 상관 ID |
| `path` | 예: `/v1/chat/completions` |
| `model_resolved` | 프록시가 해석한 모델 경로/이름 |
| `upstream_status` | 업스트림 HTTP 상태 코드(알 수 있을 때) |
| `outcome` | `success` \| `upstream_error` \| `transport_error` \| `stream_interrupted` |
| `effective` | `mlx_lm.server`와 동일 규칙으로 병합한 요청 파라미터(샘플링·길이 등) |
| `prompt_stats` | `message_count`·`prompt_chars` 등(텍스트 길이 합, 내용 비저장) |
| `server_runtime` | 서버 프로세스의 MLX CLI 기본(동시성·KV 등) 일부 |

## 개인정보·보안

- **프롬프트·완성 텍스트는 기록하지 않는다.**
- 필요 시 운영 정책에 따라 로그 파일 접근 권한을 제한한다.

## 수용 기준 (AC)

- 감사 비활성화 시 동작·성능에 실질적 부담이 없다.
- JSONL는 파서 친화적으로 **한 줄 한 이벤트**이다.
- `effective` 병합 규칙은 `mlx_lm.server`의 요청 파싱과 일치한다.
