#!/usr/bin/env python3
"""Static publication checks for the ORVIBO Cloud HACS repository."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "orvibo_cloud"
EXPECTED_FIELDS = {"domain", "name", "codeowners", "documentation", "issue_tracker", "version"}


def inspect_repository(root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    def must_exist(relpath: str) -> Path:
        path = root / relpath
        if not path.is_file():
            errors.append(f"Missing: {relpath}")
        return path

    manifest_path = must_exist(f"custom_components/{DOMAIN}/manifest.json")
    hacs_path = must_exist("hacs.json")
    for rel in ("README.md", "LICENSE", ".github/workflows/validate.yml",
                "custom_components/orvibo_cloud/__init__.py",
                "custom_components/orvibo_cloud/brand/icon.png",
                "custom_components/orvibo_cloud/orvibo_server_ca.pem",
                "custom_components/orvibo_cloud/translations/en.json",
                "HACS_PUBLISHING.md", "VALIDATION.md"):
        must_exist(rel)

    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            missing = EXPECTED_FIELDS - set(manifest)
            if missing:
                errors.append(f"Manifest missing fields: {', '.join(sorted(missing))}")
            if manifest.get("domain") != DOMAIN:
                errors.append("Manifest domain does not match integration directory")
            if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
                errors.append("Manifest version must be x.y.z")
            if not manifest.get("codeowners"):
                errors.append("Manifest must have a codeowner")
            expected_order = ["domain", "name"] + sorted(
                k for k in manifest if k not in {"domain", "name"}
            )
            if list(manifest) != expected_order:
                errors.append("Manifest keys must be ordered domain, name, then alphabetical")
        except (ValueError, UnicodeError) as err:
            errors.append(f"Invalid manifest JSON: {err}")

    if hacs_path.is_file():
        try:
            hacs = json.loads(hacs_path.read_text(encoding="utf-8"))
            if hacs.get("name") != "ORVIBO Cloud":
                errors.append("HACS display name should be ORVIBO Cloud")
            if hacs.get("zip_release") is True:
                errors.append("HACS zip_release must remain unset; source archives are used")
        except (ValueError, UnicodeError) as err:
            errors.append(f"Invalid HACS manifest JSON: {err}")

    strings = root / "custom_components/orvibo_cloud/strings.json"
    english = root / "custom_components/orvibo_cloud/translations/en.json"
    if strings.exists() and english.exists():
        if json.loads(strings.read_text()) != json.loads(english.read_text()):
            errors.append("English translation fallback is out of sync")

    component_root = root / "custom_components"
    if component_root.is_dir():
        dirs = sorted(p.name for p in component_root.iterdir() if p.is_dir())
        if dirs != [DOMAIN]:
            errors.append(f"Expected exactly one custom integration, found: {dirs}")
    return errors


if __name__ == "__main__":
    issues = inspect_repository()
    for issue in issues:
        print("FAIL:", issue, file=sys.stderr)
    if issues:
        raise SystemExit(1)
    print("PASS: ORVIBO Cloud static HACS packaging checks")
