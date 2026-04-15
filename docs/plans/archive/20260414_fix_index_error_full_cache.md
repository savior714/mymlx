# 20260414 mlx-lm 0.31.2 풀 캐시 히트 시 IndexError 수정 계획

## 1. 개요 (Context)
- 사용자 보고: `mlx_lm/generate.py:1638, in insert_segments: if len(seq[-1]) != 1: IndexError: list index out of range` 발생.
- 원인 분석: 
    - `mlx-lm 0.31.2`의 `BatchGenerator`는 입력 세그먼트 리스트가 비어있을 경우(`seq = []`) `IndexError`를 발생시킴.
    - `mlx_lm.server`는 프롬프트가 KV 캐시에 완전히 존재할 경우(`rest`가 비어있을 경우), 처리할 `segments`를 모두 제거하여 빈 리스트를 `insert_segments`에 전달함.
    - 특히 `AdvancedPromptCache`의 효율적인 매칭 성능으로 인해 전체 프롬프트가 히트되는 상황이 잦아지며 해당 버그가 노출됨.

## 2. 해결 전략 (Strategy)
- **PromptCache Safeguard**: `PromptCache`가 어떠한 경우에도 100% 매칭을 반환하지 않도록 제한.
- 매칭 결과가 비어있을 경우(Full Hit), 캐시된 상태에서 마지막 1개 토큰을 제거(`trim`)하고 해당 토큰을 '나머지(rest)'로 반환하여 `mlx-lm` 서버가 최소 1개의 세그먼트를 유지하도록 강제함.
- `PROJECT_RULES.md` 5.1절에 따라 업스트림 코드를 수정하지 않고, 서버에서 제공하는 `PromptCache` 객체 수준에서 해결함.

## 3. 작업 리스트 (Tasks)
- [ ] **`src/mlx_server/cache_utils.py` 수정**
    - `SafeguardPromptCache` 클래스 추가 (`LRUPromptCache` 상속).
    - `fetch_nearest_cache` 오버라이드하여 Full Hit 방지 로직 구현.
    - `AdvancedPromptCache`가 `SafeguardPromptCache`를 상속하도록 변경.
- [ ] **`src/mlx_server/backend.py` 수정**
    - `LRUPromptCache` 대신 `SafeguardPromptCache`를 사용하도록 변경 (고급 캐시 비활성화 시에도 안전 확보).
- [ ] **자가 검증**
    - `./verify.sh` 실행 및 결과 확인.

## 4. 상세 변경 내역

### 4.1 `src/mlx_server/cache_utils.py`
```python
from mlx_lm.models.cache import LRUPromptCache, trim_prompt_cache, can_trim_prompt_cache

class SafeguardPromptCache(LRUPromptCache):
    def fetch_nearest_cache(self, model: Any, tokens: List[int]) -> tuple[Optional[Any], List[int]]:
        cache, rest = super().fetch_nearest_cache(model, tokens)
        if cache is not None and not rest and tokens:
            if can_trim_prompt_cache(cache):
                trim_prompt_cache(cache, 1)
                return cache, tokens[-1:]
        return cache, rest
```

### 4.2 `src/mlx_server/backend.py`
```python
# Before
from mlx_lm.models.cache import LRUPromptCache
prompt_cache = LRUPromptCache(**cache_kwargs)

# After
from mlx_server.cache_utils import SafeguardPromptCache
prompt_cache = SafeguardPromptCache(**cache_kwargs)
```

## 5. 기대 효과
- 프롬프트가 완전히 캐시된 상태에서도 `mlx-lm` 서버가 중단 없이 추론을 시작할 수 있음.
- 1개 토큰의 재연산 비용은 무시할 수 있는 수준이며, 시스템 안정성이 최우선임.
