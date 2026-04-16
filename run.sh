#!/usr/bin/env bash
# MLX Server - Structured TUI Script (v7; plain terminal scroll, no memory bar)
# 1. Main Menu (Run Model, Options, Quit)
# 2. Options Sub-menu for individual tuning (Extended)
# 3. Persistent settings in ~/.mlx-server/config

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Configuration
DEFAULT_MODELS_ROOT="${HOME}/Desktop/models"
CONFIG_DIR="${HOME}/.mlx-server"
CONFIG_FILE="${CONFIG_DIR}/config"

# Ensure config directory exists
mkdir -p "$CONFIG_DIR"

# --- Globals & Defaults ---
LISTEN_HOST="127.0.0.1"
LISTEN_PORT="8080"
USER_TEMP=""
USER_MAX=""
USER_TOP_P=""
USER_TOP_K=""
USER_ADAPTER=""
USER_LOG="INFO"
USER_PROMPT_CACHE_SIZE=""
USER_DECODE_CONCURRENCY=""
USER_PROMPT_CONCURRENCY=""
USER_PREFILL_STEP_SIZE=""
USER_METAL_MEMORY_LIMIT=""
USER_METAL_CACHE_LIMIT=""
USER_PROMPT_CACHE_BYTES=""
USER_ADVANCED_CACHE="true"
USER_PAGE_SIZE="128"
USER_KV_BITS=""
USER_KV_GROUP_SIZE=""
USER_CACHE_GRACE_SECONDS=""
USER_PROMPT_NORMALIZATION="false"
USER_CACHE_OBSERVABILITY="false"
USER_CACHE_HEADROOM_RATIO=""
USER_SPECULATIVE_DECODING="false"
USER_DRAFT_MODEL=""
USER_NUM_DRAFT_TOKENS=""
USER_CHAT_TEMPLATE_ARGS=""
USER_TOOL_CHOICE_DEFAULT="auto"
USER_MCP_CONFIG_PATH=""
USER_MODELS_ROOT="$DEFAULT_MODELS_ROOT"

is_int() {
    [[ "${1:-}" =~ ^[0-9]+$ ]]
}

is_number() {
    [[ "${1:-}" =~ ^[0-9]+([.][0-9]+)?$ ]]
}

is_size_with_unit() {
    [[ "${1:-}" =~ ^[0-9]+([.][0-9]+)?(B|KB|MB|GB|TB)$ ]]
}

set_if_valid_int_range() {
    local input="$1" min="$2" max="$3" var_name="$4" label="$5"
    if [[ -z "$input" ]]; then
        return 0
    fi
    if ! is_int "$input"; then
        echo "❌ $label: 정수를 입력하세요."
        sleep 1
        return 1
    fi
    if (( input < min || input > max )); then
        echo "❌ $label: 범위는 ${min}~${max} 입니다."
        sleep 1
        return 1
    fi
    printf -v "$var_name" '%s' "$input"
    return 0
}

set_if_valid_float_range() {
    local input="$1" min="$2" max="$3" var_name="$4" label="$5"
    if [[ -z "$input" ]]; then
        return 0
    fi
    if ! is_number "$input"; then
        echo "❌ $label: 숫자를 입력하세요."
        sleep 1
        return 1
    fi
    if ! awk -v x="$input" -v lo="$min" -v hi="$max" 'BEGIN {exit !(x>=lo && x<=hi)}'; then
        echo "❌ $label: 범위는 ${min}~${max} 입니다."
        sleep 1
        return 1
    fi
    printf -v "$var_name" '%s' "$input"
    return 0
}

set_if_valid_size() {
    local input="$1" var_name="$2" label="$3"
    if [[ -z "$input" ]]; then
        return 0
    fi
    if ! is_size_with_unit "$input"; then
        echo "❌ $label: 24GB, 512MB 형식(단위 포함)으로 입력하세요."
        sleep 1
        return 1
    fi
    printf -v "$var_name" '%s' "$input"
    return 0
}

run_light_benchmark_50k() {
    echo ""
    echo "Light Benchmark (Virtual 50K Tokens)"
    echo "  - 실행 방식: 현재 서버(/v1/chat/completions)에 1회 요청 후 환산"
    echo "  - 환산 기준: measured_tps 기준으로 50,000 토큰 예상 시간 계산"
    echo "  - 주의: decode/prompt concurrency 등은 서버 재시작 후 반영됩니다."
    echo ""

    local host="$LISTEN_HOST"
    local port="$LISTEN_PORT"
    local endpoint="http://${host}:${port}"
    local temp="${USER_TEMP:-0.2}"
    local top_p="${USER_TOP_P:-1.0}"
    local top_k="${USER_TOP_K:-0}"
    local max_tokens="${USER_MAX:-160}"

    if ! curl -sS -m 2 "${endpoint}/v1/models" >/dev/null; then
        echo "❌ 서버에 연결할 수 없습니다: ${endpoint}"
        echo "   먼저 Run Model로 서버를 실행한 뒤 다시 시도하세요."
        sleep 2
        return
    fi

    UV_NO_SYNC=1 uv run python - "$endpoint" "$temp" "$top_p" "$top_k" "$max_tokens" <<'PY'
import json
import sys
import time
import httpx

endpoint = sys.argv[1]
temp = float(sys.argv[2])
top_p = float(sys.argv[3])
top_k = int(sys.argv[4])
max_tokens = int(sys.argv[5])

target_tokens = 50000

with httpx.Client(timeout=300.0) as client:
    models_resp = client.get(f"{endpoint}/v1/models")
    models_resp.raise_for_status()
    models = models_resp.json().get("data", [])
    if not models:
        raise SystemExit("❌ /v1/models 결과가 비어 있습니다.")
    model = models[0]["id"]

    context_block = "\\n".join([
        "아래는 시스템 로그 컨텍스트입니다.",
        "- cache_hit_ratio: 0.82",
        "- queue_depth: 4",
        "- avg_decode_step_ms: 12.4",
        "- metal_usage_ratio: 0.74",
    ])
    # 가벼운 벤치마크를 위해 입력 길이는 제한하고, 결과를 50K로 환산
    long_context = (context_block + "\\n") * 40

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "너는 성능 로그 요약 어시스턴트다."},
            {"role": "user", "content": long_context + "\\n핵심 지표를 5줄로 요약해줘."},
        ],
        "temperature": temp,
        "top_p": top_p,
        "top_k": top_k,
        "max_tokens": max_tokens,
        "stream": False,
    }

    t0 = time.perf_counter()
    resp = client.post(f"{endpoint}/v1/chat/completions", json=payload)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    data = resp.json()

usage = data.get("usage", {})
completion_tokens = int(usage.get("completion_tokens", 0))
prompt_tokens = int(usage.get("prompt_tokens", 0))

if completion_tokens <= 0 or elapsed <= 0:
    raise SystemExit("❌ completion_tokens를 얻지 못했습니다. 다른 모델/설정으로 재시도하세요.")

tps_e2e = completion_tokens / elapsed
pred_sec_50k = target_tokens / tps_e2e

