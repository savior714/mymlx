# 📋 안정성 강화 플랜: Qwen3-Next 모델 OOM 및 강제 종료 문제 해결

## 1. 개요 (Context)
사용자가 `Qwen3-Coder-Next-oQ4` 모델 사용 중 메모리 점유율 급증(팬 소음) 및 프로세스 강제 종료(`terminated`) 현상을 보고함. 현재 설정상 `Advanced Cache`가 비활성되어 있어 메모리 압력에 대한 능동적 대응이 부족하고, `max_tokens` 및 `wired_limit` 설정이 공유 메모리 환경에서 임계치에 도달했을 가능성이 높음.

## 2. 원인 분석 (Root Cause Analysis)
- **High Memory Pressure**: Qwen3-Next는 최신 고사양 모델로 추론 및 KV Cache 점유량이 매우 큼.
- **Advanced Cache 비활성**: 현재 `USER_ADVANCED_CACHE="false"`로 설정되어 있어, 백그라운드 축출(Proactive Eviction) 및 디스크 스왑이 작동하지 않음.
- **공격적 메모리 설정**: `USER_MAX="65536"`(대규모 컨텍스트) 및 `USER_METAL_MEMORY_LIMIT="100GB"`가 시스템 전체 안정성을 위협함.
- **ArraysCache 특성**: Qwen3-Next는 구조적으로 캐시 트리밍이 어려운 `ArraysCache`를 사용할 수 있어, 기본 MLX 서버 루프에서 메모리 회수가 지연될 수 있음.

## 3. 해결 설계 (Design)

### 3.1 Advanced Cache 활성화 (필수)
- `AdvancedPromptCache`의 **Proactive Eviction**을 활성화하여 요청 사이 유휴 시간에 VRAM을 미리 확보.
- **MemoryPressureManager**를 통한 실시간 감시 및 `CRITICAL` 상태 시 즉각적인 `mx.clear_cache()` 수행.

### 3.2 설정 최적화 (Recommended)
- `USER_METAL_MEMORY_LIMIT`: 100GB → 96GB (128GB 기기의 안정적인 Wired Limit 권장값 75% 준수).
- `USER_MAX`: 65536 → 32768 (필요 시 점진적 확대).
- `USER_PROMPT_CACHE_BYTES`: 24GB → 16GB (VRAM 압박 완화).

### 3.3 로깅 및 진단 강화
- `run.sh`에서 종료 코드(137, 139) 발생 시 사용자에게 더 구체적인 조치 방법 안내.
- `AdvancedPromptCache`의 `cache_observability`를 활성화하여 메모리 점유 현황 로그 출력.

---

## 4. 상세 작업 (Implementation Steps)

### Phase 1: 설정 변경 (Config Optimization)
1. `~/.mlx-server/config` 파일의 주요 파라미터를 안정적인 값으로 수정.
2. `USER_ADVANCED_CACHE`를 `"true"`로 변경.

### Phase 2: 코드 보완 (Safety Guard)
1. `src/mlx_server/memory_manager.py`에서 `CRITICAL` 상태 진입 시 더 공격적인 자원 회수 로직 검토.
2. `run.sh`의 OOM 안내 문구 강화.

### Phase 3: 검증 (Verification)
1. `./verify.sh` 실행으로 기능 정합성 확인.
2. `Qwen3-Coder-Next-oQ4` 로드 테스트 (사용자 환경 재현).

---

## 5. 예상 리스크 및 대책 (Risk Mitigation)
- **리스크**: Advanced Cache 활성화 시 디스크 I/O 증가로 인한 약간의 지연 발생 가능.
- **대책**: SSD Swap Cooldown(1s)을 유지하여 수명 보호 및 성능 균형 유지.
- **리스크**: Qwen3-Next의 `ArraysCache` 비호환성.
- **대책**: `backend.py`의 `_check_speculative_compat` 로직을 참고하여 안정적인 일반 추론 경로 보장.
