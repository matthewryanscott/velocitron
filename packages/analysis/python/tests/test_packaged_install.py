"""A built wheel proves a net without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = r"""
import importlib.util

from velocitron_analysis import FACTS, lint_net, prove
from velocitron_petrinet import compile_petrinet_text, parse_net

assert importlib.util.find_spec("velocitron") is None
assert importlib.util.find_spec("velocitron_engine") is not None

text = '''
net sound_workflow "Two branches"

(i) -> [split] -> (p1)
[split] -> (p2)
(p1) -> [left] -> (p3)
(p2) -> [right] -> (p4)
(p3) -> [join] -> (o)
(p4) -> [join]

marking initial (i) <- 1
'''
net = parse_net(compile_petrinet_text(text, "sound.petrinet"))
report = prove(net, facts=FACTS)
assert report.status == "proved"
assert report.net == "sound_workflow"
sink = parse_net({
    "name": "sink",
    "places": [{"name": "flag", "accepts": ["flag"]}],
    "transitions": [{"name": "clear_flag", "handler": "clear_flag"}],
    "arcs": [{
        "from": {"place": "flag"},
        "to": {"transition": "clear_flag"},
        "consume": {"type": "flag"},
    }],
})
assert [finding.rule for finding in lint_net(sink)] == ["consume-without-produce"]
print("ok")
"""


def test_wheel_install_proves_without_the_implementation(tmp_path: Path) -> None:
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
        _REPO_PACKAGES / "viz" / "python",
        _REPO_PACKAGES / "engine" / "python",
        _REPO_PACKAGES / "merge" / "python",
        _REPO_PACKAGES / "petrinet" / "python",
        _REPO_PACKAGES / "runtime" / "python",
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
    # when: a fresh interpreter imports the installed package and proves
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged prover runs and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
