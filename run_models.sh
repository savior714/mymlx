#!/usr/bin/env bash
# MLX Server — 모델 전용 터미널 (run.sh와 별도 프로세스)
# 서버 실행 중에도 다른 터미널에서 모델 폴더 설정·HF 다운로드·목록 확인 가능.
# 설정은 run.sh와 동일하게 ~/.mlx-server/config 를 사용한다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

DEFAULT_MODELS_ROOT="${HOME}/Desktop/models"
CONFIG_DIR="${HOME}/.mlx-server"
CONFIG_FILE="${CONFIG_DIR}/config"

mkdir -p "$CONFIG_DIR"

LISTEN_HOST="127.0.0.1"
LISTEN_PORT="8080"
USER_TEMP=""
USER_MAX=""
USER_TOP_P=""
USER_TOP_K=""
USER_MIN_P=""
USER_REPETITION_PENALTY=""
USER_ADAPTER=""
USER_LOG="INFO"
USER_PROMPT_CACHE_SIZE=""
USER_DECODE_CONCURRENCY=""
USER_PROMPT_CONCURRENCY=""
USER_PREFILL_STEP_SIZE=""
USER_METAL_MEMORY_LIMIT=""
USER_METAL_CACHE_LIMIT=""
USER_PROMPT_CACHE_BYTES=""
USER_ADVANCED_CACHE="false"
USER_PAGE_SIZE=""
USER_KV_BITS=""
USER_KV_GROUP_SIZE=""
USER_CACHE_GRACE_SECONDS=""
USER_PROMPT_NORMALIZATION="false"
USER_CACHE_OBSERVABILITY="false"
USER_CACHE_HEADROOM_RATIO=""
USER_MODELS_ROOT="$DEFAULT_MODELS_ROOT"

load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        # shellcheck source=/dev/null
        source "$CONFIG_FILE" 2>/dev/null || true
    fi
}

save_config() {
    {
        echo "# mlx-server persisted settings"
        echo "# Generated: $(date)"
        echo "LISTEN_HOST=\"$LISTEN_HOST\""
        echo "LISTEN_PORT=\"$LISTEN_PORT\""
        echo "USER_TEMP=\"$USER_TEMP\""
        echo "USER_MAX=\"$USER_MAX\""
        echo "USER_TOP_P=\"$USER_TOP_P\""
        echo "USER_TOP_K=\"$USER_TOP_K\""
        echo "USER_MIN_P=\"$USER_MIN_P\""
        echo "USER_REPETITION_PENALTY=\"$USER_REPETITION_PENALTY\""
        echo "USER_ADAPTER=\"$USER_ADAPTER\""
        echo "USER_LOG=\"$USER_LOG\""
        echo "USER_PROMPT_CACHE_SIZE=\"$USER_PROMPT_CACHE_SIZE\""
        echo "USER_DECODE_CONCURRENCY=\"$USER_DECODE_CONCURRENCY\""
        echo "USER_PROMPT_CONCURRENCY=\"$USER_PROMPT_CONCURRENCY\""
        echo "USER_PREFILL_STEP_SIZE=\"$USER_PREFILL_STEP_SIZE\""
        echo "USER_METAL_MEMORY_LIMIT=\"$USER_METAL_MEMORY_LIMIT\""
        echo "USER_METAL_CACHE_LIMIT=\"$USER_METAL_CACHE_LIMIT\""
        echo "USER_PROMPT_CACHE_BYTES=\"$USER_PROMPT_CACHE_BYTES\""
        echo "USER_ADVANCED_CACHE=\"$USER_ADVANCED_CACHE\""
        echo "USER_PAGE_SIZE=\"$USER_PAGE_SIZE\""
        echo "USER_KV_BITS=\"$USER_KV_BITS\""
        echo "USER_KV_GROUP_SIZE=\"$USER_KV_GROUP_SIZE\""
        echo "USER_CACHE_GRACE_SECONDS=\"$USER_CACHE_GRACE_SECONDS\""
        echo "USER_PROMPT_NORMALIZATION=\"$USER_PROMPT_NORMALIZATION\""
        echo "USER_CACHE_OBSERVABILITY=\"$USER_CACHE_OBSERVABILITY\""
        echo "USER_CACHE_HEADROOM_RATIO=\"$USER_CACHE_HEADROOM_RATIO\""
        echo "USER_MODELS_ROOT=\"$USER_MODELS_ROOT\""
    } > "$CONFIG_FILE"
}

get_models_root() {
    if [[ -n "${USER_MODELS_ROOT:-}" ]]; then
        echo "$USER_MODELS_ROOT"
    else
        echo "$DEFAULT_MODELS_ROOT"
    fi
}

show_header() {
    [ -t 1 ] && clear || echo "---"
    echo "========================================"
    echo "   MLX Server — Model Manager (별도 터미널)"
    echo "========================================"
}

