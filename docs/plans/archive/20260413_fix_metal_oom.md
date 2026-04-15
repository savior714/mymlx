# Implementation Plan - Metal Memory Management Enhancement

Metal 환경에서 발생하는 `kIOGPUCommandBufferCallbackErrorOutOfMemory` 오류를 근본적으로 해결하고, M5 Max(128GB)와 같은 고사양 장비의 성능을 최대로 활용하기 위한 메모리 관리 기능을 강화합니다.

## 1. 분석 및 해결 방향

- **현상**: M5 Max 128GB 장비에서도 Qwen3-Coder-Next(80B) 모델 사용 시 Metal OOM 발생.
- **원인 분석**:
    1. **Wired Limit 타이트함**: 현재 기본값이 `max_recommended_working_set_size`(~115GB)로 설정되어 있으나, 모델 가중치 + KV Cache + 중간 연산 버퍼가 이를 초과할 수 있음.
    2. **Cache Limit 제어 부재**: MLX가 해제된 메모리를 즉시 OS에 반환하지 않고 캐시로 들고 있어, 실제 가용 메모리가 부족해지는 현상.
    3. **Prompt Cache 관리 미흡**: 개수(`size`) 기준만 사용 시, 대규모 컨텍스트(Coding 등)에서 VRAM을 예측 불가능하게 점유.
    4. **잘못된 가이드**: 기존 명세의 권장값(8GB/16GB)이 고사양 장비 사용자에게 혼선을 줄 수 있음.
- **해결책**:
    - `metal_cache_limit` 옵션 추가 (메모리 반환 속도 조절).
    - `prompt_cache_bytes` 지원 (VRAM 점유 상한선 강제).
    - 명세의 권장값 현실화 및 Wired Limit 설정의 중요성 강조.

## 2. 주요 작업 내용

### 2.1 명세 업데이트 (`docs/specs/metal_memory.md`)
- `metal_cache_limit` 파라미터 정의 추가.
- M5 Max(128GB) 등 고사양 장비를 위한 현실적인 메모리 가이드라인 업데이트.
- `prompt_cache_bytes` 활용 방법 추가.

### 2.2 CLI 파서 확장 (`src/mlx_server/mlx_parser.py`)
- `--metal-cache-limit` 옵션 추가 (`_parse_size` 활용).

### 2.3 설정 시스템 연동 (`src/mlx_server/config.py`)
- `metal_cache_limit` 기본값(`None`) 및 환경 변수(`MLX_SERVER_METAL_CACHE_LIMIT`) 추가.

### 2.4 백엔드 로직 강화 (`src/mlx_server/backend.py`)
- `mx.metal.set_cache_limit()` 적용.
- `LRUPromptCache` 생성 시 `max_bytes` 파라미터 반영.
- 시작 시 장치 정보 및 적용된 제한값 상세 로깅.

## 3. 세부 변경 사항 (Draft)

### 3.1 `backend.py` 수정
```python
if mx.metal.is_available():
    # Wired Limit
    wired_limit = mlx_args.metal_memory_limit or mx.device_info()["max_recommended_working_set_size"]
    mx.metal.set_wired_limit(wired_limit)
    
    # Cache Limit
    if mlx_args.metal_cache_limit is not None:
        mx.metal.set_cache_limit(mlx_args.metal_cache_limit)
    
    logger.info(f"Metal wired limit: {wired_limit / 1024**3:.2f} GB")
    if mlx_args.metal_cache_limit:
        logger.info(f"Metal cache limit: {mlx_args.metal_cache_limit / 1024**3:.2f} GB")
```

## 4. 검증 계획

### 4.1 정적 검증
- CLI 도움말에서 신규 옵션(`--metal-cache-limit`, `--prompt-cache-bytes`) 확인.

### 4.2 런타임 검증
- 서버 시작 시 로그에 "Metal wired limit", "Metal cache limit"이 정확히 출력되는지 확인.
- M5 Max 128GB 환경에서 대형 모델 로드 테스트 (사용자 환경 재현 권장).

## 5. 비즈니스 로직 및 인프라 분리 원칙 준수
- 모든 하드웨어 제어 로직은 `start_backend`(`backend.py`) 내에 격리하여 비즈니스 로직(API 핸들링)과 분리함.
- `config.py`를 통해 명확한 설정 우선순위를 유지함.
