# [REMOVED] Web UI (mlx-server v0.1.0)

> [!CAUTION]
> 이 명세에 기술된 웹 UI 기능은 2026-04-12부로 프로젝트에서 제거되었습니다. `mlx-server`는 이제 순수하게 터미널 기반의 헤드리스(Headless) API 서버로 동작하며, 모든 모델 로드 및 제어는 API 또는 CLI를 통해 수행됩니다.

## 기존 Scope (참고용)
...

- **Single-page** browser UI served by the same process as the API (Starlette static mount).
- **Chat:** user messages and assistant replies against `/v1/chat/completions` (non-streaming for simplicity in v0.1).
- **Model management:** 
    - Form to set model path / HF id and call `POST /v1/mlx/models/load`, plus display of `GET /v1/mlx/status`.
    - **Visual Feedback:** 
        - Show a loading overlay during `POST /v1/mlx/models/load`.
        - Display a **Success Toast/Message** when loading completes.
        - Display the **Active Model Name** and **API Endpoint URL** prominently.
    - **Control Actions:**
        - **Load Button:** Found on each model card or the selection bar.
        - **Unload Button:** Visible when a model is active, allowing manual memory clearing via `POST /v1/mlx/models/unload`.
    - **Model Browser:** 
        - Users can search and filter models in the local model folder.
        - Models are displayed as **Cards** with status indicators (Loaded, Ready, Unknown).
        - **Auto-Refresh:** The list updates automatically when the root directory changes.
- **Local model folder:** optional field for an absolute directory on the machine running the server; **목록 불러오기** calls `GET /v1/mlx/models/local` and fills the Model Browser.
- **Finder (macOS):** **폴더 선택** (기존 Finder) 버튼은 입력된 경로를 Finder에서 엽니다 (`open -a Finder` / `open -R`). 기존의 `choose folder` 대화상자(`pick-folder`)는 성능 및 중복성 문제로 제거되었습니다.
- **Aesthetics:** Implement a modern, responsive design using glassmorphism and premium color palettes (e.g., Deep Navy, Cyan accents).
- **UX Polish:** Replace raw JSON status with formatted info; provide clear endpoint copy-pastable strings.

## Authentication

- **None** by default (local development). Same trust boundary as upstream `mlx_lm.server` warning: not for production exposure.

## Deployment

- Static assets under package `static/`; served under `/ui/` with `index.html` as the entry document.
