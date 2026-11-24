"""A built wheel registers a net without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = r"""
import importlib.util

from velocitron_engine import (
    Arc,
    ConsumePattern,
    Engine,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
)
from velocitron_netbase import SYNTH_HANDLER, VelocitronNet, net_sha256

assert importlib.util.find_spec("velocitron") is None
assert SYNTH_HANDLER == "velocitron:synth:"

net = Net(
    name="move",
    places=[Place("src", ["job"]), Place("dst", ["job"])],
    transitions=[Transition("move", handler="move@move")],
    arcs=[
        Arc(
            from_place="src",
            to_transition="move",
            consume=ConsumePattern("job", None, "consume"),
        ),
        Arc(
            from_transition="move",
            to_place="dst",
            produce=ProduceTemplate("job", "dst"),
        ),
    ],
    initial_marking=Marking(),
)


class Move(VelocitronNet):
    NET_NAME = "move"
    SOURCE = "move.petrinet"
    SOURCE_SHA256 = net_sha256(net)
    HANDLER_REFS = {"move@move": "fire_move"}
    INPUT_PLACES = {"move": ("src",)}
    OUTPUT_PLACES = {"move": ("dst",)}

    def fire_move(self, *, src):
        return {"dst": [Token("job", {"done": True})]}


class Adapter:
    def compile(self, expr):
        return expr

    def eval(self, compiled, data):
        return False


registry = HandlerRegistry()
registered = Move().register_into(registry, net)
final = Engine(registry, cel_adapter=Adapter()).advance(
    registered.net,
    Marking({"src": [Token("job", {"n": 1})]}),
)
assert [token.data for token in final["dst"]] == [{"done": True}]
print("ok")
"""


def test_wheel_install_registers_without_the_implementation(tmp_path: Path) -> None:
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
        _REPO_PACKAGES / "runtime" / "python",
        _REPO_PACKAGES / "codegen" / "python",
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
    # then: the packaged base imports and does not see the umbrella
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
