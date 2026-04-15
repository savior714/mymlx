# Implementation Plan - 모델 경로 해결 및 프록시 로직 개선

사용자가 `/v1/chat/completions` 등 OpenAI 호환 엔드포인트로 요청을 보낼 때, 모델 이름이 로컬 `Desktop/models` 폴더에 있음에도 불구하고 Hugging Face로 요청이 전송되어 401 Unauthorized 및 404 Not Found 오류가 발생하는 문제를 해결합니다.

## 1. 문제 분석
- **현상**: `Qwen3-Coder-Next-oQ4` 모델이 로컬에 존재함에도 불구하고 HF API 호출이 발생하며 401 오류가 발생함. 이후 내부 MLX 서버는 404(예외 발생 시 기본값)를 반환.
- **원인**: `src/mlx_server/proxy.py`의 `proxy_to_mlx` 함수는 모델 이름이 누락된 경우에만 주입하며, 이미 제공된 모델 이름에 대해서는 로컬 경로 해결(`resolve_model_path`)을 수행하지 않고 그대로 내부 서버에 전달함. 내부 서버는 해당 이름을 단순 문자열로 취급하여 HF에서 찾으려 시도함.

## 2. 수용 기준 (Acceptance Criteria)
- [ ] `/v1/chat/completions` 요청 바디의 `model` 필드가 로컬 Desktop 모델 루트에 존재하는 이름인 경우, 절대 경로로 변환되어 전달되어야 함.
- [ ] 모델 로드 실패 시 나타나는 404 오류의 원인을 로그를 통해 더 명확히 파악할 수 있어야 함.

## 3. 작업 내역

### 3.1 `src/mlx_server/proxy.py` 수정
- `proxy_to_mlx` 함수 내에서 요청 바디의 `model` 필드를 추출.
- `resolve_model_path`를 사용하여 해당 이름을 로컬 경로로 변환.
- 변환된 경로를 다시 바디에 담아 내부 서버로 전달.

### 3.2 로깅 강화 (선택 사항)
- 프록시에서 상류(Upstream) 서버의 응답 바디가 에러 정보를 포함하고 있을 경우 이를 로그에 남기도록 개선.

## 4. 검증 계획
1. **로컬 모델 테스트**: `Qwen3-Coder-Next-oQ4` 등 로컬에 존재하는 모델 이름을 사용하여 `/v1/chat/completions` 호출.
2. **로그 확인**: HF 접근 시도가 사라지고 로컬 경로를 사용하는지 확인.
3. **HTTP 상태 코드**: 200 OK가 반환되는지 확인.
