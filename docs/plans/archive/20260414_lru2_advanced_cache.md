# Implementation Plan - LRU 2.0 (Pressure-Aware & Priority-Based Cache)

M5 Max 128GB Unified Memory 환경에서 Qwen 2.5 122B와 같은 초거대 모델을 안정적으로 운용하기 위해, 지능형 메모리 압박 감지 및 우선순위 기반 디스크 스왑 시스템을 도입합니다.

## 1. 개요 (Overview)

- **배경**: 거대 모델 가중치가 VRAM의 상당 부분을 점유함에 따라, KV-Cache를 위한 가용 공간이 가변적이며 부족할 수 있음.
- **해결책**:
    - **LRU 2.0**: 단순 시간 기반(LRU)에서 [우선순위(Priority) + 시간(Recency) + 메모리 압박(Pressure)] 기반으로 진화.
    - **Disk Swap**: 메모리 부족 시 중요도가 낮은 캐시를 SSD로 비동기 스왑 (`safetensors` & `mmap`).
    - **Proactive Monitoring**: `mx.metal.get_active_memory()`를 통한 임계값 기반 대응.

## 2. 주요 구성 요소 설계

### 2.1 MemoryPressureManager
- **역할**: Metal 가용 메모리 상태 추적 및 상태 정의.
- **임계값**:
    - `Soft Limit (80%)`: 경고 상태. 백그라운드 스왑 준비.
    - `Hard Limit (95%)`: 위기 상태. 즉각적인 축출(Eviction) 및 강제 캐시 해제.

### 2.2 PersistentCacheLayer
- **역할**: SSD 디렉토리를 활용한 캐시 영속화.
- **기술**: `safetensors` 포맷 사용. `mx.load_safetensors`의 `mmap` 기능을 통한 지연 로딩(Zero-copy).
- **비동기화**: `ThreadPoolExecutor`를 사용하여 추론 루프 차단 없이 백그라운드 저장.

### 2.3 LRU2CacheManager (통합 레이어)
- `AdvancedPromptCache`를 확장하여 위 기능들을 통합.
- 캐시 블록별 `priority` 필드 추가 (P0: Pinned ~ P3: Ephemeral).

## 3. 작업 단계 (Implementation Steps)

### Phase 1: 기반 클래스 구현 (`src/mlx_server/cache_utils.py`)
- `CacheBlock` 메타데이터 구조 개선.
- `MemoryPressureManager` 클래스 추가.
- `PersistentCacheLayer` 클래스 추가 (Async Swap 로직 포함).

### Phase 2: LRU 2.0 로직 통합
- `AdvancedPromptCache`를 `LRU2CacheManager`로 업그레이드하거나 내부 로직을 LRU 2.0으로 교체.
- `check_pressure()` 연동 및 `evacuate()` 메서드 구현.

### Phase 3: 백엔드 및 API 연동
- `src/mlx_server/backend.py`에서 메모리 제한 설정 및 캐시 매니저 초기화.
- 요청 시 `priority` 정보를 주입받을 수 있도록 인터페이스 확장 (Optional).

## 4. 세부 설계 사항

### 4.1 Priority Hierarchy
| 등급 | 명칭 | 대상 | 전략 |
| :--- | :--- | :--- | :--- |
| **P0** | **Pinned** | 시스템 프롬프트, 핵심 스키마 | 삭제 불가 |
| **P1** | **High** | 활성 세션 이력 | Disk Swap 1순위 |
| **P2** | **Normal** | 일반 대화 이력 | LRU 삭제 대상 |
| **P3** | **Ephemeral** | 일회성 Task | 즉시 파지(Purge) |

### 4.2 Async Swap Workflow
1. 메모리 압박 감지 (`WARNING`).
2. P2 그룹 중 LRU 순서로 후보 선정.
3. `ThreadPoolExecutor`를 통해 `mx.save_safetensors` 실행.
4. 완료 시 VRAM에서 해제 (`del` & `mx.metal.clear_cache()`).
5. 메타데이터에 `location="DISK"` 표시.

## 5. 검증 계획

- **단위 테스트**: `MemoryPressureManager`의 임계값 감지 로직 검증.
- **통합 테스트**: 대량의 요청을 발생시켜 실제 VRAM 임계값 도달 시 스왑 기능 작동 확인.
- **성능 테스트**: Disk Swap된 캐시 재로드 시 TTFT 비교.

## 6. 리스크 관리
- **SSD IOPS 부하**: 빈번한 스왑 방지를 위해 `WARNING` 상태에서의 지연 쓰기(Batching) 고려.
- **Atomic Integrity**: 스왑 중인 블록에 대한 동시 접근 제어(Locking).
