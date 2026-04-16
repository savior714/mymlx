# Knowledge: run.sh 메인 메뉴 2번(Options) 상세 가이드

## §1. 메타 정보
- **Last Verified**: 2026-04-15
- **Author**: mlx-server Team
- **Category**: TUI Option Tuning
- **Source of Truth**: `run.sh`의 `menu_options()`

## §2. 범위 및 해석 기준

이 문서는 `run.sh` 실행 후 메인 메뉴에서 **`2. Options`**를 선택했을 때 표시되는 **1~32번 항목 전체**를 설명한다.

- 기준 버전: `run.sh`의 `menu_options()` 구현
- 목적: "옵션의 기술적 의미", "값 조절 시 기대 변화", "권장 튜닝 순서"를 운영 관점에서 정리
- 주의: 최적값은 모델 크기, 컨텍스트 길이, 동시 요청 패턴에 따라 달라진다.

---

## §3. 빠른 튜닝 우선순위

처리량(TPS)과 안정성을 함께 맞추려면 아래 순서가 안전하다.

1. `10 Decode Concurrency`
2. `11 Prompt Concurrency`
3. `12 Prefill Step Size`
4. `15 Prompt Cache Bytes`
5. `13 Metal Memory Limit` / `14 Metal Cache Limit`
6. `18 KV Cache Bits` / `19 KV Group Size`
7. `23 Cache Headroom Ratio`

---

## §4. 옵션 상세(1~32)

### 1) Host (`LISTEN_HOST`)
- **기술 의미**: 서버 바인딩 주소(접근 범위/보안 경계 결정).
- **값 상향/확장 효과**: `0.0.0.0`으로 두면 외부 기기 접근 가능.
- **값 하향/제한 효과**: `127.0.0.1`이면 로컬 전용으로 노출 최소화.
- **성능 영향**: TPS 직접 영향은 거의 없음.
- **권장**: 개발 기본은 `127.0.0.1`, 내부망 공유가 필요할 때만 `0.0.0.0`.

### 2) Port (`LISTEN_PORT`)
- **기술 의미**: HTTP 수신 포트.
- **변경 효과**: 다른 서비스와 포트 충돌 회피, 다중 서버 병행 운영 가능.
- **성능 영향**: 실질 TPS 영향 없음.
- **권장 범위**: 1024~65535, 흔한 값은 `8080`, `3000`, `18080`.

### 3) Temperature (`USER_TEMP`)
- **기술 의미**: 샘플링 무작위성(다양성) 강도.
- **상향 효과**: 창의성/다양성 증가, 결과 변동성 증가.
- **하향 효과**: 재현성/일관성 증가.
- **권장 시작점**: 코드/정확성 작업 `0.0~0.3`, 일반 대화 `0.2~0.7`.

### 4) Max Tokens (`USER_MAX`)
- **기술 의미**: 요청 1회 생성 토큰 상한.
- **상향 효과**: 장문 응답 완결성 증가.
- **하향 효과**: 지연/OOM 리스크 완화.
- **권장**: 기본은 보수적으로, 장문이 필요할 때만 단계적으로 증가.

### 5) Top-P (`USER_TOP_P`)
- **기술 의미**: 누클리어스 샘플링 컷오프.
- **상향 효과**: 후보 폭 증가로 다양성 상승.
- **하향 효과**: 보수적/안정적 출력.
- **권장**: `0.8~1.0` 범위에서 `temperature`와 함께 조정.

### 6) Top-K (`USER_TOP_K`)
- **기술 의미**: 상위 K 후보만 샘플링.
- **상향 효과**: 표현 다양성 증가 가능.
- **하향 효과**: 패턴 안정화.
- **권장**: `0`(비활성) 또는 `20~100` 실험.

### 7) Adapter Path (`USER_ADAPTER`)
- **기술 의미**: LoRA/Adapter 가중치 경로.
- **설정 효과**: 특정 도메인 성능 향상 가능.
- **주의**: 어댑터 품질/호환성에 따라 지연/품질이 달라질 수 있음.

