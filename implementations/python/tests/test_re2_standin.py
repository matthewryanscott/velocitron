"""celpy imports with a stand-in for re2 when google-re2 is missing (ADR 0054).

Each check runs in a fresh interpreter where ``import re2`` fails, since
celpy can be imported only once per process.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

HIDE_RE2 = (
    "import sys\nsys.modules['re2'] = None  # import re2 now raises ImportError\n"
)


def _run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", HIDE_RE2 + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_celpy_imports_with_the_stand_in_and_matches_uses_re():
    out = _run(
        """
        from velocitron_cel import re2_standin_used
        from velocitron_cel import CelpyAdapter
        adapter = CelpyAdapter()
        print(re2_standin_used())
        print(adapter.eval(adapter.compile("token.id.matches('^a[0-9]+$')"), {"token": {"id": "a12"}}))
        # A backreference: RE2 rejects it, Python's re accepts it.
        print(adapter.eval(adapter.compile("token.id.matches('(a)\\\\\\\\1')"), {"token": {"id": "aa"}}))
        print(sys.modules.get('re2'))
        """
    )
    assert out.split("\n")[:4] == ["True", "True", "True", "None"]


def test_a_bad_pattern_is_an_eval_error_with_the_stand_in():
    out = _run(
        """
        from velocitron_cel import CelEvalError, CelpyAdapter
        adapter = CelpyAdapter()
        try:
            adapter.eval(adapter.compile("token.id.matches('(')"), {"token": {"id": "a"}})
        except CelEvalError:
            print("error")
        """
    )
    assert out.strip() == "error"


def test_the_hint_says_that_matches_uses_re():
    out = _run(
        """
        from velocitron_cel import slow_backend_hint, CelpyAdapter
        print(slow_backend_hint(CelpyAdapter(), environ={}, wheel_available=False))
        """
    )
    assert "Python's re module" in out


def test_the_real_re2_is_used_when_it_imports():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "try:\n"
            "    import re2\n"
            "    real = True\n"
            "except ImportError:\n"
            "    real = False\n"
            "from velocitron_cel import load_celpy, re2_standin_used\n"
            "load_celpy()\n"
            "print(real != re2_standin_used())",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "True"


def test_an_engine_on_a_native_backend_never_imports_celpy():
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "from velocitron_cel import CelpyAdapter\n"
            "from velocitron_runtime import Engine\n"
            "from velocitron_engine import HandlerRegistry\n"
            "import velocitron_cli\n"
            "engine = Engine(HandlerRegistry())\n"
            "print(isinstance(engine._cel_adapter, CelpyAdapter), 'celpy' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if out[0] == "True":
        pytest.skip("only the celpy backend is installed")
    assert out[1] == "False"
