# 🚀 Implementation Plan: Advanced Prompt Cache v2.0 Roadmap

M5 Max(128GB) 환경의 잠재력을 극한으로 끌어올리기 위한 차세대 캐시 시스템 고도화 로드맵입니다.

## 1. 단계별 마일스톤 (Milestones)

### Phase 4: Performance & Semantic Hit (현재 작업)
- [ ] **Hardware-Accelerated Hashing**: `xxhash` (XXH3) 도입으로 해싱 오버헤드 최소화.
- [ ] **Anchor-based Semantic Paging**: 개행(`\n\n`), Chat Special Tokens 등을 기준으로 가변 길이 페이징 구현.
- [ ] **Vectorized Token Processing**: 대규모 컨텍스트 입력 시 블록 분할 및 해싱 성능 최적화.

### Phase 5: Disk Persistence (영속성)
- [ ] **Safetensors Serialization**: KV-Cache 상태를 디스크에 직렬화하여 저장.
- [ ] **Mmap-based Lazy Loading**: 서버 재시작 시 `mmap`으로 캐시 메타데이터 즉시 복구.
- [ ] **Async Persistence Manager**: 추론 성능에 영향을 주지 않는 비동기 저장 파이프라인.

### Phase 6: VRAM-Aware Efficiency (안정성)
- [ ] **Quantized KV-Cache (Q4)**: VRAM 절감을 위한 캐시 양자화 적용.
- [ ] **Metal Memory Pressure Monitor**: 가용 메모리 상시 감시 및 능동적 Eviction.
- [ ] **Priority-based Pinning**: 핵심 시스템 프롬프트 및 지식 블록 보호.

---

## 2. Phase 4 상세 작업 명세

### Task 4.1: XXH3 Hashing 통합
*   **파일**: `src/mlx_server/cache_utils.py`
*   **변경**: `TokenHasher` 클래스에서 `xxhash.xxh3_64_hexdigest` 사용 시도로 전환 (폴백 유지).

### Task 4.2: Anchor-based Paging 구현
*   **파일**: `src/mlx_server/cache_utils.py`
*   **로직**:
    1.  정규식 또는 토큰 매칭으로 앵커 포인트 탐색.
    2.  `page_size`가 아닌 의미적 경계(Semantic Boundary)에서 블록 생성.
    3.  히트율 비교 검증.

---

## 3. 검증 계획 (Verification)
- **정적 검증**: `xxhash` 임포트 성공 및 해시 일관성 확인.
- **성능 검증**: 대규모 컨텍스트(10k+) 입력 시 해싱 소요 시간 측정.
- **히트율 검증**: 동일한 채팅 기록에 대해 Anchor-based 방식이 고정 크기 방식보다 높은 히트율을 기록하는지 확인.
