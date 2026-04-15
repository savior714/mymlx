# run.sh 메모리 할당 옵션 추가 계획

## 문서 메타
- **Last Verified**: 2026-04-13
- **Author**: system
- **Status**: Draft
- **Reference**: `run.sh`, `config.py`, `mlx_parser.py`

---

## 1. 개요

`run.sh`에 메모리 할당 관련 옵션을 추가하여, 사용자가 터미널에서 직접 메모리 관련 설정을 조정할 수 있도록 개선합니다.

---

## 2. 추가할 메모리 옵션

| 옵션 | 환경 변수 | 기본값 | 설명 |
|------|-----------|--------|------|
| `--prompt-cache-size` | `USER_PROMPT_CACHE_SIZE` | 10 | 키 캐시 최대 개수 |
| `--decode-concurrency` | `USER_DECODE_CONCURRENCY` | 32 | 디코딩 병렬 처리 수 |
| `--prompt-concurrency` | `USER_PROMPT_CONCURRENCY` | 8 | 프롬프트 병렬 처리 수 |
| `--prefill-step-size` | `USER_PREFILL_STEP_SIZE` | 2048 | 프리필 처리 단계 크기 |

---

## 3. `run.sh` 변경 사항

### 3.1 설정 로드 섹션 추가
```bash
LOAD_PROMPT_CACHE=""
LOAD_DECODE_CONC=""
LOAD_PROMPT_CONC=""
LOAD_PREFILL_STEP=""
```

### 3.2 기본값 설정
```bash
USER_PROMPT_CACHE_SIZE="${USER_PROMPT_CACHE_SIZE:-}"
USER_DECODE_CONCURRENCY="${USER_DECODE_CONCURRENCY:-}"
USER_PROMPT_CONCURRENCY="${USER_PROMPT_CONCURRENCY:-}"
USER_PREFILL_STEP_SIZE="${USER_PREFILL_STEP_SIZE:-}"
```

### 3.3 메모리 옵션 선택 인터페이스
```bash
read -p "Prompt Cache Size [$USER_PROMPT_CACHE_SIZE]: " input
[[ -n "$input" ]] && USER_PROMPT_CACHE_SIZE="$input"

read -p "Decode Concurrency [$USER_DECODE_CONCURRENCY]: " input
[[ -n "$input" ]] && USER_DECODE_CONCURRENCY="$input"

read -p "Prompt Concurrency [$USER_PROMPT_CONCURRENCY]: " input
[[ -n "$input" ]] && USER_PROMPT_CONCURRENCY="$input"

read -p "Prefill Step Size [$USER_PREFILL_STEP_SIZE]: " input
[[ -n "$input" ]] && USER_PREFILL_STEP_SIZE="$input"
```

### 3.4 설정 지속성
```bash
[[ -n "$USER_PROMPT_CACHE_SIZE" ]] && echo "export USER_PROMPT_CACHE_SIZE=\"$USER_PROMPT_CACHE_SIZE\""
[[ -n "$USER_DECODE_CONCURRENCY" ]] && echo "export USER_DECODE_CONCURRENCY=\"$USER_DECODE_CONCURRENCY\""
[[ -n "$USER_PROMPT_CONCURRENCY" ]] && echo "export USER_PROMPT_CONCURRENCY=\"$USER_PROMPT_CONCURRENCY\""
[[ -n "$USER_PREFILL_STEP_SIZE" ]] && echo "export USER_PREFILL_STEP_SIZE=\"$USER_PREFILL_STEP_SIZE\""
```

### 3.5 CLI 인자 추가
```bash
[[ -n "$USER_PROMPT_CACHE_SIZE" ]] && ARGS+=(--prompt-cache-size "$USER_PROMPT_CACHE_SIZE")
[[ -n "$USER_DECODE_CONCURRENCY" ]] && ARGS+=(--decode-concurrency "$USER_DECODE_CONCURRENCY")
[[ -n "$USER_PROMPT_CONCURRENCY" ]] && ARGS+=(--prompt-concurrency "$USER_PROMPT_CONCURRENCY")
[[ -n "$USER_PREFILL_STEP_SIZE" ]] && ARGS+=(--prefill-step-size "$USER_PREFILL_STEP_SIZE")
```

---

## 4. `config.py` 변경 사항

### 4.1 `_mlx_defaults()`에 메모리 옵션 추가
```python
"prompt_cache_size": 10,
"decode_concurrency": 32,
"prompt_concurrency": 8,
"prefill_step_size": 2048,
```

### 4.2 `_env_mlx_overrides()`에 환경 변수 파싱 추가
```python
if v := env.get(f"{_ENV_PREFIX}PROMPT_CACHE_SIZE"):
    o["prompt_cache_size"] = int(v)
if v := env.get(f"{_ENV_PREFIX}DECODE_CONCURRENCY"):
    o["decode_concurrency"] = int(v)
if v := env.get(f"{_ENV_PREFIX}PROMPT_CONCURRENCY"):
    o["prompt_concurrency"] = int(v)
if v := env.get(f"{_ENV_PREFIX}PREFILL_STEP_SIZE"):
    o["prefill_step_size"] = int(v)
```

---

## 5. `mlx_parser.py` 변경 사항

이미 존재하는 메모리 관련 옵션을 그대로 유지:
- `--prompt-cache-size` (line 122-126)
- `--decode-concurrency` (line 103-108)
- `--prompt-concurrency` (line 109-114)
- `--prefill-step-size` (line 115-120)

---

## 6. 구현 순서

1. `run.sh`에 메모리 옵션 선택 인터페이스 추가
2. `config.py`에 메모리 관련 환경 변수 지원 추가
3. `run.sh`에 메모리 옵션 CLI 인자 전달 추가
4. 테스트 및 검증

---

## 7. 테스트 계획

1. `./run.sh` 실행 후 메모리 옵션 입력 테스트
2. 설정 지속성 테스트 (`~/.mlx-server/config` 확인)
3. 재기동 시 이전 값 자동 적용 테스트
4. `uv run mlx-server serve --help`로 옵션 확인
