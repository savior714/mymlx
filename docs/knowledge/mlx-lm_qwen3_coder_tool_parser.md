# Knowledge: mlx-lm Qwen3-Coder Tool Parser 에러 해결

## §1. 메타 정보
- **Last Verified**: 2026-04-13
- **Source**: 내부 분석
- **Author**: system
- **Created**: 2026-04-13
- **Revised**: 2026-04-13 (세션 초기화 문제 발견 후 정정)
- **Related**: `src/mlx_server/proxy.py`, `docs/specs/behavioral_enforcement.md`

## §2. 핵심 솔루션

### 2.1 문제
mlx-lm 0.31.2의 Qwen3-Coder tool parser는 모델 응답에서 `<function=...>` XML 태그를 찾습니다. 이 태그가 없으면 `ValueError: No function provided.` 에러가 발생합니다.

**에러 로그**:
```
File ".../mlx_lm/tool_parsers/qwen3_coder.py", line 114, in parse_tool_call
  raise ValueError("No function provided.")
ValueError: No function provided.
```

**발생 시나리오**:
1. Qwen3-Coder 계열 모델 사용 중
2. tool call 기능을 활성화하려는 요청을 보냈으나, 모델 응답이 올바른 형식이 아님
3. 또는 요청에 `tools` 파라미터가 없는데 tool call을 기대함

### 2.2 해결책 (수정됨)
**이전 오류**: `tools` 파라미터를 제거하는 로직 → **세션 초기화 문제 유발**

**정상 동작**: `tools` 파라미터를 **upstream으로 그대로 전달**해야 함

**이유**:
- 클라이언트(IDE/MCP)는 `tools`/`tool_calls`/`finish_reason`이 일관되게 와야 함
- `tools`만 제거하면 응답 구조가 기대와 어긋나 세션을 초기화함
- Qwen3-Coder 모델은 `tools` 파라미터를 받고 올바른 XML 포맷으로 응답하는 것이 정상

**구현 위치**: [`src/mlx_server/proxy.py:65-87`](src/mlx_server/proxy.py:65)

```python
# 1. Provide default model if missing
if not data.get("model"):
    # ... model injection logic ...

# 2. Resolve model name/path
model_name = data.get("model")
if model_name and isinstance(model_name, str):
    # ... path resolution logic ...

# 3. NO 'tools' REMOVAL - pass through to upstream
# tools/tool_calls/finish_reason must be consistent between request and response
# to prevent session reset in IDE/MCP clients
```

### 2.3 SSE 버퍼링 개선
중간 프록시가 스트림을 끊는 경우를 줄이기 위해 SSE 응답에 다음 헤더를 추가:

**구현 위치**: [`src/mlx_server/proxy.py:100-102`](src/mlx_server/proxy.py:100)

```python
if "text/event-stream" in ct:
    resp_headers.setdefault("Cache-Control", "no-cache")
    resp_headers["X-Accel-Buffering"] = "no"
```

## §3. 프로젝트 적용
- **적용 위치**: `src/mlx_server/proxy.py`
- **적용 일자**: 2026-04-13
- **관련 문서**: 
  - `docs/specs/behavioral_enforcement.md`
  - `docs/knowledge/mlx-lm_api.md`
  - `pyproject.toml` (mlx-lm>=0.31.2)

## §4. 참고 사항
- mlx-lm 0.32.x+로 업그레이드하면 더 안정적인 tool parser를 사용할 수 있음
- Qwen3-Coder 모델을 사용하면서 tool call 기능을 활성화하려면 mlx-lm 최신 버전을 고려
- **중요**: `tools` 파라미터는 절대 제거하지 말고 upstream으로 전달해야 함
