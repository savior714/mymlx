#!/usr/bin/env python3
"""Verify docs markdown files are clean UTF-8 text."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate UTF-8/BOM/replacement-character issues in markdown files."
    )
    parser.add_argument("--dir", default="docs", help="Directory to scan recursively")
    return parser.parse_args()


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    data = path.read_bytes()

    if data.startswith(b"\xef\xbb\xbf"):
        errors.append("UTF-8 BOM detected")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"Invalid UTF-8 sequence ({exc})")
        return errors

    if "\ufffd" in text:
        errors.append("Replacement character (�) detected")

    if "\x00" in text:
        errors.append("NUL byte detected")

    return errors


def main() -> int:
    args = parse_args()
    root = Path(args.dir)

    if not root.exists() or not root.is_dir():
        print(f"[verify_korean_text] Directory not found: {root}")
        return 2

    md_files = sorted(root.rglob("*.md"))
    if not md_files:
        print(f"[verify_korean_text] No markdown files found under: {root}")
        return 0

    failures: list[tuple[Path, list[str]]] = []
    for path in md_files:
        errors = check_file(path)
        if errors:
            failures.append((path, errors))

    if failures:
        print("[verify_korean_text] FAILED")
        for path, errors in failures:
            print(f"- {path}")
            for msg in errors:
                print(f"  - {msg}")
        return 1

    print(f"[verify_korean_text] OK ({len(md_files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
