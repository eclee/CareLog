#!/usr/bin/env python3
"""Offline repository checks used locally and by GitHub Actions.

The checks intentionally avoid starting Flask or touching a database. They
validate Python/Jinja syntax, literal route links, POST-form CSRF fields,
translations, GitHub YAML, local Markdown links, release files, and the key
features introduced in CareLog 1.2.0.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
LOCALES = ROOT / "locales"


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def check_python(errors: list[str]) -> None:
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", ".venv", "venv"} for part in path.parts):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            fail(f"Python syntax error in {path.relative_to(ROOT)}: {exc}", errors)


def _blueprint_name(tree: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "bp" for target in node.targets):
            continue
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "Blueprint"
            and call.args
            and isinstance(call.args[0], ast.Constant)
        ):
            return str(call.args[0].value)
    return None


def _known_endpoints(errors: list[str]) -> set[str]:
    endpoints = {"root", "static"}
    for path in sorted((ROOT / "routes").glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        blueprint = _blueprint_name(tree)
        if not blueprint:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "bp"
                    and decorator.func.attr == "route"
                ):
                    endpoints.add(f"{blueprint}.{node.name}")
                    break
    if len(endpoints) <= 2:
        fail("No Blueprint endpoints were discovered", errors)
    return endpoints


def check_templates(errors: list[str]) -> None:
    env = Environment()
    endpoints = _known_endpoints(errors)
    post_form = re.compile(
        r"<form\b(?=[^>]*\bmethod\s*=\s*['\"]post['\"])[^>]*>(.*?)</form>",
        re.IGNORECASE | re.DOTALL,
    )
    url_for = re.compile(r"url_for\(\s*['\"]([^'\"]+)['\"]")
    used_endpoints: set[str] = set()

    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        try:
            env.parse(text)
        except Exception as exc:  # Jinja exposes several syntax exception classes.
            fail(f"Jinja syntax error in {path.relative_to(ROOT)}: {exc}", errors)
        for index, match in enumerate(post_form.finditer(text), start=1):
            if "_csrf_token" not in match.group(1):
                fail(
                    f"POST form #{index} in {path.relative_to(ROOT)} has no CSRF field",
                    errors,
                )
        used_endpoints.update(url_for.findall(text))

    unknown = sorted(used_endpoints - endpoints)
    if unknown:
        fail(f"Unknown literal template endpoint(s): {unknown}", errors)


def load_translation_payloads(errors: list[str]) -> dict[str, dict[str, object]]:
    payloads: dict[str, dict[str, object]] = {}
    for path in sorted(LOCALES.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"Cannot read {path.relative_to(ROOT)}: {exc}", errors)
            continue
        if not isinstance(payload, dict):
            fail(f"Locale root must be an object: {path.relative_to(ROOT)}", errors)
            continue
        payloads[path.stem] = payload
    return payloads


def check_translations(errors: list[str]) -> set[str]:
    payloads = load_translation_payloads(errors)
    expected_languages = {"zh", "id", "vi", "fil", "th"}
    missing_languages = expected_languages - set(payloads)
    if missing_languages:
        fail(f"Required locale(s) missing: {sorted(missing_languages)}", errors)
    if "zh" not in payloads:
        return set()

    reference = set(payloads["zh"]) - {"_meta"}
    placeholder = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
    for code, payload in payloads.items():
        meta = payload.get("_meta")
        if not isinstance(meta, dict):
            fail(f"Missing _meta in locales/{code}.json", errors)
        else:
            for key in ("code", "name", "native_name", "short", "html_lang", "order"):
                if key not in meta:
                    fail(f"Missing locale metadata {key!r} for {code}", errors)
            if meta.get("code") != code:
                fail(f"Locale code does not match filename for {code}", errors)

        keys = set(payload) - {"_meta"}
        if keys != reference:
            fail(
                f"Translation keys differ for {code}: "
                f"missing={sorted(reference - keys)}, extra={sorted(keys - reference)}",
                errors,
            )
            continue
        for key in reference:
            value = payload.get(key)
            reference_value = payloads["zh"].get(key)
            if not isinstance(value, str) or not isinstance(reference_value, str):
                fail(f"Translation {code}.{key} must be a string", errors)
                continue
            if set(placeholder.findall(value)) != set(placeholder.findall(reference_value)):
                fail(f"Placeholder mismatch in {code}.{key}", errors)
    return reference


def check_translation_references(keys: set[str], errors: list[str]) -> None:
    # Dynamic families such as t('intake_' ~ key) are accepted when at least
    # one concrete key with that prefix exists in the locale files.
    literal = re.compile(r"\b(?:t|tr)\(\s*['\"]([^'\"]+)['\"]")
    for base in (ROOT / "templates", ROOT / "routes", ROOT / "services"):
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".html", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            for key in literal.findall(text):
                if key.endswith("_") and any(item.startswith(key) for item in keys):
                    continue
                if key not in keys:
                    fail(f"Unknown translation key {key!r} in {path.relative_to(ROOT)}", errors)


def check_yaml(errors: list[str]) -> None:
    paths = [ROOT / "docker-compose.yml"]
    github = ROOT / ".github"
    paths.extend(sorted(github.rglob("*.yml")))
    paths.extend(sorted(github.rglob("*.yaml")))
    for path in paths:
        if not path.exists():
            continue
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"YAML syntax error in {path.relative_to(ROOT)}: {exc}", errors)
            continue
        if payload is None:
            fail(f"Empty YAML file: {path.relative_to(ROOT)}", errors)

    for path in sorted((github / "ISSUE_TEMPLATE").glob("*.yml")):
        if path.name == "config.yml":
            continue
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        required = {"name", "description", "body"}
        missing = required - set(payload)
        if missing:
            fail(f"Issue form {path.relative_to(ROOT)} is missing {sorted(missing)}", errors)
        if "about" in payload:
            fail(f"Issue form {path.relative_to(ROOT)} uses 'about'; use 'description'", errors)


def check_markdown_links(errors: list[str]) -> None:
    link_pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not (path.parent / target).resolve().exists():
                fail(f"Broken local link in {path.relative_to(ROOT)}: {raw_target}", errors)


def check_feature_invariants(errors: list[str]) -> None:
    files = {
        "admin": (ROOT / "routes/admin.py").read_text(encoding="utf-8"),
        "front": (ROOT / "routes/front.py").read_text(encoding="utf-8"),
        "family": (ROOT / "routes/family.py").read_text(encoding="utf-8"),
        "media_route": (ROOT / "routes/media.py").read_text(encoding="utf-8"),
        "media_service": (ROOT / "services/media.py").read_text(encoding="utf-8"),
        "abnormal": (ROOT / "services/abnormal.py").read_text(encoding="utf-8"),
        "schema": (ROOT / "services/schema.py").read_text(encoding="utf-8"),
        "reports": (ROOT / "services/reports.py").read_text(encoding="utf-8"),
        "models": (ROOT / "models.py").read_text(encoding="utf-8"),
        "nav": (ROOT / "templates/_main_nav.html").read_text(encoding="utf-8"),
        "base": (ROOT / "templates/base.html").read_text(encoding="utf-8"),
        "base_front": (ROOT / "templates/base_front.html").read_text(encoding="utf-8"),
        "users_template": (ROOT / "templates/admin/users.html").read_text(encoding="utf-8"),
        "css": (ROOT / "static/style.css").read_text(encoding="utf-8"),
        "translations": (ROOT / "translations.py").read_text(encoding="utf-8"),
    }
    required = {
        "soft account deletion route": (
            '@bp.route("/users/<int:uid>/delete", methods=["POST"])'
            in files["admin"]
            and "target.deleted_at = datetime.now()" in files["admin"]
            and "db.session.delete(target)" not in files["admin"]
        ),
        "self-deletion safeguard": "target.id == me.id" in files["admin"],
        "caregiver dashboard access": (
            '@login_required("family", "admin", "worker")' in files["family"]
        ),
        "configurable care parameters": (
            "DEFAULT_CARE_PARAMETERS" in files["models"]
            and "water_quick_amounts_ml" in files["models"]
            and '@bp.route("/parameters", methods=["GET", "POST"])'
            in files["admin"]
        ),
        "configurable elder birthday default": (
            '"default_elder_birthday": "1940-01-01"' in files["models"]
            and "default_elder_birthday" in files["admin"]
        ),
        "medication reference images": (
            'kind="med_reference"' in files["admin"]
            and "plan_photos" in files["front"]
        ),
        "structured media paths": (
            'PurePosixPath("elders")' in files["media_service"]
            and '"care-records"' in files["media_service"]
            and '"medication-plans"' in files["media_service"]
            and "thumbnail_filename" in files["models"]
            and "checksum" in files["models"]
        ),
        "id-based protected media": (
            '@bp.route("/photos/<int:photo_id>")' in files["media_route"]
            and '"private, no-store"' in files["media_route"]
        ),
        "filterable paginated audit": (
            '@bp.route("/audit")' in files["admin"]
            and "request_date_range()" in files["admin"]
            and "query.paginate" in files["admin"]
            and "actor_role" in files["models"]
        ),
        "structured admin photo library": (
            '@bp.route("/photos")' in files["admin"]
            and "PHOTO_KIND_ZH" in files["admin"]
            and "source_record_id" in files["admin"]
        ),
        "persistent abnormal events": (
            "class AbnormalEvent" in files["models"]
            and '@bp.route("/abnormal")' in files["admin"]
            and "evaluate_vital" in files["abnormal"]
            and "abnormal_event_photos" in files["models"]
        ),
        "database compatibility migration": (
            "ensure_schema_compatibility" in files["schema"]
            and "COLUMN_MIGRATIONS" in files["schema"]
        ),
        "report minimum": '"min"' in files["reports"] and "water_min" in files["reports"],
        "report maximum": '"max"' in files["reports"] and "water_max" in files["reports"],
        "persistent base navigation": (
            "_main_nav.html" in files["base"]
            and "_main_nav.html" in files["base_front"]
        ),
        "admin navigation links": all(
            endpoint in files["nav"]
            for endpoint in (
                "admin.index",
                "family.dashboard",
                "front.home",
                "admin.photos",
                "admin.abnormal",
            )
        ),
        "scoped compact user typography": (
            "users-management-page" in files["users_template"]
            and ".users-management-page" in files["css"]
            and "font-size: 14px" in files["css"]
        ),
        "automatic locale discovery": (
            'LOCALE_DIR.glob("*.json")' in files["translations"]
        ),
    }
    for name, passed in required.items():
        if not passed:
            fail(f"Feature invariant missing: {name}", errors)


def check_release_files(errors: list[str]) -> None:
    required = [
        ".dockerignore",
        ".env.example",
        ".gitattributes",
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
        ".gitignore",
        "CHANGELOG.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "DISCLAIMER.md",
        "Dockerfile",
        "LICENSE",
        "Makefile",
        "README.md",
        "README.en.md",
        "SECURITY.md",
        "VERSION",
        "docs/ARCHITECTURE.md",
        "docs/BUILD_AND_DEPLOY.md",
        "docs/GITHUB_PUBLISHING.md",
        "docs/LOCALIZATION.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/UPGRADE.md",
        "pyproject.toml",
        "requirements-dev.txt",
        "tests/test_features.py",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"Required release file is missing: {relative}", errors)

    forbidden = [".env", "carelog.db", ".venv", ".git"]
    for relative in forbidden:
        if (ROOT / relative).exists():
            fail(f"Private runtime file must not be packaged: {relative}", errors)

    runtime_suffixes = {".db", ".sqlite", ".sqlite3"}
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in runtime_suffixes:
            fail(f"Runtime database must not be packaged: {path.relative_to(ROOT)}", errors)

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    if "CARELOG_HOST_PORT" not in compose or "CARELOG_HOST_PORT" not in env_example:
        fail("Docker host-port variable is inconsistent", errors)
    if re.search(r"^CARELOG_SECRET=\S+", env_example, re.MULTILINE):
        fail(".env.example must not ship with a usable CARELOG_SECRET", errors)


def main() -> int:
    errors: list[str] = []
    check_python(errors)
    check_templates(errors)
    keys = check_translations(errors)
    check_translation_references(keys, errors)
    check_yaml(errors)
    check_markdown_links(errors)
    check_feature_invariants(errors)
    check_release_files(errors)

    if errors:
        print("Static checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Static checks passed: Python, templates, endpoints, CSRF, translations, "
        "YAML, links, feature invariants, and release files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
