# Speculative Decoding (Spec-Driven Design)

## 문서 메타 (Version SSOT)

| 항목 | 내용 |
|------|------|
| **Last Verified** | 2026-04-16 |
| **mlx-lm** | `0.31.2` |
| **Reference** | `PROJECT_RULES.md`, `docs/specs/model_lifecycle.md`, `docs/specs/cli_reference.md` |

---

## 1. 개요

Speculative Decoding(추측 디코딩)은 **작은 Draft 모델**이 빠르게 토큰 후보를 생성하고, **큰 Target 모델**이 한 번의 forward pass로 검증·수정하여 전체 생성 속도를 높이는 기법이다.

mlx-server는 **`mlx_lm.server` 루프백 프록시 아키텍처**를 유지하며, 업스트림의 speculative decoding을 **투명하게 전달(passthrough)** 한다.

---

## 2. 아키텍처 (데이터 흐름)

```
User Request
  → Starlette (proxy.py)
    → httpx → mlx_lm.server (ThreadingHTTPServer, 127.0.0.1:임의포트)
      → APIHandler.do_POST
        → ResponseGenerator._serve_single()  ← draft_model 있으면 이 경로
          → stream_generate(model, draft_model=..., num_draft_tokens=...)
            → speculative_generate_step()
              ↳ draft 모델 N개 토큰 생성
              ↳ target 모델 단일 forward pass 검증
              ↳ 수락된 토큰: from_draft=True
              ↳ 수정된 토큰: from_draft=False
  ← SSE/JSON 응답
```

### 2.1 Sequential-Only 경로

`ModelProvider.load()` 시 `draft_model`이 로드되면 `is_batchable = False`가 설정된다.
따라서 speculative decoding 요청은 항상 **`_serve_single()`** (비배치 경로)을 통과하며,
`BatchGenerator`에 의한 continuous batching은 비활성화된다.

---

## 3. 설정 인터페이스

### 3.1 CLI 플래그

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `--draft-model` | `None` | Draft 모델 경로 (로컬 또는 HF Repo ID) |
| `--num-draft-tokens` | `3` | Draft 모델이 한 번에 생성할 후보 토큰 수 |

### 3.2 명시적 로드 API

`POST /v1/mlx/models/load`

```json
{
  "model": "/path/to/target-model",
  "draft_model": "/path/to/draft-model"
}
```

### 3.3 요청 바디 오버라이드

`POST /v1/chat/completions` 바디에서 요청별 오버라이드 가능:

| 필드 | 설명 |
|------|------|
| `num_draft_tokens` | 해당 요청에서만 사용할 draft 토큰 수 (CLI 기본값 대체) |
| `draft_model` | 요청별 draft 모델 지정 (업스트림 `APIHandler`에서 처리) |

### 3.4 환경 변수

| 변수 | 설명 |
|------|------|
| `MLX_SERVER_DRAFT_MODEL` | `--draft-model`과 동일 |
| `MLX_SERVER_NUM_DRAFT_TOKENS` | `--num-draft-tokens`와 동일 |

---

## 4. Draft-Target 호환성 요구사항

### 4.1 필수 조건

- **Tokenizer 호환**: Draft와 Target 모델은 **동일한 `vocab_size`** 를 가져야 한다.
  업스트림은 `vocab_size` 불일치 시 경고만 출력하고 진행하지만, 결과 품질은 보장되지 않는다.
- **Trimmable KV Cache**: `speculative_generate_step()`은 거부된 토큰의 KV cache를 되감는다(`_rewind_cache`). 
  `RotatingKVCache`(with `keep > 0`) 등 trim 불가능한 캐시 타입은 에러를 발생시킨다.

### 4.2 권장 조건

- **동일 토크나이저**: 동일 토크나이저(BPE vocab 완전 일치)를 공유하는 모델 쌍이 최적이다.
- **아키텍처 계열 일치**: 예) Qwen3-30B-A3B(Target) + Qwen3-1.7B(Draft) — 동일 Qwen3 계열.
- **양자화 호환**: Target이 4-bit 양자화된 경우, Draft도 양자화 호환성을 확인해야 한다.

### 4.3 흔한 실패 원인

| 증상 | 원인 | 해결 |
|------|------|------|
| `ValueError: Draft model tokenizer does not match` | `vocab_size` 불일치 | 동일 계열/토크나이저 모델 사용 |
| `ValueError: Speculative decoding requires a trimmable prompt cache` | RotatingKVCache(keep>0) | `--max-kv-size` 제거 또는 0으로 설정 |
| 생성 품질 저하 (비정상 토큰) | 토크나이저 BPE 불일치 | 동일 토크나이저 모델 쌍으로 교체 |
| OOM / Metal 메모리 부족 | 두 모델의 합산 메모리 초과 | 더 작은 Draft 모델 사용 또는 `--kv-bits` 양자화 |

---

