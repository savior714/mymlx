# Knowledge: run.sh Options — 숨김/아카이브 옵션 목록

## §1. 메타 정보
- **Last Verified**: 2026-04-16
- **Category**: TUI Option Archive
- **Source of Truth**: `run.sh`의 `menu_options()`

## §2. 목적

`run.sh`의 `2. Options` 메뉴는 운영/보안/UX 이유로 **공개 옵션만 노출**한다.  
이 문서는 기본 UI에서 **숨김 처리된 옵션들의 범주**를 기록한다.

## §3. 숨김(비공개) 처리된 옵션 범주

- **Sampling / 품질 튜닝**: `temperature`, `top_p`, `top_k`, `min_p`, `repetition_penalty`, `presence_penalty`
- **Adapter / 로그**: `adapter_path`, `log_level`
- **Advanced cache / observability**: `advanced_cache`, `prompt_normalization`, `cache_observability`
- **Speculative decoding**: `speculative_decoding`, `draft_model`, `num_draft_tokens`
- **Tool/MCP integration**: `tool_choice_default`, `mcp_config_path`
- **추가 벤치마크**: stream TPS 비교, 5회 요약 벤치 등(필요 시 재노출)

## §4. 재노출 정책(운영 원칙)

- **기본값**: 숨김 유지(비공개)
- **재노출**: 운영자가 코드에서 명시적으로 메뉴에 다시 추가할 때만