menu_list_local_models() {
    show_header
    local models_root
    models_root="$(get_models_root)"
    echo "로컬 모델 목록: ${models_root}"
    echo "----------------------------------------"
    local models=()
    if [[ -d "$models_root" ]]; then
        for d in "$models_root"/*/; do
            [[ -d "$d" ]] && models+=("$(basename "$d")")
        done
    fi
    if [[ ${#models[@]} -eq 0 ]]; then
        echo "  (없음)"
    else
        for i in "${!models[@]}"; do
            printf "  %2d. %s\n" "$((i+1))" "${models[$i]}"
        done
    fi
    echo "----------------------------------------"
    [ -t 0 ] && read -p "Press Enter to continue..." _unused || true
}

menu_models_root() {
    show_header
    local current_root
    current_root="$(get_models_root)"
    echo "Models Folder Settings"
    echo "----------------------------------------"
    echo "Current Root: $current_root"
    echo "Default Root: $DEFAULT_MODELS_ROOT"
    echo "----------------------------------------"
    read -p "New models folder path (empty=keep current): " input
    if [[ -z "$input" ]]; then
        return
    fi
    local expanded="${input/#\~/$HOME}"
    if [[ ! -d "$expanded" ]]; then
        echo "❌ 폴더가 존재하지 않습니다: $expanded"
        echo "   먼저 폴더를 생성한 뒤 다시 설정하세요."
        sleep 2
        return
    fi
    USER_MODELS_ROOT="$expanded"
    save_config
    echo "✅ 모델 폴더가 설정되었습니다: $USER_MODELS_ROOT"
    sleep 1
}

menu_download_hf() {
    show_header
    local models_root
    models_root="$(get_models_root)"
    echo "Hugging Face Model Download"
    echo "----------------------------------------"
    echo "Target Root: $models_root"
    echo "예) mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
    echo "Private/Gated 모델은 사전 로그인 필요: huggingface-cli login"
    echo "----------------------------------------"
    read -p "HF Repo ID 또는 URL: " repo_input
    if [[ -z "$repo_input" ]]; then
        return
    fi

    local repo_id="$repo_input"
    repo_id="${repo_id#https://huggingface.co/}"
    repo_id="${repo_id#http://huggingface.co/}"
    repo_id="${repo_id%/}"
    repo_id="${repo_id#models/}"

    if [[ "$repo_id" != */* ]]; then
        echo "❌ 올바른 Hugging Face Repo ID를 입력하세요. (예: org/model)"
        sleep 2
        return
    fi

    if [[ ! -d "$models_root" ]]; then
        echo "❌ 모델 루트 폴더가 존재하지 않습니다: $models_root"
        sleep 2
        return
    fi

    local repo_leaf="${repo_id##*/}"
    local target_dir="$models_root/$repo_leaf"
    local n=2
    while [[ -e "$target_dir" ]]; do
        target_dir="$models_root/${repo_leaf}-${n}"
        ((n++))
    done

    echo ""
    echo "Downloading:"
    echo "  repo_id:    $repo_id"
    echo "  local_dir:  $target_dir"
    echo ""

    set +e
    MLX_SERVER_MODELS_ROOT="$models_root" UV_NO_SYNC=1 uv run python - "$repo_id" "$target_dir" <<'PY'
import sys
from huggingface_hub import snapshot_download

repo_id = sys.argv[1]
target_dir = sys.argv[2]

snapshot_download(
    repo_id=repo_id,
    local_dir=target_dir,
    resume_download=True,
)
print(target_dir)
PY
    local exit_code=$?
    set -e

    if [[ $exit_code -ne 0 ]]; then
        echo "❌ 다운로드에 실패했습니다."
        echo "   - Repo ID 정확성"
        echo "   - private/gated 모델이면 로그인 상태 확인: huggingface-cli whoami"
        echo "   - 로그인 필요 시: huggingface-cli login"
        echo "   - 접근 권한 요청이 필요한 모델인지 Hugging Face 페이지에서 확인"
        echo "   - 네트워크 상태"
        sleep 3
        return
    fi

    echo "✅ 다운로드 완료: $target_dir"
    echo "   run.sh 의 Run Model에서 '${target_dir##*/}' 를 선택하거나 서버를 재로드하세요."
    sleep 2
}

main() {
    if [[ $# -gt 0 ]]; then
        echo "Usage: ./run_models.sh"
        echo "(인자 없이 실행 — 모델 관리 메뉴만 제공)"
        exit 1
    fi

    load_config

    while true; do
        show_header
        echo "1. 로컬 모델 목록"
        echo "2. 모델 폴더 경로 설정 (run.sh와 동일 설정 파일)"
        echo "3. Hugging Face에서 다운로드"
        echo "4. 종료"
        echo "----------------------------------------"
        read -p "Selection [1-4]: " choice

        case "$choice" in
            1) menu_list_local_models ;;
            2) menu_models_root ;;
            3) menu_download_hf ;;
            4) echo "Goodbye!"; exit 0 ;;
            *) echo "Invalid selection."; sleep 1 ;;
        esac
    done
}

main "$@"
