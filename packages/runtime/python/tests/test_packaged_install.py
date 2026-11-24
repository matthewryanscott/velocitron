"""A built wheel runs a firing without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util

from velocitron_engine import Arc, ConsumePattern, Marking, Net, Place, ProduceTemplate, Token, Transition
from velocitron_runtime import HandlerSpec, Runtime, TokenArrival

for name in (
    "velocitron",
    "velocitron_dsl",
    "velocitron_ir",
    "velocitron_journal",
    "velocitron_merge",
    "velocitron_play",
    "velocitron_play_check",
    "velocitron_viz",
):
    assert importlib.util.find_spec(name) is None, name
assert importlib.util.find_spec("velocitron_engine") is not None
assert importlib.util.find_spec("velocitron_cel") is not None

class Adapter:
    def compile(self, expr):
        return expr

    def eval(self, compiled, data):
        return False

net = Net(
    name="move",
    places=[Place("src", ["job"]), Place("dst", ["job"])],
    transitions=[Transition("move", handler="move")],
    arcs=[
        Arc(from_place="src", to_transition="move", consume=ConsumePattern("job", None, "consume")),
        Arc(from_transition="move", to_place="dst", produce=ProduceTemplate("job", "dst")),
    ],
    initial_marking=Marking(),
)

async def handler(inp, ctx):
    return {
        "status": "completed",
        "outputTokens": {"dst": [Token("job", {"done": True})]},
        "error": None,
        "metadata": {},
    }

runtime = Runtime(
    net=net,
    handlers={"move": HandlerSpec(handler, "main")},
    lanes={"main": 1},
    cel_adapter=Adapter(),
)

import asyncio

async def play():
    await runtime.start()
    await runtime.inject(TokenArrival("src", Token("job", {"id": 1})))
    await runtime.wait_idle()
    await runtime.stop()

asyncio.run(play())
assert list(runtime.marking.get("src", ())) == []
assert list(runtime.marking["dst"])[0].data == {"done": True}
print("ok")
"""


def test_wheel_install_runs_without_the_implementation(tmp_path: Path) -> None:
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
    engine = _PROJECT_ROOT.parents[1] / "engine" / "python"
    cel = _PROJECT_ROOT.parents[1] / "cel" / "python"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(engine),
            str(cel),
            str(wheel),
        ],
        check=True,
        env=env,
    )
    script = tmp_path / "check.py"
    script.write_text(_CHECK, encoding="utf-8")
    # when: a fresh interpreter imports the installed package and runs
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged runtime fires and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
