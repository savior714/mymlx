# Metal 메모리 제한 명세

## 문서 메타 (Version SSOT)
- **Last Verified**: 2026-04-15
- **Tested Version**: mlx-server v0.1.0
- **Reference**: `docs/CRITICAL_LOGIC.md`, `src/mlx_server/backend.py`

---

## 1. 개요

이 명세는 Apple Silicon(Metal) 환경에서 GPU 메모리 부족 오류를 해결하기 위한 **Metal wired limit 수동 설정** 기능을 정의합니다.

### 1.1 문제 정의
- **오류**: `kIOGPUCommandBufferCallbackErrorOutOfMemory` - Metal 명령 버퍼 실행 실패
- **원인**: `mlx_lm.server`가 자동으로 설정하는 `max_recommended_working_set_size`가 모델 로드 시 부족할 수 있음
- **해결**: 사용자가 `--metal-memory-limit` 옵션으로 수동 제한 설정 가능

---

## 2. 기술 사양

### 2.0 `parse_size` 단위 (`mlx_lm.utils._parse_size`)

이 옵션들은 문자열을 파싱해 **정수 바이트**로 변환합니다.

- **접미사 없음**: 값은 **바이트**입니다. 예: `24` → 24바이트 (24GB 아님).
- **GB / MB 등**: 예: `24GB`, `16MB` — 기대한 용량이 기가바이트·메가바이트 단위이면 **반드시 접미사를 붙입니다**.
- **권장**: CLI·환경 변수·YAML 모두 `24GB`처럼 단위를 포함해 입력합니다.

### 2.1 CLI 옵션

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--metal-memory-limit` | `str` (parse_size) | `null` (auto) | Metal wired 상한 (예: `8GB`, `96GB`) |
| `--metal-cache-limit` | `str` (parse_size) | `null` (auto) | Metal cache 상한 (예: `4GB`, `32GB`) |
| `--prompt-cache-bytes` | `str` (parse_size) | `null` | KV 캐시 총량 상한 (예: `16GB`, `24GB`) |
| `--cache-grace-seconds` | `float` | `15.0` | `hits=0` 신규 블록의 최소 보호 시간(초) |
| `--prompt-normalization` | `flag` | `false` | 프롬프트 공백/개행 정규화로 캐시 키 안정화 |
| `--cache-observability` | `flag` | `false` | 캐시 히트/미스/축출 사유 상세 계측 활성화 |

### 2.2 환경 변수

(`parse_size` 규칙은 위 **2.0절**과 동일 — 예: `export MLX_SERVER_PROMPT_CACHE_BYTES=24GB`)

| 변수 | 타입 | 설명 |
|------|------|------|
| `MLX_SERVER_METAL_MEMORY_LIMIT` | `str` | Metal wired memory limit |
| `MLX_SERVER_METAL_CACHE_LIMIT` | `str` | Metal cache limit |
| `MLX_SERVER_PROMPT_CACHE_BYTES` | `str` | Prompt / KV cache 바이트 상한 |
| `MLX_SERVER_CACHE_GRACE_SECONDS` | `float` | 신규 콜드 블록 보호 시간(초) |
| `MLX_SERVER_PROMPT_NORMALIZATION` | `bool` | 프롬프트 정규화 on/off |
| `MLX_SERVER_CACHE_OBSERVABILITY` | `bool` | 상세 캐시 계측 로깅 on/off |

### 2.3 YAML Config

```yaml
mlx:
  metal_memory_limit: "96GB"
  metal_cache_limit: "16GB"
```

---

## 3. 구현 세부사항

### 3.1 파싱 로직 ([`mlx_parser.py`](src/mlx_server/mlx_parser.py))

`--metal-memory-limit`, `--metal-cache-limit`, `--prompt-cache-bytes`는 모두 `type=_parse_size`이며, **2.0절** 단위 규칙을 따릅니다. 최신 도움말 문자열은 소스 파일을 참고합니다.

### 3.2 백엔드 설정 ([`backend.py`](src/mlx_server/backend.py))

```python
if mx.metal.is_available():
    # Wired Limit
    wired_limit = mlx_args.metal_memory_limit or mx.device_info()["max_recommended_working_set_size"]
    mx.set_wired_limit(wired_limit)
    
    # Cache Limit
    if mlx_args.metal_cache_limit is not None:
        mx.set_cache_limit(mlx_args.metal_cache_limit)
```

---

## 4. 사용 예제

### 4.1 M5 Max (128GB) 대형 모델용 설정 (Qwen3-Coder-Next)

```bash
uv run mlx-server serve \
  --model Qwen3-Coder-Next-oQ4 \
  --metal-memory-limit 100GB \
  --metal-cache-limit 8GB \
  --prompt-cache-bytes 16GB