print("")
print("✅ Benchmark Result")
print(f"  model               : {model}")
print(f"  endpoint            : {endpoint}")
print(f"  prompt_tokens       : {prompt_tokens}")
print(f"  completion_tokens   : {completion_tokens}")
print(f"  elapsed_sec         : {elapsed:.3f}")
print(f"  measured_tps_e2e    : {tps_e2e:.2f} tok/s")
print(f"  virtual_50k_seconds : {pred_sec_50k:.1f} sec")
print(f"  virtual_50k_minutes : {pred_sec_50k/60:.2f} min")
PY

    [ -t 0 ] && read -p "Press Enter to continue..." _unused || true
}

run_stream_decode_benchmark_50k() {
    echo ""
    echo "Streaming Decode Benchmark (Virtual 50K Tokens)"
    echo "  - 실행 방식: stream=true로 1회 실측"
    echo "  - 출력 항목: prefill, E2E TPS, Decode TPS, 50K 환산 시간"
    echo "  - 주의: Decode TPS는 체감 속도 비교용 지표입니다."
    echo ""

    local host="$LISTEN_HOST"
    local port="$LISTEN_PORT"
    local endpoint="http://${host}:${port}"
    local temp="${USER_TEMP:-0.2}"
    local top_p="${USER_TOP_P:-1.0}"
    local top_k="${USER_TOP_K:-0}"
    local max_tokens="${USER_MAX:-160}"

    if ! curl -sS -m 2 "${endpoint}/v1/models" >/dev/null; then
        echo "❌ 서버에 연결할 수 없습니다: ${endpoint}"
        echo "   먼저 Run Model로 서버를 실행한 뒤 다시 시도하세요."
        sleep 2
        return
    fi

    UV_NO_SYNC=1 uv run python - "$endpoint" "$temp" "$top_p" "$top_k" "$max_tokens" <<'PY'
import json
import sys
import time
import httpx

endpoint = sys.argv[1]
temp = float(sys.argv[2])
top_p = float(sys.argv[3])
top_k = int(sys.argv[4])
max_tokens = int(sys.argv[5])
target_tokens = 50000

with httpx.Client(timeout=300.0) as client:
    models_resp = client.get(f"{endpoint}/v1/models")
    models_resp.raise_for_status()
    models = models_resp.json().get("data", [])
    if not models:
        raise SystemExit("❌ /v1/models 결과가 비어 있습니다.")
    model = models[0]["id"]

    context_block = "\n".join([
        "아래는 시스템 로그 컨텍스트입니다.",
        "- cache_hit_ratio: 0.82",
        "- queue_depth: 4",
        "- avg_decode_step_ms: 12.4",
        "- metal_usage_ratio: 0.74",
    ])
    long_context = (context_block + "\n") * 40

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "너는 성능 로그 요약 어시스턴트다."},
            {"role": "user", "content": long_context + "\n핵심 지표를 5줄로 요약해줘."},
        ],
        "temperature": temp,
        "top_p": top_p,
        "top_k": top_k,
        "max_tokens": max_tokens,
        "stream": True,
    }

    t0 = time.perf_counter()
    first_token_ts = None
    last_token_ts = None
    token_events = 0

    with client.stream("POST", f"{endpoint}/v1/chat/completions", json=payload) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            obj = json.loads(data)
            delta = obj.get("choices", [{}])[0].get("delta", {})
            piece = delta.get("content")
            if piece:
                now = time.perf_counter()
                if first_token_ts is None:
                    first_token_ts = now
                last_token_ts = now
                token_events += 1

    total_elapsed = time.perf_counter() - t0

if token_events <= 0:
    raise SystemExit("❌ 스트리밍 토큰 이벤트를 얻지 못했습니다.")

prefill_sec = (first_token_ts - t0) if first_token_ts is not None else total_elapsed
decode_window_sec = max(1e-9, (last_token_ts - first_token_ts) if first_token_ts is not None and last_token_ts is not None else 0.0)
decode_tps = token_events / decode_window_sec
e2e_tps = token_events / max(1e-9, total_elapsed)

pred_50k_decode_sec = target_tokens / decode_tps
pred_50k_e2e_sec = target_tokens / e2e_tps

print("")
print("✅ Streaming Benchmark Result")
print(f"  model                    : {model}")
print(f"  endpoint                 : {endpoint}")
print(f"  measured_token_events    : {token_events}")
print(f"  prefill_sec              : {prefill_sec:.3f}")
print(f"  decode_window_sec        : {decode_window_sec:.3f}")
print(f"  end_to_end_sec           : {total_elapsed:.3f}")
print(f"  measured_tps_decode      : {decode_tps:.2f} tok/s")
print(f"  measured_tps_e2e         : {e2e_tps:.2f} tok/s")
print(f"  virtual_50k_decode_sec   : {pred_50k_decode_sec:.1f} sec")
print(f"  virtual_50k_e2e_sec      : {pred_50k_e2e_sec:.1f} sec")
print(f"  virtual_50k_decode_min   : {pred_50k_decode_sec/60:.2f} min")
print(f"  virtual_50k_e2e_min      : {pred_50k_e2e_sec/60:.2f} min")
PY

    [ -t 0 ] && read -p "Press Enter to continue..." _unused || true
}

