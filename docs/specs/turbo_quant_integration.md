# KV 캐시 양자화 통합 명세 (Turbo Quant Integration)

## 문서 메타 (Version SSOT)
| 항목 | 내용 |
|------|------|
| **Last Verified** | 2026-04-15 |
| **Status** | Phase A 완료, Phase B/C 미착수 |
| **Reference** | `docs/CRITICAL_LOGIC.md`, `docs/specs/advanced_cache_manager.md` |
| **Upstream PRs** | mlx-lm #1067 (TurboQuant), #1073 (server kv-bits), #1074 (QuantizedRotatingKVCache) |

---

## 1. 개요 (Overview)

KV 캐시 양자화를 LRU 2.0 아키텍처에 통합하여, 동일 VRAM 내 캐싱 가능한 시퀀스 수를 **4배 이상 확장**하고 SSD Swap I/O를 **75~80% 절감**한다.

### 1.1 핵심 목표
- **VRAM 절감**: 128k 토큰 기준 KV 캐시 ~32GB → ~7~8GB (4-bit/3-bit)
- **SSD 수명 연장**: Swap 파일 크기 축소로 쓰기 부하 4배 감소
- **Resurrection 속도 향상**: mmap 로드 대상 파일이 작아져 I/O 오버헤드 급감
- **Safe Zone 복귀**: 110GB 점유 → 80~85GB로 macOS Swap 미사용 구간 확보

---

## 2. 기술 배경

