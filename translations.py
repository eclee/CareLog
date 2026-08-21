"""CareLog internationalization helpers.

Every language is a self-contained JSON file in ``locales/``. The ``_meta``
object describes how the language appears in selectors; every other key is a
translated UI string. Adding another language therefore does not require a
Python, route, or template change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCALE_DIR = Path(__file__).resolve().parent / "locales"
DEFAULT_LANGUAGE = "zh"


def _load_locales() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    translations: dict[str, dict[str, str]] = {}
    metadata: dict[str, dict[str, Any]] = {}

    for path in sorted(LOCALE_DIR.glob("*.json")):
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid locale file: {path}")

        raw_meta = payload.pop("_meta", None)
        if not isinstance(raw_meta, dict):
            raise ValueError(f"Locale metadata is missing: {path}")

        code = str(raw_meta.get("code") or path.stem).strip()
        if code != path.stem:
            raise ValueError(f"Locale code must match filename: {path}")
        required_meta = ("name", "native_name", "short", "html_lang")
        if any(not isinstance(raw_meta.get(key), str) for key in required_meta):
            raise ValueError(f"Locale metadata is incomplete: {path}")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
            raise ValueError(f"Locale translations must be strings: {path}")

        metadata[code] = {
            "code": code,
            "name": raw_meta["name"],
            "native_name": raw_meta["native_name"],
            "short": raw_meta["short"],
            "html_lang": raw_meta["html_lang"],
            "order": int(raw_meta.get("order", 999)),
        }
        translations[code] = payload

    if DEFAULT_LANGUAGE not in translations:
        raise ValueError(f"Default locale {DEFAULT_LANGUAGE!r} is missing")

    reference = set(translations[DEFAULT_LANGUAGE])
    for code, payload in translations.items():
        missing = reference - set(payload)
        extra = set(payload) - reference
        if missing or extra:
            raise ValueError(
                f"Translation keys differ for {code}: "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )

    ordered_codes = sorted(metadata, key=lambda code: (metadata[code]["order"], code))
    ordered_metadata = {code: metadata[code] for code in ordered_codes}
    ordered_translations = {code: translations[code] for code in ordered_codes}
    return ordered_metadata, ordered_translations


LANGUAGES, T = _load_locales()


def normalize_lang(code: str | None) -> str:
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def tr(lang: str | None, key: str) -> str:
    code = normalize_lang(lang)
    return T[code].get(key, T[DEFAULT_LANGUAGE].get(key, key))


def tr_format(lang: str | None, key: str, **values: object) -> str:
    try:
        return tr(lang, key).format(**values)
    except (KeyError, ValueError):
        return tr(lang, key)
