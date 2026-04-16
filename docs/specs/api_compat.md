# API compatibility (mlx-server v0.1.0)

**Validated with:** `mlx-lm` 0.31.x (see `pyproject.toml`)

## Baseline (upstream `mlx_lm.server`)

The following routes are forwarded to the embedded MLX HTTP server unchanged:

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/v1/chat/completions` | OpenAI-style chat; `stream: true` returns SSE |
| `POST` | `/v1/completions` | Text completions |
| `POST` | `/chat/completions` | Alias for chat |
| `POST` | `/v1/embeddings` | 업스트림 미지원. 래퍼가 OpenAI 형식 에러(`501`)로 명시 응답 |
| `GET` | `/v1/models` | Lists cached HF models + CLI `--model` path if local |
| `GET` | `/v1/models/{repo_id}` | Subpaths as upstream |
| `GET` | `/health` | `{"status": "ok"}` |

## Extended routes (this wrapper)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/mlx/status` | Process-local load state (see below) |
| `GET` | `/v1/mlx/cache/stats` | **LRU 2.0 상세 캐시 통계** (VRAM/Disk 점유, 히트레이트, 축출 카운트 등) |
| `GET` | `/v1/mlx/models/local?root=…` | 서버 파일시스템의 `root` 하위 디렉토리 목록 조회 (로컬 모델 탐색용) |
| `GET` | `/v1/mlx/models/remote?q=…` | Hugging Face Hub 모델 검색 |
| `POST` | `/v1/mlx/models/load` | 모델 명시적 로드/교체 (see `model_lifecycle.md`) |
| `POST` | `/v1/mlx/models/unload` | 활성 모델 언로드 및 VRAM 해제 |

## JSON request bodies

- **`tools` / `tool_choice`**: forwarded to upstream with the rest of the body (required for agentic clients; the proxy must not strip them).
- **Unknown top-level fields** in `/v1/*` completion bodies: passed through to upstream; upstream validates known parameters. Clients should not rely on extra fields being persisted.
- **Model Injection**: If the `model` field is missing or `null` in `/v1/chat/completions` or `/v1/completions`, this proxy automatically injects the currently active model from the `ModelProvider`.
- **Multimodal chat (`content` as array)**: Upstream `mlx_lm.server` only supports text. Before forwarding `/v1/chat/completions` (and `/chat/completions`), this proxy removes non-`text` parts (e.g. `image_url`) and concatenates `{"type":"text","text":"..."}` fragments into a single string `content`, so OpenAI-style multimodal requests degrade to text-only instead of returning upstream error `Only 'text' content type is supported.`
- **Streaming:** `stream: true` uses `text/event-stream`; non-streaming returns JSON. Custom `/v1/mlx/*` routes always use JSON.

## Response headers

- Proxied responses preserve `Content-Type` and CORS-related headers from the MLX server where applicable.