### 8) Log Level (`USER_LOG`)
- **기술 의미**: 런타임 로그 상세도.
- **상향(DEBUG) 효과**: 진단 정보 증가.
- **하향(ERROR) 효과**: 로그 오버헤드 감소.
- **권장**: 평시 `INFO`, 이슈 분석 시 `DEBUG`.

### 9) Prompt Cache Size (`USER_PROMPT_CACHE_SIZE`)
- **기술 의미**: 캐시 엔트리 개수 상한.
- **상향 효과**: 반복 요청 히트율 개선 가능.
- **하향 효과**: 메타데이터 부담 감소.
- **연계 옵션**: `15 Prompt Cache Bytes`와 함께 봐야 실제 메모리 사용이 맞춰짐.

### 10) Decode Concurrency (`USER_DECODE_CONCURRENCY`)
- **기술 의미**: 디코드(생성) 단계 병렬 처리 수.
- **상향 효과**: 총 TPS 상승 가능성이 가장 큼.
- **하향 효과**: 안정성 개선, OOM/abort 리스크 감소.
- **운영 권장**: `1 -> 2 -> 4 -> 8` 식으로 단계 상승, 실패 시 한 단계 롤백.

### 11) Prompt Concurrency (`USER_PROMPT_CONCURRENCY`)
- **기술 의미**: prefill(입력 인코딩) 병렬 처리 수.
- **상향 효과**: 긴 입력 다건 처리량 개선.
- **하향 효과**: 피크 메모리 압력 완화.
- **권장**: 긴 컨텍스트가 많을 때 `2~4`부터 점검.

### 12) Prefill Step Size (`USER_PREFILL_STEP_SIZE`)
- **기술 의미**: prefill 청크 크기.
- **상향 효과**: 처리 효율 향상 가능, 대신 피크 메모리 증가 가능.
- **하향 효과**: 메모리 피크 완화, 오버헤드 증가 가능.
- **권장**: 기본 `2048`에서 `1024/4096` 비교 실험.

### 13) Metal Memory Limit (`USER_METAL_MEMORY_LIMIT`)
- **기술 의미**: MLX Wired 메모리 상한.
- **상향 효과**: 대형 모델/긴 컨텍스트 여유 증가.
- **하향 효과**: OS/다른 앱 여유 확보.
- **입력 형식**: `96GB`, `512MB`처럼 단위 필수.

### 14) Metal Cache Limit (`USER_METAL_CACHE_LIMIT`)
- **기술 의미**: Metal 임시 캐시 상한.
- **상향 효과**: 재할당 감소로 속도 안정 가능.
- **하향 효과**: 메모리 회수 빨라져 OOM 완화.
- **권장**: `4GB -> 6GB -> 8GB` 식 단계 조정.

### 15) Prompt Cache Bytes (`USER_PROMPT_CACHE_BYTES`)
- **기술 의미**: KV/Prompt 캐시 총 바이트 상한.
- **상향 효과**: 캐시 히트율/반복 응답 속도 개선 가능.
- **하향 효과**: 피크 메모리 급증 방지.
- **운영 팁**: 모델 크기와 동시성에 맞춰 `12GB~24GB`에서 시작.

### 16) Advanced Cache (`USER_ADVANCED_CACHE`)
- **기술 의미**: 고급 캐시 엔진 ON/OFF 토글.
- **ON 효과**: 반복/유사 요청에서 재사용 효율 개선 가능.
- **OFF 효과**: 동작 단순화, 디버깅/재현성에 유리할 수 있음.
- **권장**: 반복 프롬프트 워크로드면 ON, 문제 추적 시 OFF 비교.

### 17) Paged Cache Size (`USER_PAGE_SIZE`)
- **기술 의미**: 캐시 페이지 단위(토큰).
- **작게 설정 효과**: 재사용 정밀도 증가.
- **크게 설정 효과**: 관리 오버헤드 감소.
- **권장**: 기본 `128`, 유사 요청이 매우 많으면 `256` 테스트.

