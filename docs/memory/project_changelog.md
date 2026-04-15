# Project Changelog

### [2026-04-13]
- **[Proxy]** `/v1/embeddings`를 의도된 미지원 엔드포인트로 고정하고, `501` + OpenAI 형식 에러 JSON(`embeddings_not_supported`)을 반환하도록 변경했습니다. 또한 업스트림 `4xx/5xx` 응답을 스트리밍 중계하지 않고 버퍼링 반환하도록 조정하여 `httpx.ReadError` 기반 ASGI 예외 로그를 제거했습니다.
- **[TUI]** `run.sh`에 실시간 메모리 감시 상단 바 추가.
    - ANSI 스크롤 영역 제한(`\e[2;r`)을 사용하여 로그와 분리된 고정 상태 표시줄 구현.
    - `top` 및 `memory_pressure` 명령을 활용한 실시간 RAM/VRAM 및 시스템 부하 표시.
- **[Plan]** `docs/plans/archive/20260413_run_sh_memory_monitor.md` 작성 및 구현 완료.
- **[Fix]** Metal OOM 해결을 위한 메모리 관리 강화 (Cache Limit, Byte Cache) 완료.
- **웹 UI 제거**: `src/mlx_server/static/` 폴더와 `/ui` 관련 모든 라우트를 제거하여 프로젝트를 경량화했습니다.
- **헤드리스 API 서버 전환**: Starlette 앱을 순수 API 서버로 리팩토링하고, macOS 전용 Finder 연동 기능 등 UI 의존적 기능을 삭제했습니다.
- **CLI 안내 개선**: 서버 기동 로그 및 도움말에서 웹 UI 관련 안내를 삭제하고 헤드리스 API 서버임을 명시했습니다.
- **테스트 스위트 정비**: 제거된 기능에 대한 테스트를 삭제하고 헤드리스 API 서버의 안정성을 재검증했습니다.
- **바탕화면 모델 폴더 우선 정책**: `~/Desktop/models`를 기본 모델 루트로 설정하여, 모델 이름만으로 로컬 모델을 즉시 로드할 수 있도록 개선했습니다. (HF Hub 검색보다 로컬 탐색 우선)
- **대화형 실행 스크립트 고도화**: `run.sh`를 통해 터미널에서 로컬 모델을 목록으로 보고 선택하며, 주요 파라미터(Temp, Max Tokens 등)를 즉석에서 변경할 수 있는 인터랙티브 모드를 구현했습니다.
- **버그 수정 (macOS 호환성)**: macOS 기본 Bash 3.2에서 `mapfile` 명령어를 찾지 못하는 오류를 해결하기 위해 모델 목록 생성 로직을 `for` 루프 방식으로 교체했습니다.
- **버그 수정 (프록시 경로 해결)**: `/v1/chat/completions` 등 OpenAI API 호출 시 바디에 포함된 모델 이름이 로컬에 존재할 경우 이를 절대 경로로 변환하지 않아 HF 접근 시도(401) 및 로드 실패(404)가 발생하는 문제를 해결했습니다.
- **에러 로깅 개선**: 내부 MLX 서버에서 에러가 발생할 경우 해당 에러 바디를 서버 로그에 상세히 기록하도록 개선했습니다.
- **대화형 실행 스크립트 개선 (v2)**: `run.sh` 인터페이스를 개선하여 3단계 워크플로우(모델 선택 → 확인/수정 → 실행)를 도입했습니다. `select` 명령어 대신 macOS Bash 3.2 호환 숫자 입력 메뉴를 사용하고, 실행 전 최종 확인을 추가하여 실수를 방지했습니다.
- **설정 지속성 (v3)**: `run.sh`에 사용자 입력 옵션을 `~/.mlx-server/config` 파일에 저장하고, 다음 실행 시 이전 설정을 기본값으로 불러오도록 개선했습니다. `PERSIST` 선택을 통해 설정 저장 여부를 결정할 수 있습니다.
- **버그 수정 (run.sh 쌍따옴표 매칭 오류)**: `run.sh`에 CLI 인자(`--model ...`)를 전달했을 때 `mlx-server serve` 명령어가 자동으로 추가되지 않아 `unexpected EOF while looking for matching '"'` 에러가 발생하는 문제를 해결했습니다. `run.sh` 43-55번째 줄을 수정하여 첫 인자가 `--` 또는 `-`로 시작할 경우 자동으로 `serve` 명령어를 추가하도록 했습니다.
- **버그 수정 (프록시 세션 초기화)**: `proxy.py`에서 `tools` 키를 삭제하는 로직을 제거하여, 클라이언트(IDE/MCP)가 `tools`/`tool_calls`/`finish_reason` 필드를 일관되게 수신할 수 있도록 수정했습니다. 요청에서 `tools`만 제거하면 응답 구조가 기대와 어긋나 세션을 초기화하는 경우가 많았습니다.
- **SSE 버퍼링 개선**: `proxy.py`에서 SSE 응답에 `Cache-Control: no-cache`와 `X-Accel-Buffering: no` 헤더를 추가하여, 중간 프록시가 버퍼링하다 스트림을 끊는 경우를 줄였습니다.
- **API 명세 업데이트**: `specs/api_compat.md`에 `tools`/`tool_choice` 필드가 upstream으로 그대로 전달된다는 규칙을 명시했습니다.
- **run.sh 설정 로드 버그 수정**: `TEMP`, `MAX`, `LOG` 변수도 `~/.mlx-server/config`에서 로드하도록 수정하여, 설정이 다음 실행 시 기본값으로 제대로 적용되도록 개선했습니다.
- **run.sh 인터페이스 개선**: fzf/rofi가 설치되어 있으면 터미널 UI로 모델 선택, 없으면 기존 숫자 메뉴 폴백 방식으로 인터페이스를 개선했습니다.
- **run.sh 이전 값 자동 적용 (v5)**: `read -p "Temperature [$USER_TEMP]: " input` 형식으로 파라미터 입력 시 이전 값을 표시하고, 사용자가 엔터만 치면(입력하지 않으면) 이전 값이 자동으로 유지되도록 개선했습니다. 모델 선택 시에도 동일한 방식으로 이전 값이 자동 적용됩니다.
- **run.sh 메모리 할당 옵션 추가 (v6)**: `run.sh`에 메모리 관련 옵션(`--prompt-cache-size`, `--decode-concurrency`, `--prompt-concurrency`, `--prefill-step-size`)을 추가하여, 터미널에서 직접 메모리 설정을 조정할 수 있도록 개선했습니다. 설정 지속성(`~/.mlx-server/config`)도 메모리 옵션을 포함하도록 확장했습니다.
### [2026-04-16]
- **[Git]** 프로젝트 코드를 신규 원격 저장소(`https://github.com/savior714/mymlx`)에 푸시했습니다.
    - `.gitignore` 최적화 (.cache, scratch, server.log 등 제외).
    - 초기 커밋 및 `main` 브랜치 업로드 완료.

