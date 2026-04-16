# Model lifecycle (mlx-server v0.1.0)

## Load sources

- **Local model name or path**: 
  - 모델의 이름만 입력할 경우, **`local_models_root`** 폴더 내에서 해당 이름의 디렉토리를 먼저 검색합니다.
  - 기본값은 `~/Desktop/models`이며, `run.sh > Models Folder`에서 변경하면 해당 경로가 우선 적용됩니다.
  - 절대 경로가 입력되거나 현재 작업 디렉토리에 존재하는 경로인 경우 해당 경로를 직접 사용합니다.
- **Hugging Face repo id** (예: `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`):
  - 로컬에서 모델을 찾지 못한 경우에만 HF Hub에서 검색을 시도합니다.
  - **주의**: Hugging Face 모델 사용 시 반드시 `조직명/모델명` 형식을 지켜야 하며, 접두사가 누락될 경우 404/401 에러가 발생할 수 있습니다.
- **CLI / config default:** optional `model` in config or `--model`; if set, the process preloads that model at startup (same as `mlx_lm.server --model`). 모델 이름 분석 시 위와 동일한 우선순위 규칙이 적용됩니다.

## Configuration settings

| Key | Default | Description |
|-----|---------|-------------|
| `local_models_root` | `~/Desktop/models` | 로컬 모델을 검색할 기본 루트 디렉토리입니다. (`MLX_SERVER_LOCAL_MODELS_ROOT`로 런타임 오버라이드 가능) |

## `run.sh` 운영 흐름 (TUI)

`run.sh` 사용 시 권장 흐름은 다음과 같습니다.

1. `Models Folder`에서 로컬 모델 루트 디렉토리 설정
2. `Download from Hugging Face`에서 Repo ID/URL 입력 후 모델 다운로드
3. `Run Model`에서 목록 선택 또는 수동 입력으로 서버 실행

Hugging Face에서 다운로드한 모델은 설정한 모델 루트 하위 폴더에 저장되며, 이후 `Run Model` 목록에 자동으로 노출됩니다.

## Single active model (swap, not multi-tenant)

- At most **one** full model+draft+adapter triple is resident at a time, matching upstream `ModelProvider` behavior (swap replaces the previous load).

## Explicit load API

`POST /v1/mlx/models/load`

```json
{
  "model": "/path/or/hf-repo-id",
  "adapter_path": null,
  "draft_model": null
}
```

- `adapter_path`, `draft_model`: optional strings; omitted or `null` means unchanged / use CLI defaults where applicable.
- **Success:** `200` with `{"status": "ok", "model_key": [path, adapter, draft]}` (tuple serialized as array).
- **Failure:** `400`/`500` with `{"detail": "..."}`.

Implicit load via `POST /v1/chat/completions` with `"model": "..."` remains supported (upstream). If no model is specified in the completion request, the model most recently loaded via `/v1/mlx/models/load` is used as the default.

## Explicit unload API

`POST /v1/mlx/models/unload`

- **Description:** Releases the currently loaded model from memory.
- **Success:** `200` with `{"status": "ok", "message": "Model unloaded"}`.
- **Failure:** `500` if the internal provider fails to reset.


## Configuration precedence

1. **Environment variables** `MLX_SERVER_*` (see `config.py` / README)
2. **YAML config file** (`--config`)
3. **CLI flags** (최우선 순위, 상세 설명은 [`cli_reference.md`](../docs/specs/cli_reference.md) 참조)

## In-flight requests

- Load/swap may block briefly; concurrent chat requests during swap are **not** queued by this wrapper—upstream behavior applies (avoid swapping under heavy load for predictable latency).
