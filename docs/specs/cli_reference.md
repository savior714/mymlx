# 🛠️ CLI 및 구성 옵션 상세 참조 (CLI Reference)

본 문서는 `mlx-server`에서 사용 가능한 모든 명령행 인자(CLI Flags)와 구성 옵션에 대한 상세 설명을 제공합니다.

## 1. 서버 제어 및 네트워크 (Server Control)

| 옵션 | 환경 변수 | 기본값 | 설명 |
|------|-----------|--------|------|
| `--listen-host` | `MLX_SERVER_LISTEN_HOST` | `127.0.0.1` | HTTP 서버가 바인딩할 호스트 주소입니다. |
| `--listen-port` | `MLX_SERVER_LISTEN_PORT` | `8080` | HTTP 서버가 사용할 포트 번호입니다. |
| `--config`, `-c` | - | `None` | YAML 구성 파일의 경로입니다. (`mlx` 및 `listen` 블록 포함 가능) |
| `--log-level` | `MLX_SERVER_LOG_LEVEL` | `INFO` | 로그 출력 레벨을 설정합니다. (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |

---

## 2. 모델 로딩 및 관리 (Model Management)

| 옵션 | 설명 |
|------|------|
| `--model` | 로드할 모델의 로컬 경로 또는 Hugging Face Repo ID입니다. <br/>※ 로컬 검색 우선순위: `~/Desktop/models` -> 현재 디렉토리 -> 절대 경로 |
| `--adapter-path` | LoRA 어댑터 가중치 및 구성의 경로입니다. (선택 사항) |
| `--draft-model` | 투기적 디코딩(Speculative Decoding)에 사용할 드래프트 모델의 경로입니다. |
| `--num-draft-tokens` | 드래프트 모델이 생성할 토큰 수입니다. (기본값: 3) |
| `--trust-remote-code` | 토크나이저 등에서 원격 코드를 허용할지 여부입니다. |
| `--local-models_root` | 로컬 모델 검색의 기준이 되는 루트 디렉토리입니다. (기본값: `~/Desktop/models`) |

---

## 3. 추론 및 샘플링 파라미터 (Inference/Sampling)

OpenAI 호환 API 요청 시 전달되는 파라미터의 기본값을 설정합니다.

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--temp` | `0.0` | 샘플링 온도. 값이 높을수록 창의적이고, 0에 가까울수록 결정론적입니다. |
| `--top-p` | `1.0` | 핵심 샘플링(Nucleus Sampling) 임계값입니다. |
| `--top-k` | `0` | Top-K 샘플링 제한. `0`은 비활성화를 의미합니다. |
| `--min-p` | `0.0` | Min-P 샘플링 임계값. `0.0`은 비활성화를 의미합니다. |
| `--repetition-penalty` | `0.0` | 반복 억제 패널티. `0.0`은 비활성화, `1.1~1.3` 범위에서 반복 억제에 효과적입니다. |
| `--repetition-context-size` | `20` | 반복 패널티를 적용할 최근 토큰 윈도우 크기입니다. |
| `--presence-penalty` | `0.0` | 존재 패널티. `0.0`은 비활성화. 등장 여부에 따라 고정 패널티를 적용하여 새로운 토픽 사용을 유도합니다. 범위: `-2.0`~`2.0`. |
| `--presence-context-size` | `20` | 존재 패널티를 적용할 최근 토큰 윈도우 크기입니다. |
| `--max-tokens` | `512` | 한 번의 요청으로 생성할 최대 토큰 수입니다. |

---

## 4. 메탈(Metal) GPU 및 메모리 관리 (Memory Management)

Apple Silicon 통합 메모리 환경에 최적화된 설정입니다.

| 옵션 | 단위 예시 | 설명 |
|------|-----------|------|
| `--metal-memory-limit` | `96GB`, `100GB` | MLX에서 사용할 **Metal 유선(Wired) 메모리**의 상한선입니다. 설정하지 않으면 시스템 권장값이 사용됩니다. |
| `--metal-cache-limit` | `4GB`, `16GB` | Metal 캐시 풀의 제한입니다. 대규모 할당 시 캐시를 해제하여 VRAM을 확보하는 속도를 조절합니다. |
| `--prompt-cache-bytes` | `24GB`, `512MB` | LRU 프롬프트 캐시가 사용할 전체 KV-Cache 메모리의 상한선입니다. |

---

## 5. 동시성 및 배치 처리 (Concurrency & Batching)

서버의 처리량(Throughput)과 성능을 최적화하기 위한 고급 옵션입니다.

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--decode-concurrency` | `32` | 배치가 가능한 경우, 병렬로 디코딩할 요청의 수입니다. |
| `--prompt-concurrency` | `8` | 배치가 가능한 경우, 병렬로 프롬프트를 처리(Prefill)할 요청의 수입니다. |
| `--prefill-step-size` | `2048` | 프롬프트 처리 시 청크(Chunk) 단위 크기입니다. |

---

## 6. 고급 캐시 관리 (Advanced Cache)

`docs/specs/advanced_cache_manager.md` 시스템과 관련된 설정입니다.

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--advanced-cache` | `true` | 내용 기반 해싱 및 논리적 페이지 관리를 통한 고급 캐시 시스템을 활성화합니다. (기본값: 활성) |
| `--no-advanced-cache` | - | 고급 캐시 시스템을 비활성화하고 기존 방식으로 폴백합니다. |
| `--page-size` | `128` | 가상화된 블록 관리를 위한 페이지 크기(토큰 단위)입니다. <br/>- 작은 값: 정밀한 캐시 공유 및 메모리 효율 <br/>- 큰 값: 관리 오버헤드 감소 |
| `--prompt-cache-size` | `10` | 프롬프트 캐시에 유지할 고유한 KV-Cache 상태의 최대 개수입니다. |

---

## 7. 기타 옵션 (Misc)

| 옵션 | 설명 |
|------|------|
| `--allowed-origins` | CORS 허용 오리진 설정 (기본값: `*`) |
| `--chat-template` | 토크나이저에 사용할 특정 채팅 템플릿을 지정합니다. |
| `--use-default-chat-template` | 모델 구성에 템플릿이 없어도 기본 채팅 템플릿을 강제 사용합니다. |
| `--chat-template-args` | `apply_chat_template`에 전달할 JSON 형식의 추가 인자입니다. (예: `'{"enable_thinking":false}'`) |
| `--pipeline` | 텐서 병렬화 대신 파이프라이닝을 사용합니다. |

---

## 8. 추론 감사 로그 (Inference audit)

크래시·오류 분석을 위한 구조화 로그(JSONL) 및 마지막 요청 스냅샷 파일입니다. 상세 스키마는 **`docs/specs/inference_audit_log.md`** 를 참고한다.

| 옵션 | 환경 변수 | 설명 |
|------|-----------|------|
| `--audit-log-path` | `MLX_SERVER_AUDIT_LOG_PATH` | 추론 완료 시 한 줄 JSON을 추가(append)한다. |
| `--audit-snapshot-path` | `MLX_SERVER_AUDIT_SNAPSHOT_PATH` | 각 요청 시작 시 덮어쓰는 JSON(비정상 종료 시 마지막 요청 메타). 생략 시 `--audit-log-path`와 같은 디렉터리에 `{stem}_last_request.json` 자동 사용. |

---

## 9. `run.sh` 제어 센터 동작 규약

### 9.1 메인 메뉴 구조

`run.sh` 실행 시 메인 메뉴는 다음 순서로 고정한다.

1. `Run Model` — 로컬 모델 목록 선택/수동 입력 후 서버 실행
2. `Options` — 서버/캐시/메모리 관련 옵션 설정
3. `Models Folder` — 로컬 모델 모음집 루트 경로 설정
4. `Download from Hugging Face` — Repo ID/URL 붙여넣기 다운로드
5. `Quit` — 종료

### 9.2 모델 루트 경로 해석

- `Models Folder`에서 설정한 경로는 `~/.mlx-server/config`의 `USER_MODELS_ROOT`에 저장한다.
- 서버 실행 시 `MLX_SERVER_LOCAL_MODELS_ROOT` 환경 변수로 주입하여, 모델명 해석의 1차 검색 루트로 사용한다.
- `USER_MODELS_ROOT`가 비어 있으면 기본값 `~/Desktop/models`를 사용한다.

### 9.3 Hugging Face 다운로드 규약

- 입력 허용: `org/model` 또는 `https://huggingface.co/org/model`
- URL 접두사는 내부에서 제거하여 Repo ID로 정규화한다.
- 다운로드 대상 폴더명은 기본적으로 `model`(Repo ID 마지막 세그먼트)이며, 충돌 시 `-2`, `-3` 접미사로 자동 회피한다.
- Private/Gated 모델은 사전 로그인(`huggingface-cli login`)이 필요하다.
- 실패 시 확인 항목: Repo ID 형식, 로그인 상태(`huggingface-cli whoami`), 권한 승인 여부, 네트워크 상태

### 9.4 옵션 설명 원칙 (TUI 문구 표준)

`Options` 화면과 각 `... Guide` 문구는 아래 패턴을 따른다.

- **정의**: 옵션이 제어하는 리소스/행동
- **상향 영향**: 값을 올릴 때의 성능/품질/안정성 변화
- **하향 영향**: 값을 낮출 때의 성능/품질/안정성 변화
- **튜닝 팁**: 단계별 변경 순서와 권장 범위

### 9.5 토큰 생산 속도(TPS) 튜닝 우선순위

`kv-bits=8` 유지 기준에서 권장 우선순위:

1. `--decode-concurrency` (생성 TPS 직접 영향)
2. `--prompt-concurrency` (prefill 처리량 영향)
3. `--prefill-step-size` (효율/피크 메모리 균형)
4. `--metal-cache-limit` (재할당 빈도/지연 안정성)
5. `--prompt-cache-bytes`, `--cache-headroom-ratio` (캐시 히트율/메모리 압력)
6. `--page-size` (상대적으로 미세 조정)
