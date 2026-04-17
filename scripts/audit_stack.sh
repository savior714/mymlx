#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

failed=0

pass() {
  echo "[PASS] $1"
}

fail() {
  echo "[FAIL] $1"
  failed=1
}

check_absent_file() {
  local pattern="$1"
  local label="$2"
  if rg --files -g "$pattern" | rg . >/dev/null 2>&1; then
    fail "$label detected: $pattern"
  else
    pass "$label not detected"
  fi
}

check_absent_pattern() {
  local pattern="$1"
  local label="$2"
  shift 2
  local exclude_args=("$@")

  if rg -n "${exclude_args[@]}" "$pattern" . >/dev/null 2>&1; then
    fail "$label detected by pattern: $pattern"
  else
    pass "$label not detected"
  fi
}

check_absent_pattern_glob() {
  local pattern="$1"
  local label="$2"
  local include_glob="$3"
  shift 3
  local exclude_args=("$@")

  if rg -n "${exclude_args[@]}" --glob "$include_glob" "$pattern" . >/dev/null 2>&1; then
    fail "$label detected by pattern: $pattern"
  else
    pass "$label not detected"
  fi
}

echo "== Stack denylist audit =="

# Denylist files
check_absent_file "Makefile" "Make task runner"
check_absent_file "Dockerfile" "Dockerfile"
check_absent_file "Dockerfile.*" "Dockerfile variants"
check_absent_file "docker-compose.yml" "docker compose"
check_absent_file "docker-compose.yaml" "docker compose"
check_absent_file "docker-compose*.yml" "docker compose variants"
check_absent_file "docker-compose*.yaml" "docker compose variants"
check_absent_file "package-lock.json" "npm lockfile"
check_absent_file "yarn.lock" "yarn lockfile"
check_absent_file "pnpm-lock.yaml" "pnpm lockfile"
check_absent_file "vite.config.*" "vite config"

# Denylist content signals
COMMON_EXCLUDES=(
  --glob '!.git/**'
  --glob '!.venv/**'
  --glob '!node_modules/**'
  --glob '!.cursor/**'
  --glob '!docs/**'
  --glob '!scripts/audit_stack.sh'
  --glob '!docs/specs/stack_upgrade_enforcement_guide.md'
)

check_absent_pattern_glob '^#!/bin/zsh' "zsh shebang in scripts" '*.sh' "${COMMON_EXCLUDES[@]}"
check_absent_pattern 'postgres://' "postgres DSN in source" "${COMMON_EXCLUDES[@]}"

if [[ "$failed" -ne 0 ]]; then
  echo "Stack audit failed."
  exit 1
fi

echo "Stack audit passed."
