"""A built wheel generates a module without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = r"""
import importlib.util

from velocitron_codegen import SYNTH_HANDLER, generate_module, net_sha256
from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import compile_petrinet_text, parse_net

assert importlib.util.find_spec("velocitron") is None
assert SYNTH_HANDLER == "velocitron:synth:"

text = '''
net sound "One transition"

(i) -> [go] -> (o)
[go] handler "go@sound"
'''
lowered = lower_petrinet_text(text, "sound.petrinet")
net = parse_net(compile_petrinet_text(text, "sound.petrinet"))
module = generate_module(
    net,
    source="sound.petrinet",
    source_name="sound.petrinet",
    text=text,
    contributions=lowered["contributions"],
)
assert module.net_name == "sound"
assert module.sha256 == net_sha256(net)
assert "class SoundNet" in module.text
assert "def fire_go" in module.text
print("ok")
"""


def test_wheel_install_generates_without_the_implementation(tmp_path: Path) -> None:
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
        _REPO_PACKAGES / "viz" / "python",
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
    # when: a fresh interpreter imports the installed package and generates
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged generator runs and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
