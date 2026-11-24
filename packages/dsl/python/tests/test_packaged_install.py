"""A built wheel lowers .petrinet text without the monorepo checkout."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHECK = """
import importlib.util

from velocitron_dsl import PetrinetDslError, lower_petrinet_text

assert importlib.util.find_spec("velocitron") is None
assert importlib.util.find_spec("velocitron_grammar") is None
net = lower_petrinet_text(
    'net coin_deposit "Coin deposit"\\n\\n(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)\\n',
    "coin_deposit.petrinet",
)
assert net["format"] == "velocitron.petrinet/contribution-ir"
assert net["documentKind"] == "net"
assert net["contributions"][0]["value"]["name"] == "coin_deposit"
assert "places" not in net
assert "nets" not in net
composition = lower_petrinet_text(
    'composition wired_pulse\\n\\nuse "pulse_source.petrinet" as source\\n'
    'use "pulse_sink.petrinet" as sink\\n'
    "wire source.(pulse_out) -> sink.(pulse_in)\\n",
    "wired_pulse.petrinet",
)
assert composition["documentKind"] == "composition"
assert composition["contributions"][0]["value"]["namespace"] == "wired_pulse"
assert "nets" not in composition
try:
    lower_petrinet_text("net", "truncated.petrinet")
except PetrinetDslError as error:
    span = error.diagnostic.span.as_dict()
    assert span["start"] == {"byteOffset": 3, "line": 1, "column": 4}
else:
    raise SystemExit("truncated source lowered")
assert not hasattr(__import__("velocitron_dsl"), "resolve_contribution_ir")
print("ok")
"""


def test_wheel_install_lowers_a_document_without_the_implementation(
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
    viz = _PROJECT_ROOT.parents[1] / "viz" / "python"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(viz), str(wheel)],
        check=True,
        env=env,
    )
    script = tmp_path / "check.py"
    script.write_text(_CHECK, encoding="utf-8")
    # when: a fresh interpreter imports the installed package and lowers text
    checked = subprocess.run(
        [str(python), str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    # then: the packaged lowerer emits contribution IR and not a resolved document
    assert checked.returncode == 0, f"{checked.stdout}\n{checked.stderr}"
    assert checked.stdout.strip() == "ok"