run_repeat_benchmark_5x() {
    echo ""
    echo "5x Repeat Benchmark Summary"
    echo "  - 1: Light Benchmark(24) 5회"
    echo "  - 2: Stream TPS Compare(25) 5회"
    echo ""
    read -p "Select benchmark type [1-2]: " bench_type

    if [[ "$bench_type" != "1" && "$bench_type" != "2" ]]; then
        echo "Invalid selection."
        sleep 1
        return
    fi

    local host="$LISTEN_HOST"
    local port="$LISTEN_PORT"
    local endpoint="http://${host}:${port}"
    local temp="${USER_TEMP:-0.2}"
    local top_p="${USER_TOP_P:-1.0}"
    local top_k="${USER_TOP_K:-0}"
    local max_tokens="${USER_MAX:-160}"

    if ! curl -sS -m 2 "${endpoint}/v1/models" >/dev/null; then
        echo "❌ 서버에 연결할 수 없습니다: ${endpoint}"
        echo "   먼저 Run Model로 서버를 실행한 뒤 다시 시도하세요."
        sleep 2
        return
    fi

    UV_NO_SYNC=1 uv run python - "$endpoint" "$temp" "$top_p" "$top_k" "$max_tokens" "$bench_type" <<'PY'
import json
import sys
import time
import httpx

endpoint = sys.argv[1]
temp = float(sys.argv[2])
top_p = float(sys.argv[3])
top_k = int(sys.argv[4])
max_tokens = int(sys.argv[5])
bench_type = sys.argv[6]  # 1=light(e2e), 2=stream(decode+e2e)
runs = 5

def summary(values):
    return min(values), sum(values)/len(values), max(values)

with httpx.Client(timeout=300.0) as client:
    models_resp = client.get(f"{endpoint}/v1/models")
    models_resp.raise_for_status()
    models = models_resp.json().get("data", [])
    if not models:
        raise SystemExit("❌ /v1/models 결과가 비어 있습니다.")
    model = models[0]["id"]

    context_block = "\n".join([
        "아래는 시스템 로그 컨텍스트입니다.",
        "- cache_hit_ratio: 0.82",
        "- queue_depth: 4",
        "- avg_decode_step_ms: 12.4",
        "- metal_usage_ratio: 0.74",
    ])
    long_context = (context_block + "\n") * 40

    e2e_tps_values = []
    decode_tps_values = []
    prefill_values = []

    for i in range(runs):
        if bench_type == "1":
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "너는 성능 로그 요약 어시스턴트다."},
                    {"role": "user", "content": long_context + "\n핵심 지표를 5줄로 요약해줘."},
                ],
                "temperature": temp,
                "top_p": top_p,
                "top_k": top_k,
                "max_tokens": max_tokens,
                "stream": False,
            }
            t0 = time.perf_counter()
            resp = client.post(f"{endpoint}/v1/chat/completions", json=payload)
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            completion_tokens = int(usage.get("completion_tokens", 0))
            if completion_tokens <= 0 or elapsed <= 0:
                continue
            e2e_tps_values.append(completion_tokens / elapsed)
            print(f"[{i+1}/{runs}] e2e_tps={completion_tokens/elapsed:.2f}")
        else:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "너는 성능 로그 요약 어시스턴트다."},
                    {"role": "user", "content": long_context + "\n핵심 지표를 5줄로 요약해줘."},
                ],
                "temperature": temp,
                "top_p": top_p,
                "top_k": top_k,
                "max_tokens": max_tokens,
                "stream": True,
            }
            t0 = time.perf_counter()
            first_token_ts = None
            last_token_ts = None
            token_events = 0
            with client.stream("POST", f"{endpoint}/v1/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        now = time.perf_counter()
                        if first_token_ts is None:
                            first_token_ts = now
                        last_token_ts = now
                        token_events += 1
            total_elapsed = time.perf_counter() - t0
            if token_events <= 0:
                continue
            prefill_sec = (first_token_ts - t0) if first_token_ts is not None else total_elapsed
            decode_window_sec = max(1e-9, (last_token_ts - first_token_ts) if first_token_ts is not None and last_token_ts is not None else 0.0)
            decode_tps = token_events / decode_window_sec
            e2e_tps = token_events / max(1e-9, total_elapsed)
            prefill_values.append(prefill_sec)
            decode_tps_values.append(decode_tps)
            e2e_tps_values.append(e2e_tps)
            print(f"[{i+1}/{runs}] decode_tps={decode_tps:.2f}, e2e_tps={e2e_tps:.2f}, prefill={prefill_sec:.3f}s")

if not e2e_tps_values:
    raise SystemExit("❌ 유효한 벤치마크 샘플을 얻지 못했습니다.")

e2e_min, e2e_avg, e2e_max = summary(e2e_tps_values)
print("")
print("✅ 5x Summary")
print(f"  model          : {model}")
print(f"  endpoint       : {endpoint}")
print(f"  samples        : {len(e2e_tps_values)} / {runs}")
print(f"  e2e_tps(min)   : {e2e_min:.2f}")
print(f"  e2e_tps(avg)   : {e2e_avg:.2f}")
print(f"  e2e_tps(max)   : {e2e_max:.2f}")
print(f"  50k_e2e(min)   : {50000/e2e_max:.1f} sec")
print(f"  50k_e2e(avg)   : {50000/e2e_avg:.1f} sec")
print(f"  50k_e2e(max)   : {50000/e2e_min:.1f} sec")

if bench_type == "2" and decode_tps_values:
    d_min, d_avg, d_max = summary(decode_tps_values)
    p_min, p_avg, p_max = summary(prefill_values)
    print(f"  decode_tps(min): {d_min:.2f}")
    print(f"  decode_tps(avg): {d_avg:.2f}")
    print(f"  decode_tps(max): {d_max:.2f}")
    print(f"  50k_decode(min): {50000/d_max:.1f} sec")
    print(f"  50k_decode(avg): {50000/d_avg:.1f} sec")
    print(f"  50k_decode(max): {50000/d_min:.1f} sec")
    print(f"  prefill(min)   : {p_min:.3f} sec")
    print(f"  prefill(avg)   : {p_avg:.3f} sec")
    print(f"  prefill(max)   : {p_max:.3f} sec")
PY

    [ -t 0 ] && read -p "Press Enter to continue..." _unused || true
}

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
        echo "USER_SPECULATIVE_DECODING=\"$USER_SPECULATIVE_DECODING\""
        echo "USER_DRAFT_MODEL=\"$USER_DRAFT_MODEL\""
        echo "USER_NUM_DRAFT_TOKENS=\"$USER_NUM_DRAFT_TOKENS\""
        echo "USER_CHAT_TEMPLATE_ARGS=\"$USER_CHAT_TEMPLATE_ARGS\""
        echo "USER_TOOL_CHOICE_DEFAULT=\"$USER_TOOL_CHOICE_DEFAULT\""
        echo "USER_MCP_CONFIG_PATH=\"$USER_MCP_CONFIG_PATH\""
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
    echo "      MLX Server Control Center"
    echo "========================================"
}

