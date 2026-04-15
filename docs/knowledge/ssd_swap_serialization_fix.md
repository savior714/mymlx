# Knowledge: SSD Swap 직렬화/역직렬화 레이어 인덱스 불일치 버그 수정

## §1. 메타 정보
- **Last Verified**: 2026-04-15
- **Source**: 런타임 로그 분석 + safetensors 파일 구조 검증
- **Author**: AI Pair-Programmer
- **Created**: 2026-04-15
- **Tags**: #cache #ssd-swap #serialization #bug-fix #kv-cache

## §2. 문제 (Problem)

### 증상
```
❌ Failed to swap in cache: 'layer_0_k'
❌ Resurrection failed for dc67673b
```
SSD에서 KV 캐시를 로드(Swap-in/Resurrection)할 때 `KeyError: 'layer_0_k'`가 발생하여,
**캐시가 있음에도 복원 실패 → 10만+ 토큰 전체 재처리** → TTFT 급격히 증가.

### 근본 원인
`PersistentCacheLayer`의 **저장(serialize)과 로드(deserialize) 사이의 레이어 인덱스 계약 불일치**.

**저장 시** (`swap_out`):
- `kv_state` 리스트를 순회하면서 `layer is None`인 항목을 **건너뜀**
- 결과: `layer_3_k, layer_7_k, layer_11_k, ...` (비연속 인덱스)

**로드 시** (`swap_in` — 구버전):
```python
# ❌ 구버전: 연속 인덱스를 가정
num_layers = len(kv_dict) // 2  # 예: 24 keys / 2 = 12
for i in range(num_layers):     # 0, 1, 2, ..., 11
    k = kv_dict[f"layer_{i}_k"]  # → KeyError: 'layer_0_k' !!!
```

**실제 safetensors 파일의 키 구조** (dc67673b 검증 결과):
```
Layer indices: [3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47]
Min layer: 3, Max layer: 47, Count: 12
layer_0_k exists: False  ← 이것이 KeyError의 직접 원인
```

이것은 **mlx-lm의 KVCache 리스트 구조** 때문에 발생한다:
- 48-layer Qwen 모델에서 KV 캐시 리스트는 48개 항목
- 그 중 12개(매 4번째)만 실제 데이터가 있고, 나머지는 `None` 또는 `keys=None`

## §3. 해결책 (Solution)

### 3.1 직렬화 (`_serialize_kv_state`) — static method 분리
```python
@staticmethod
def _serialize_kv_state(kv_state: Any) -> dict:
    kv_dict = {}
    for i, layer in enumerate(kv_state):
        if layer is None:
            continue
        if hasattr(layer, "keys") and hasattr(layer, "values"):
            if layer.keys is None:  # ← 빈 KVCache 체크 추가
                continue
            kv_dict[f"layer_{i}_k"] = layer.keys
            kv_dict[f"layer_{i}_v"] = layer.values
        elif isinstance(layer, (list, tuple)) and len(layer) >= 2:
            if layer[0] is None:
                continue
            kv_dict[f"layer_{i}_k"] = layer[0]
            kv_dict[f"layer_{i}_v"] = layer[1]
    return kv_dict
```

### 3.2 역직렬화 (`_deserialize_kv_state`) — regex 기반 인덱스 파싱
```python
@staticmethod
def _deserialize_kv_state(kv_dict: dict) -> List[tuple]:
    import re
    layer_indices = set()
    for key in kv_dict:
        m = re.match(r"layer_(\d+)_[kv]", key)
        if m:
            layer_indices.add(int(m.group(1)))

    if not layer_indices:
        return []

    max_idx = max(layer_indices)
    kv_state = [None] * (max_idx + 1)
    for i in sorted(layer_indices):
        k_key, v_key = f"layer_{i}_k", f"layer_{i}_v"
        if k_key in kv_dict and v_key in kv_dict:
            kv_state[i] = (kv_dict[k_key], kv_dict[v_key])
    return kv_state
```

### 3.3 부가 수정 사항

| 항목 | 내용 |
|------|------|
| **`mx.eval()` 호출 추가** | 저장 전 lazy 텐서를 물질화하여 빈 safetensors 방지 |
| **손상 파일 자동 정리** | swap_in 실패 시 해당 .safetensors 파일 자동 삭제 |
| **evacuate 코드 중복 제거** | sync fallback도 `_serialize_kv_state` + `_write_to_ssd` 재사용 |

## §4. 핵심 교훈 (Key Takeaways)

1. **저장/로드는 반드시 한 쌍의 함수로 관리**: 직렬화 ↔ 역직렬화 계약이 한 곳에서 관리되어야 불일치를 방지할 수 있다.
2. **인덱스 연속성을 가정하지 말 것**: MLX-LM의 KVCache 리스트는 모델 아키텍처(GQA, MQA 등)에 따라 일부 레이어만 활성화될 수 있다.
3. **SSD 캐시 파일은 자기 설명적(Self-describing)이어야 함**: safetensors 키 이름 자체가 레이어 인덱스를 포함하므로, 파싱 기반 복원이 가장 안전하다.

## §5. 프로젝트 적용
- **적용 위치**: `src/mlx_server/cache_utils.py` (PersistentCacheLayer 클래스)
- **적용 일자**: 2026-04-15
- **테스트**: `tests/test_lru2_cache.py` (TestPersistentCacheLayerSerialization — 4개 케이스)
- **관련 문서**: `docs/knowledge/advanced_cache_strategy.md`, `docs/plans/20260414_priority_cache_ssd_opt.md`
