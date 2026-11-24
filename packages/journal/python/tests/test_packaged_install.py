"""A built wheel appends and replays without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util
import tempfile
from pathlib import Path

from velocitron_engine import Arc, ConsumePattern, Marking, Net, Place, ProduceTemplate, Token, Transition
from velocitron_journal import (
    DurableJournal,
    JsonlJournal,
    open_database,
    read_events,
    replay_records,
)

for name in (
    "velocitron",
    "velocitron_cel",
    "velocitron_dsl",
    "velocitron_ir",
    "velocitron_merge",
    "velocitron_play",
    "velocitron_play_check",
    "velocitron_viz",
):
    assert importlib.util.find_spec(name) is None, name
assert importlib.util.find_spec("velocitron_engine") is not None

net = Net(
    name="move",
    places=[Place("src", ["job"]), Place("dst", ["job"])],
    transitions=[Transition("move", handler="move")],
    arcs=[
        Arc(from_place="src", to_transition="move", consume=ConsumePattern("job", None, "consume")),
        Arc(from_transition="move", to_place="dst", produce=ProduceTemplate("job", "dst")),
    ],
    initial_marking=Marking({"src": [Token("job", {"id": 1})]}),
)
record = {
    "firingId": "move/move/0",
    "netId": "move",
    "transition": "move",
    "attempt": 0,
    "status": "completed",
    "inputTokens": {"src": [Token("job", {"id": 1})]},
    "outputTokens": {"dst": [Token("job", {"id": 1, "done": True})]},
    "error": None,
    "metadata": {},
    "timestamps": {"fired_at": "2026-01-01T00:00:00Z"},
}
journal = JsonlJournal()
journal.record_firing(record)
marking = replay_records(net, journal.records())
assert list(marking["src"]) == []
assert list(marking["dst"])[0].data == {"id": 1, "done": True}

with tempfile.TemporaryDirectory() as directory:
    connection = open_database(Path(directory) / "events.db")
    durable = DurableJournal(connection, "move")
    durable.record_firing(record)
    events = read_events(connection, "move")
    assert events[0].kind == "firing"
    assert events[0].payload["transition"] == "move"
    connection.close()
print("ok")
"""


def test_wheel_install_replays_without_the_implementation(tmp_path: Path) -> None:
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
    # when: a fresh interpreter imports the installed package and replays
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged journal replays and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
