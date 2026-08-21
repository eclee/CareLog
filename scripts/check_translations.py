#!/usr/bin/env python3
"""Validate locale metadata and translation-key parity."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from translations import DEFAULT_LANGUAGE, LANGUAGES, T

reference = set(T[DEFAULT_LANGUAGE])
failed = False
for code, meta in LANGUAGES.items():
    keys = set(T[code])
    missing = reference - keys
    extra = keys - reference
    if missing or extra:
        failed = True
    status = "OK" if not missing and not extra else f"missing={sorted(missing)} extra={sorted(extra)}"
    print(f"{code:>3}  {meta['native_name']:<20} {len(keys):>3} keys  {status}")

raise SystemExit(1 if failed else 0)