### [2026-04-15]
- **[Refactor: Core Architecture Phase 1-4]**: 비즈니스 로직과 인프라 유틸리티 분리 완료.
    - **Phase 1**: `model_resolver.py`, `memory_manager.py` 신설 및 `backend.py` 정리. [DONE]
    - **Phase 2**: `request_transformer.py` 신설 및 `proxy.py`의 요청 정규화 로직 이관. `MlxRequestTransformer.transform`으로 캡슐화. [DONE]
    - **Phase 3**: `handlers.py` 신설 및 `app.py`의 라우트 핸들러 독립화. [DONE]
    - **Phase 4**: `cache_index.py` 신설 및 `advanced_prompt_cache.py`의 메타데이터 관리 로직 분리. [DONE]
- **[Fix]** `proxy.py` 내의 대규모 코드 중복 및 `app.py` 내의 중복 임포트 정리.
- **[Feature] Proactive Eviction & Inference Headroom**: 추론 중 메모리 압력으로 인한 stall 문제 해결.
    - `MemoryPressureManager`에 `headroom_ratio=0.65` 도입 — 캐시가 VRAM의 65%까지만 차도록 제한하여 추론 여유분 15% 확보.
    - **Background Maintenance Thread** (5초 간격) — 요청 사이 유휴 시간에 proactive eviction 수행. 추론 도중 eviction이 필요한 상황을 사전 예방.
    - **Dynamic Lazy Threshold** — WARNING 상태에서 고정 30초 idle 기준을 동적으로 조정 (메모리 압력↑ → threshold 3초까지 ↓). 급할수록 빠르게 evict.
    - `backend.py` shutdown에서 maintenance thread 정리 추가.
    - 신규 테스트 7개 추가 (headroom, proactive evict, dynamic threshold, stop_maintenance 등), 전체 38/38 통과.
