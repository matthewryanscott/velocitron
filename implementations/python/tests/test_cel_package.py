"""The in-repo CEL package evaluates the same expressions as velocitron_cel."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

from velocitron_cel import (
    CachingCelAdapter,
    CelEvalError,
    CelpyAdapter,
    slow_backend_hint,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_SRC = str(_REPO_ROOT / "packages" / "cel" / "python" / "src")


def _package() -> Any:
    sys.path.insert(0, _PACKAGE_SRC)
    import velocitron_cel

    return velocitron_cel


def test_package_celpy_matches_the_implementation() -> None:
    # given: the source-tree velocitron-cel adapter and the implementation adapter
    velocitron_cel = _package()
    try:
        package = velocitron_cel.CelpyAdapter()
        implementation = CelpyAdapter()
        cases = [
            ("n >= 1", {"n": 1}),
            ("n >= 1", {"n": 0}),
            ("n + 1", {"n": 1}),
            ("a.b == 1", {"a": {"b": 1}}),
            (
                "{'kind': 'held', 'delivery': binding.pending[0].id, 'attempt': 1}",
                {"binding": {"pending": [{"id": "d-1"}]}},
            ),
            ("'hello'.matches('h.*')", {}),
        ]
        # when: both adapters evaluate the same expressions
        compared = [
            (
                package.eval(package.compile(expr), data),
                implementation.eval(implementation.compile(expr), data),
            )
            for expr, data in cases
        ]
        # then: the values agree, and the cache and hint live on velocitron_cel
        for package_value, implementation_value in compared:
            assert package_value == implementation_value
        assert velocitron_cel.CachingCelAdapter is CachingCelAdapter
        assert velocitron_cel.slow_backend_hint is slow_backend_hint
    finally:
        sys.path.remove(_PACKAGE_SRC)


def test_package_eval_errors_match_the_implementation() -> None:
    # given: a missing field on both adapters
    velocitron_cel = _package()
    try:
        package = velocitron_cel.CelpyAdapter()
        implementation = CelpyAdapter()

        def message(adapter: Any, error_type: type[BaseException]) -> str:
            try:
                adapter.eval(adapter.compile("missing.field"), {})
            except error_type as exc:
                return str(exc)
            raise AssertionError("missing field was accepted")

        def normalize(text: str) -> str:
            text = text.replace("velocitron_cel._vendor", "velocitron._vendor")
            return re.sub(r" at 0x[0-9a-fA-F]+", " at 0x0", text)

        # when: both evaluations fail
        package_message = message(package, velocitron_cel.CelEvalError)
        implementation_message = message(implementation, CelEvalError)
        # then: the failure text agrees once the vendored path and object ids are aligned
        assert normalize(package_message) == normalize(implementation_message)
        assert "undeclared reference to 'missing'" in package_message
    finally:
        sys.path.remove(_PACKAGE_SRC)
