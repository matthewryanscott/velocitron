"""A built wheel parses .play text without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util

from velocitron_play import PlayError, grammar_text, parse_play, project_source

assert importlib.util.find_spec("velocitron") is None
assert "grammar VelocitronPlay;" in grammar_text()
play = parse_play('play shop "One purchase"\\nadvance 90m\\n')
assert play.name == "shop"
body = play.paths[0].steps[0].body
assert body.seconds == 5400
assert body.relative is False
projected = project_source('play s\\ninject (p) <- c {"a": 1, "a": 2}\\n')
assert projected["ok"] is False
assert projected["code"] == "SC102"
try:
    parse_play("  play s\\n")
except PlayError as error:
    assert error.diagnostic.code == "SC101"
    assert error.diagnostic.position.line == 1
else:
    raise SystemExit("indented source parsed")
print("ok")
"""


def test_wheel_install_parses_a_play_without_the_implementation(tmp_path: Path) -> None:
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
    # when: a fresh interpreter imports the installed package and parses a play
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged grammar parses a play, and not an indented header
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
