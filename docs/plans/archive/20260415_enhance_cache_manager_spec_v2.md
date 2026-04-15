# Plan: Advanced Cache Manager Specification Enhancement V2

사용자 피드백을 반영하여 `docs/specs/advanced_cache_manager.md`를 M5 Max 128GB의 잠재력을 최대한 끌어올릴 수 있는 차세대 아키텍처로 고도화합니다.

## 1. 주요 업데이트 항목 (V2)

### 1.1 계층적 머클 해싱 (Hierarchical Merkle Hashing)
- **기존**: 전체 시퀀스 $O(N)$ 해싱.
- **개선**: 블록 단위 머클 트리 구조 도입. 특정 블록 변경 시 해당 경로만 업데이트하는 **증분 해싱(Incremental Hashing)** 구현.
- **위치**: Section 2.1 메커니즘 업데이트.

### 1.2 Unified Memory Zero-Copy Swap (mmap)
- **기존**: VRAM ↔ DISK 간 데이터 이동 중심 설계.
- **개선**: Apple Silicon의 통합 메모리 이점을 활용한 **`mmap` 기반 Zero-copy 로딩**. OS Page Cache가 실제 연산 시점에 하드웨어 페이지 폴트를 통해 데이터를 로드하도록 설계.
- **위치**: Section 9.3 및 10.1 (Persistence Layer) 고도화.

### 1.3 캐시 인식형 스케줄러 (Prefix-Priority Scheduler)
- **신규**: 다중 사용자 환경에서 동일 프리틱스를 공유하는 요청을 묶어 처리하는 배칭 전략.
- **기능**: **Continuous Batching** 및 새로운 요청을 기존 연산에 끼워 넣는 **Interleaving** 로직 정의.
- **위치**: 신설 Section 8 (Cache-Aware Scheduling).

### 1.4 동적 KV-Cache 양자화 (Dynamic KV Quantization)
- **기존**: 메모리 부족 시 즉각적인 Disk Swap.
- **개선**: Soft Limit(80%) 시점에 P2/P3 블록을 4-bit/8-bit로 **시급한(On-the-fly) 양자화**. 디스크 I/O를 줄이고 인메모리 수용량을 2~4배 확장.
- **위치**: Section 9.1 및 10.1 (Runtime Layer) 업데이트.

### 1.5 Sentinel Block System
- **기존**: Last Token 남기기 가드레일.
- **개선**: 모델 무한 루프 및 IndexError를 완벽 방지하는 **Sentinel Block** 시스템으로 정교화.
- **위치**: Section 7.1 업데이트.

## 2. 작업 순서

1.  **`docs/specs/advanced_cache_manager.md` 업데이트**: V2 항목들을 상세히 기술하여 명세서 수정.
2.  **`docs/CRITICAL_LOGIC.md` 업데이트**: 핵심 설계 결정(Merkle Hash, Zero-copy, Scheduling) 반영.
3.  **검증**: 명세서 간의 정합성 확인 및 수용 기준(AC) 보완.

## 3. 예상 변경 요약

- **Section 2**: SHA-256을 머클 트리 증분 해싱으로 교체.
- **Section 7**: Sentinel Block 도입으로 안정성 가드레일 강화.
- **Section 8 (New)**: Cache-Aware Scheduling 섹션 추가.
- **Section 9**: 양자화 전략 및 mmap 로드 효율성 강조.
- **Section 10**: 계층별 역할을 V2 아키텍처 구성 요소에 맞게 재정의.
