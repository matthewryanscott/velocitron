#!/usr/bin/env python3
"""Pyodide parity harness: the browser story fails loudly, in CI (ADR 0058).

The primer runs the pure-Python ``velocitron-cli`` wheel and its in-repo
dependency wheels in Pyodide (a Web Worker); a native dependency added
later would install fine everywhere else and break the wheels only there.
This harness fails when

  - those wheels no longer install in Pyodide,
  - Pyodide's output differs from the native CLI's on the play cases, or
  - the Pyodide run touched the network outside its own local origin.

Both sides run the same ``velocitron play …`` commands on the same case
directories and are diffed byte for byte. The pinned Pyodide npm package,
the prebuilt Pyodide core, and the lock/dependency wheels are cached under
``tools/.pyodide-parity/`` (gitignored) after the first fetch; a complete
cache hit makes the run fully offline. Cache safety is by pin, not by
expiry: the pin below, a checked sha256 for every fetched wheel, and a
manifest of the cached file digests.

One command for CI (also wired as the nox session ``pyodide_parity``):

    uv run --project implementations/python python tools/pyodide_parity.py

References: spec/play-language.md; ADR 0058 (the browser runs the package
through Pyodide).

Requires Python 3.12+ (the repo floor), Node >= 24.15 (the workspace
engine floor), and network access on the first fetch only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PY_DIR = REPO_ROOT / "implementations" / "python"
CACHE = REPO_ROOT / "tools" / ".pyodide-parity"

# The pin. Bump deliberately, together: the npm package version and the
# CDN distribution must be the same Pyodide release, and the version table
# below pins the pure-Python dependency wheels micropip installs beside
# the velocitron-cli wheel and its in-repo dependency wheels. Every fetched
# wheel is sha256-checked against its
# registry's own digest before it enters the cache.
PYODIDE_VERSION = "314.0.7"
CDN = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"

# The Pyodide-built wheels the CLI closure pulls in through micropip
# (read from pyodide-lock.json, checked against the lock's sha256): the
# pure-Python dependencies that Pyodide also ships built for
# wasm, taken from the lock rather than PyPI.
LOCK_PACKAGES = (
    "micropip",
    "jsonschema",
    "referencing",
    "jsonschema-specifications",
    "attrs",
    "rpds-py",
    "python-dateutil",
    "six",
    "tzdata",
    "typing-extensions",
    "pyrsistent",
)

# Pure-Python dependency wheels, at the versions checked to install in
# Pyodide and to match the package floors. Fetched once from
# PyPI's JSON API, sha256-checked, cached, installed by micropip.
#
# In-repo wheels built on every run. ``velocitron-cli`` is the console
# entry. The rest are the packages that entry imports. There is no
# ``velocitron`` library wheel.
LOCAL_WHEELS = (
    "packages/spec",
    "packages/ir/python",
    "packages/cel/python",
    "packages/engine/python",
    "packages/journal/python",
    "packages/merge/python",
    "packages/viz/python",
    "packages/dsl/python",
    "packages/petrinet/python",
    "packages/play/python",
    "packages/runtime/python",
    "packages/analysis/python",
    "packages/play-check/python",
    "packages/explain/python",
    "packages/equiv/python",
    "packages/codegen/python",
    "packages/skill/python",
    "packages/cli/python",
)
PYPI_PACKAGES = {
    "lark": "1.3.1",
    "pendulum": "3.3.0",
    "antlr4-python3-runtime": "4.13.2",
    "json5": "0.17.3",
}

# The commands both sides run, in order; the Node driver mirrors this table.
COMMANDS: dict[str, list[str]] = {
    "check": ["play", "check", "case.play"],
    "check-json": ["play", "check", "case.play", "--json"],
    "walk": ["play", "walk", "case.play"],
    "walk-json": ["play", "walk", "case.play", "--format", "json"],
    "sequence": ["play", "sequence", "case.play"],
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get(url: str, expected_sha256: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"user-agent": "velocitron-pyodide-parity"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
        raise SystemExit(f"sha256 mismatch for {url}")
    return data


def _cache_dir(*parts: str) -> Path:
    directory = CACHE.joinpath(*parts)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# ── Preparation ──────────────────────────────────────────────────────────


def _fetch_or_cache() -> tuple[Path, Path]:
    """The npm package directory and the prepared serving root, from cache
    or the registries. Files land per-digest; a partial cache resumes."""
    npm_root = _cache_dir("npm")
    package_dir = npm_root / "package"
    dist = _cache_dir("dist")

    manifest_path = CACHE / "manifest.json"
    npm_tarball = CACHE / "pyodide.tgz"
    wanted = {
        "dist/pyodide/pyodide.mjs",
        "dist/pyodide/pyodide.asm.mjs",
        "dist/pyodide/pyodide.asm.wasm",
        "dist/pyodide/python_stdlib.zip",
        "dist/pyodide/pyodide-lock.json",
    }
    if manifest_path.is_file() and npm_tarball.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["pyodide_version"] == PYODIDE_VERSION and wanted <= set(manifest["files"]):
            # A warm cache is complete core + lock wheels + the built CLI wheel
            # (local wheels are rebuilt and re-hashed when the cache is filled,
            # so the manifest need not pin them beyond the CLI wheel's presence).
            has_wheel = any(name.startswith("dist/wheels/velocitron_cli-") for name in manifest["files"])
            lock = json.loads((package_dir / "pyodide-lock.json").read_text(encoding="utf-8"))
            has_lock_wheels = all(name in lock["packages"] for name in LOCK_PACKAGES)
            if has_wheel and has_lock_wheels:
                return package_dir, dist

    # First (or stale-pin) fetch: populate the cache's immutable parts.
    # The CLI and leaf wheels are rebuilt below; the manifest is rewritten
    # then too, so a rebuilt wheel's digest always matches.
    if manifest_path.is_file():
        print(f"pyodide parity: pin {PYODIDE_VERSION} not fully cached; refetching")
    else:
        print(f"pyodide parity: populating the cache under {CACHE} (first fetch only)")
    npm_root.mkdir(parents=True, exist_ok=True)
    if not npm_tarball.is_file():
        registry = json.loads(_get("https://registry.npmjs.org/pyodide"))
        version_meta = registry["versions"][PYODIDE_VERSION]
        npm_tarball.write_bytes(_get(version_meta["dist"]["tarball"]))
    staging = Path(tempfile.mkdtemp(prefix="pyodide-parity-"))
    try:
        with tarfile.open(npm_tarball) as tar:
            tar.extractall(staging, filter="data")
        if package_dir.exists():
            shutil.rmtree(package_dir)
        shutil.copytree(staging / "package", package_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    (dist / "pyodide").mkdir(parents=True, exist_ok=True)
    for name in sorted(wanted):
        core_name = name.removeprefix("dist/pyodide/")
        (dist / "pyodide" / core_name).write_bytes((package_dir / core_name).read_bytes())

    lock = json.loads((package_dir / "pyodide-lock.json").read_text(encoding="utf-8"))
    for name in LOCK_PACKAGES:
        if name not in lock["packages"]:
            raise SystemExit(f"{name} is not in pyodide-lock.json; update LOCK_PACKAGES")
        entry = lock["packages"][name]
        file_name = entry["file_name"]
        (dist / "pyodide" / file_name).write_bytes(
            _get(CDN + file_name, entry["sha256"])
        )

    wheels = _cache_dir("dist", "wheels")
    for name, version in PYPI_PACKAGES.items():
        data = json.loads(_get(f"https://pypi.org/pypi/{name}/{version}/json"))
        wheels_meta = [
            release
            for release in data["urls"]
            if release["packagetype"] == "bdist_wheel" and release["filename"].endswith("-py3-none-any.whl")
        ]
        if len(wheels_meta) != 1:
            raise SystemExit(f"expected one py3-none-any wheel for {name} {version}")
        release = wheels_meta[0]
        (wheels / release["filename"]).write_bytes(
            _get(release["url"], release["digests"]["sha256"])
        )

    for stale in (*wheels.glob("velocitron-*.whl"), *wheels.glob("velocitron_*.whl")):
        stale.unlink()
    for relative in LOCAL_WHEELS:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(wheels)],
            cwd=REPO_ROOT / relative,
            check=True,
        )
    if len(list(wheels.glob("velocitron_cli-*.whl"))) != 1:
        raise SystemExit("uv build produced no velocitron-cli wheel")

    files = sorted(
        str(path.relative_to(CACHE))
        for path in CACHE.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "pyodide.tgz"}
    )
    manifest_path.write_text(
        json.dumps(
            {
                "pyodide_version": PYODIDE_VERSION,
                "files": files,
                "sha256": {name: _sha256((CACHE / name).read_bytes()) for name in files},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return package_dir, dist


def _verify_cache() -> None:
    """Every cached file still matches the manifest's sha256."""
    manifest = json.loads((CACHE / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["sha256"].items():
        path = CACHE / name
        if not path.is_file() or _sha256(path.read_bytes()) != digest:
            raise SystemExit(f"pyodide parity cache is incomplete; remove {CACHE} and rerun")


# ── Cases and runs ───────────────────────────────────────────────────────


def _case_dirs() -> list[Path]:
    return sorted(path for path in (REPO_ROOT / "packages" / "spec" / "conformance" / "play").iterdir() if path.is_dir())


def _read_run(out: Path, stem: str) -> tuple[int, bytes, bytes]:
    code = int((out / f"{stem}.code").read_text(encoding="utf-8").strip())
    return code, (out / f"{stem}.stdout").read_bytes(), (out / f"{stem}.stderr").read_bytes()


def _run_cli(cases: list[Path], work: Path) -> dict[str, tuple[int, bytes, bytes]]:
    """The native CLI side: the same commands through the installed package."""
    out = work / "cli"
    out.mkdir(parents=True)
    runs: dict[str, tuple[int, bytes, bytes]] = {}
    env = {**os.environ, "VELOCITRON_NO_CEL_WARNING": "1"}
    for case in cases:
        for command, args in COMMANDS.items():
            stem = f"{case.name}.{command}"
            completed = subprocess.run(
                ["uv", "run", "--no-sync", "--project", str(PY_DIR), "velocitron", *args],
                cwd=case,
                capture_output=True,
                env=env,
                check=False,
            )
            (out / f"{stem}.stdout").write_bytes(completed.stdout)
            (out / f"{stem}.stderr").write_bytes(completed.stderr)
            (out / f"{stem}.code").write_text(f"{completed.returncode}\n", encoding="utf-8")
            runs[stem] = (completed.returncode, completed.stdout, completed.stderr)
    return runs


def main() -> int:
    package_dir, dist = _fetch_or_cache()
    _verify_cache()

    wheels = dist / "wheels"
    expected_wheels = len(LOCAL_WHEELS) + len(PYPI_PACKAGES)
    if len(list(wheels.glob("*.whl"))) < expected_wheels:
        # The dependency wheels are cache-managed; a missing one means the
        # manifest allowed a stale state through.
        raise SystemExit("the cache is missing dependency wheels; remove the cache and rerun")

    cases = _case_dirs()
    if not cases:
        raise SystemExit("no play conformance cases found")

    with tempfile.TemporaryDirectory(prefix="pyodide-parity-") as work_path:
        work = Path(work_path)
        cli_runs = _run_cli(cases, work)

        driver_out = work / "pyodide"
        completed = subprocess.run(
            ["node", str(REPO_ROOT / "tools" / "pyodide_parity_driver.mjs"),
             str(package_dir), str(dist), str(REPO_ROOT / "packages" / "spec" / "conformance" / "play"), str(driver_out)],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout + completed.stderr)
            return completed.returncode
        summary = json.loads((driver_out / "summary.json").read_text(encoding="utf-8"))
        if summary["installError"]:
            sys.stderr.write(f"the wheel failed to install in Pyodide:\n{summary['installError']}\n")
            return 1
        if summary["fetchOtherOrigin"]:
            sys.stderr.write(
                "the Pyodide run fetched outside its own origin (network is not "
                "closed after the cache is warm):\n"
                + "\n".join(summary["fetchOtherOrigin"])
                + "\n"
            )
            return 1

        failures: list[str] = []
        for case in cases:
            for command in COMMANDS:
                stem = f"{case.name}.{command}"
                code, stdout, stderr = _read_run(driver_out, stem)
                if (code, stdout, stderr) != cli_runs[stem]:
                    failures.append(stem)
        if failures:
            sys.stderr.write(
                "Pyodide output differs from the CLI's on: "
                + ", ".join(failures)
                + f"\n(diffs under {driver_out} against the CLI runs)\n"
            )
            return 1

        print(
            f"pyodide parity: pyodide {summary['pyodide_version']}, "
            f"{len(cases)} cases x {len(COMMANDS)} commands identical "
            f"(wheels: {', '.join(summary['wheels'])})"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())