# [Plan] KV 캐시 양자화 통합 (TurboQuant A→B→C)

- **심각도**: Enhancement (성능 최적화)
- **상태**: Phase A 완료 (2026-04-15)
- **관련 명세**: `docs/specs/turbo_quant_integration.md`
- **관련 지식**: `docs/knowledge/turbo_quant_mlx_lm.md`

---

## 1. 배경

122B급 초거대 모델을 128GB 단일 워크스테이션에서 운용할 때, KV 캐시가 시스템 메모리의 25~30%를 점유한다. KV 캐시 양자화를 LRU 2.0 + Async Swap에 통합하면 **동일 VRAM으로 4배 이상의 시퀀스를 캐싱**할 수 있다.

---

## 2. Phase A: 네이티브 kv-bits 패스스루 [완료]

### 2.1 현재 완료된 항목
- [x] `backend.py`: `_patch_kv_quantization()` 함수로 `stream_generate`에 `kv_bits` 주입
- [x] `config.py`: `kv_bits`(None), `kv_group_size`(64) 기본값 + `MLX_SERVER_KV_BITS` 환경 변수
- [x] `mlx_parser.py`: `--kv-bits` (4, 8), `--kv-group-size` CLI 인자 등록

### 2.2 잔여 Task

#### Task A.1: `run.sh` TUI에 KV Bits 옵션 추가 ✅
- **파일**: `run.sh`
- **변경**:
  1. [x] 전역 변수 `USER_KV_BITS=""` 추가
  2. [x] `save_config` / `load_config`에 `USER_KV_BITS` 포함
  3. [x] Options 메뉴에 항목 18번으로 KV Bits 추가 + `edit_kv_bits` 함수
  4. [x] `start_server`에서 `[[ -n "$USER_KV_BITS" ]] && ARGS+=(--kv-bits "$USER_KV_BITS")` 추가

#### Task A.2 (선택): `--quantized-kv-start` 파라미터 추가
- **파일**: `mlx_parser.py`, `config.py`, `backend.py`
- **목적**: 처음 N개 토큰은 FP16으로 유지하여 초기 어텐션 품질 보장
- **우선순위**: Low (기본값 0으로 비활성화 가능)

### 2.3 검증
- [x] `--kv-bits 4`로 서버 기동 시 로그 메시지 확인 (backend.py L128)
- [x] `run.sh` Options에서 KV Bits 설정 → 서버 인자 전달 확인
- [x] 기존 테스트 전체 통과 (42/42 passed)

---

## 3. Phase B: TurboQuant 직접 통합 [대기]

> **전제**: mlx-lm PR #1067 머지 완료

### Task B.1: TurboQuant 파라미터 패스스루
- **파일**: `backend.py`, `mlx_parser.py`, `config.py`
- **변경**: `_patch_kv_quantization`에 `turbo_kv_bits`, `turbo_fp16_layers` 지원

### Task B.2: 직렬화 계약 확장
- **파일**: `cache_utils.py` (PersistentCacheLayer)
- **변경**: `_serialize_kv_state`에서 TurboQuantKVCache의 packed uint32 텐서 인식
- **하위 호환**: 기존 FP16/QuantizedKV 파일과 공존 가능해야 함

### Task B.3: CLI/TUI 연동
- **파일**: `mlx_parser.py`, `run.sh`
- **변경**: `--turbo-kv-bits` (2, 3, 4), `--turbo-fp16-layers` 인자 추가

### Task B.4: 아키텍처 호환성 체크
- **변경**: 모델 로드 시 MLA/SSM 아키텍처 감지 → TurboQuant 자동 비활성화 및 경고

---

## 4. Phase C: Quantization-Aware Cache Manager [대기]

> **전제**: Phase B 완료

### Task C.1: 동적 임계값 조정
- **파일**: `cache_utils.py` (AdvancedPromptCache)
- **변경**: `kv_bits` 인식하여 `_SSD_WRITE_THRESHOLD`(1로 하향) 및 `headroom_ratio`(0.75) 자동 조정

### Task C.2: 메타데이터 확장
- **변경**: `block_metadata`에 `quantization: {bits, type}` 필드 추가
- **용도**: 캐시 통계, 혼합 정밀도 블록 관리

### Task C.3: API 통계 노출
- **파일**: `app.py` 또는 `proxy.py`
- **변경**: `/v1/mlx/cache/stats`에 양자화 모드, 압축률, 비트 수 표시

---

## 5. 수치 목표 (Qwen 122B, M5 Max 128GB)

| 항목 | 현재 (FP16) | Phase A | Phase B |
| :--- | :--- | :--- | :--- |
| 128k KV 용량 | ~32GB | ~8GB | ~7GB |
| 동시 시퀀스 | 2~3개 | 10~12개 | 12~15개 |
| SSD Swap 크기 | 1.0× | 0.25× | 0.22× |
| 총 메모리 | ~110GB | ~85GB | ~80GB |
