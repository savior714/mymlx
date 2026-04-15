# Critical Logic & Architectural Decisions

## 문서 메타 (Version SSOT)
- **Last Verified**: 2026-04-15
- **Tested Version**: mlx-server v0.1.0-alpha
- **Min Supported**: PROJECT_RULES.md (500라인 가드레일 준수)
- **Reference**: specs/**/*.md, README.md, PROJECT_RULES.md

이 문서는 mlx-server 프로젝트의 핵심 아키텍처 설계 결정과 비즈니스 로직의 근거를 기록하는 SSOT(Single Source of Truth)입니다.

---

## 1. 문서 경계 (SSOT 계약)

- **`PROJECT_RULES.md` (규칙/운영 SSOT)**: 팀/에이전트가 항상 따라야 하는 "운영 규범"과 기술 스택, 검증 프로토콜 기록.
- **`docs/CRITICAL_LOGIC.md` (결정/불변 SSOT)**: 특정 시점에 **대안들 중 하나를 채택**한 결정(Decision Log)과 아키텍처 불변 정책 기록.
- **`specs/` (요구사항/계약 SSOT)**: 결정된 결과물인 API 명세, 모델 수명주기, UI 계약 등 기술 규격의 본문.

---

## 2. 핵심 아키텍처 결정 (Architectural Decisions)

### 2026-04-12: MLX 추론 엔진 - `mlx_lm.server` 루프백 프록시 아키텍처 채택

- **Context**: MLX 기반 모델 추론을 구현할 때, `mlx_lm` 라이브러리를 직접 임포트하여 커스텀 추론 루프를 작성할 것인지, 아니면 상용 수준의 안정성을 가진 `mlx_lm.server`를 백엔드로 활용할 것인지 결정이 필요함.
- **Decision**: 
  1. **Loopback Proxy**: 이 서버는 자체적으로 추론 루프를 돌리지 않고, 별도 스레드/프로세스에서 실행되는 `mlx_lm.server` (ThreadingHTTPServer 기반)에 HTTP 프록시 요청을 보내는 방식을 채택함.
  2. **책임 분리**: 공개 HTTP 레이어(Starlette)는 사용자 관리, 모델 로딩 상태 제어, `/ui` 제공, API 호환성 레이어를 담당하고, 실제 추론 성능과 텐서 연산은 `mlx_lm` 업스트림 엔진에 맡김.
- **Rationale**: 
  - **업스트림 호환성**: `mlx-lm`의 잦은 업데이트와 추론 최적화를 가장 빠르게 수용할 수 있음.
  - **안정성**: 추론 루프의 버그나 메모리 이슈가 API 관리 서버의 가용성에 미치는 영향을 최소화함.
  - **개발 속도**: 검증된 OpenAI 호환 서버인 `mlx_lm.server`를 재사용함으로써 핵심 부가가치(관리 기능, UI)에 집중함.
- **증적**: `src/mlx_server/proxy.py`, `src/mlx_server/backend.py`.

### 2026-04-12: 브라우저 UI 제거 및 헤드리스(Headless) 터미널 중심 아키텍처 전환

- **Context**: 초기 개발 단계에서 시각적 확인을 위해 도입했던 웹 UI가 프로젝트의 복잡도를 높이고, 사용자의 "터미널 기반 최소 기능" 선호에 따라 유지보수 비용 대비 효용이 낮아짐.
- **Decision**: 
  1. **UI Removal**: `src/mlx_server/static/` 폴더와 `/ui` 관련된 모든 라우트를 제거함.
  2. **Headless API Server**: 서버는 이제 순수하게 OpenAI 호환 API 및 `/v1/mlx/` 관리용 API만 제공하는 헤드리스 서버로 동작함.
  3. **CLI Focus**: 향후 모델 관리 및 추론 제어를 터미널 CLI 도구로 확장하는 방향으로 선회함.
- **Rationale**: 프로젝트의 본질인 "Apple Silicon 최적화 MLX 서버"에 집중하고, 불필요한 프론트엔드 의존성과 복잡성을 제거하여 가볍고 견고한 터미널 도구로서의 정체성을 강화함.
- **증적**: `docs/plans/archive/20260413_simplify_to_terminal.md`, `src/mlx_server/app.py`.

