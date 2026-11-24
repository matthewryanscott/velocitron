"""A built wheel fires a net without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
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
    symbolic_outputs,
)
from velocitron_engine import journal as journal_mod

for name in (
    "velocitron",
    "velocitron_cel",
    "velocitron_dsl",
    "velocitron_ir",
    "velocitron_merge",
    "velocitron_play",
):
    assert importlib.util.find_spec(name) is None, name

assert not hasattr(journal_mod, "JsonlJournal")
assert not hasattr(journal_mod, "replay_events")

class Adapter:
    def compile(self, expr):
        raise AssertionError(expr)

    def eval(self, compiled, data):
        raise AssertionError(compiled)

def move(inp):
    token = inp["inputTokens"]["src"][0]
    return {
        "status": "completed",
        "outputTokens": {"dst": [Token("job", {"id": token.data["id"], "done": True})]},
        "error": None,
        "metadata": {},
    }

places = [Place("src", ["job"]), Place("dst", ["job"])]
net = Net(
    name="move",
    places=places,
    transitions=[Transition("move", handler="move")],
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
)
registry = HandlerRegistry()
registry.register_transition("move", move)
engine = Engine(registry, cel_adapter=Adapter())
moved, record = engine.fire(
    net, Marking({"src": [Token("job", {"id": 1})]}), "move", attempt=0
)
assert record["status"] == "completed"
assert list(moved["dst"])[0].data == {"id": 1, "done": True}

carry = Net(
    name="carry",
    places=places,
    transitions=[Transition("go")],
    arcs=[
        Arc(
            from_place="src",
            to_transition="go",
            consume=ConsumePattern("job", None, "consume"),
        ),
        Arc(
            from_transition="go",
            to_place="dst",
            produce=ProduceTemplate("job", "dst"),
        ),
    ],
)
outcome = Engine(HandlerRegistry(), cel_adapter=Adapter()).advance(
    carry, Marking({"src": [Token("job", {"id": 7})]}), outputs=symbolic_outputs
)
assert len(outcome.firings) == 1
assert list(outcome.marking["dst"])[0].data == {"id": 7}
try:
    Engine(HandlerRegistry())
except ValueError as exc:
    assert "cel_adapter is required" in str(exc)
else:
    raise SystemExit("missing adapter was accepted")
print("ok")
"""


def test_wheel_install_fires_without_the_implementation(tmp_path: Path) -> None:
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
    # when: a fresh interpreter imports the installed package and fires
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged engine fires and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
