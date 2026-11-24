"""A built wheel parses .petrinet text without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = _PROJECT_ROOT.parent / "fixtures"
_CHECK = """
import importlib.util
import sys

from velocitron_grammar import PetrinetParseError, grammar_text, parse_petrinet

assert importlib.util.find_spec("velocitron") is None
assert "grammar VelocitronPetriNet;" in grammar_text()
net = parse_petrinet(sys.argv[1], source_name="net.petrinet")
composition = parse_petrinet(sys.argv[2], source_name="composition.petrinet")
assert net.kind == "net"
assert net.name == "coin_deposit"
assert composition.kind == "composition"
assert composition.name == "wired_pulse"
assert not hasattr(net, "contributions")
try:
    parse_petrinet("sentinel")
except PetrinetParseError as error:
    assert error.line == 1 and error.column == 1
else:
    raise SystemExit("sentinel parsed")
print("ok")
"""


def test_wheel_install_parses_a_document_without_the_implementation(
    tmp_path: Path,
) -> None:
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
    # when: a fresh interpreter imports the installed package and parses fixtures
    checked = subprocess.run(
        [
            str(python),
            str(script),
            (_FIXTURES / "net.petrinet").read_text(encoding="utf-8"),
            (_FIXTURES / "composition.petrinet").read_text(encoding="utf-8"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged grammar parses a net and a composition, and not a sentinel
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
