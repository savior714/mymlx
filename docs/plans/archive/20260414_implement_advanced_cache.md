# 🛠️ Implementation Plan: Advanced Cache & Virtualized Memory

M5 Max의 성능을 극대화하기 위한 고급 캐시 시스템 구현 계획입니다.

## 1. 단계별 마일스톤 (Milestones)

### Phase 1: Hash-Based Prefix Caching (기초)
- [ ] `src/mlx_server/backend.py`의 `PromptCache` 래퍼 구현
- [ ] 입력 토큰 시퀀스에 대한 SHA-256 해싱 모듈 추가
- [ ] SQLite 또는 인메모리 `HashStore` 구현 (KV-Cache 매핑 보관)
- [ ] 캐시 히트 시 `mlx-lm` 엔진에 캐시 상태 주입 로직 검증

### Phase 2: Virtualized Block Manager (고도화)
- [ ] 고정 크기(128 tokens) 블록 관리자 구현
- [ ] `mlx-lm`의 KV-Cache 텐서를 블록 단위로 슬라이싱/결합하는 어댑터 작성
- [ ] 동적 할당 및 LRU 기반 블록 교체 알고리즘 적용
- [ ] Metal 통합 메모리 점유율 모니터링 연동

### Phase 3: Integration & Testing (검증)
- [ ] RAG 시나리오(긴 컨텍스트)에서의 TTFT 성능 측정
- [ ] 다수 사용자 동시 접속 시의 메모리 안정성 테스트
- [ ] `run.sh` TUI에 실시간 캐시 히트율 표시 추가

---

## 2. 세부 작업 명세 (Task Details)

### Task 1.1: Content Hasher 구현
*   **목표**: `mlx-lm` 토크나이저 출력을 받아 안정적인 해시 생성.
*   **위치**: `src/mlx_server/cache_utils.py` (신규)

### Task 1.2: Backend Integration
*   **목표**: `MlxBackend` 클래스가 생성 시 고급 캐시 관리자를 초기화하도록 수정.
*   **파일**: `src/mlx_server/backend.py`

---

## 3. 검증 계획 (Verification)
- **성능**: 동일한 시스템 프롬프트를 가진 5개 요청의 평균 TTFT 비교.
- **안정성**: `mx.metal.get_active_memory()`가 임계치를 넘지 않는지 상시 모니터링.

---

## 4. 결정 사항 (Decisions)
- **Hash Algorithm**: Apple Silicon 가속을 받는 `hashlib.sha256` 사용.
- **Block Size**: MLX 연산 효율과 메모리 입도를 고려하여 `128`로 우선 설정.
