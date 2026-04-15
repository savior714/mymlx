# [Plan] Fix MLX Cache Resurrection Error (AttributeError)

## 1. 문제 분석 (Problem Analysis)
*   **에러 메시지**: `❌ Failed to swap in cache: module 'mlx.core' has no attribute 'load_safetensors'`
*   **원인**: `mlx.core` 모듈에는 `load_safetensors`라는 명칭의 속성이 존재하지 않음. MLX는 `.safetensors` 확장을 지원하는 상위 API인 `mx.load()`를 사용해야 함.
*   **현상**: 메모리 압박 시 SSD로 스왑된 캐시를 다시 로드(Resurrect)하려고 할 때 에러가 발생하여 캐시 히트 효과가 사라짐.

---

## 2. 작업 Task (Action Plan)

### Task 1: `src/mlx_server/cache_utils.py` 수정
*   [ ] `PersistentCacheLayer.swap_in()` 메서드에서 `mx.load_safetensors`를 `mx.load`로 변경.
*   [ ] `PersistentCacheLayer._write_to_ssd()` 메서드에서 `mx.save_safetensors`를 `mx.save`로 변경 (일관성 및 상위 API 사용 권장).
*   [ ] `AdvancedPromptCache.evacuate_if_needed()` 내의 직접 쓰기 코드에서도 `mx.save`로 통합.

### Task 2: 검증 (Verification)
*   [ ] `scripts/reproduce_swap_error.py` (임시) 생성하여 `PersistentCacheLayer` 단독 테스트.
*   [ ] 가상 데이터를 저장한 후 다시 로드 시 동일한 텐서 값이 복원되는지 확인.
*   [ ] `./verify.sh` 실행 (존재할 경우).

---

## 3. 예상 변경 사항
```diff
- kv_dict = mx.load_safetensors(str(path))
+ kv_dict = mx.load(str(path))
```

---

## 4. 리스크 및 후속 조치
*   **mmap 지원**: `mx.load()`는 `.safetensors` 파일 로드 시 기본적으로 memory mapping을 사용하여 효율적임.
*   **성능**: 캐시 복원 속도가 정상화되어 TTFT가 개선될 것으로 기대.