### 18) KV Cache Bits (`USER_KV_BITS`)
- **기술 의미**: KV 캐시 양자화 비트폭(4/8/Off).
- **4bit 효과**: 메모리 절감 최대, 품질 저하 가능성 있음.
- **8bit 효과**: 절감과 품질의 균형.
- **Off 효과**: 품질 우선, 메모리 부담 큼.
- **권장**: 메모리 압력/중단 이슈가 있으면 8bit부터 적용, 필요 시 4bit.

### 19) KV Group Size (`USER_KV_GROUP_SIZE`)
- **기술 의미**: KV 양자화 그룹 크기.
- **작게 설정 효과**: 품질/정밀도 유리.
- **크게 설정 효과**: 압축 효율 유리.
- **권장**: `kv-bits=8` 기준 `32`와 `64` 비교.

### 20) Cache Grace Secs (`USER_CACHE_GRACE_SECONDS`)
- **기술 의미**: cold 블록 최소 보존 시간(초).
- **상향 효과**: 재사용 기회 증가.
- **하향 효과**: 빠른 회수로 메모리 압박 완화.
- **권장 시작점**: `10~30`초.

### 21) Prompt Normalize (`USER_PROMPT_NORMALIZATION`)
- **기술 의미**: 입력 공백/개행 정규화 토글.
- **ON 효과**: 캐시 키 일관성 증가, 히트율 개선 가능.
- **OFF 효과**: 원문 형태 보존.
- **권장**: 캐시 히트율 개선 목적이면 ON 실험.

### 22) Cache Observability (`USER_CACHE_OBSERVABILITY`)
- **기술 의미**: 캐시 진단 로그 토글.
- **ON 효과**: 병목/축출 원인 분석에 유리.
- **OFF 효과**: 로그 오버헤드 최소화.
- **권장**: 튜닝/장애 분석 시 ON, 순수 성능 운영 시 OFF.

### 23) Cache Headroom (`USER_CACHE_HEADROOM_RATIO`)
- **기술 의미**: 메모리 압박 상황에서 목표 여유 비율.
- **낮게 설정 효과**: 안정성 상승, 캐시 보존량 감소.
- **높게 설정 효과**: 캐시 보존량 증가 가능, 압박 리스크 증가.
- **권장 범위**: `0.70 ~ 0.90`.

### 24) Light Benchmark (Run)
- **기술 의미**: 1회 요청 실측 후 50K 토큰 시간을 환산.
- **출력 지표**: E2E TPS, 50K 예상 소요 시간.
- **용도**: 빠른 기준선 확인.

### 25) Stream TPS Compare (Run)
- **기술 의미**: `stream=true`로 Decode TPS와 E2E TPS 분리 측정.
- **출력 지표**: prefill, decode_tps, e2e_tps, 50K 환산.
- **용도**: "첫 토큰 지연 vs 생성 구간 속도" 분리 분석.

### 26) 5x Summary Bench (Run)
- **기술 의미**: 24 또는 25 시나리오를 5회 반복해 min/avg/max 통계 제공.
- **용도**: 단일 측정 편차를 줄인 운영값 결정.

### 27) Speculative Decoding (`USER_SPECULATIVE_DECODING`)
- **기술 의미**: 추측 디코딩(Speculative Decoding) 사용 여부 토글.
- **ON 효과**: Draft(소형) 모델이 토큰 후보를 빠르게 생성하고 Target(대형) 모델이 한 번의 forward pass로 검증/수정. 코딩, 보일러플레이트 등 예측 가능한 패턴에서 생성 속도 크게 향상 가능.
- **OFF 효과**: 표준 디코딩 사용. Continuous batching(동시 요청 배칭) 가능.
- **주의**: ON 시 `is_batchable = False`가 설정되어 **continuous batching이 자동 비활성화**된다. 동시 다수 요청 환경에서는 처리량이 오히려 저하될 수 있다.
- **연계 옵션**: 반드시 `28 Draft Model Path`를 함께 설정해야 동작. `29 Num Draft Tokens`로 후보 수 조절.

