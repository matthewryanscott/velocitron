"""A built wheel checks a play without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = r"""
import importlib.util
from pathlib import Path

from velocitron_play import read_play
from velocitron_play_check import check_play, render_walkthrough

assert importlib.util.find_spec("velocitron") is None
root = Path("shop")
root.mkdir()
(root / "shop.petrinet").write_text(
    'net shop "Shop"\n\n'
    "(orders) -purchase-> [accept] -purchase-> (accepted)\n\n"
    "marking initial (orders) <- $o\n"
    '$o: purchase {"id": "o-1"}\n',
    encoding="utf-8",
)
play_path = root / "shop.play"
play_path.write_text(
    'play shop "One purchase"\n'
    'net "shop.petrinet"\n'
    "fire [accept]\n"
    'expect (accepted) has purchase {"id": "o-1"}\n',
    encoding="utf-8",
)
report = check_play(read_play(play_path))
assert report.passed
assert "accept" in render_walkthrough(report.traces[0])
print("ok")
"""


def test_wheel_install_checks_a_play_without_the_implementation(tmp_path: Path) -> None:
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
        _REPO_PACKAGES / "spec",
        _REPO_PACKAGES / "ir" / "python",
        _REPO_PACKAGES / "grammar" / "python",
        _REPO_PACKAGES / "cel" / "python",
        _REPO_PACKAGES / "dsl" / "python",
        _REPO_PACKAGES / "engine" / "python",
        _REPO_PACKAGES / "merge" / "python",
        _REPO_PACKAGES / "petrinet" / "python",
        _REPO_PACKAGES / "play" / "python",
        _REPO_PACKAGES / "viz" / "python",
        _REPO_PACKAGES / "runtime" / "python",
        _REPO_PACKAGES / "analysis" / "python",
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
    # when: a fresh interpreter imports the installed package and checks a play
    checked = subprocess.run(
        [str(python), str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the wheel checks the play and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