### 2.1 mlx-lm 네이티브 KV 양자화 (`--kv-bits`)
- `mlx_lm.generate.generate_step`에 `kv_bits` 파라미터 지원 (v0.22+)
- `QuantizedKVCache`: 표준 아핀 양자화 (group-wise, 4-bit 또는 8-bit)
- `QuantizedRotatingKVCache`: bounded-context + 양자화 결합 (PR #1074)
- **제약**: 배칭 비활성화 필요 (`BatchQuantizedKVCache` 미구현)

### 2.2 TurboQuant (PR #1067)
- **알고리즘**: PolarQuant (Walsh-Hadamard Transform + Lloyd-Max 최적 코드북)
- **압축률**: 3-bit에서 4.6×, Fused Metal 커널로 0.98× FP16 속도 유지
- **Bit-packed 저장**: 3-bit × 10 = 30bit per uint32
- **Layer-adaptive**: 첫/끝 N개 레이어를 FP16으로 유지하여 소형 모델 품질 보장
- **호환 아키텍처**: 표준 MHA만 지원 (MLA, SSM 비호환)
- **API**: `generate_step(prompt, model, turbo_kv_bits=3, turbo_fp16_layers=1)`

---

## 3. 통합 아키텍처 (Phase A/B/C)

### 3.1 레이어별 역할

| 레이어 | 역할 | KV 양자화 적용 방식 |
| :--- | :--- | :--- |
| **Inference Engine** | 토큰 생성, KV 캐시 생성 | `kv_bits` 또는 `turbo_kv_bits` 설정으로 생성 시점부터 양자화 |
| **Cache Manager** | 우선순위, Eviction | 양자화된 캐시는 용량이 작으므로 headroom/threshold 동적 조정 |
| **I/O Optimizer** | SSD Swap | 양자화 상태 그대로 직렬화 → I/O 병목 제거 |
| **Persistent Layer** | safetensors 저장/mmap 로드 | 양자화 텐서의 dtype 차이를 인식하여 저장/복원 |

### 3.2 데이터 흐름

```
Request → Tokenize → generate_step(kv_bits=4)
                         ↓
                   QuantizedKVCache 생성 (4-bit)
                         ↓
              AdvancedPromptCache.insert_cache()
                         ↓
           ┌─────────────┴─────────────┐
           ↓                           ↓
     VRAM (양자화 상태)         evacuate → SSD (양자화 그대로)
                                        ↓
                               safetensors (1/4 크기)
                                        ↓
                              Resurrection (mmap, 4× 빠름)
```

---

## 4. Phase 정의 및 수용 기준 (AC)

### Phase A: 네이티브 kv-bits 패스스루 [완료]
> 기존 `mlx_lm`의 `kv_bits` 파라미터를 서버에 전달하여 추론 시점부터 양자화된 KV 캐시 생성

**구현 현황**:
- [x] `backend.py`: `_patch_kv_quantization()` — `stream_generate` 래핑으로 `kv_bits` 주입
- [x] `config.py`: `kv_bits`, `kv_group_size` 기본값 및 환경 변수 지원
- [x] `mlx_parser.py`: `--kv-bits` (4, 8), `--kv-group-size` CLI 인자

**잔여 작업**:
- [x] `run.sh` TUI Options 메뉴에 KV Bits 옵션 추가
- [ ] `--quantized-kv-start` 파라미터 추가 (Phase A.1, 선택)

**AC**:
- `--kv-bits 4`로 서버 기동 시 로그에 `KV cache quantization enabled: kv_bits=4` 출력
- KV 캐시 메모리가 FP16 대비 약 75% 감소 확인 (Metal 메모리 통계)
- 기존 테스트 전체 통과

### Phase B: TurboQuant 직접 통합 [미착수]
> mlx-lm PR #1067 머지 후, `turbo_kv_bits` 파라미터 지원 및 직렬화 계약 확장

**작업 범위**:
- [ ] `_patch_kv_quantization`에 `turbo_kv_bits`, `turbo_fp16_layers` 지원 추가
- [ ] `mlx_parser.py`에 `--turbo-kv-bits` (2, 3, 4), `--turbo-fp16-layers` CLI 인자 추가
- [ ] `PersistentCacheLayer._serialize_kv_state`에서 bit-packed uint32 텐서 인식 분기
- [ ] `config.py` / `run.sh` 연동

**AC**:
- `--turbo-kv-bits 3`로 기동 시 3-bit PolarQuant 압축 적용
- SSD Swap 파일 크기가 FP16 대비 ~4.6× 축소
- Resurrection 시 bit-packed 텐서 정상 복원

**전제 조건**: mlx-lm PR #1067 머지 완료

### Phase C: Quantization-Aware Cache Manager [미착수]
> LRU 2.0의 임계값과 정책을 양자화 모드에 맞게 동적 조정

**작업 범위**:
- [ ] `AdvancedPromptCache`에 `kv_bits` 인식 로직 추가
- [ ] `_SSD_WRITE_THRESHOLD` 동적 조정 (양자화 시 1로 하향)
- [ ] `headroom_ratio` 양자화 모드 전용 값 (0.75)
- [ ] `block_metadata`에 `quantization` 필드 추가
- [ ] `/v1/mlx/cache/stats`에 양자화 통계 노출

**AC**:
- 양자화 모드에서 더 많은 캐시 블록을 VRAM에 유지
- SSD 저장 임계값이 양자화 상태에 따라 자동 조정
- 캐시 통계 API에 양자화 모드 및 비트 수 표시

---

## 5. 수치적 기대 효과 (Qwen 122B, M5 Max 128GB)

| 항목 | FP16 | Phase A (4-bit) | Phase B (TQ3) |
| :--- | :--- | :--- | :--- |
| 128k 토큰 KV 용량 | ~32GB | ~8GB | ~7GB |
| VRAM 동시 시퀀스 | 2~3개 | 10~12개 | 12~15개 |
| SSD Swap 파일 | 1.0× | 0.25× | 0.22× |
| Resurrection I/O | 1.0× | ~3.0× | ~4.6× |
| 총 메모리 점유 | ~110GB | ~85GB | ~80GB |

---

## 6. 리스크 및 제약

| 리스크 | 심각도 | 대응 |
| :--- | :--- | :--- |
| TurboQuant PR #1067 미머지 | Medium | Phase A로 즉시 효과 확보, Phase B는 머지 대기 |
| MLA/SSM 아키텍처 비호환 | Low | Qwen3-Coder = 표준 MHA, 모델 로드 시 아키텍처 체크 |
| kv_bits 활성 시 배칭 비활성화 | Medium | 단일 요청 워크로드에서는 영향 없음 |
| 직렬화 계약 변경 (Phase B) | Medium | `_serialize`/`_deserialize` 쌍 확장으로 하위 호환 유지 |
