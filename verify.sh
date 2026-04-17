#!/usr/bin/env bash
# Unified verification: ruff + ty + pytest + docs-encoding + machine-readable summary for agents.
# Writes verify-last-result.json; on failure, verify-*-failures.txt for the failed stage.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

JSON_OUT="${ROOT}/verify-last-result.json"
RUFF_FAIL_OUT="${ROOT}/verify-ruff-failures.txt"
TY_FAIL_OUT="${ROOT}/verify-ty-failures.txt"
PY_FAIL_OUT="${ROOT}/verify-pytest-failures.txt"
DOC_FAIL_OUT="${ROOT}/verify-docs-failures.txt"
TMP_RUFF="$(mktemp)"
TMP_TY="$(mktemp)"
TMP_PY="$(mktemp)"
TMP_DOC="$(mktemp)"
trap 'rm -f "$TMP_RUFF" "$TMP_TY" "$TMP_PY" "$TMP_DOC"' EXIT

rm -f "$JSON_OUT" "$RUFF_FAIL_OUT" "$TY_FAIL_OUT" "$PY_FAIL_OUT" "$DOC_FAIL_OUT"

START_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
_ms() { uv run python -c "import time; print(int(time.time() * 1000))"; }

# --- ruff (required) ---
RUFF_START="$(_ms)"
set +e
uv run ruff check src tests 2>&1 | tee "$TMP_RUFF"
RUFF_EXIT=${PIPESTATUS[0]}
set -e
RUFF_END="$(_ms)"
RUFF_MS=$((RUFF_END - RUFF_START))
if [[ "$RUFF_EXIT" -ne 0 ]]; then
  cp "$TMP_RUFF" "$RUFF_FAIL_OUT"
fi

TY_EXIT=0
TY_MS=0
SKIP_TY=0
SKIP_PY=0

if [[ "$RUFF_EXIT" -eq 0 ]]; then
  # --- ty (optional severity: project may emit warnings only; non-zero = failure) ---
  TY_START="$(_ms)"
  set +e
  uv run ty check src 2>&1 | tee "$TMP_TY"
  TY_EXIT=${PIPESTATUS[0]}
  set -e
  TY_END="$(_ms)"
  TY_MS=$((TY_END - TY_START))
  if [[ "$TY_EXIT" -ne 0 ]]; then
    cp "$TMP_TY" "$TY_FAIL_OUT"
    SKIP_PY=1
  fi
else
  SKIP_TY=1
  SKIP_PY=1
fi

PYEXIT=0
PY_MS=0
DOC_EXIT=0
DOC_MS=0
SKIP_DOC=0
if [[ "$RUFF_EXIT" -eq 0 && "$TY_EXIT" -eq 0 ]]; then
  PY_START="$(_ms)"
  set +e
  uv run pytest "$@" 2>&1 | tee "$TMP_PY"
  PYEXIT="${PIPESTATUS[0]}"
  set -e
  PY_END="$(_ms)"
  PY_MS=$((PY_END - PY_START))
  if [[ "$PYEXIT" -ne 0 ]]; then
    cp "$TMP_PY" "$PY_FAIL_OUT"
  fi
else
  SKIP_PY=1
  SKIP_DOC=1
fi

if [[ "$RUFF_EXIT" -eq 0 && "$TY_EXIT" -eq 0 && "$PYEXIT" -eq 0 ]]; then
  DOC_START="$(_ms)"
  set +e
  uv run python scripts/verify_korean_text.py --dir docs 2>&1 | tee "$TMP_DOC"
  DOC_EXIT="${PIPESTATUS[0]}"
  set -e
  DOC_END="$(_ms)"
  DOC_MS=$((DOC_END - DOC_START))
  if [[ "$DOC_EXIT" -ne 0 ]]; then
    cp "$TMP_DOC" "$DOC_FAIL_OUT"
  fi
else
  SKIP_DOC=1
