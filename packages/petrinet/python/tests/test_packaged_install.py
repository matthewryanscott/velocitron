"""A built wheel compiles .petrinet text without the monorepo checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPO_PACKAGES = _PROJECT_ROOT.parents[1]
_CHECK = """
import importlib.util

from velocitron_petrinet import compile_petrinet_text, parse_net
import velocitron_petrinet

assert importlib.util.find_spec("velocitron") is None
document = compile_petrinet_text(
    'net coin_deposit "Coin deposit"\\n\\n(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)\\n',
    "coin_deposit.petrinet",
)
assert document["name"] == "coin_deposit"
assert "places" in document
assert "contributions" not in document
assert parse_net(document).name == "coin_deposit"
assert not hasattr(velocitron_petrinet, "emit_petrinet")
print("ok")
"""


def test_wheel_install_compiles_without_the_implementation(tmp_path: Path) -> None:
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
        _REPO_PACKAGES / "cel" / "python",
        _REPO_PACKAGES / "dsl" / "python",
        _REPO_PACKAGES / "viz" / "python",
        _REPO_PACKAGES / "engine" / "python",
        _REPO_PACKAGES / "merge" / "python",
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
    # when: a fresh interpreter imports the installed package and compiles text
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged compiler returns a canonical net and does not import velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
