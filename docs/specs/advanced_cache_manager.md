# 🧬 Advanced Cache Manager — Implementation Spec v1.0 (Integrated)

## 0. 설계 원칙 (Non-Negotiable Invariants)

본 시스템은 어떠한 경우에도 다음 **불변식**을 유지해야 한다.

### I1. Tail Integrity
```python
reconstructed_input == cached_prefix + original_tail
```
- 캐시 히트 시에도 전체 컨텍스트의 정합성이 유지되어야 하며, tail 토큰의 유실을 엄격히 금지한다.

### I2. Page Immutability (CoW)
- 모든 KV Page는 생성 후 **Immutable**하다.
- 내용 수정이나 공유 페이지의 변경이 필요한 경우 반드시 **Copy-on-Write (CoW)**를 수행하여 물리적으로 분격한다.

### I3. Full-Hit Safety (Sentinel)
- Full-hit 발생 시 모델 엔진(mlx-lm)의 `IndexError`를 방지하기 위해:
    - 매칭된 프리픽스의 마지막 n개(최소 1개) 토큰을 강제로 Runtime Prefill로 보낸다.
    - 또는 전용 `Full-Hit Safe Path` 분기를 사용하여 엔진을 구동한다.

### I4. Cache Key Strictness
- `model_id`, `tokenizer_version`, `quantization`, `rope_scaling` 등 환경 식별자가 하나라도 다르면 절대 캐시를 공유하지 않는다.

### I5. Refcount Consistency
- 모든 페이지는 `refcount`를 유지한다.
- `refcount == 0`인 페이지는 즉시 Reclaim 또는 Cold Storage(Disk) 이동 후보가 된다.

---

## 1. 자료구조 (Data Structures)

### 1.1 CacheKey (Environment-aware Hash)
```python
@dataclass(frozen=True)
class CacheKey:
    # 1. 환경 (계층 1)
    model_id: str
    tokenizer_version: str
    quantization: str  # "4bit", "8bit", "none"
    
    # 2. 내용 (계층 2 - Merkle Root)
    # 128 토큰 블록 체인의 최종 해시
    prefix_chain_hash: str 
    
    def __hash__(self):
        # 환경 + 내용의 결합 해시 반환
        return hash((self.model_id, self.tokenizer_version, self.quantization, self.prefix_chain_hash))
```

### 1.2 KVPage (Atomic Storage Unit)
```python
@dataclass
class KVPage:
    page_id: str         # UUID 또는 Hash
    tokens: List[int]    # 포함된 토큰 ID들
    kv_tensor: Any       # MLX Array (K, V)
    
    # 메타데이터
    refcount: int
    generation: int      # CoW 발생 시 증가
    location: str        # "VRAM", "DISK", "PURGED"
    
    # 점수화용 필드
    priority: int        # P0(Pinned) ~ P3(Ephemeral)
    last_access: float
    reuse_count: int
    depth: int           # 체인 내의 깊이 (0-based)
```

---

## 2. 핵심 로직 (Core Pipelines)

### 2.1 Fetch (Longest Prefix Match)
```python
def fetch(tokens: List[int]) -> Tuple[Optional[List[KVPage]], List[int]]:
    # 1. 블록 경계 계산
    indices = compute_block_indices(tokens)
    
    # 2. 역순 검색 (Longest Path First)
    for i in reversed(indices):
        chain_hash = compute_chain_hash(tokens[:i])
        key = CacheKey(current_model, tokenizer, quant_mode, chain_hash)
        
        pages = index_layer.lookup(key)
        if pages:
            # 3. Full-hit 방제 (Sentinel logic) 적용
            if i == len(tokens):
                return reconstruct_with_sentinel(pages, tokens)
            return pages, tokens[i:]
            
    return None, tokens
```

### 2.2 Insert & Evict
```python
def insert(tokens: List[int], kv_cache: List[KVPage], priority: int):
    # 1. VRAM 압박 체크
    if runtime_layer.usage_ratio() > SOFT_LIMIT:
        maintenance_thread.trigger_eviction()
        
    # 2. CoW 보장
    writable_pages = [runtime_layer.ensure_writable(p) for p in kv_cache]
    
    # 3. 인덱스 등록
    chain_hash = compute_chain_hash(tokens)
    key = CacheKey(..., chain_hash)
    index_layer.register(key, writable_pages, priority)
```

---

## 3. 계층 아키텍처 (Layered Architecture)

### 3.1 Index Layer (Control Plane)
- **책임**: `CacheKey` 기반의 조회 및 `prefix_chain_hash` 관리.
- **물리 구현**: `src/mlx_server/cache_index.py`

### 3.2 Runtime Layer (Computing Plane)
- **책임**: `KVPage`의 `kv_tensor` 수명 주기, CoW 로직, VRAM 할당.
- **물리 구현**: `src/mlx_server/advanced_prompt_cache.py`

### 3.3 Persistence Layer (I/O Plane)
- **책임**: SSD 스왑(safetensors), mmap 기반 Zero-copy 로드.
- **물리 구현**: `src/mlx_server/cache_persistent.py`

---

## 4. 실패 모드 및 운영 (Operations)

- **OOM Guard (95%)**: 즉각적 503 반환 및 GC 강제 수행.
- **Checksum Fail**: 캐시 폐기 및 원본 prefill 강제.
- **Background Thread**: 5초 주기로 `score = f(recency, reuse, depth)` 계산 및 축출.