### 28) Draft Model Path (`USER_DRAFT_MODEL`)
- **기술 의미**: Speculative Decoding에 사용할 소형 Draft 모델 경로.
- **입력 형식**: 로컬 절대 경로(예: `~/Desktop/models/Qwen3-1.7B-4bit`) 또는 HF Repo ID.
- **호환성 조건**: Target 모델과 **동일한 `vocab_size`를 가진 토크나이저**를 공유해야 함. 불일치 시 생성 품질 심각히 저하.
- **권장 크기**: Target 크기의 1/10~1/30. 예: 30B Target → 1~3B Draft(4-bit 기준 ~0.5~2GB 추가 메모리).
- **성능 영향**: Draft 모델이 너무 크면 forward pass 비용이 높아져 이점이 감소.

### 29) Num Draft Tokens (`USER_NUM_DRAFT_TOKENS`)
- **기술 의미**: Draft 모델이 한 스텝에서 생성할 후보 토큰 수.
- **상향(16~20) 효과**: 코딩/보일러플레이트 등 예측 가능한 패턴에서 수락률이 높아 속도 이점 극대화.
- **하향(3~5) 효과**: 짧은 응답, 비정형 추론, 큰 Draft 모델(>7B)에서 overhead 감소.
- **기본값**: `3`.
- **권장 범위**: 코딩 `16~20`, 복잡 추론 `8~12`, 짧은 응답/큰 Draft `3~5`.

### 30) Chat Template Args (`USER_CHAT_TEMPLATE_ARGS`)
- **기술 의미**: 토크나이저의 `apply_chat_template`에 전달할 JSON 인자.
- **대표 설정**: `{"enable_thinking":true}` → 모델의 reasoning/thinking 모드 활성화(Qwen3 등 지원 모델).
- **`enable_thinking: false`**: thinking 비활성화하여 빠르고 간결한 응답.
- **빈 값(`{}`)**: 모델 기본 템플릿 동작 유지.
- **성능 영향**: thinking 모드 ON 시 출력 토큰 수 증가(내부 추론 토큰 포함)로 총 지연 증가 가능. 품질은 향상될 수 있음.
- **입력 형식**: 유효한 JSON 문자열 필수. 잘못된 형식 입력 시 거부.

### 31) Tool Choice Default (`USER_TOOL_CHOICE_DEFAULT`)
- **기술 의미**: 클라이언트가 `tool_choice`를 지정하지 않았을 때 프록시 레이어에서 주입하는 기본값.
- **`auto`(기본)**: 모델이 tool 호출 여부를 자율 판단. OpenAI API 기본 동작과 동일.
- **`none`**: tool 호출을 하지 않고 텍스트만 생성. tools 배열이 있어도 무시.
- **`required`**: 반드시 하나 이상의 tool을 호출. 에이전트 워크플로우에서 tool 호출을 강제할 때 사용.
- **적용 조건**: 요청 바디에 `tools` 배열이 존재하고 `tool_choice`가 없을 때만 주입. `tools`가 없는 일반 채팅 요청에는 영향 없음.
- **프록시 동작**: `request_transformer.py`에서 chat completion 요청을 변환할 때 `data["tool_choice"]`를 설정.
- **CLI 플래그**: `--tool-choice-default auto|none|required`
- **환경 변수**: `MLX_SERVER_TOOL_CHOICE_DEFAULT`

### 32) MCP Config Path (`USER_MCP_CONFIG_PATH`)
- **기술 의미**: MCP(Model Context Protocol) 설정 JSON 파일 경로. 서버가 이 파일을 `GET /v1/mlx/mcp-config` 엔드포인트로 노출하여 클라이언트 측 tool 통합을 지원.
- **설정 시 효과**: 클라이언트(Cursor, Continue, 커스텀 에이전트 등)가 해당 엔드포인트를 조회하여 MCP 서버 목록/도구 정보를 자동으로 가져갈 수 있음.
- **미설정 시**: 엔드포인트가 `configured: false`를 반환.
- **입력 형식**: 파일 경로 (예: `~/.mcp.json`, `~/projects/my-agent/.mcp.json`). `~`는 자동 확장.
- **유효성 검증**: 파일 존재 여부를 TUI에서 경고(존재하지 않아도 설정 가능). API 호출 시 JSON 파싱 실패는 422 응답.
- **CLI 플래그**: `--mcp-config-path PATH`
- **환경 변수**: `MLX_SERVER_MCP_CONFIG_PATH`
- **API 응답 예시**:
  ```json
  {
    "configured": true,
    "path": "/Users/user/.mcp.json",
    "config": { "mcpServers": { ... } }
  }
  ```

