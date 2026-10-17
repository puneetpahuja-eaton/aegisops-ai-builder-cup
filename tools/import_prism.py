"""Bulk-import the participant-owned PRISM reference without rewriting its behavior.

Usage: python tools/import_prism.py --source ..\\PRISM
The allowlist excludes documents, reports, caches and local configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    destination = ROOT / "prism_reference"
    if destination.exists():
        raise FileExistsError("Reference already imported. Do not overwrite integrated changes.")
    paths = sorted((source / "prism").rglob("*.py"))
    paths += [source / "dashboard" / "app.py", source / "data" / "assets.csv",
              source / "data" / "live_scenarios.json"]
    manifest = {}
    for path in paths:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Import integrity failure: {relative}")
        manifest[relative.as_posix()] = digest
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Imported and hash-verified {len(paths)} canonical files. Original PRISM is unchanged.")


if __name__ == "__main__":
    main()