- **[Fix: metadata 누수]**: `block_metadata`에서 `tokens` 필드 제거하여 메모리 중복 방지. PURGED 메타 GC 로직 추가 (300초 초과 시 정리).
- **[Feature] KV 캐시 양자화 Phase A (kv-bits 패스스루)**: 서버/CLI/run.sh에서 `--kv-bits` 옵션을 전달하여 추론 시점부터 양자화된 KV 캐시를 생성하도록 연동.
- **[TUI]** `run.sh` 메인 메뉴를 `Run/Options/Models Folder/Download from Hugging Face/Quit` 5단계로 확장했습니다.
- **[TUI]** `Models Folder` 설정을 추가하여 `~/.mlx-server/config`의 `USER_MODELS_ROOT`를 통해 로컬 모델 루트를 영속적으로 관리하도록 개선했습니다.
- **[TUI]** `Download from Hugging Face` 메뉴를 추가해 Repo ID/URL 붙여넣기 다운로드를 지원하고, 폴더명 충돌 시 자동 suffix(`-2`, `-3`) 회피를 적용했습니다.
- **[TUI]** Hugging Face private/gated 모델 사용자를 위해 `huggingface-cli login`/`whoami` 기반 로그인·권한 점검 안내를 추가했습니다.
- **[UX]** `run.sh` 옵션 설명 문구를 전면 개편해 각 항목을 `정의 / 상향 영향 / 하향 영향 / 튜닝 팁` 패턴으로 통일했습니다.
- **[Docs]** `docs/specs/cli_reference.md`에 `run.sh` 메뉴 구조, 모델 루트 경로 해석, HF 다운로드 규약, TPS 튜닝 우선순위를 SSOT로 문서화했습니다.
- **[Refactor: Cache Module Split]**: `advanced_prompt_cache.py`가 500라인을 초과함에 따라, `MemoryPressureManager`를 `memory_manager.py`로, `_tuples_to_kvcache`를 `cache_utils.py`로 분리하여 모듈화 가드레일을 준수했습니다. (`advanced_prompt_cache.py`: 504 -> 433라인)
### [2026-04-15]
- **[Feature] Advanced Cache Implementation Spec v1.0 통합 완료**
    - **핵심 아키텍처**: 3계층(Index, Runtime, Persistence) 분리 및 `CacheIndex` 도입.
    - **격리 강화**: `CacheKey`에 `model_id`, `quantization` 필드 추가로 환경 변화 대응 및 I4/I5 불변식 구현.
    - **축출 최적화**: 다차원 점수(Priority, Recency, Reuse, Depth) 기반 eviction 로직 통합.
    - **QA**: `tests/test_lru2_cache.py` 구조적 리팩토링 및 기본 불변식 테스트 통과.

- **[Spec: Advanced Cache Implementation Spec v1.1]**: 이전 명세를 실제 `mlx-lm` 및 `vLLM` 선진 사례에 맞춰 고도화했습니다. [DONE]
    - **Metadata-rich Cache Key**: `tokenizer_version`, `chat_template`, `quantization`, `rope_scaling` 등을 포함한 복합 키 설계.
    - **3-Layer Architecture**: Index (Control), Runtime (Compute), Persistence (I/O) 계층으로 책임을 명확히 분리.
    - **CoW Enhancement**: `refcount` 및 `generation` 세대 관리 도입으로 동시성 안전 강화.
    - **Dynamic Scoring**: `recency`, `reuse`, `cost`, `depth`를 결합한 상세 스코어링 공식 명문화.
    - **Failure Modes**: OOM Guard (Soft 80%, Hard 95%, Guard 98%) 및 Fail-fast 경로 구체화.
- **[Docs]** `docs/CRITICAL_LOGIC.md`에 캐시 정합성 및 안정성을 위한 핵심 설계 결정 사항 반영 완료.

### [2026-04-14]
- **[Rules]** `PROJECT_RULES.md`를 Senior-grade EMR 프로젝트(freeEMR)의 고도화된 프로토콜을 참고하여 전면 업데이트했습니다.
    - **문서 SSOT 경계 구체화**: Specs, Decision Log(CRITICAL_LOGIC.md), Memory, Knowledge 역할을 명확히 구분하여 지식 관리 체계를 강화했습니다.
    - **파일/경로 프로토콜 도입**: `File-Read-Once`(단일 호출 읽기), `Path Verification`(프로젝트 루트 기준 전체 경로 사용) 규칙을 추가하여 에이전트 작업의 정확도를 높였습니다.
    - **Pre-Guard 도입**: Starlette 라우팅 순서 및 레이어 분리 가드레일을 명문화하여 회귀 오류를 사전 차단했습니다.
    - **운영 프로토콜 강화**: 도구 실패 시 자가 교정 원칙(Loop Prevention)과 DuckDuckGo MCP 기반의 웹 검색/자산화 정책을 명시했습니다.
    - **인코딩 표준화**: 모든 문서의 UTF-8(BOM 없음) 유지 및 셸 리다이렉션 사용 금지 원칙을 강화했습니다.
- **[Fix]** `mlx-lm 0.31.2` 풀 캐시 히트 시 `BatchGenerator` `IndexError` 수정 (`SafeguardPromptCache` 도입).
- **[Fix]** `AdvancedPromptCache` 접두사 매칭 시 나머지 토큰 유실(무한 반복 현상) 수정.
- **[Fix]** `mx.load_safetensors` 관련 `AttributeError` 해결 (`mx.load`로 표준화).
- **[Feature]** **LRU 2.0 (Advanced Cache)** 도하: 우선순위(Priority) 기반 계층형 캐싱 및 SSD 비동기 스왑(Swap) 기본 로직 구현.
- **[Opt]** SSD 수명 보호를 위한 스왑 쿨다운(Cooldown, 1초) 및 Lazy Swap(30초 대기) 전략 도입.
- **[Docs]** SDD 프로토콜에 따른 `docs/plans/` 및 `docs/specs/` 대대적 정비.
