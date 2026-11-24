"""Print the platforms that PyPI has CPython wheels for, per Python ABI.

Use it to keep the wheel table in packages/cel/python/src/velocitron_cel/defaults.py
current (ADR 0053): `python3 tools/cel_rust_wheels.py` checks the Rust backend's
package, and `python3 tools/cel_rust_wheels.py google-re2` checks the package the
cel-python backend needs (ADR 0054).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from urllib.request import urlopen


def main() -> None:
    package = sys.argv[1] if len(sys.argv) > 1 else "common-expression-language"
    with urlopen(f"https://pypi.org/pypi/{package}/json") as response:
        release = json.load(response)
    platforms: dict[str, set[str]] = defaultdict(set)
    for file in release["urls"]:
        name: str = file["filename"]
        if not name.endswith(".whl"):
            continue
        _, _, python, abi, platform = name[: -len(".whl")].split("-")[-5:]
        if python.startswith("cp"):
            # The ABI tag tells a free-threaded build (cp314t) apart.
            key = abi if abi.startswith("cp") else python
            for tag in platform.split("."):
                platforms[key].add(tag)
    print(f"{package} {release['info']['version']}")
    for python in sorted(platforms, key=lambda tag: (len(tag), tag)):
        print(f"  {python}: {' '.join(sorted(platforms[python]))}")


if __name__ == "__main__":
    main()
