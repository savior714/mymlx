# mlx-lm KV Cache Full-Hit Bug ($IndexError$) 및 해결 방인

- **작성일**: 2026-04-14
- **대상**: mlx-lm 0.31.2 이상 서버 환경
- **태그**: #mlx-lm #cache #bug #stability #kv-cache

## 1. 개요 (Background)
`mlx-lm 0.31.2` 버전의 `BatchGenerator`를 사용할 때, 입력 프롬프트가 이전에 연산된 KV Cache에 100% 매칭되어 '처리할 토큰(rest)'이 하나도 남지 않는 경우 서버가 가 `IndexError: list index out of range`와 함께 충돌하는 현상이 발견됨.

## 2. 현상 분석 (Bug Analysis)
### 2.1 원인 (Root Cause)
1. `mlx_lm.server`의 `ResponseGenerator._generate` 루프에서 입력 `segments`를 순회하며 이미 캐시된 부분을 제거(`pop`)함.
2. 프롬프트가 완전히 캐시되었을 경우, `segments` 리스트는 비어있는 상태가 됨.
3. 이를 `BatchGenerator.insert_segments`로 전달하면, `seq[-1]` 접근 시 리스트가 비어있어 인덱스 오류 발생.

### 2.2 부수 현상 (Side Effect)
캐시 레이어에서 접두사(Prefix) 매칭 후 나머지 토큰들을 제대로 결합하지 않을 경우, 모델이 문맥을 누락하고 특정 지점에서 무한 반복되는 현상이 동반될 수 있음.

## 3. 해결 방안 (Solution)

### 3.1 SafeguardPromptCache 도입
`LRUPromptCache`를 상속받아 `fetch_nearest_cache` 메서드를 오버라이드하여, 100% 매칭 시 마지막 1개 토큰을 강제로 `rest` 영역으로 반환함.

```python
def fetch_nearest_cache(self, model: Any, tokens: List[int]):
    cache, rest = super().fetch_nearest_cache(model, tokens)
    if cache is not None and not rest and tokens:
        # 마지막 1개 토큰을 남기고 캐시를 1개만큼 trim 함
        if can_trim_prompt_cache(cache):
            trim_prompt_cache(cache, 1)
            return cache, tokens[-1:]
    return cache, rest
```

### 3.2 Tail Retention 로직 보강
고급 캐시(Hash-based/Block-based) 매칭 시, 매칭된 접두사 토큰들과 원본 입력의 나머지 부분을 반드시 결합하여 반환할 것.

```python
# GOOD
full_rest = prefix_rest + tokens[matched_len:]
return cache, full_rest
```

## 4. 참고 사항
- 이 패치는 업스트림(`mlx-lm`) 코드를 수정하지 않고 래퍼 라이브러리 수준에서 안전을 확보하는 권장 방식임.
- 1개 토큰의 연산 비용은 전체 컨텍스트 로딩 시간에 비해 무시할 수준임.
- 상세 구현 내역은 `src/mlx_server/cache_utils.py` 참고.
