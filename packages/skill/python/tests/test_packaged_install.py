"""A built wheel resolves the skill without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = r"""
import importlib.util
from pathlib import Path

from velocitron_skill import skill_root

assert importlib.util.find_spec("velocitron") is None
root = skill_root()
assert root.name == "skill"
assert root.parent.name == "velocitron_skill"
assert not root.is_symlink()
assert (root / "SKILL.md").is_file()
assert (root / "kitchen-sink.play").is_file()
assert (root / "scripts" / "cli-help.sh").is_file()
text = (root / "SKILL.md").read_text(encoding="utf-8")
assert "velocitron skill" in text
print("ok")
"""


def test_wheel_install_resolves_the_skill_outside_the_checkout(tmp_path: Path) -> None:
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
    # when: a fresh interpreter imports the installed package
    checked = subprocess.run(
        [str(python), str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the wheel carries the skill files and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
