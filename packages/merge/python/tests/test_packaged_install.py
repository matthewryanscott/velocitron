"""A built wheel merges nets without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util

from velocitron_merge import (
    Arc,
    ConsumePattern,
    Net,
    NetValidationError,
    Place,
    Port,
    ProduceTemplate,
    Transition,
    Wire,
    merge_nets,
    port_fusion_map,
)

assert importlib.util.find_spec("velocitron") is None
assert importlib.util.find_spec("velocitron_ir") is None
assert importlib.util.find_spec("velocitron_dsl") is None
assert importlib.util.find_spec("velocitron_cel") is None

def place(name, port=None):
    return Place(name=name, accepts=["task"], port=port)

prod = Net(
    name="prod",
    places=[
        place("src"),
        place("out", Port(direction="output", type="task")),
    ],
    transitions=[Transition(name="make", handler="noop")],
    arcs=[
        Arc(
            from_place="src",
            to_transition="make",
            consume=ConsumePattern(type="task", predicate=None, mode="consume"),
        ),
        Arc(
            from_transition="make",
            to_place="out",
            produce=ProduceTemplate(type="task", destination="out"),
        ),
    ],
)
cons = Net(
    name="cons",
    places=[
        place("inbox", Port(direction="input", type="task")),
        place("done"),
    ],
    transitions=[Transition(name="take", handler="noop")],
    arcs=[
        Arc(
            from_place="inbox",
            to_transition="take",
            consume=ConsumePattern(type="task", predicate=None, mode="consume"),
        ),
        Arc(
            from_transition="take",
            to_place="done",
            produce=ProduceTemplate(type="task", destination="done"),
        ),
    ],
)
wire = Wire("prod", "out", "cons", "inbox")
merged = merge_nets({"prod": prod, "cons": cons}, [wire], name="wired")
assert merged.name == "wired"
assert {place.name for place in merged.places} == {"prod.src", "prod.out", "cons.done"}
assert port_fusion_map({"prod": prod, "cons": cons}, [wire]) == {
    "prod.out": "prod.out",
    "cons.inbox": "prod.out",
}
assert not hasattr(__import__("velocitron_merge"), "parse_net")
left = Net(
    name="a",
    places=[place("p")],
    transitions=[],
    arcs=[],
    domains={"task.kind": ["one"]},
)
right = Net(
    name="b",
    places=[place("p")],
    transitions=[],
    arcs=[],
    domains={"task.kind": ["two"]},
)
try:
    merge_nets({"a": left, "b": right}, [])
except NetValidationError as exc:
    assert "domain task.kind differs" in str(exc)
else:
    raise SystemExit("domain conflict accepted")
print("ok")
"""


def test_wheel_install_merges_without_the_implementation(tmp_path: Path) -> None:
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
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(engine), str(wheel)],
        check=True,
        env=env,
    )
    script = tmp_path / "check.py"
    script.write_text(_CHECK, encoding="utf-8")
    # when: a fresh interpreter imports the installed package and merges
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged merge fuses the wire and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
