"""A built wheel loads contribution IR without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _PROJECT_ROOT.parent / "fixtures" / "cel-string.contribution-ir.json"
_CHECK = """
import importlib.util
import json
import sys

from velocitron_ir import contribution_ir_schema_text, load_contribution_ir_text

assert importlib.util.find_spec("velocitron") is None
schema = json.loads(contribution_ir_schema_text())
assert schema["$id"] == "https://velocitron.dev/spec/petrinet-contribution-ir.schema.json"
document = load_contribution_ir_text(sys.argv[1])
assert document["documentKind"] == "net"
assert document["contributions"][0]["value"] == {"cel": "token.n + 1"}
print("ok")
"""


def test_wheel_install_loads_a_document_without_the_implementation(
    tmp_path: Path,
) -> None:
    # given: a wheel built from this project and a throwaway virtualenv
    dist = tmp_path / "dist"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    completed = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    wheel = next(dist.glob("*.whl"))
    venv = tmp_path / "venv"
    subprocess.run(
        ["uv", "venv", str(venv), "--python", "3.12"],
        check=True,
        env=env,
    )
    python = venv / "bin" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
        env=env,
    )
    script = tmp_path / "check.py"
    script.write_text(_CHECK, encoding="utf-8")
    # when: a fresh interpreter imports the installed package and loads a fixture
    checked = subprocess.run(
        [str(python), str(script), _FIXTURE.read_text(encoding="utf-8")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged schema validates the document and CEL text stays a string
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
