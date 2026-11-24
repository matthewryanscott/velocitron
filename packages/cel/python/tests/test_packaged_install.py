"""A built wheel evaluates CEL without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util

from velocitron_cel import (
    CelEvalError,
    CelExprAdapter,
    CelRustAdapter,
    get_default_adapter,
)

assert importlib.util.find_spec("velocitron") is None
adapter = get_default_adapter()
assert type(adapter).__name__ == "CelpyAdapter"
assert adapter.eval(adapter.compile("n + 1"), {"n": 1}) == 2
assert adapter.eval(adapter.compile("a.b == 1"), {"a": {"b": 1}}) is True
try:
    adapter.compile("> > >")
except Exception:
    pass
else:
    raise SystemExit("syntax accepted")
try:
    adapter.eval(adapter.compile("missing.field"), {})
except CelEvalError:
    pass
else:
    raise SystemExit("missing field accepted")
CelExprAdapter()
CelRustAdapter()
from velocitron_cel import CachingCelAdapter, slow_backend_hint
assert CachingCelAdapter.__name__ == "CachingCelAdapter"
assert callable(slow_backend_hint)
print("ok")
"""


def test_wheel_install_evaluates_without_the_implementation(tmp_path: Path) -> None:
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
    # when: a fresh interpreter imports the installed package and evaluates CEL
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the wheel evaluates with bundled celpy and does not include velocitron
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
