#!/usr/bin/env python3
"""Rewrite the file lists in tools/release-allowlist.json from built artifacts.

Build the velocitron-cli release artifacts from the repository root first:

    uv run --project implementations/python --group release python -m build \
      --no-isolation --outdir ARTIFACT_ROOT/python packages/cli/python

Then run `python3 tools/refresh_allowlist.py ARTIFACT_ROOT`. It prints each
added and removed member.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile
import zipfile

ALLOWLIST = Path(__file__).resolve().parent / "release-allowlist.json"


def members(path: Path, archive_format: str) -> list[str]:
    if archive_format == "zip":
        with zipfile.ZipFile(path) as archive:
            return [name for name in archive.namelist() if not name.endswith("/")]
    with tarfile.open(path) as archive:
        return [member.name for member in archive.getmembers() if member.isfile()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    artifact_root = parser.parse_args().artifact_root
    allowlist = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    for spec in allowlist["artifacts"]:
        built = members(artifact_root / spec["path"], spec["format"])
        listed = set(spec["files"])
        for name in sorted(listed - set(built)):
            print(f"{spec['kind']}: - {name}")
        for name in sorted(set(built) - listed):
            print(f"{spec['kind']}: + {name}")
        spec["files"] = sorted(built)
    ALLOWLIST.write_bytes(
        (json.dumps(allowlist, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