fi

OVERALL=0
if [[ "$RUFF_EXIT" -ne 0 ]]; then OVERALL=$RUFF_EXIT
elif [[ "$TY_EXIT" -ne 0 ]]; then OVERALL=$TY_EXIT
elif [[ "$PYEXIT" -ne 0 ]]; then OVERALL=$PYEXIT
elif [[ "$DOC_EXIT" -ne 0 ]]; then OVERALL=$DOC_EXIT
fi

export V_SCHEMA="mlx_server.verify.v2"
export V_EXIT="$OVERALL"
export V_TS="$START_UTC"
export V_JSON_OUT="$JSON_OUT"
export V_RUFF_EXIT="$RUFF_EXIT"
export V_RUFF_MS="$RUFF_MS"
export V_TY_EXIT="$TY_EXIT"
export V_TY_MS="$TY_MS"
export V_SKIP_TY="$SKIP_TY"
export V_PYEXIT="$PYEXIT"
export V_PY_MS="$PY_MS"
export V_SKIP_PY="$SKIP_PY"
export V_DOC_EXIT="$DOC_EXIT"
export V_DOC_MS="$DOC_MS"
export V_SKIP_DOC="$SKIP_DOC"

uv run python <<'PY'
import json
import os
from pathlib import Path

def hint() -> str:
    if int(os.environ["V_EXIT"]) == 0:
        return "All verification stages passed."
    if int(os.environ["V_RUFF_EXIT"]) != 0:
        return "ruff failed; read verify-ruff-failures.txt for details."
    if int(os.environ["V_TY_EXIT"]) != 0:
        return "ty failed; read verify-ty-failures.txt for details."
    if int(os.environ["V_PYEXIT"]) != 0:
        return "pytest failed; read verify-pytest-failures.txt for details."
    return "docs verification failed; read verify-docs-failures.txt for details."


def failed_stage():
    if int(os.environ["V_EXIT"]) == 0:
        return None
    if int(os.environ["V_RUFF_EXIT"]) != 0:
        return "ruff"
    if int(os.environ["V_TY_EXIT"]) != 0:
        return "ty"
    if int(os.environ["V_PYEXIT"]) != 0:
        return "pytest"
    return "docs"


stages = [
    {
        "name": "ruff",
        "exitCode": int(os.environ["V_RUFF_EXIT"]),
        "elapsedMs": int(os.environ["V_RUFF_MS"]),
    },
]
if int(os.environ["V_SKIP_TY"]):
    stages.append({"name": "ty", "exitCode": None, "elapsedMs": 0, "skipped": True})
else:
    stages.append(
        {
            "name": "ty",
            "exitCode": int(os.environ["V_TY_EXIT"]),
            "elapsedMs": int(os.environ["V_TY_MS"]),
        }
    )
if int(os.environ["V_SKIP_PY"]):
    stages.append({"name": "pytest", "exitCode": None, "elapsedMs": 0, "skipped": True})
else:
    stages.append(
        {
            "name": "pytest",
            "exitCode": int(os.environ["V_PYEXIT"]),
            "elapsedMs": int(os.environ["V_PY_MS"]),
        }
    )
if int(os.environ["V_SKIP_DOC"]):
    stages.append({"name": "docs", "exitCode": None, "elapsedMs": 0, "skipped": True})
else:
    stages.append(
        {
            "name": "docs",
            "exitCode": int(os.environ["V_DOC_EXIT"]),
            "elapsedMs": int(os.environ["V_DOC_MS"]),
        }
    )

doc = {
    "schema": os.environ["V_SCHEMA"],
    "exitCode": int(os.environ["V_EXIT"]),
    "failedStage": failed_stage(),
    "stages": stages,
    "agentHint": hint(),
    "timestampUtc": os.environ["V_TS"],
}
Path(os.environ["V_JSON_OUT"]).write_text(
    json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY

exit "$OVERALL"