```

---

## 5. 권장 설정 가이드라인

### 5.1 고사양 장비 (128GB RAM 이상)

- **Wired Limit**: RAM의 80-90% 권장 (예: 100GB). 시스템 안정성을 위해 약간의 여유를 둡니다.
- **Cache Limit**: `8GB`~`16GB` 권장. 너무 크면 실제 연산용 메모리가 부족해지고, 너무 작으면 캐시 히트율이 떨어집니다.
- **Prompt Cache Bytes**: 사용하는 모델 크기에 맞춰 조절 (`8GB`~`32GB`).

### 5.2 중급 장비 (32GB~64GB RAM)

- **Wired Limit**: 75% 권장.
- **Cache Limit**: `4GB`~`8GB` 권장.

---

## 7. 옵션별 상세 가이드 및 기대 효과

각 설정값이 시스템에 미치는 영향과 조정 시 기대할 수 있는 결과입니다.

### 7.1 `--metal-memory-limit` (Wired Limit)
- **정의**: GPU가 독점적으로 점유하는 물리 메모리(Wired)의 최대 상한선입니다.
- **상향 시 (+)**: 더 큰 파라미터를 가진 모델을 로드할 수 있게 됩니다.
- **하향 시 (-)**: 시스템의 다른 프로세스(브라우저, IDE 등)가 사용할 메모리 여유가 생기지만, 모델 로드 중 OOM이 발생할 확률이 높아집니다.
- **권장**: RAM의 80~90% (M5 128GB 기준 100GB 내외).

### 7.2 `--metal-cache-limit` (Cache Limit)
- **정의**: MLX가 연산 후 즉시 반환하지 않고 들고 있는 임시 버퍼 캐시의 크기입니다.
- **상향 시 (+)**: 동일한 크기의 연산이 반복될 때 메모리 할당 오버헤드가 줄어들어 미세하게 속도가 향상됩니다.
- **하향 시 (-)**: 메모리를 OS에 더 자주 반환하므로, 전체 시스템의 메모리 압박(Memory Pressure)이 줄어들고 OOM을 방지하는 데 가장 효과적입니다.
- **권장**: `8GB`~`16GB`. OOM 발생 시 `4GB` 이하로 줄이는 것을 추천합니다.

### 7.3 `--prompt-cache-bytes` (KV Cache Byte Limit)
- **정의**: 대화 문맥(KV Cache)이 차지할 수 있는 총 메모리 크기입니다.
- **단위**: **2.0절** 참고 — `24GB`처럼 접미사를 붙이고, 숫자만 쓰면 바이트로 해석됩니다 (`24` ≠ 24GB).
- **상향 시 (+)**: 긴 대화나 복잡한 코딩 문맥을 더 많이 기억하고 빠르게 재사용(Prompt Caching)할 수 있습니다.
- **하향 시 (-)**: 문맥이 길어질 때 갑자기 발생하는 OOM을 물리적으로 차단합니다. 한도를 초과하면 오래된 문맥부터 캐시에서 제거됩니다.
- **권장**: 모델 크기의 20~50% 정도 (예: 80B 모델 사용 시 `16GB`~`32GB`).

### 7.4 `--decode-concurrency` / `--prompt-concurrency`
- **정의**: 동시에 처리할 요청(배치)의 수입니다.
- **상향 시 (+)**: 여러 사용자가 동시에 접속할 때 전체적인 처리량(Throughput)이 좋아집니다.
- **하향 시 (-)**: 단일 요청에 대한 응답 속도(Latency)가 안정화되고, 피크 타임의 VRAM 사용량이 낮아집니다.
- **권장**: 개인용 `1~4`, 서버용 `8~32`.

---

## 8. 빠른 트러블슈팅 가이드

| 상황 | 추천 조치 |
|------|-----------|
| **모델 로드 중 즉시 OOM** | `--metal-memory-limit` 상향 혹은 더 낮은 양자화(Q4 -> Q3) 모델 사용 |
| **답변 생성 중 간헐적 OOM** | `--metal-cache-limit`을 `4GB`로 축소, `--prompt-cache-bytes` 설정 |
| **시스템 전체가 버벅임** | `--metal-memory-limit`을 RAM의 70% 수준으로 하향 |

---

## 9. 관련 문서

- [`docs/CRITICAL_LOGIC.md`](docs/CRITICAL_LOGIC.md) - 아키텍처 결정
- [`src/mlx_server/backend.py`](src/mlx_server/backend.py) - Metal limit 설정 로직
- [`src/mlx_server/config.py`](src/mlx_server/config.py) - 설정 병합 로직
- [`src/mlx_server/mlx_parser.py`](src/mlx_server/mlx_parser.py) - CLI 파서
- [`src/mlx_server/app.py`](src/mlx_server/app.py) - `/v1/mlx/cache/stats` 관측 API
