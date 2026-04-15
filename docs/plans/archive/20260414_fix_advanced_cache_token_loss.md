# 20260414 AdvancedPromptCache 토큰 유실 및 무한 반복 버그 수정 계획

## 1. 개요 (Context)
- 사용자 보고: 서버가 특정 지점에서 같은 내용을 반복하며, 토큰 크기가 1씩만 증가함.
- 원인 분석: 
    - `AdvancedPromptCache.fetch_nearest_cache`에서 블록 일치(Page Hit)가 발생했을 때, 접두사(Prefix)에 대해서만 `super().fetch_nearest_cache`를 호출함.
    - `super()` 호출 결과로 반환된 `rest`는 접두사 내에서 매칭되지 않은 부분만 포함함.
    - 하지만 원래의 `tokens` 리스트에는 접두사 이후의 토큰들이 더 존재할 수 있는데, 이를 결과에 포함하지 않고 버림으로써 **모델이 프롬프트의 뒷부분을 보지 못하고 접두사의 마지막 부분에서만 추론을 반복**하게 됨.
    - 특히 최근 도입된 `SafeguardPromptCache`가 접두사 매칭 시 마지막 1개 토큰을 `rest`로 항상 반환하도록 강제하면서, 이 1개 토큰만 처리 대상이 되고 그 뒤의 모든 실제 프롬프트 내용이 유실됨.

## 2. 해결 전략 (Strategy)
- 접두사 매칭 결과 반환 시, 접두사 내의 나머지 토큰(`res_rest`)과 **접두사 이후의 모든 토큰(`tokens[matched_len:]`)을 결합**하여 완전한 `rest` 리스트를 구성함.
- 이를 통해 캐시 히트 이후의 모든 프롬프트 정보가 온전하게 모델에 전달되도록 함.

## 3. 작업 리스트 (Tasks)
- [x] **`src/mlx_server/cache_utils.py` 수정**
    - `AdvancedPromptCache.fetch_nearest_cache` 내에서 `full_rest` 구성을 `res_rest + tokens[matched_len:]`으로 수정.
    - 로그 메시지에 실제 매칭된 토큰 수를 정확히 계산하여 표시.
    - **추가 개선**: `find_best_blocks`에서 전체 시퀀스 해시를 먼저 확인하여 반복 요청 시 100% 캐시 히트(Safeguard 제외) 보장.
- [x] **자가 검증**
    - `pytest` 실행 (10 passed).
    - 로직 검토: 접두사 이후 토큰 유실 여부 및 반복 요청 최적화 확인.

## 4. 상세 변경 예정 내역

### 4.1 `src/mlx_server/cache_utils.py` 수정 코드 (개념)
```python
            if cached_tokens:
                # 접두사(matched_len)에 대해 캐시 조회
                res_cache, res_rest = super().fetch_nearest_cache(model, tokens[:matched_len])
                if res_cache is not None:
                    # 유실되던 뒷부분(tokens[matched_len:])을 결합
                    full_rest = res_rest + tokens[matched_len:]
                    actual_matched = len(tokens) - len(full_rest)
                    logger.info(f"💾 Advanced Cache Hit: {actual_matched} tokens (hash: {h[:8]})")
                    return res_cache, full_rest
```

## 5. 기대 효과
- 프롬프트 뒷부분이 유실되지 않아 모델이 정상적인 문맥에서 추론을 수행함.
- `SafeguardPromptCache`와의 호환성이 확보되어 `IndexError`와 무한 반복 버그를 동시에 해결함.
