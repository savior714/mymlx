# Knowledge: run.sh 메인 메뉴 2번(Options) 상세 가이드

## §1. 메타 정보
- **Last Verified**: 2026-04-15
- **Author**: mlx-server Team
- **Category**: TUI Option Tuning
- **Source of Truth**: `run.sh`의 `menu_options()`

## §2. 범위 및 해석 기준

이 문서는 `run.sh` 실행 후 메인 메뉴에서 **`2. Options`**를 선택했을 때 표시되는 **공개(Public) 옵션(1~16)**만 설명한다.

숨김/아카이브된 옵션(예: Temperature/Top-P/Top-K/Speculative/MCP/Tool Choice/Presence Penalty 등)은 기본 UI에서 노출하지 않는다.

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

## §4. 공개 옵션 상세(1~16)

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

### 3) Max Tokens (`USER_MAX`)
- **기술 의미**: 요청 1회 생성 토큰 상한.
- **상향 효과**: 장문 응답 완결성 증가.
- **하향 효과**: 지연/OOM 리스크 완화.
- **기본값(업스트림 mlx-lm)**: `512` (OpenAI 스타일 요청 필드 `max_tokens`의 기본값).
- **핵심 제약**: \(prompt\_tokens + max\_tokens \le\) 모델 컨텍스트 길이.
- **운영 원칙**: 잘라짐(`finish_reason=length`)이 보일 때만 단계적으로 증가.

### 4) Prompt Cache Size (`USER_PROMPT_CACHE_SIZE`)
- **기술 의미**: 캐시 엔트리 개수 상한.
- **상향 효과**: 반복 요청 히트율 개선 가능.
- **하향 효과**: 메타데이터 부담 감소.
- **연계 옵션**: `15 Prompt Cache Bytes`와 함께 봐야 실제 메모리 사용이 맞춰짐.
- **기본값(업스트림 mlx-lm)**: `10`.

### 7) Decode Concurrency (`USER_DECODE_CONCURRENCY`)
- **기술 의미**: 디코드(생성) 단계 병렬 처리 수.
- **상향 효과**: 총 TPS 상승 가능성이 가장 큼.
- **하향 효과**: 안정성 개선, OOM/abort 리스크 감소.
- **기본값(업스트림 mlx-lm)**: `32`.
- **운영 팁**: 안정성 우선이면 낮게 시작해 단계적으로 상향하고, 문제 발생 시 즉시 롤백.

### 8) Prompt Concurrency (`USER_PROMPT_CONCURRENCY`)
- **기술 의미**: prefill(입력 인코딩) 병렬 처리 수.
- **상향 효과**: 긴 입력 다건 처리량 개선.
- **하향 효과**: 피크 메모리 압력 완화.
- **기본값(업스트림 mlx-lm)**: `8`.
- **운영 팁**: TTFT 급증/메모리 압박이 있으면 먼저 하향.

### 9) Prefill Step Size (`USER_PREFILL_STEP_SIZE`)
- **기술 의미**: prefill 청크 크기.
- **상향 효과**: 처리 효율 향상 가능, 대신 피크 메모리 증가 가능.
- **하향 효과**: 메모리 피크 완화, 오버헤드 증가 가능.
- **기본값(업스트림 mlx-lm)**: `2048`.
- **운영 팁**: 장문·동시성이 높을수록 보수적으로(상향은 피크 메모리와 트레이드오프).

### 10) Metal Memory Limit (`USER_METAL_MEMORY_LIMIT`)
- **기술 의미**: MLX Wired 메모리 상한.
- **상향 효과**: 대형 모델/긴 컨텍스트 여유 증가.
- **하향 효과**: OS/다른 앱 여유 확보.
- **입력 형식**: `96GB`, `512MB`처럼 단위 필수.
- **주의**: 이 값은 `mlx-server` 운영 옵션이며, 업스트림 `mlx-lm`의 공개 문서에 범위가 고정되어 있지 않다.

### 11) Metal Cache Limit (`USER_METAL_CACHE_LIMIT`)
- **기술 의미**: Metal 임시 캐시 상한.
- **상향 효과**: 재할당 감소로 속도 안정 가능.
- **하향 효과**: 메모리 회수 빨라져 OOM 완화.
- **운영 팁**: 크래시/메모리 압박이 있으면 하향, 지연 변동이 크면 상향을 검토.