### 2026-04-14: Advanced Prompt Cache - Full Sequence Hashing 우선 전략 채택

- **Context**: Logical Paging 기반의 캐시 시스템에서 페이지 경계(128 tokens)에 정렬되지 않은 프롬프트 뒷부분이 반복 요청 시에도 계속 재연산되는 성능 저하 현상이 발견됨.
- **Decision**: 
  1. **Full-Sequence First**: 블록 단위 매칭을 시도하기 전, 입력 프롬프트 전체에 대한 해시 일치 여부를 0순위로 검사함.
  2. **Hybrid Retrieval**: 전체 일치 실패 시에만 기존의 블록 단위(128 tokens) 백오프 검색을 수행함.
- **Rationale**: 동일 프롬프트에 대한 반복적인 요청(Coding Assistant, IDE 연동 등)에서 TTFT를 극도로 단축하고, 불필요한 GPU 연산 자원을 절약하기 위함.
- **증적**: `src/mlx_server/cache_utils.py`, `docs/knowledge/advanced_cache_strategy.md`.

### 2026-04-14: LRU 2.0 - Priority-Aware & SSD Swap 전략 채택 (VRAM Relief)

- **Context**: 대규모 모델 구동 시 통합 메모리(Unified Memory)의 부족으로 인한 Metal OOM 위험이 상존함. 단순 축출(Eviction)은 캐시 히트율을 떨어뜨리고 TTFT를 재발생시킴.
- **Decision**: 
  1. **Priority Tagging**: 모든 캐시 블록에 P0(Pinned) ~ P3(Ephemeral) 등급을 부여하여 삭제 우선순위를 결정함.
  2. **Async SSD Swap**: 메모리 압박(Warning 80%, Critical 95%) 감지 시, 비활성 캐시 블록을 삭제하는 대신 SSD로 비동기 스왑(Swap-out) 처리함.
  3. **Zero-copy Resurrection**: 스왑된 블록은 `mx.load`(mmap)를 통해 투명하게 VRAM으로 다시 로드(Swap-in)됨.
  4. **SSD Longevity Opt**: 1초 쿨다운 및 30초 대기(Lazy Swap) 전략을 통해 SSD 쓰기 부하를 최소화함.
- **Rationale**: VRAM의 한계를 넘어서는 가상화된 캐시 레이어를 구축하여, 잦은 캐시 미스 없이도 시스템 안정성을 확보하기 위함.
- **증적**: `src/mlx_server/cache_utils.py`, `docs/plans/archive/20260414_priority_cache_ssd_opt.md`.

### 2026-04-15: SSD Swap 직렬화/역직렬화 계약(Serialization Contract) 확립

- **Context**: SSD에 저장된 KV 캐시를 로드(Resurrection)할 때 `KeyError: 'layer_0_k'`가 발생하여 캐시 복원 실패 → 10만+ 토큰 전체 재처리가 발생. 원인은 저장 시 `None` 레이어를 건너뛰어 비연속 인덱스(`layer_3, layer_7, ...`)가 생기지만, 로드 시 연속 인덱스(`layer_0, layer_1, ...`)를 가정했기 때문.
- **Decision**: 
  1. **Paired Serialization Functions**: `_serialize_kv_state()`와 `_deserialize_kv_state()`를 static method 한 쌍으로 분리하여 계약을 명시적으로 관리함.
  2. **Index Parsing**: 로드 시 `range(N)` 대신 regex로 safetensors 키 이름에서 실제 인덱스를 파싱하여 비연속 인덱스를 안전하게 처리.
  3. **Pre-save Materialization**: `mx.eval()`을 저장 직전에 호출하여 lazy 텐서의 미평가 상태 방지.
  4. **Corrupted File Cleanup**: swap_in 실패 시 손상 파일을 자동으로 삭제하여 반복 실패 방지.
- **Rationale**: 직렬화 ↔ 역직렬화가 동일한 인덱스 계약을 공유해야 하며, 모델 아키텍처(GQA/MQA)에 따라 일부 레이어만 활성화될 수 있으므로 연속성을 가정해서는 안 됨.
- **증적**: `src/mlx_server/cache_utils.py`, `docs/knowledge/ssd_swap_serialization_fix.md`.

### 2026-04-15: KV 캐시 양자화 — 3단계 통합 전략 채택 (Phase A→B→C)