# --- 1. Model Selection & Execution ---
menu_run_model() {
    show_header
    local models_root
    models_root="$(get_models_root)"
    echo "Available Models in ${models_root}:"
    echo "----------------------------------------"

    local models=()
    if [[ -d "$models_root" ]]; then
        for d in "$models_root"/*/; do
            [[ -d "$d" ]] && models+=("$(basename "$d")")
        done
    fi

    if [[ ${#models[@]} -eq 0 ]]; then
        echo "  (none found)"
    else
        for i in "${!models[@]}"; do
            printf "  %2d. %s\n" "$((i+1))" "${models[$i]}"
        done
    fi

    echo "  0. Manual Input"
    echo "  B. Back to Main Menu"
    echo "----------------------------------------"
    read -p "Select a model: " selection

    case "$selection" in
        [Bb]) return ;;
        0)
            read -p "Model name/path: " input
            [[ -n "$input" ]] && start_server "$input"
            ;;
        [0-9]*)
            idx=$((selection - 1))
            if [[ $idx -ge 0 && $idx -lt ${#models[@]} ]]; then
                start_server "${models[$idx]}"
            else
                echo "Invalid selection."
                sleep 1
            fi
            ;;
        *)
            echo "Invalid selection."
            sleep 1
            ;;
    esac
}

start_server() {
    local model="$1"
    local models_root
    models_root="$(get_models_root)"
    echo ""
    echo "Starting server with model: $model"
    
    # Build arguments array
    local ARGS=(serve --model "$model" --listen-host "$LISTEN_HOST" --listen-port "$LISTEN_PORT")
    [[ -n "$USER_TEMP" ]] && ARGS+=(--temp "$USER_TEMP")
    [[ -n "$USER_MAX" ]] && ARGS+=(--max-tokens "$USER_MAX")
    [[ -n "$USER_TOP_P" ]] && ARGS+=(--top-p "$USER_TOP_P")
    [[ -n "$USER_TOP_K" ]] && ARGS+=(--top-k "$USER_TOP_K")
    [[ -n "$USER_ADAPTER" ]] && ARGS+=(--adapter-path "$USER_ADAPTER")
    [[ -n "$USER_LOG" ]] && ARGS+=(--log-level "$USER_LOG")
    [[ -n "$USER_PROMPT_CACHE_SIZE" ]] && ARGS+=(--prompt-cache-size "$USER_PROMPT_CACHE_SIZE")
    [[ -n "$USER_DECODE_CONCURRENCY" ]] && ARGS+=(--decode-concurrency "$USER_DECODE_CONCURRENCY")
    [[ -n "$USER_PROMPT_CONCURRENCY" ]] && ARGS+=(--prompt-concurrency "$USER_PROMPT_CONCURRENCY")
    [[ -n "$USER_PREFILL_STEP_SIZE" ]] && ARGS+=(--prefill-step-size "$USER_PREFILL_STEP_SIZE")
    [[ -n "$USER_METAL_MEMORY_LIMIT" ]] && ARGS+=(--metal-memory-limit "$USER_METAL_MEMORY_LIMIT")
    [[ -n "$USER_METAL_CACHE_LIMIT" ]] && ARGS+=(--metal-cache-limit "$USER_METAL_CACHE_LIMIT")
    [[ -n "$USER_PROMPT_CACHE_BYTES" ]] && ARGS+=(--prompt-cache-bytes "$USER_PROMPT_CACHE_BYTES")
    
    if [[ "$USER_ADVANCED_CACHE" == "true" ]]; then
        ARGS+=(--advanced-cache)
    else
        ARGS+=(--no-advanced-cache)
    fi
    [[ -n "$USER_PAGE_SIZE" ]] && ARGS+=(--page-size "$USER_PAGE_SIZE")
    [[ -n "$USER_KV_BITS" ]] && ARGS+=(--kv-bits "$USER_KV_BITS")
    [[ -n "$USER_KV_GROUP_SIZE" ]] && ARGS+=(--kv-group-size "$USER_KV_GROUP_SIZE")
    [[ -n "$USER_CACHE_GRACE_SECONDS" ]] && ARGS+=(--cache-grace-seconds "$USER_CACHE_GRACE_SECONDS")
    [[ "$USER_PROMPT_NORMALIZATION" == "true" ]] && ARGS+=(--prompt-normalization)
    [[ "$USER_CACHE_OBSERVABILITY" == "true" ]] && ARGS+=(--cache-observability)
    [[ -n "$USER_CACHE_HEADROOM_RATIO" ]] && ARGS+=(--cache-headroom-ratio "$USER_CACHE_HEADROOM_RATIO")

    if [[ "$USER_SPECULATIVE_DECODING" == "true" && -n "$USER_DRAFT_MODEL" ]]; then
        ARGS+=(--draft-model "$USER_DRAFT_MODEL")
        [[ -n "$USER_NUM_DRAFT_TOKENS" ]] && ARGS+=(--num-draft-tokens "$USER_NUM_DRAFT_TOKENS")
    fi

    [[ -n "$USER_CHAT_TEMPLATE_ARGS" ]] && ARGS+=(--chat-template-args "$USER_CHAT_TEMPLATE_ARGS")
    [[ -n "$USER_TOOL_CHOICE_DEFAULT" && "$USER_TOOL_CHOICE_DEFAULT" != "auto" ]] && ARGS+=(--tool-choice-default "$USER_TOOL_CHOICE_DEFAULT")
    [[ -n "$USER_MCP_CONFIG_PATH" ]] && ARGS+=(--mcp-config-path "$USER_MCP_CONFIG_PATH")

    echo "Models Root: $models_root"
    echo "Command: MLX_SERVER_LOCAL_MODELS_ROOT=\"$models_root\" uv run mlx-server ${ARGS[*]}"
    echo "----------------------------------------"

    local exit_code=0
    local safe_retry_applied=0

    run_server_once() {
        local -a run_args=("$@")
        set +e
        MLX_SERVER_LOCAL_MODELS_ROOT="$models_root" uv run mlx-server "${run_args[@]}"
        exit_code=$?
        set -e
    }

    run_safe_fallback() {
        local -a fallback_args=("$@")
        local strip_next=0
        local token=""
        local -a rebuilt=()
        for token in "${fallback_args[@]}"; do
            if [[ $strip_next -eq 1 ]]; then
                strip_next=0
                continue
            fi
            case "$token" in
                --decode-concurrency|--prompt-concurrency)
                    strip_next=1
                    ;;
                --advanced-cache|--no-advanced-cache)
                    ;;
                *)
                    rebuilt+=("$token")
                    ;;
            esac
        done
        rebuilt+=(--decode-concurrency 1 --prompt-concurrency 1 --no-advanced-cache)

        echo ""
        echo "⚠ SIGABRT 감지: Metal command encoder 충돌 가능성으로 안전 모드 재시도합니다."
        echo "   안전 모드: --decode-concurrency 1 --prompt-concurrency 1 --no-advanced-cache"
        echo "----------------------------------------"
        run_server_once "${rebuilt[@]}"
        safe_retry_applied=1
    }

    run_server_once "${ARGS[@]}"
    if [[ $exit_code -eq 134 ]]; then
        run_safe_fallback "${ARGS[@]}"
    fi
    if [[ $exit_code -ne 0 ]]; then
        echo ""
        echo "========================================"
        echo "서버 실행 중 오류가 발생했습니다. (Code: $exit_code)"
        if [[ $exit_code -eq 139 ]]; then
            echo "⚠ SIGSEGV (Signal 11) — Metal GPU 메모리 부족으로 프로세스가 강제 종료되었습니다."
            echo "  → KV 캐시 양자화(--kv-bits 4/8) 또는 Metal Memory Limit 조정을 권장합니다."
        elif [[ $exit_code -eq 137 ]]; then
            echo "⚠ SIGKILL (Signal 9) — 시스템 메모리 압력(Jetsam)으로 프로세스가 종료되었습니다."
        elif [[ $exit_code -eq 134 ]]; then
            echo "⚠ SIGABRT (Signal 6) — 내부 assertion 실패."
            if [[ $safe_retry_applied -eq 1 ]]; then
                echo "  → 안전 모드 재시도에서도 실패했습니다."
            else
                echo "  → decode/prompt concurrency를 1로 낮추고 --no-advanced-cache를 권장합니다."
            fi
        fi
        echo "========================================"
        sleep 3
    fi

    [ -t 0 ] && read -p "Press Enter to return to menu..." _unused || true
}

# --- 2. Options Management ---
menu_options() {
    while true; do
        show_header
        echo "Current Settings & Explanations"
        echo "Guide: 값 상향/하향 시 TPS(토큰/초), 지연, 메모리, 품질 간 트레이드오프를 함께 확인하세요."
        echo "----------------------------------------------------------------------"
        printf " %2d. Host:               %-15s (바인딩 주소: 보안/접근 범위 제어 | TPS 직접 영향은 거의 없음)\n" 1 "$LISTEN_HOST"
        printf " %2d. Port:               %-15s (수신 포트: 충돌 회피/동시 운영 | TPS 직접 영향은 거의 없음)\n" 2 "$LISTEN_PORT"
        printf " %2d. Temperature:        %-15s (샘플링 다양성: ↑창의성·변동성 / ↓재현성 | 토큰 품질 체감 영향)\n" 3 "${USER_TEMP:-Default}"
        printf " %2d. Max Tokens:         %-15s (출력 상한: ↑장문·총지연↑ / ↓짧은응답·총지연↓ | 요청당 생성 토큰량 결정)\n" 4 "${USER_MAX:-Default}"
        printf " %2d. Top-P:              %-15s (누클리어스 범위: ↑다양성 / ↓보수성 | 디코드 안정성·일관성 영향)\n" 5 "${USER_TOP_P:-Default}"
        printf " %2d. Top-K:              %-15s (후보 제한: ↑다양성 / ↓안정성 | 생성 패턴·노이즈 제어)\n" 6 "${USER_TOP_K:-Default}"
        printf " %2d. Adapter Path:       %-15s (LoRA 적용: 품질/도메인 성능 변화 | TPS는 모델·어댑터 구조에 따라 변동)\n" 7 "${USER_ADAPTER:-None}"
        printf " %2d. Log Level:          %-15s (로그 상세도: DEBUG↑진단·오버헤드↑ / ERROR↑가벼움)\n" 8 "$USER_LOG"
        printf " %2d. Prompt Cache Size:  %-15s (캐시 엔트리 수: ↑히트율·재사용 / ↓메타 메모리·관리비용)\n" 9 "${USER_PROMPT_CACHE_SIZE:-Default}"
        printf " %2d. Decode Concurrency: %-15s (생성 병렬도: ↑총TPS / ↑OOM·개별지연 가능 | 토큰처리량 핵심)\n" 10 "${USER_DECODE_CONCURRENCY:-Default}"
        printf " %2d. Prompt Concurrency: %-15s (prefill 병렬도: ↑입력처리량 / ↑피크메모리 | 긴 컨텍스트 처리 속도 영향)\n" 11 "${USER_PROMPT_CONCURRENCY:-Default}"
        printf " %2d. Prefill Step Size:  %-15s (prefill 청크: ↑효율 가능 / ↑피크메모리 | 첫 토큰 지연(TTFT) 영향)\n" 12 "${USER_PREFILL_STEP_SIZE:-Default}"
        printf " %2d. Metal Memory Limit: %-15s (Wired 상한: ↑모델 여유 / ↓시스템 여유 | OOM/스로틀 안정성 영향)\n" 13 "${USER_METAL_MEMORY_LIMIT:-Default}"
        printf " %2d. Metal Cache Limit:  %-15s (Metal 캐시 상한: ↑재사용 / ↓메모리 회수 | 안정성↔순간속도 균형)\n" 14 "${USER_METAL_CACHE_LIMIT:-Default}"
        printf " %2d. Prompt Cache Bytes: %-15s (KV 총량 상한: ↑재사용·반복응답↑ / ↑메모리 점유)\n" 15 "${USER_PROMPT_CACHE_BYTES:-Default}"
        printf " %2d. Advanced Cache:     %-15s (고급 캐시: ON=히트율·재사용↑ / OFF=단순·예측가능)\n" 16 "$USER_ADVANCED_CACHE"
        printf " %2d. Paged Cache Size:   %-15s (페이지 크기: 작게=정밀재사용 / 크게=관리오버헤드↓)\n" 17 "${USER_PAGE_SIZE:-Default}"
        printf " %2d. KV Cache Bits:      %-15s (KV 양자화: 4bit 메모리절감↑·품질↓ 가능 / 8bit 균형)\n" 18 "${USER_KV_BITS:-Off}"
        printf " %2d. KV Group Size:      %-15s (양자화 그룹: 작게=품질↑ / 크게=압축·메모리절감↑)\n" 19 "${USER_KV_GROUP_SIZE:-Default}"
        printf " %2d. Cache Grace Secs:   %-15s (cold 보호시간: ↑재사용기회 / ↑메모리 체류)\n" 20 "${USER_CACHE_GRACE_SECONDS:-Default}"
        printf " %2d. Prompt Normalize:   %-15s (입력 정규화: ON=키일관성·캐시히트↑ / OFF=원문보존)\n" 21 "$USER_PROMPT_NORMALIZATION"
        printf " %2d. Cache Observability:%-15s (캐시 계측로그: ON=병목분석↑ / OFF=로그오버헤드↓)\n" 22 "$USER_CACHE_OBSERVABILITY"
        printf " %2d. Cache Headroom:     %-15s (목표 여유비율: 낮게=안정↑ / 높게=캐시보존↑)\n" 23 "${USER_CACHE_HEADROOM_RATIO:-Default}"
        printf " %2d. Light Benchmark:    %-15s (정의: 1회 실측 후 50K 토큰 시간 환산)\n" 24 "Run"
        printf " %2d. Stream TPS Compare: %-15s (정의: Decode TPS vs E2E TPS 분리 측정)\n" 25 "Run"
        printf " %2d. 5x Summary Bench:   %-15s (정의: 24/25 기준 5회 반복 통계)\n" 26 "Run"
        echo "----------------------------------------------------------------------"
        echo " ── Speculative Decoding & Advanced ──"
        printf " %2d. Speculative Decode: %-15s (추측 디코딩: ON=Draft 모델로 속도↑ / OFF=표준 생성 | 배칭 불가)\n" 27 "$USER_SPECULATIVE_DECODING"
        printf " %2d. Draft Model Path:  %-15s (Draft 모델 경로: 로컬 절대경로 또는 HF Repo ID)\n" 28 "${USER_DRAFT_MODEL:-None}"
        printf " %2d. Num Draft Tokens:  %-15s (Draft 토큰 수: ↑수락률 높은 패턴에 유리 / ↓오버헤드 감소)\n" 29 "${USER_NUM_DRAFT_TOKENS:-3}"
        printf " %2d. Chat Template Args:%-15s (채팅 템플릿 인자: enable_thinking 등 JSON)\n" 30 "${USER_CHAT_TEMPLATE_ARGS:-'{}'}"
        echo " ── Tool Integration ──"
        printf " %2d. Tool Choice Default:%-14s (tool_choice 기본값: auto=모델판단 / none / required)\n" 31 "$USER_TOOL_CHOICE_DEFAULT"
        printf " %2d. MCP Config Path:   %-15s (MCP 설정 JSON 경로: 클라이언트 tool 통합용)\n" 32 "${USER_MCP_CONFIG_PATH:-None}"
        echo "----------------------------------------------------------------------"
        echo " B. Back to Main Menu"
        echo "----------------------------------------------------------------------"
        read -p "Select option to edit [1-32, B]: " opt

        case "$opt" in
            1)
                echo "Host Guide:"
                echo "  - 정의: 서버가 바인딩할 네트워크 주소"
                echo "  - 127.0.0.1: 로컬 전용(보안 안전)"
                echo "  - 0.0.0.0: 외부 접근 허용(방화벽/인증 필수)"
                read -p "Host [$LISTEN_HOST]: " input
                if [[ -n "$input" ]]; then
                    if [[ "$input" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
                        LISTEN_HOST="$input"
                    else
                        echo "❌ Host: IPv4 형식으로 입력하세요. (예: 127.0.0.1)"
                        sleep 1
                    fi
                fi
                ;;
            2)
                echo "Port Guide:"
                echo "  - 정의: 서버 수신 포트"
                echo "  - 상향 영향(예: 8080 -> 18080): 서비스 분리/동시 운영에 유리"
                echo "  - 하향 영향(예: 8080 -> 3000): 기존 도구 기본값과 맞추기 쉬움"
                echo "  - 튜닝 팁: 충돌 시 비어있는 포트로 이동 후 클라이언트 base URL만 동기화"
                echo "  - 권장 범위: 1024~65535 (예: 8080, 3000, 18080)"
                read -p "Port [$LISTEN_PORT]: " input
                set_if_valid_int_range "$input" 1 65535 LISTEN_PORT "Port"
                ;;
            3)
                echo "Temperature Guide:"
                echo "  - 정의: 생성 다양성 제어"
                echo "  - 상향: 창의성/변동성 증가"
                echo "  - 하향: 재현성/일관성 증가"
                echo "  - 권장: 0.0~0.7"
                read -p "Temperature [$USER_TEMP]: " input
                set_if_valid_float_range "$input" 0 2 USER_TEMP "Temperature"
                ;;
            4)
                echo "Max Tokens Guide:"
                echo "  - 정의: 한 요청의 최대 출력 토큰"
                echo "  - 상향: 장문 완결 가능성 증가"
                echo "  - 하향: OOM/지연 리스크 감소"
                echo "  - 팁: 장문 작업 시에만 높이고 기본은 보수적으로 운영"
                read -p "Max Tokens [$USER_MAX]: " input
                set_if_valid_int_range "$input" 1 131072 USER_MAX "Max Tokens"
                ;;
            5)
                echo "Top-P Guide:"
                echo "  - 정의: 확률 질량 누적 컷오프"
                echo "  - 상향(1.0 근접): 다양성 증가"
                echo "  - 하향(0.8~0.95): 보수적/안정적 출력"
                read -p "Top-P [$USER_TOP_P]: " input
                set_if_valid_float_range "$input" 0 1 USER_TOP_P "Top-P"
                ;;
            6)
                echo "Top-K Guide:"
                echo "  - 정의: 상위 K개 후보만 샘플링"
                echo "  - 상향: 표현 다양성 증가"
                echo "  - 하향: 출력 패턴 안정화"
                echo "  - 팁: 0=비활성, 보통 20~100"
                read -p "Top-K [$USER_TOP_K]: " input
                set_if_valid_int_range "$input" 0 10000 USER_TOP_K "Top-K"
                ;;
            7)
                echo "Adapter Guide:"
                echo "  - 정의: LoRA/Adapter 가중치 경로"
                echo "  - 설정 시: 도메인 특화 성능 향상 가능"
                echo "  - 비우면: 베이스 모델만 사용"
                read -p "Adapter Path [$USER_ADAPTER]: " input
                [[ -n "$input" ]] && USER_ADAPTER="$input"
                ;;
            8) edit_log_level ;;
            9)
                echo "Prompt Cache Size Guide:"
                echo "  - 정의: 보관할 캐시 엔트리 개수 상한"
                echo "  - 상향: 반복 요청 히트율 증가 가능"
                echo "  - 하향: 메타데이터/관리 오버헤드 감소"
                echo "  - 팁: bytes 상한(prompt-cache-bytes)과 함께 튜닝"
                read -p "Prompt Cache Size [$USER_PROMPT_CACHE_SIZE]: " input
                set_if_valid_int_range "$input" 1 1000000 USER_PROMPT_CACHE_SIZE "Prompt Cache Size"
                ;;
            10)
                echo "Decode Concurrency Guide:"
                echo "  - 정의: 생성 단계 병렬 처리 수"
                echo "  - 상향: TPS 증가 가능(가장 영향 큼)"
                echo "  - 하향: 안정성 증가/OOM 리스크 감소"
                echo "  - 팁: 1 -> 2 -> 4 순차 상승 테스트"
                read -p "Decode Concurrency [$USER_DECODE_CONCURRENCY]: " input
                set_if_valid_int_range "$input" 1 1024 USER_DECODE_CONCURRENCY "Decode Concurrency"
                ;;
            11)
                echo "Prompt Concurrency Guide:"
                echo "  - 정의: prefill 단계 병렬 처리 수"
                echo "  - 상향: 긴 입력 처리량 개선 가능"
                echo "  - 하향: 피크 메모리 압력 완화"
                echo "  - 팁: 긴 컨텍스트가 많을 때 2~4 범위 점검"
                read -p "Prompt Concurrency [$USER_PROMPT_CONCURRENCY]: " input
                set_if_valid_int_range "$input" 1 1024 USER_PROMPT_CONCURRENCY "Prompt Concurrency"
                ;;
            12)
                echo "Prefill Step Size Guide:"
                echo "  - 정의: 긴 프롬프트 prefill 청크 크기"
                echo "  - 상향(예: 4096): 효율 개선 가능, 피크 메모리 증가 가능"
                echo "  - 하향(예: 1024): 메모리 피크 완화, 오버헤드 증가 가능"
                echo "  - 팁: 기본 2048에서 워크로드별 미세조정"
                read -p "Prefill Step Size [$USER_PREFILL_STEP_SIZE]: " input
                set_if_valid_int_range "$input" 1 131072 USER_PREFILL_STEP_SIZE "Prefill Step Size"
                ;;
            13)
                echo "Metal Memory Limit Guide:"
                echo "  - 정의: MLX Wired 메모리 상한"
                echo "  - 상향: 대형 모델/장문 여유 증가"
                echo "  - 하향: OS/다른 앱 여유 증가"
                echo "  - 팁: 반드시 단위 포함 (예: 96GB, 100GB)"
                read -p "Metal Memory Limit [$USER_METAL_MEMORY_LIMIT]: " input
                set_if_valid_size "$input" USER_METAL_MEMORY_LIMIT "Metal Memory Limit"
                ;;
            14)
                echo "Metal Cache Limit Guide:"
                echo "  - 정의: Metal 임시 캐시 상한"
                echo "  - 상향: 재할당 감소로 속도 안정 가능"
                echo "  - 하향: 메모리 회수 빨라져 OOM 완화"
                echo "  - 팁: 4GB -> 6GB -> 8GB 순으로 균형 탐색"
                read -p "Metal Cache Limit  [$USER_METAL_CACHE_LIMIT]: " input
                set_if_valid_size "$input" USER_METAL_CACHE_LIMIT "Metal Cache Limit"
                ;;
            15)
                echo "Prompt Cache Bytes Guide:"
                echo "  - 정의: KV/Prompt 캐시 총량 바이트 상한"
                echo "  - 상향: 캐시 히트율/반복 응답 속도 개선 가능"
                echo "  - 하향: 피크 메모리 급증 방지"
                echo "  - 팁: 12GB~24GB 범위에서 단위 포함 입력"
                read -p "Prompt Cache Bytes (e.g. 24GB) [$USER_PROMPT_CACHE_BYTES]: " input
                set_if_valid_size "$input" USER_PROMPT_CACHE_BYTES "Prompt Cache Bytes"
                ;;
            16)
                toggle_advanced_cache
                echo "Advanced Cache: $USER_ADVANCED_CACHE"
                echo "  - 정의: 콘텐츠 기반 고급 캐시 엔진 사용 여부"
                echo "  - ON: 반복/유사 요청에서 캐시 히트율 상승 가능 -> 평균 TPS 개선 가능"
                echo "  - OFF: 동작 단순화, 디버깅/재현성은 좋아질 수 있으나 재사용 이점 감소"
                echo "  - 팁: 동일 프롬프트 재요청이 많은 워크로드면 ON 권장"
                sleep 1
                ;;
            17) 
                echo "Page Size Guide:"
                echo "  - 정의: 캐시 블록 인덱싱 토큰 단위"
                echo "  - 작게(예: 64): 재사용 정밀도 상승"
                echo "  - 크게(예: 256): 관리 오버헤드 감소"
                echo "  - 팁: 기본 128, 반복/유사 요청 많으면 256도 테스트"
                read -p "Page Size (Tokens) [$USER_PAGE_SIZE]: " input
                set_if_valid_int_range "$input" 16 4096 USER_PAGE_SIZE "Paged Cache Size"
                ;;
            18)
                echo "KV Cache Bits Guide:"
                echo "  - 정의: KV 캐시 양자화 정밀도(4/8bit)"
                echo "  - 4bit: 메모리 절감 폭 최대 -> OOM 완화/동시성 확대에 유리"
                echo "  - 8bit: 품질 손실 완화, 메모리 절감은 4bit보다 작음"
                echo "  - Off(FP): 품질 우선, 메모리 사용량 증가"
                echo "  - 토큰 생성 영향: 메모리 압박이 줄면 스로틀/중단 감소로 실효 TPS 개선 가능"
                edit_kv_bits
                ;;
            19) 
                echo "KV Group Size Guide:"
                echo "  - 정의: KV 양자화 그룹 크기"
                echo "  - 작게(예: 32): 품질/정밀도 유리"
                echo "  - 크게(예: 64~128): 압축 효율 유리"
                echo "  - 팁: kv-bits=8이면 32/64를 우선 비교"
                read -p "KV Group Size [$USER_KV_GROUP_SIZE]: " input
                set_if_valid_int_range "$input" 1 1024 USER_KV_GROUP_SIZE "KV Group Size"
                ;;
            20)
                echo "Cache Grace Seconds Guide:"
                echo "  - 정의: 신규 cold 블록 최소 보존 시간(초)"
                echo "  - 상향: 재사용 기회 증가, 메모리 체류 증가"
                echo "  - 하향: 빠른 회수, 재계산 증가 가능"
                echo "  - 팁: 10~30초 범위에서 시작"
                read -p "Cache Grace Seconds [$USER_CACHE_GRACE_SECONDS]: " input
                set_if_valid_float_range "$input" 0 600 USER_CACHE_GRACE_SECONDS "Cache Grace Seconds"
                ;;
            21)
                toggle_prompt_normalization
                echo "Prompt Normalize: $USER_PROMPT_NORMALIZATION"
                echo "  - 정의: 입력 공백/개행 정규화"
                echo "  - ON: 캐시 키 일관성 상승, 히트율 개선 가능"
                echo "  - OFF: 원문 보존"
                echo "  - 토큰 생성 영향: 히트율 상승 시 prefill 비용이 줄어 TTFT/평균 응답시간 개선 가능"
                sleep 1
                ;;
            22)
                toggle_cache_observability
                echo "Cache Observability: $USER_CACHE_OBSERVABILITY"
                echo "  - 정의: 캐시 진단/통계 로그 수준"
                echo "  - ON: 병목/축출 원인 파악에 유리"
                echo "  - OFF: 로그 오버헤드 최소화"
                echo "  - 토큰 생성 영향: ON은 미세한 로깅 오버헤드가 있을 수 있어 극한 TPS 벤치에서 불리할 수 있음"
                sleep 1
                ;;
            23)
                echo "Cache Headroom Ratio Guide:"
                echo "  - 정의: 메모리 압박 시 목표 여유 비율"
                echo "  - 낮게(예: 0.75): 안정성↑, 캐시 보존량↓"
                echo "  - 높게(예: 0.85): 히트율↑ 가능, 압박 리스크↑"
                echo "  - 권장 범위: 0.70 ~ 0.90"
                read -p "Cache Headroom Ratio [$USER_CACHE_HEADROOM_RATIO]: " input
                set_if_valid_float_range "$input" 0.50 0.95 USER_CACHE_HEADROOM_RATIO "Cache Headroom Ratio"
                ;;
            24)
                run_light_benchmark_50k
                ;;
            25)
                run_stream_decode_benchmark_50k
                ;;
            26)
                run_repeat_benchmark_5x
                ;;
            27)
                toggle_speculative_decoding
                echo "Speculative Decoding: $USER_SPECULATIVE_DECODING"
                echo "  - 정의: Draft(소형) 모델이 토큰 후보를 빠르게 생성하고 Target(대형) 모델이 검증"
                echo "  - ON 효과: 생성 속도 향상 가능 (코딩 등 예측 가능한 패턴에서 특히 효과적)"
                echo "  - OFF 효과: 표준 디코딩, continuous batching 가능"
                echo "  - ⚠ ON 시 continuous batching(동시 요청 배칭)은 자동 비활성화됩니다"
                if [[ "$USER_SPECULATIVE_DECODING" == "true" && -z "$USER_DRAFT_MODEL" ]]; then
                    echo "  ⚠ Draft Model Path가 설정되지 않았습니다. 28번에서 설정하세요."
                fi
                sleep 1
                ;;
            28)
                echo "Draft Model Path Guide:"
                echo "  - 정의: Speculative Decoding에 사용할 소형 Draft 모델 경로"
                echo "  - 로컬 경로 예: ~/Desktop/models/Qwen3-1.7B-4bit"
                echo "  - HF Repo ID 예: mlx-community/Qwen3-1.7B-4bit"
                echo "  - 주의: Target 모델과 동일한 토크나이저(vocab_size)를 공유해야 합니다"
                echo "  - 권장: Target 크기의 1/10~1/30 크기 (예: 30B Target → 1~3B Draft)"
                read -p "Draft Model Path [${USER_DRAFT_MODEL:-None}]: " input
                if [[ -n "$input" ]]; then
                    USER_DRAFT_MODEL="$input"
                fi
                ;;
            29)
                echo "Num Draft Tokens Guide:"
                echo "  - 정의: Draft 모델이 한 번에 생성할 후보 토큰 수"
                echo "  - 상향(16~20): 코딩/보일러플레이트 등 예측 가능한 패턴에서 효과적"
                echo "  - 하향(3~5): 짧은 응답이나 큰 Draft 모델(>7B)일 때 적합"
                echo "  - 권장 범위: 코딩 16~20, 추론 8~12, 짧은 응답 3~5"
                read -p "Num Draft Tokens [${USER_NUM_DRAFT_TOKENS:-3}]: " input
                set_if_valid_int_range "$input" 1 64 USER_NUM_DRAFT_TOKENS "Num Draft Tokens"
                ;;
            30)
                echo "Chat Template Args Guide:"
                echo "  - 정의: 토크나이저 apply_chat_template에 전달할 JSON 인자"
                echo "  - 예: {\"enable_thinking\":true}  → 모델 reasoning/thinking 모드 활성화"
                echo "  - 예: {\"enable_thinking\":false} → thinking 비활성화 (빠른 응답)"
                echo "  - 빈 값: 기본 템플릿 동작 유지"
                echo "  - 현재: ${USER_CHAT_TEMPLATE_ARGS:-'{}'}"
                read -p "Chat Template Args (JSON): " input
                if [[ -n "$input" ]]; then
                    if python3 -c "import json; json.loads('$input')" 2>/dev/null; then
                        USER_CHAT_TEMPLATE_ARGS="$input"
                    else
                        echo "❌ 유효한 JSON 형식이 아닙니다. 예: {\"enable_thinking\":true}"
                        sleep 1
                    fi
                fi
                ;;
            31)
                echo "Tool Choice Default Guide:"
                echo "  - 정의: 클라이언트가 tool_choice를 지정하지 않았을 때 서버가 주입할 기본값"
                echo "  - auto: 모델이 tool 호출 여부를 자율 판단 (OpenAI 기본값)"
                echo "  - none: tool 호출을 하지 않고 텍스트만 생성"
                echo "  - required: 반드시 tool을 호출 (tool이 없으면 에러)"
                echo "  - 주의: 요청에 tools 배열이 있을 때만 적용됩니다"
                echo "  현재: $USER_TOOL_CHOICE_DEFAULT"
                echo ""
                echo "  1. auto     (모델 자율 판단 — 권장)"
                echo "  2. none     (tool 호출 비활성화)"
                echo "  3. required (tool 호출 강제)"
                read -p "Select [1-3]: " input
                case "$input" in
                    1) USER_TOOL_CHOICE_DEFAULT="auto" ;;
                    2) USER_TOOL_CHOICE_DEFAULT="none" ;;
                    3) USER_TOOL_CHOICE_DEFAULT="required" ;;
                esac
                ;;
            32)
                echo "MCP Config Path Guide:"
                echo "  - 정의: MCP(Model Context Protocol) 설정 JSON 파일 경로"
                echo "  - 용도: 서버가 GET /v1/mlx/mcp-config 엔드포인트로 설정을 노출"
                echo "  - 클라이언트(Cursor, Continue 등)가 이 엔드포인트를 조회하여 tool 서버 목록을 가져감"
                echo "  - 예: ~/.mcp.json, ~/projects/.mcp.json"
                echo "  - 빈 값: MCP config 엔드포인트 비활성"
                read -p "MCP Config Path [${USER_MCP_CONFIG_PATH:-None}]: " input
                if [[ -n "$input" ]]; then
                    local expanded="${input/#\~/$HOME}"
                    if [[ -f "$expanded" ]]; then
                        USER_MCP_CONFIG_PATH="$input"
                        echo "✅ MCP Config 설정 완료: $input"
                    else
                        echo "⚠ 파일이 존재하지 않습니다: $expanded"
                        read -p "그래도 설정하시겠습니까? [y/N]: " confirm
                        if [[ "$confirm" =~ ^[Yy]$ ]]; then
                            USER_MCP_CONFIG_PATH="$input"
                        fi
                    fi
                fi
                ;;
            [Bb]) save_config; return ;;
            *) echo "Invalid selection."; sleep 1 ;;
        esac
    done
}

toggle_speculative_decoding() {
    if [[ "$USER_SPECULATIVE_DECODING" == "true" ]]; then
        USER_SPECULATIVE_DECODING="false"
    else
        USER_SPECULATIVE_DECODING="true"
    fi
}

toggle_prompt_normalization() {
    if [[ "$USER_PROMPT_NORMALIZATION" == "true" ]]; then
        USER_PROMPT_NORMALIZATION="false"
    else
        USER_PROMPT_NORMALIZATION="true"
    fi
}

toggle_cache_observability() {
    if [[ "$USER_CACHE_OBSERVABILITY" == "true" ]]; then
        USER_CACHE_OBSERVABILITY="false"
    else
        USER_CACHE_OBSERVABILITY="true"
    fi
}

toggle_advanced_cache() {
    if [[ "$USER_ADVANCED_CACHE" == "true" ]]; then
        USER_ADVANCED_CACHE="false"
    else
        USER_ADVANCED_CACHE="true"
    fi
}

edit_kv_bits() {
    echo ""
    echo "KV Cache Quantization:"
    echo "  1. 4-bit  (75% VRAM saved, recommended for 100B+ models)"
    echo "  2. 8-bit  (50% VRAM saved, higher precision)"
    echo "  3. Off    (FP16, full precision)"
    echo ""
    echo "Current: ${USER_KV_BITS:-Off}"
    read -p "Select [1-3]: " input
    case "$input" in
        1) USER_KV_BITS="4" ;;
        2) USER_KV_BITS="8" ;;
        3) USER_KV_BITS="" ;;
    esac
}

edit_log_level() {
    local levels=("DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL")
    echo ""
    echo "Available Log Levels:"
    for i in "${!levels[@]}"; do
        printf "  %d. %s\n" "$((i+1))" "${levels[$i]}"
    done
    read -p "Select level [Current: $USER_LOG]: " input
    if [[ "$input" =~ ^[1-5]$ ]]; then
        USER_LOG="${levels[$((input-1))]}"
    fi
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
    echo "   Run Model 메뉴에서 '$target_dir' 또는 '${target_dir##*/}'를 선택하세요."
    sleep 2
}

# --- Main Logic ---
main() {
    # Check for CLI arguments first (non-interactive mode)
    if [[ $# -gt 0 ]]; then
        if [[ "$1" == "--" || "$1" == -* ]]; then
            uv run mlx-server serve "$@"
        else
            uv run mlx-server "$@"
        fi
        exit $?
    fi

    load_config

    while true; do
        show_header
        echo "1. Run Model"
        echo "2. Options"
        echo "3. Models Folder"
        echo "4. Download from Hugging Face"
        echo "5. Quit"
        echo "----------------------------------------"
        read -p "Selection [1-5]: " choice

        case "$choice" in
            1) menu_run_model ;;
            2) menu_options ;;
            3) menu_models_root ;;
            4) menu_download_hf ;;
            5) echo "Goodbye!"; exit 0 ;;
            *) echo "Invalid selection."; sleep 1 ;;
        esac
    done
}

main "$@"
