#!/usr/bin/env bash
# Unified verification: pytest + machine-readable summary for agents.
# Writes verify-last-result.json; on failure, verify-pytest-failures.txt (pytest output).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

JSON_OUT="${ROOT}/verify-last-result.json"
FAIL_OUT="${ROOT}/verify-pytest-failures.txt"
TMP_LOG="$(mktemp)"
trap 'rm -f "$TMP_LOG"' EXIT

rm -f "$JSON_OUT" "$FAIL_OUT"

START_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
START_MS="$(uv run python -c "import time; print(int(time.time() * 1000))")"

set +e
uv run pytest "$@" 2>&1 | tee "$TMP_LOG"
PYEXIT="${PIPESTATUS[0]}"
END_MS="$(uv run python -c "import time; print(int(time.time() * 1000))")"
set -e

ELAPSED_MS=$((END_MS - START_MS))

if [[ "$PYEXIT" -ne 0 ]]; then
  cp "$TMP_LOG" "$FAIL_OUT"
fi

export V_EXIT="$PYEXIT"
export V_ELAPSED_MS="$ELAPSED_MS"
export V_TS="$START_UTC"
export V_JSON_OUT="$JSON_OUT"

uv run python <<'PY'
import json
import os
from pathlib import Path

exit_code = int(os.environ["V_EXIT"])
elapsed_ms = int(os.environ["V_ELAPSED_MS"])
failed_stage = "pytest" if exit_code != 0 else None
hint = (
    "All verification stages passed."
    if exit_code == 0
    else "pytest failed; read verify-pytest-failures.txt for details."
)
doc = {
    "schema": "mlx_server.verify.v1",
    "exitCode": exit_code,
    "failedStage": failed_stage,
    "stages": [{"name": "pytest", "exitCode": exit_code, "elapsedMs": elapsed_ms}],
    "agentHint": hint,
    "timestampUtc": os.environ["V_TS"],
}
Path(os.environ["V_JSON_OUT"]).write_text(
    json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY

exit "$PYEXIT"