---

## §5. 실전 튜닝 시나리오

### 시나리오 A: OOM/SIGABRT가 자주 발생
1. `10 Decode Concurrency` 하향
2. `11 Prompt Concurrency` 하향
3. `18 KV Cache Bits`를 8bit(필요 시 4bit)
4. `15 Prompt Cache Bytes` 하향
5. `14 Metal Cache Limit` 하향 또는 `13 Metal Memory Limit` 재조정

### 시나리오 B: TPS를 더 올리고 싶음
1. `10 Decode Concurrency` 단계 상승
2. `11 Prompt Concurrency` 단계 상승
3. `12 Prefill Step Size` 비교(2048/4096)
4. `16 Advanced Cache=ON`, `21 Prompt Normalize=ON`
5. `24/25/26`으로 수치 재검증

### 시나리오 C: Speculative Decoding으로 단일 요청 속도 극대화
1. `27 Speculative Decoding` ON
2. `28 Draft Model Path`에 Target과 동일 계열 소형 모델 설정 (예: Qwen3-1.7B-4bit)
3. `29 Num Draft Tokens`를 `16`으로 시작 (코딩 워크로드 기준)
4. `10 Decode Concurrency`는 `1`로 제한 (배칭 불가이므로 무의미)
5. 로그에서 수락률(α) 확인 → α < 0.5이면 Num Draft Tokens 하향 또는 Draft 모델 교체
6. 다수 동시 요청이 필요하면 OFF로 전환하고 decode concurrency 복원

### 시나리오 D: 응답 품질 저하가 체감됨
1. `18 KV Cache Bits`를 8bit 또는 Off로 상향
2. `19 KV Group Size`를 더 작게
3. 샘플링(`3/5/6`)을 보수적으로 재설정

---

## §6. 저장/반영 동작

- `Options`에서 변경한 값은 `B`로 빠져나갈 때 `save_config()`를 통해 `~/.mlx-server/config`에 저장된다.
- 실제 서버 실행 시 `start_server()`가 저장 값을 CLI 인자로 구성해 `uv run mlx-server serve ...`에 주입한다.
- 즉, **옵션 변경 -> 저장 -> Run Model 재실행**이 반영의 기본 루프다.

---

## §7. MacBook 128GB + 45~50GB Q4 모델 권장값

아래는 **Apple Silicon 128GB 통합 메모리** 환경에서, **45~50GB급 Q4 모델**을 주력으로 올리는 상황을 가정한 실전 권장값이다.

### 7.1 공통 가정
- 동시 사용자 수는 낮거나 중간(개인/소규모 팀)
- 요청은 짧은 질의 + 가끔 긴 컨텍스트 혼합
- 목표는 "중단 없는 안정성" 우선, 이후 TPS를 단계적으로 확장

### 7.2 권장 프리셋 A (안정 우선, 첫 시작값)

`2. Options`에서 아래 값부터 시작:

- `10 Decode Concurrency`: `2`
- `11 Prompt Concurrency`: `2`
- `12 Prefill Step Size`: `2048`
- `13 Metal Memory Limit`: `96GB`
- `14 Metal Cache Limit`: `6GB`
- `15 Prompt Cache Bytes`: `16GB`
- `16 Advanced Cache`: `ON`
- `17 Paged Cache Size`: `128`
- `18 KV Cache Bits`: `8`
- `19 KV Group Size`: `64`
- `20 Cache Grace Secs`: `20`
- `21 Prompt Normalize`: `ON`
- `22 Cache Observability`: `OFF` (성능 운영 기준)
- `23 Cache Headroom`: `0.78`
- `27 Speculative Decoding`: `OFF` (동시 요청 배칭 우선)
- `30 Chat Template Args`: `{}` (기본 템플릿)

