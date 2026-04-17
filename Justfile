set shell := ["bash", "-cu"]

default:
    @just --list

lint:
    uv run ruff check src tests

typecheck:
    uv run ty check src

test *ARGS:
    uv run pytest {{ARGS}}

audit-stack:
    bash scripts/audit_stack.sh

ci:
    just audit-stack
    just lint
    just typecheck
    just test
