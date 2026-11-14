#!/usr/bin/env python3
"""Build deterministic ORVIBO HACS-friendly install and complete source ZIPs.

No networking, GitHub actions, or mutation of the source tree.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
EXCLUDED_FILENAMES = {".DS_Store"}


def packaged_files(root: Path) -> list[Path]:
    return sorted(
        (p for p in root.rglob("*")
         if p.is_file()
         and not EXCLUDED_PARTS.intersection(p.relative_to(root).parts)
         and p.name not in EXCLUDED_FILENAMES
         and p.suffix != ".pyc"),
        key=lambda p: p.relative_to(root).as_posix(),
    )


def make_zip(destination: Path, root: Path, prefix: str = "") -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for source in packaged_files(root):
            relative = source.relative_to(root).as_posix()
            path = f"{prefix}{relative}"
            entry = ZipInfo(path, (2026, 11, 14, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            mode = stat.S_IFREG | (0o755 if source.stat().st_mode & 0o111 else 0o644)
            entry.external_attr = mode << 16
            archive.writestr(entry, source.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)


def build(root: Path, output: Path, version: str) -> tuple[Path, Path]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Only stable numeric versions may be packaged for production")
    manifest = json.loads((root / "custom_components/orvibo_cloud/manifest.json").read_text())
    if manifest.get("version") != version:
        raise ValueError(f"Manifest version mismatch: {manifest.get('version')} != {version}")
    if (root / "README.md").read_bytes() != (root / "custom_components/orvibo_cloud/README.md").read_bytes():
        raise ValueError("Root and integration README differ")
    if not (root / f"RELEASE_NOTES_{version}.md").is_file():
        raise ValueError("Release notes missing")
    install = output / f"orvibo_cloud_v{version}_ha_install.zip"
    source = output / f"orvibo_cloud_v{version}_full_source.zip"
    make_zip(install, root / "custom_components", "custom_components/")
    make_zip(source, root, f"orvibo_cloud_v{version}/")
    return install, source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="1.4.1")
    args = parser.parse_args()
    install, source = build(ROOT, args.output, args.version)
    for item in (install, source):
        with ZipFile(item) as z:
            if z.testzip() is not None:
                raise ValueError(f"Broken archive: {item}")
        print(item)


if __name__ == "__main__":
    main()