- **Context**: 122B급 모델에서 KV 캐시가 128k 토큰 기준 ~32GB를 점유하여 128GB 워크스테이션의 VRAM을 압박. macOS Swap 발생으로 시스템 전체 성능 저하. 단순 Eviction은 캐시 히트율을 떨어뜨리므로, 캐시 자체의 용량을 줄이는 양자화 접근이 필요.
- **대안 분석**:
  1. **네이티브 kv-bits (아핀 양자화)**: mlx-lm generate_step에 이미 지원. 4-bit로 75% 절감. 즉시 적용 가능하나 최대 압축률은 4×.
  2. **TurboQuant (PolarQuant 3-bit)**: mlx-lm PR #1067. WHT + Lloyd-Max 코드북으로 4.6× 압축, Fused Metal 커널로 FP16의 0.98× 속도. 단, PR 미머지 상태이며 MLA/SSM 비호환.
  3. **커스텀 mx.quantize 래핑**: 자체 양자화 레이어 구현. 업스트림 호환성 리스크가 크고 Metal 커널 최적화 부재.
- **Decision**: **3단계 점진적 통합(A→B→C)** 채택.
  - **Phase A** (즉시): 네이티브 `kv_bits` 패스스루 — `backend.py`의 `_patch_kv_quantization`으로 `stream_generate`에 주입. `run.sh` TUI 연동.
  - **Phase B** (PR #1067 머지 후): TurboQuant `turbo_kv_bits` 패스스루 + `PersistentCacheLayer` 직렬화 계약 확장 (packed uint32 인식).
  - **Phase C** (Phase B 완료 후): Quantization-Aware Cache Manager — `headroom_ratio`, `_SSD_WRITE_THRESHOLD` 등을 양자화 모드에 맞게 동적 조정.
  - 대안 3(커스텀 구현)은 **업스트림 호환성 리스크**와 **Metal 커널 부재**로 기각.
- **Rationale**: 업스트림의 검증된 양자화 구현을 활용하여 유지보수 비용을 최소화하면서도, SSD Swap 시너지(파일 크기 4× 축소, I/O 4× 감소)를 극대화함. Phase A만으로도 즉각적인 75% 메모리 절감 효과.
- **증적**: `docs/specs/turbo_quant_integration.md`, `docs/plans/20260415_turbo_quant_plan.md`, `docs/knowledge/turbo_quant_mlx_lm.md`.

### 2026-04-15: 컨텍스트 재주입 최소화를 위한 Cache Observability + Grace Eviction 채택

- **Context**: 메모리 압박 구간에서 `hits=0` 블록이 즉시 PURGED되어, 직후 유사 요청 시 대규모 프롬프트 재처리(`Prompt processing progress` 급증)가 반복됨.
- **Decision**:
  1. **원인 분해 계측 강화**: 캐시 히트율(`full_hit_rate`, `paged_hit_rate`)과 미스 사유(`miss_reason_counts`)를 런타임 통계로 수집.
  2. **Grace Eviction**: 신규 콜드 블록(`hits=0`)에 최소 보호 시간(`cache_grace_seconds`)을 적용하여 즉시 PURGE를 억제.
  3. **Dynamic SSD Threshold**: `_SSD_WRITE_THRESHOLD`를 메모리 압박 비율에 따라 동적 조정해 SSD 쓰기량과 재연산 비용의 균형 유지.
  4. **Ops API 노출**: `/v1/mlx/cache/stats`로 운영 관측 데이터를 외부에서 확인 가능하게 표준화.
  5. **Prompt Normalization(옵션)**: 공백/개행 정규화로 캐시 키 흔들림을 줄이는 선택적 경로 제공.
- **Rationale**: 재연산 자체를 줄이려면 단순 용량 확장보다 “축출 타이밍 제어 + 미스 원인 가시화 + 키 안정화”를 함께 적용해야 효과가 큼.
- **증적**: `src/mlx_server/advanced_prompt_cache.py`, `src/mlx_server/advanced_prompt_cache_eviction.py`, `src/mlx_server/app.py`, `src/mlx_server/proxy.py`.

### 2026-04-15: Core Architecture Refactoring - Decoupling Logic & Infra (Phase 1-4)

- **Context**: 프로젝트가 성장함에 따라 `backend.py`, `proxy.py`, `app.py`, `advanced_prompt_cache.py` 등 주요 파일들이 500라인 가드레일에 근접하거나 비즈니스 로직과 인프라 로직이 혼재되어 유지보수성이 저하됨.
- **Decision**: 
  1. **Phase 1 (Domain Utils)**: 모델 검색 및 Metal 초기화 로직을 `model_resolver.py`, `memory_manager.py`로 분리.
  2. **Phase 2 (Request Pipeline)**: 요청 정규화 및 변환 로직을 `request_transformer.py`로 분리하여 `MlxRequestTransformer.transform`으로 캡슐화.
  3. **Phase 3 (Route Handlers)**: `app.py`에서 인라인으로 정의되던 모든 라우트 핸들러를 `handlers.py`로 독립화.
  4. **Phase 4 (Cache Indexing)**: `AdvancedPromptCache`에서 블럭 메타데이터 및 인덱싱 관리 로직을 `cache_index.py`로 분리.
- **Rationale**: 
  - **가독성 및 유지보수성**: 각 모듈의 책임을 명확히 하여 단일 책임 원칙(SRP)을 강화함.
  - **가드레일 준수**: 모든 소스 파일을 500라인 미만으로 유지하여 에이전트의 작업 정확도를 보장함.
  - **테스트 용이성**: 인프라 의존성 없이 비즈니스 로직(정규화, 변환 등)을 독립적으로 테스트할 수 있는 기반 마련.
- **증적**: `docs/plans/archive/20260415_refactor_core_architecture.md`, `src/mlx_server/` 하위 신설 모듈들.

---

## 3. 불변 정책 (Invariants)

- **OS/Platform**: 본 프로젝트는 **Apple Silicon (macOS)** 환경을 1순위 타겟으로 하며, 타 플랫폼(Windows, Linux)에 대한 호환성은 고려하되 MLX 최적화를 우선한다.
- **Namespace**: 신규로 추가되는 모든 관리용 API는 `/v1/mlx/` 경로 아래에 배치하여 기존 OpenAI 호환 엔드포인트와 충돌을 피한다.
- **Modularization**: 파일당 500라인 가드레일을 준수하며, 위반 조짐 시 즉시 리팩토링한다.
- **Headless Only**: 특별한 요청이 없는 한 브라우저 기반 UI는 더 이상 프로젝트의 핵심 기능으로 취급하지 않으며, 모든 기능은 CLI 또는 API를 통해 접근 가능해야 한다.
- **Diff Escape**: `apply_diff` 사용 시 `=======`, `<<<<<<<`, `>>>>>>>` 마커는 백슬래시로 이스케이프(`\=======`, `\<<<<<<<`, `\>>>>>>>`)해야 합니다. 자세한 내용은 `docs/knowledge/apply_diff_escape_rules.md`를 참조하세요.

### 2026-04-15: vLLM 스타일 블록 레벨 프리픽스 캐싱 및 3계층 구조 채택

- **Context**: 기존 단순 SHA256 해시 기반 프리픽스 캐싱은 중복 연산을 줄이는 데 한계가 있고, 대규모 동시 요청 환경에서 메모리 조각화 및 비효율적인 캐시 재사용 문제가 발생함. 또한 `mlx-lm` 서버의 `Full-hit` 시 `IndexError` 및 `Tail Integrity` 유실 위험이 보고됨.
- **Decision**: 
  1. **Block-level Hierarchical Hashing**: 128 토큰 고정 블록 단위 해싱 + 프리픽스 해시 체인 도입.
  2. **Metadata-rich Cache Key**: `model_id`, `tokenizer_version`, `quantization` 등을 포함한 복합 키로 캐시 유효성 보장.
  3. **3-Layer Architecture**: Index (Metadata/Hash), Runtime (VRAM/CoW), Persistence (Disk/SafeTensors) 계층으로 분리하여 관심사 분리.
  4. **Score-based Eviction**: 고정 우선순번 대신 `recency`, `reuse`, `cost`, `depth`를 결합한 동적 점수 모델 사용.
  5. **CoW with Immutability**: VRAM 공유 페이지의 읽기 전용 보장 및 참조 카운트(ref_count) 관리로 동시성 안전 확보.
  6. **Invariant Enforcement**: `Tail Integrity`(`prefix + tail == input`) 및 `Full-hit Exception Path`를 명시적 설계 원칙으로 고정.
- **Rationale**: vLLM의 선진적인 PagedAttention 및 Prefix Caching 설계를 MLX 환경에 맞게 이식하여, 메모리 효율성을 극대화하고 추론 안정성을 확보하기 위함.
- **증적**: `docs/specs/advanced_cache_manager.md`, `docs/plans/archive/20260415_enhance_cache_manager_spec.md`.

### 2026-04-15: Advanced Cache V2 — 하드웨어 잠재력 극대화 아키텍처 채택

- **Context**: V1의 블록 레벨 해싱은 긴 컨텍스트에서 여전히 $O(N)$ 해싱 비용이 발생하며, Unified Memory의 이점을 활용한 DISK I/O 최적화와 다중 사용자 환경의 스케줄링 보완이 필요함.
- **Decision**: 
  1. **Hierarchical Merkle Hashing**: $O(\log N)$ 증분 해싱을 위해 머클 트리 구조 도입.
  2. **Zero-Copy Swap (mmap)**: `mx.array`와 `mmap`을 결합하여 DISK ↔ VRAM 복사 없이 OS Page Cache 레벨에서 캐시를 즉시 로드.
  3. **Prefix-Priority Scheduler**: 동일 프리픽스 공유 요청을 묶는 Continuous Batching 및 Interleaving 매커니즘 도입.
  4. **Dynamic On-the-fly Quantization**: 메모리 압박 시 P2/P3 블록을 4-bit/8-bit로 즉시 양자화하여 메모리 수용량 2~4배 확장.
  5. **Sentinel Block System**: `IndexError` 방지를 위해 최장 매칭 프리픽스의 마지막 n개 토큰을 연산 엔진에 강제 전달하는 보초 시스템 구축.
- **Rationale**: M5 Max 128GB의 Unified Memory 인프라를 소프트웨어 레벨에서 완벽히 동기화하여, 병목 없는 초거대 컨텍스트 처리 및 고밀도 동시성을 달성하기 위함.
- **증적**: `docs/specs/advanced_cache_manager.md`, `docs/plans/archive/20260415_enhance_cache_manager_spec_v2.md`.

### 2026-04-15: Advanced Cache Implementation Spec v1.0 — 결정적 안정성 및 정합성 설계

- **Context**: V2 아키텍처를 실제 구현 가능한 수준으로 구체화하고, 다양한 환경 변화(모델 교체, 프롬프트 템플릿 변경 등)에도 캐시 정합성을 보장하기 위한 엄격한 규칙이 필요함.
- **Decision**: 
  1. **Core Invariants (I1-I5)**: Tail Integrity, Page Immutability(CoW), Full-Hit Safety(Sentinel), Key Strictness, Refcount Consistency를 시스템의 근간 원칙으로 고정.
  2. **Metadata-rich Cache Key**: 단순 토큰 해시가 아닌 `tokenizer_version`, `chat_template`, `quantization`, `rope_scaling` 등을 포함한 복합 키를 통해 환경 변화에 따른 오판독 원천 차단.
  3. **Multi-factor Eviction Scoring**: 단순히 LRU가 아닌 `Recency`, `Reuse Count`, `Recovery Cost(Disk/CPU)`, `Block Depth`를 결합한 가중 점수 모델 채택.
  4. **Refcount-based CoW**: `refcount` 및 `generation` 번호를 활용한 물리적 페이지 격리 매커니즘으로 동시 읽기/쓰기 안전 보장.
  5. **Fail-safe Paths**: OOM Guard(Soft 80%, Hard 95%), Disk Load Fail(Invalidate), Hash Mismatch, Sentinel Violation 대응 경로 정의.
- **Rationale**: 명확한 불변식과 환경 인지형(Environment-aware) 캐시 키를 정의함으로써, 어떤 복잡한 설정 변화나 메모리 압박 상황에서도 데이터 오염 없는 결정적 성능을 제공하기 위함.
- **증적**: `docs/specs/advanced_cache_manager.md`, `docs/plans/archive/20260415_integrate_implementation_spec_v1.md`.

---
<footer>
이 문서는 아키텍처의 중대한 변화가 있을 때마다 갱신되며, `specs/`의 기술적 사양과 상호 참조됩니다.
</footer>
