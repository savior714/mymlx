# mlx-server

[`mlx-lm`](https://github.com/ml-explore/mlx-lm) `mlx_lm.server`를 같은 프로세스에 임베드하고, Starlette로 프록시·확장한 로컬 개발용 HTTP 서버입니다.

## 요구 사항

- Python 3.12+
- Apple Silicon + MLX (공식 mlx-lm과 동일)

## 🚀 핵심 기능

- **MLX 최적화**: Apple Silicon에서 `mlx-lm` 엔진을 활용한 초고속 추론.
- **OpenAI 호환 API**: `/v1/chat/completions` 등 기존 OpenAI SDK와의 완벽한 호환성.
- **동적 모델 관리**: 서버 재기동 없이 `/v1/mlx/models/load` 및 `/unload` API를 통해 실시간 모델 교체 가능.
- **헤드리스(Headless) 설계**: 불필요한 웹 UI 없이 터미널 환경에 최적화된 가볍고 견고한 API 서버.
- **대화형 CLI 도구**: `./run.sh`를 통해 터미널에서 로컬 모델을 목록으로 보고 선택하며, 파라미터를 즉석에서 설정할 수 있는 인터랙티브 모드 제공.

---

## 🛠️ 빠른 시작

### 1. 설치
```bash
# uv 사용 권장
git clone https://github.com/your-repo/mlx-server.git
cd mlx-server
uv sync
```

### 2. 서버 실행

#### 방법 1: 대화형 CLI 도구 (`./run.sh`)
```bash
# 로컬 모델 목록에서 선택하고 파라미터 설정
./run.sh
```

#### 방법 2: 직접 CLI 실행
```bash
# 기본 포트(8080)에서 헤드리스 모드로 실행
uv run mlx-server serve --model Qwen/Qwen2.5-7B-Instruct-MLX

# 사용 가능한 옵션 확인
uv run mlx-server serve --help
```

서버가 실행되면 `http://localhost:8080`에서 OpenAI 호환 API를 즉시 사용할 수 있습니다.

---

## 스펙

- [`specs/api_compat.md`](specs/api_compat.md): OpenAI 호환 API 및 확장 API 명세
- [`docs/specs/cli_reference.md`](docs/specs/cli_reference.md): CLI 및 구성 옵션 상세 참조
- [`specs/model_lifecycle.md`](specs/model_lifecycle.md): 모델 로드/언로드 수명주기
- [`specs/ui.md`](specs/ui.md): [제거됨] 기존 웹 UI 명세 (v0.1.0 기준)

## 아키텍처

- [`docs/CRITICAL_LOGIC.md`](docs/CRITICAL_LOGIC.md): 핵심 설계 결정 및 불변 정책
- [`docs/memory/MEMORY.md`](docs/memory/MEMORY.md): 세션 지식 인덱스
- [`docs/memory/project_changelog.md`](docs/memory/project_changelog.md): 프로젝트 변경 이력

## 테스트

```bash
uv run pytest
```

통합 검증(에이전트 보고용 `verify-last-result.json` 생성):

```bash
./verify.sh
```

추가 인자는 `pytest`에 그대로 전달됩니다(예: `./verify.sh -k smoke`).
