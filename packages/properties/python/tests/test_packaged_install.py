"""A built wheel checks a marking without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = r"""
import importlib.util

from velocitron_engine import Marking, Net, Place, Token
from velocitron_properties import AtMostN, check_marking

assert importlib.util.find_spec("velocitron") is None

class Adapter:
    def compile(self, expr: str) -> str:
        return expr

    def eval(self, compiled: str, data: dict) -> bool:
        del compiled, data
        return True

net = Net(name="box", places=[Place("shelf", ["job"])], transitions=[], arcs=[])
marking = Marking({"shelf": [Token("job", {"id": "a"})]})
report = check_marking(net, marking, [AtMostN("shelf", 0)], cel_adapter=Adapter())
assert not report.ok
assert report.violations[0].place == "shelf"
print("ok")
"""


def test_wheel_install_checks_a_marking_without_the_implementation(
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
    siblings = [
        _REPO_PACKAGES / "cel" / "python",
        _REPO_PACKAGES / "engine" / "python",
        _REPO_PACKAGES / "journal" / "python",
    ]
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            *(str(path) for path in siblings),
            str(wheel),
        ],
        check=True,
        env=env,
    )
    script = tmp_path / "check.py"
    script.write_text(_CHECK, encoding="utf-8")
    # when: a fresh interpreter imports the installed package
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged checker runs and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