**의도**:
- **OS/백그라운드 앱 여유를 남기면서도** Q4 모델 운용 안정성을 우선 확보한다.
- 캐시는 충분히 주되(`16GB`), headroom을 보수적으로(`0.78`) 둬서 급격한 메모리 압박을 줄인다.

### 7.3 권장 프리셋 B (균형형, 보통 운영값)

A 프리셋이 24/25/26 벤치에서 안정적이면 다음으로 이동:

- `10 Decode Concurrency`: `4`
- `11 Prompt Concurrency`: `3`
- `12 Prefill Step Size`: `2048` 또는 `3072`
- `13 Metal Memory Limit`: `100GB`
- `14 Metal Cache Limit`: `8GB`
- `15 Prompt Cache Bytes`: `20GB`
- `16 Advanced Cache`: `ON`
- `17 Paged Cache Size`: `128` (유사 요청 많으면 `256` 테스트)
- `18 KV Cache Bits`: `8`
- `19 KV Group Size`: `64`
- `20 Cache Grace Secs`: `20~30`
- `21 Prompt Normalize`: `ON`
- `22 Cache Observability`: `OFF` (문제 분석 시만 ON)
- `23 Cache Headroom`: `0.80~0.82`

**의도**:
- **안정성은 유지하면서 TPS를 체감 상승**시키는 기본 운영 구간.
- 45~50GB Q4 모델 다수 워크로드에서 가장 먼저 시도할 만한 구간.

### 7.4 권장 프리셋 C (처리량 우선, 신중 적용)

부하가 높고 A/B에서 여유가 충분할 때만:

- `10 Decode Concurrency`: `6` (상황에 따라 `8`까지)
- `11 Prompt Concurrency`: `4`
- `12 Prefill Step Size`: `3072` 또는 `4096`
- `13 Metal Memory Limit`: `104GB`
- `14 Metal Cache Limit`: `8~10GB`
- `15 Prompt Cache Bytes`: `24GB`
- `16 Advanced Cache`: `ON`
- `17 Paged Cache Size`: `256`
- `18 KV Cache Bits`: `8` 유지 권장 (메모리 압박 시 `4` 테스트)
- `19 KV Group Size`: `64` (품질 민감하면 `32`)
- `20 Cache Grace Secs`: `30`
- `21 Prompt Normalize`: `ON`
- `22 Cache Observability`: `OFF`
- `23 Cache Headroom`: `0.82~0.85`

**의도**:
- 총 TPS를 최대한 확보하되, 장시간 운용에서 압박 신호가 보이면 즉시 B로 롤백한다.

### 7.5 즉시 롤백 규칙 (장애 회피)

아래 징후가 보이면 즉시 다운튜닝:

1. `SIGABRT(134)` 또는 `SIGSEGV(139)` 발생
2. 첫 토큰 지연(TTFT) 급증 + tail latency 악화
3. 같은 요청에서 응답 시간 분산이 급격히 커짐

롤백 순서:
1. `10 Decode Concurrency` 1단계 하향
2. `11 Prompt Concurrency` 1단계 하향
3. `12 Prefill Step Size` 하향(4096 -> 2048 -> 1024)
4. `15 Prompt Cache Bytes` 하향
5. 필요 시 `18 KV Cache Bits`를 `8 -> 4`

### 7.6 샘플링 기본값(품질/재현성 기준)

Q4 대형 모델 운영에서 시작점 권장:

- `3 Temperature`: `0.2`
- `5 Top-P`: `0.9~0.95`
- `6 Top-K`: `40` (또는 `0`으로 비활성)
- `4 Max Tokens`: `512` (긴 출력 필요 시 점진 상향)

### 7.7 벤치 기반 적용 절차(권장)

1. 프리셋 A 적용 후 `24`(Light) 3회
2. `25`(Stream TPS Compare) 3회로 TTFT/Decode 분리 확인
3. `26`(5x Summary)로 평균/편차 확인
4. 안정적이면 B로 1단계 상승
5. C는 장시간(최소 30~60분) 무오류 확인 후 유지