## 5. 성능 튜닝 가이드

### 5.1 `num_draft_tokens` 스윗 스팟 탐색

| 시나리오 | 권장 범위 | 근거 |
|----------|-----------|------|
| **코딩 (정형적 패턴)** | 16–20 | 보일러플레이트, import 등 예측 가능한 토큰이 많아 수락률이 높음 |
| **복잡 로직/추론** | 8–12 | 비정형 토큰이 많아 수락률이 낮으므로 과도한 draft는 오히려 overhead |
| **짧은 응답 (1–2문장)** | 3–5 | 생성 토큰 자체가 적으므로 draft overhead 대비 이점이 적음 |
| **매우 큰 Draft 모델 (>7B)** | 3–5 | Draft 자체의 forward pass 비용이 높아 토큰 수를 줄여야 함 |

### 5.2 Draft 모델 크기 가이드라인

| Target 크기 | 권장 Draft 크기 | 메모리 비용 (4-bit 기준) |
|-------------|-----------------|--------------------------|
| 70B–120B+ | 1B–3B | ~1–2 GB |
| 30B–70B | 0.5B–3B | ~0.5–2 GB |
| 7B–14B | 0.5B–1B | ~0.3–0.7 GB |

### 5.3 메모리 계획

두 모델이 동시에 메모리에 상주하므로:

```
필요 메모리 ≈ Target 모델 가중치 + Draft 모델 가중치
             + Target KV Cache + Draft KV Cache
             + 연산 중간 텐서
```

128GB 통합 메모리 기준으로 `--metal-memory-limit 110GB` 정도를 설정하면
운영 체제 및 기타 프로세스 여유를 확보할 수 있다.

---

## 6. 관측(Observability)

### 6.1 수락률(α) 메트릭

- **업스트림 한계**: `mlx_lm.server` HTTP 응답에는 `from_draft` 필드가 **포함되지 않는다**.
  `GenerationResponse.from_draft`는 Python API에서만 접근 가능하다.
- **mlx-server 패치**: `backend.py`의 `_patch_speculative_observability()`가 
  `stream_generate`를 래핑하여 요청 완료 시 수락률을 INFO 로그로 출력한다.

```
INFO  Speculative decoding stats: 142/180 tokens accepted (α=0.79), draft_tokens_per_step=16
```

### 6.2 Inference Audit

`server_runtime_snapshot`에 아래 필드가 포함된다:

| 필드 | 설명 |
|------|------|
| `draft_model` | 현재 로드된 Draft 모델 경로 |
| `num_draft_tokens` | CLI 기본 draft 토큰 수 |

### 6.3 향후 확장 (미구현)

- **요청별 α 메트릭을 HTTP 응답 헤더로 노출** (예: `X-MLX-Acceptance-Rate`)
  → 업스트림 `APIHandler` 수정 필요. 현재는 스펙만 기록하고 구현하지 않음.

---

## 7. 알려진 제약 사항

| 제약 | 원인 | 영향 |
|------|------|------|
| **배칭 불가** | `is_batchable = False` (draft 모델 로드 시) | 동시 요청 시 순차 처리 |
| **Prompt Progress 미지원** | `speculative_generate_step`이 `prompt_progress_callback` 제거 | 긴 프롬프트 처리 시 스트리밍 keepalive 불가 |
| **KV-bits 양자화 호환** | `kv_bits`는 `generate_step`의 `quantized_kv_start` 기반 → speculative 경로에서도 지원 | 단, `quantized_kv_start`가 speculative 경로에서 0으로 고정됨 |
| **RotatingKVCache 비호환** | `can_trim_prompt_cache` 검사 실패 | `--max-kv-size` 사용 시 에러 |

---

## 8. Smoke Test 절차

```bash
# 1. Target + Draft 로드 (CLI)
uv run mlx-server \
  --model ~/Desktop/models/Qwen3-30B-A3B-4bit \
  --draft-model ~/Desktop/models/Qwen3-1.7B-4bit \
  --num-draft-tokens 16 \
  --kv-bits 8 \
  --metal-memory-limit 110GB

# 2. 추론 요청
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-30B-A3B-4bit",
    "messages": [{"role":"user","content":"Write a Python quicksort"}],
    "max_tokens": 256,
    "num_draft_tokens": 16
  }'

# 3. 로그에서 수락률 확인
# INFO Speculative decoding stats: N/M tokens accepted (α=X.XX)

# 4. API를 통한 로드 (대안)
curl -s http://127.0.0.1:8080/v1/mlx/models/load \
  -H "Content-Type: application/json" \
  -d '{
    "model": "~/Desktop/models/Qwen3-30B-A3B-4bit",
    "draft_model": "~/Desktop/models/Qwen3-1.7B-4bit"
  }'
```

---

## 9. 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-04-16 | 초안 작성: 아키텍처, 호환성, 튜닝 가이드, 관측 설계 |
