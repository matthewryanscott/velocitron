"""A built wheel validates a net without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = r"""
import importlib.util
import sys
from io import StringIO
from pathlib import Path

from velocitron_cli import main, viz_main
from velocitron_skill import skill_root

assert importlib.util.find_spec("velocitron") is None

path = Path("sound.petrinet")
path.write_text(
    '''
net sound "One transition"

(i) -> [go] -> (o)
[go] handler "go@sound"
''',
    encoding="utf-8",
)
stdout, stderr = StringIO(), StringIO()
sys.stdout, sys.stderr = stdout, stderr
assert main(["validate", "sound.petrinet"]) == 0
assert stdout.getvalue() == "net\n"
stdout.seek(0)
stdout.truncate(0)
stderr.seek(0)
stderr.truncate(0)
assert main(["to-petrinet", "sound.petrinet"]) == 0
assert 'net sound "One transition"' in stdout.getvalue()
assert viz_main(["--legend"]) == 0
assert "digraph" in stdout.getvalue()
root = skill_root()
assert root.name == "skill"
assert root.parent.name == "velocitron_skill"
assert (root / "SKILL.md").is_file()
stdout.seek(0)
stdout.truncate(0)
dest = Path("skills-out")
dest.mkdir()
assert main(["skill", str(dest)]) == 0
assert (dest / "velocitron" / "SKILL.md").is_file()
assert "installed velocitron skill" in stdout.getvalue()
print("ok", file=sys.__stdout__)
"""


def test_wheel_install_validates_without_the_implementation(tmp_path: Path) -> None:
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
        _REPO_PACKAGES / "play" / "python",
        _REPO_PACKAGES / "play-check" / "python",
        _REPO_PACKAGES / "viz" / "python",
        _REPO_PACKAGES / "runtime" / "python",
        _REPO_PACKAGES / "analysis" / "python",
        _REPO_PACKAGES / "codegen" / "python",
        _REPO_PACKAGES / "explain" / "python",
        _REPO_PACKAGES / "equiv" / "python",
        _REPO_PACKAGES / "skill" / "python",
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
    # when: a fresh interpreter imports the installed package and validates
    checked = subprocess.run(
        [str(python), str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged dispatcher runs and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
