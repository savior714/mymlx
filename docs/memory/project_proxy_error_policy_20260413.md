# Project Note: Proxy Error/Embeddings Policy (2026-04-13)

## 배경
- `/v1/embeddings` 요청이 업스트림 `mlx_lm.server`에서 404가 나고, 프록시 스트리밍 중 `httpx.ReadError`가 ASGI 예외로 이어지는 문제가 발생했다.

## 결정
- `mlx-server`는 **임베딩을 지원하지 않는다**.
- `/v1/embeddings`는 프록시 패스스루가 아니라, 래퍼에서 즉시 `501` + OpenAI 스타일 `error` JSON으로 응답한다.
- 업스트림 `4xx/5xx` 응답은 스트리밍으로 중계하지 않고 안전하게 버퍼링 후 일반 `Response`로 반환한다.

## 적용 결과
- `POST /v1/embeddings` 호출 시 명시적 미지원 응답(`embeddings_not_supported`)을 반환한다.
- 업스트림 에러 상황에서 `Exception in ASGI application` 스택트레이스 노이즈가 제거된다.
- 회귀 검증: `uv run pytest` 통과.
