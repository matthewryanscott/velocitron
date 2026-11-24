#!/usr/bin/env python3
"""Copy the contribution-IR schema into the IR packages.

The canonical schemas live in ``packages/spec``. ``velocitron`` loads them
through ``velocitron-spec`` and does not ship a second copy. The
contribution-IR packages ship ``petrinet-contribution-ir.schema.json`` so a
git-subdirectory install can validate IR without the rest of the monorepo.

``--check`` exits nonzero when a packaged IR copy would differ.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SOURCE_ROOT = REPOSITORY_ROOT / "packages" / "spec"
IR_SCHEMA_NAME = "petrinet-contribution-ir.schema.json"
IR_SCHEMA_OUTPUTS = (
    REPOSITORY_ROOT
    / "packages"
    / "ir"
    / "python"
    / "src"
    / "velocitron_ir"
    / "schemas"
    / IR_SCHEMA_NAME,
    REPOSITORY_ROOT / "packages" / "ir" / "typescript" / IR_SCHEMA_NAME,
)


def _copies() -> tuple[tuple[Path, Path], ...]:
    source = SCHEMA_SOURCE_ROOT / IR_SCHEMA_NAME
    return tuple((source, target) for target in IR_SCHEMA_OUTPUTS)


def _stale_outputs() -> list[Path]:
    stale: list[Path] = []
    for source, target in _copies():
        try:
            actual = target.read_bytes()
        except OSError:
            actual = None
        if actual != source.read_bytes():
            stale.append(target)
    return stale


def _run(check: bool) -> int:
    if check:
        stale = _stale_outputs()
        if stale:
            listing = "\n".join(f"- {path}" for path in stale)
            print(
                f"Packaged Python schemas are stale:\n{listing}\n"
                "Run python3 tools/generate-schemas-python.py.",
                file=sys.stderr,
            )
            return 1
        print("Packaged Python schemas are current.")
        return 0
    for source, target in _copies():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    print("Packaged Python schemas updated.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when a packaged copy differs from packages/spec/",
    )
    return _run(parser.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
