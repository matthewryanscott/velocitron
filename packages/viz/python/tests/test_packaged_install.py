"""A built wheel renders a net without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util

from velocitron_viz import (
    Arc,
    ConsumePattern,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
    apply_view,
    net_render_model,
    net_to_dot,
)
from velocitron_viz import render as render_mod

for name in (
    "velocitron",
    "velocitron_cel",
    "velocitron_dsl",
    "velocitron_ir",
    "velocitron_merge",
    "velocitron_play",
):
    assert importlib.util.find_spec(name) is None, name
assert importlib.util.find_spec("velocitron_engine") is not None

assert not hasattr(render_mod, "main")

net = Net(
    name="fusion-net",
    places=[
        Place("window", ["tok"], annotations={"fusion": True}),
        Place("src", ["job"]),
    ],
    transitions=[Transition("open", handler="open_h")],
    arcs=[
        Arc(
            from_place="src",
            to_transition="open",
            consume=ConsumePattern("job", None, "consume"),
        ),
        Arc(
            from_transition="open",
            to_place="window",
            produce=ProduceTemplate("tok", "window"),
        ),
    ],
    initial_marking=Marking({"window": [Token("tok", {})]}),
)
dot = net_to_dot(net)
assert '"window@open"' in dot
assert '"window" [' not in dot
model = net_render_model(net)
view = apply_view(
    model,
    {
        "annotations": {
            "petrinet.dsl/v1": {
                "views": {
                    "wired": {
                        "positions": {"place:src": {"x": 1, "y": 2}},
                        "routes": {},
                    }
                },
                "arcHandles": {},
            }
        }
    },
    "wired",
)
assert 'pos="1,2!"' in view
assert "layout=neato;" in view
print("ok")
"""


def test_wheel_install_renders_without_the_implementation(tmp_path: Path) -> None:
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
    # when: a fresh interpreter imports the installed package and renders
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged renderer draws and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
