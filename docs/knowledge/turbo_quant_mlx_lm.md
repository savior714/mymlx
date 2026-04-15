# TurboQuant KV 캐시 압축 — MLX-LM 기술 레퍼런스

## 문서 메타
- **작성일**: 2026-04-15
- **출처**: mlx-lm PR #1067, #1073, #1074, arXiv 2504.19874
- **목적**: 웹 검색 결과 자산화 (Knowledge Archiving)

---

## 1. 업스트림 PR 현황 (2026-04-15 기준)

### PR #1067: TurboQuant KV cache compression (3-bit, 4.6×)
- **상태**: Open (리뷰 진행 중)
- **저자**: @arozanov
- **핵심**: PolarQuant 알고리즘 + Fused Metal 커널
- **파일 추가**: `turboquant_cache.py`, `turboquant_rotation.py`, `turboquant_packing.py`, `turboquant_metal.py`, `turboquant_kernels.py`
- **API**: `generate_step(prompt, model, turbo_kv_bits=3, turbo_fp16_layers=1)`
- **호환**: 표준 MHA만 (MLA, SSM 비호환 — GLM-4.7-Flash, Qwen3.5-35B-A3B 테스트 실패)
- **URL**: https://github.com/ml-explore/mlx-lm/pull/1067

### PR #1073: server에 `--kv-bits` 추가
- **상태**: Open
- **핵심**: `mlx_lm.server`에 `--kv-bits`, `--kv-group-size`, `--quantized-kv-start` CLI 인자 추가
- **제약**: `kv_bits` 설정 시 배칭 비활성화 (`BatchQuantizedKVCache` 미구현)
- **URL**: https://github.com/ml-explore/mlx-lm/pull/1073

### PR #1074: QuantizedRotatingKVCache + KVSplit
- **상태**: Open
- **핵심**: `--max-kv-size`와 `--kv-bits` 동시 사용 가능. K/V 별 다른 bit 수 지원 (예: `kv_bits=(8, 4)`)
- **URL**: https://github.com/ml-explore/mlx-lm/pull/1074

---

## 2. TurboQuant 알고리즘 (PolarQuant)

### 2.1 작동 원리
1. **Normalize**: 각 KV 벡터의 norm 저장
2. **Rotate**: 고정 랜덤 직교 행렬(Walsh-Hadamard Transform)로 회전 → 좌표가 가우시안 분포로 변환
3. **Quantize**: Lloyd-Max 최적 코드북으로 스칼라 양자화 (3-bit = 8 centroid)
4. **Bit-pack**: 3-bit 인덱스를 uint32로 패킹 (10개/word)
5. **Dequantize**: centroid 룩업 + 역회전 + 스케일 복원

### 2.2 핵심 특성
- **Data-oblivious**: 입력 데이터와 무관한 고정 회전 행렬 사용 → 캘리브레이션 불필요
- **Fused Metal 커널**: quantize/dequantize를 단일 GPU 디스패치로 처리
- **Incremental decode buffer**: 디코딩 시 새 토큰만 역양자화 → O(1) 비용

### 2.3 비트별 품질 (logit cosine similarity)
| Bits | 압축률 | 품질 (cosine sim) | 비고 |
| :--- | :--- | :--- | :--- |
| 4-bit | 4.0× | 0.949~0.997 | 대부분 모델에서 무손실급 |
| 3-bit | 4.6× | 0.988~0.995 | 32B+ 모델에서 동일 출력 |
| 2-bit | 8.0× | 가변 | 실험적, 소형 모델 품질 저하 가능 |

### 2.4 3-bit > 4-bit 역설
PR #1067 저자 코멘트: "3-bit 코드북이 WHT 회전 후의 가우시안 분포에 더 잘 맞아 K 텐서에서 4-bit보다 품질이 좋다."

---

## 3. 벤치마크 데이터

### 3.1 Qwen2.5-32B-Instruct-4bit (M4 Pro 48GB)
| Config | 압축 | 속도 | 품질 |
| :--- | :--- | :--- | :--- |
| FP16 | 1.0× | 12.4 tok/s | baseline |
| TQ3 (all layers) | 4.6× | 12.1 tok/s | identical |

### 3.2 컨텍스트 스케일링 (32B, 3-bit)
| Context | FP16 Cache | TQ3 Cache | 절감 |
| :--- | :--- | :--- | :--- |
| 4K | 1088 MB | 225 MB | 863 MB |
| 8K | 2112 MB | 449 MB | 1.7 GB |
| 16K | 4160 MB | 897 MB | 3.3 GB |

### 3.3 200K 컨텍스트 (Llama-3-8B, 32GB Mac)
- FP16: swap death, 1시간 이상 멈춤 → 프로세스 강제 종료
- TurboQuant: KV 캐시 10.7GB, 정상 완료

---

## 4. 우리 프로젝트와의 통합 포인트

### 4.1 현재 구현 (Phase A: 네이티브 kv-bits)
- `backend.py`의 `_patch_kv_quantization()`이 `stream_generate`를 래핑하여 `kv_bits` 주입
- `--kv-bits 4` 또는 `MLX_SERVER_KV_BITS=4`로 활성화

### 4.2 향후 확장 (Phase B: TurboQuant)
- PR #1067 머지 후 `turbo_kv_bits`, `turbo_fp16_layers` 파라미터 패스스루
- `PersistentCacheLayer` 직렬화에서 bit-packed uint32 텐서 처리 필요
- `TurboQuantKVCache`의 `dequantize()` / `copy()` 메서드 활용

### 4.3 SSD Swap 시너지
- 양자화된 KV 텐서는 safetensors 직렬화 시 자동으로 작은 크기로 저장
- 기존 `_serialize_kv_state` → `_deserialize_kv_state` 파이프라인 그대로 사용 가능 (Phase A)
- TurboQuant의 packed uint32는 별도 직렬화 분기 필요 (Phase B)