### 5) Prompt Cache Bytes (`USER_PROMPT_CACHE_BYTES`)
- **기술 의미**: KV/Prompt 캐시 총 바이트 상한.
- **상향 효과**: 캐시 히트율/반복 응답 속도 개선 가능.
- **하향 효과**: 피크 메모리 급증 방지.
- **운영 팁**: 모델 크기와 동시성에 맞춰 `12GB~24GB`에서 시작.

### 6) Paged Cache Size (`USER_PAGE_SIZE`)
- **기술 의미**: 캐시 페이지 단위(토큰).
- **작게 설정 효과**: 재사용 정밀도 증가.
- **크게 설정 효과**: 관리 오버헤드 감소.
- **권장**: 기본 `128`, 유사 요청이 매우 많으면 `256` 테스트.

### 12) KV Cache Bits (`USER_KV_BITS`)
- **기술 의미**: KV 캐시 양자화 비트폭(4/8/Off).
- **4bit 효과**: 메모리 절감 최대, 품질 저하 가능성 있음.
- **8bit 효과**: 절감과 품질의 균형.
- **Off 효과**: 품질 우선, 메모리 부담 큼.
- **권장**: 운영 기본은 `8bit`, 메모리 압력/중단 이슈가 있으면 `8bit`부터 적용 후 필요 시 `4bit`.

### 13) KV Group Size (`USER_KV_GROUP_SIZE`)
- **기술 의미**: KV 양자화 그룹 크기.
- **작게 설정 효과**: 품질/정밀도 유리.
- **크게 설정 효과**: 압축 효율 유리.
- **권장**: `kv-bits=8` 기준 `32`와 `64` 비교.

### 14) Cache Grace Secs (`USER_CACHE_GRACE_SECONDS`)
- **기술 의미**: cold 블록 최소 보존 시간(초).
- **상향 효과**: 재사용 기회 증가.
- **하향 효과**: 빠른 회수로 메모리 압박 완화.
- **입력 허용 범위(run.sh 검증)**: `0~600`.

### 15) Cache Headroom (`USER_CACHE_HEADROOM_RATIO`)
- **기술 의미**: 메모리 압박 상황에서 목표 여유 비율.
- **낮게 설정 효과**: 안정성 상승, 캐시 보존량 감소.
- **높게 설정 효과**: 캐시 보존량 증가 가능, 압박 리스크 증가.
- **입력 허용 범위(run.sh 검증)**: `0.50 ~ 0.95`.

---

## §8. 근거 링크(업스트림)

- `mlx-lm` HTTP server request fields / `max_tokens` 기본값: `https://raw.githubusercontent.com/ml-explore/mlx-lm/main/mlx_lm/SERVER.md`
- `mlx-lm` server CLI 기본값(`--max-tokens`, `--decode-concurrency`, `--prompt-concurrency`, `--prefill-step-size`, `--prompt-cache-size`): `https://raw.githubusercontent.com/ml-explore/mlx-lm/564281f7/mlx_lm/server.py`

### 16) Light Benchmark (Run)
- **기술 의미**: 1회 요청 실측 후 50K 토큰 시간을 환산.
- **출력 지표**: E2E TPS, 50K 예상 소요 시간.
- **용도**: 빠른 기준선 확인.

## §5. 숨김/아카이브 옵션

- 이 문서 범위 밖의 옵션들은 기본 TUI에서 “비공개”로 숨긴다.
- 필요 시 코드 수준에서만 재노출하거나 별도 아카이브 문서로 관리한다.

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
3. 샘플링(`3/5/6/33`)을 보수적으로 재설정
4. 반복 루프가 보이면 `34 Repetition Penalty`를 1.1부터 적용
5. 같은 단어/토픽만 반복되면 `35 Presence Penalty`를 0.3부터 적용

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
- `33 Min-P`: `0.05` (Top-P 보완 노이즈 필터)
- `34 Repetition Penalty`: `0.0`(비활성) 또는 장문 루프 시 `1.1`
- `35 Presence Penalty`: `0.0`(비활성) 또는 다양성 확보 시 `0.3~0.6`
- `4 Max Tokens`: `512` (긴 출력 필요 시 점진 상향)

### 7.7 벤치 기반 적용 절차(권장)

1. 프리셋 A 적용 후 `24`(Light) 3회
2. `25`(Stream TPS Compare) 3회로 TTFT/Decode 분리 확인
3. `26`(5x Summary)로 평균/편차 확인
4. 안정적이면 B로 1단계 상승
5. C는 장시간(최소 30~60분) 무오류 확인 후 유지
