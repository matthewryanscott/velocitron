"""CEL result cache and the CLI note about the slow celpy backend.

``CachingCelAdapter`` keeps each result per expression and activation.
``slow_backend_hint`` is the note ``velocitron`` prints when CEL is on
celpy. Both live in this package.
"""

from __future__ import annotations

import json
import os
import platform
import struct
import sys
import sysconfig
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

__all__ = [
    "CachingCelAdapter",
    "NO_CEL_WARNING_ENV",
    "interpreter_machine",
    "rust_wheel_available",
    "slow_backend_hint",
]


class CachingCelAdapter:
    """Wraps an adapter and keeps each result per expression and activation.

    The wrapper matches :class:`velocitron_cel.CelAdapter`: ``compile`` and
    ``eval``. It does not subclass that protocol, so importing this module
    does not cycle through the package root.

    A CEL result depends only on the expression and the values it is given.
    Token data is JSON, so the activation's sorted JSON text identifies its
    values; an activation that is not JSON is evaluated without the cache.
    An eval error is kept too and raised again as a new ``CelEvalError``.
    A container result is copied on every return, so no caller can change
    the kept one. The cache is cleared when it holds ``limit`` results.
    """

    def __init__(self, inner: Any, limit: int = 100_000) -> None:
        self._inner = inner
        self._limit = limit
        self._results: dict[tuple[int, str], tuple[Any, bool, Any]] = {}

    def compile(self, expr: str) -> Any:
        return self._inner.compile(expr)

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        from velocitron_cel import CelEvalError

        try:
            text = json.dumps(data, sort_keys=True)
        except (TypeError, ValueError):
            return self._inner.eval(compiled, data)
        key = (id(compiled), text)
        found = self._results.get(key)
        # The entry holds the compiled expression, so its id is not reused
        # while the entry lives.
        if found is None or found[0] is not compiled:
            try:
                found = (compiled, True, self._inner.eval(compiled, data))
            except CelEvalError as error:
                found = (compiled, False, str(error))
            if len(self._results) >= self._limit:
                self._results.clear()
            self._results[key] = found
        _, ok, value = found
        if not ok:
            raise CelEvalError(value)
        return deepcopy(value) if isinstance(value, (dict, list)) else value  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


NO_CEL_WARNING_ENV = "VELOCITRON_NO_CEL_WARNING"

# The platforms `common-expression-language` 0.10.0 publishes CPython wheels
# for (PyPI, checked 2026-10-20), as (system, machine) of the interpreter.
# There are none for musl Linux, 32-bit Windows or Windows on ARM. Free-threaded
# wheels exist for Linux only, from 3.14. `tools/cel_rust_wheels.py` prints the
# current list from PyPI; update the table when it changes (ADR 0053).
_RUST_WHEEL_MACHINES = {
    "Darwin": {"x86_64", "arm64"},
    "Linux": {"x86_64", "aarch64", "armv7l", "ppc64le", "s390x", "i686"},
    "Windows": {"AMD64"},
}
_RUST_WHEEL_MACHINES_315 = {"Linux": {"x86_64", "i686"}}


def rust_wheel_available(
    system: str,
    machine: str,
    version: tuple[int, int],
    implementation: str = "CPython",
    libc: str = "glibc",
    free_threaded: bool = False,
) -> bool:
    """Whether pip can install the Rust backend from a wheel for this
    interpreter. ``machine`` is the interpreter's: ``i686`` for 32-bit
    Python on an x86_64 kernel, ``win32`` for 32-bit Python on Windows."""
    if implementation != "CPython":
        return False
    if system == "Linux" and libc != "glibc":
        return False
    if free_threaded and (system != "Linux" or version < (3, 14)):
        return False
    if (3, 11) <= version <= (3, 14):
        table = _RUST_WHEEL_MACHINES
    elif version == (3, 15):
        table = _RUST_WHEEL_MACHINES_315
    else:
        return False
    return machine in table.get(system, set())


def interpreter_machine(system: str, machine: str, bits: int) -> str:
    """The machine a wheel must be built for: a 32-bit interpreter on a
    64-bit kernel needs a 32-bit wheel, and ``platform.machine()`` names the
    kernel's."""
    if bits == 64:
        return machine
    if system == "Windows":
        return "win32"
    if machine in {"x86_64", "i386", "i586", "i686"}:
        return "i686"
    if machine in {"aarch64", "armv8l", "armv7l"}:
        return "armv7l"
    return machine


def _this_platform_has_rust_wheel() -> bool:
    system = platform.system()
    return rust_wheel_available(
        system,
        interpreter_machine(system, platform.machine(), struct.calcsize("P") * 8),
        sys.version_info[:2],
        platform.python_implementation(),
        platform.libc_ver()[0],
        bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    )


def slow_backend_hint(
    adapter: Any | None = None,
    environ: Mapping[str, str] | None = None,
    wheel_available: bool | None = None,
    re2_standin: bool | None = None,
    suggest_rust: bool = True,
) -> str | None:
    """A note for the CLI user about the cel-python backend, or None.

    It says that the Rust backend is faster, when ``suggest_rust`` is set
    and a Rust wheel exists for this platform, and that ``matches()`` follows Python's regex rules, when
    the ``re2`` stand-in is in use (ADR 0054). None when another backend is
    in use, when neither applies, or when ``VELOCITRON_NO_CEL_WARNING`` is
    set to a non-empty value.
    """
    from velocitron_cel import CelpyAdapter, get_default_adapter, re2_standin_used

    environ = os.environ if environ is None else environ
    if environ.get(NO_CEL_WARNING_ENV):
        return None
    adapter = get_default_adapter() if adapter is None else adapter
    if not isinstance(adapter, CelpyAdapter):
        return None
    if not suggest_rust:
        wheel_available = False
    elif wheel_available is None:
        wheel_available = _this_platform_has_rust_wheel()
    if re2_standin is None:
        re2_standin = re2_standin_used()
    lines: list[str] = []
    if wheel_available:
        lines += [
            "velocitron: CEL runs on the cel-python backend. The optional Rust "
            "backend evaluates CEL several times faster. Install it with:",
            "  pip install 'velocitron-cel[cel-rust]'",
            "  uv tool install --force 'velocitron-cli[cel-rust]'   (for a uv tool install)",
        ]
    if re2_standin:
        lines += [
            "velocitron: google-re2 is not installed, so CEL matches() uses "
            "Python's re module: it accepts backreferences and lookaround that "
            "RE2 rejects, and it does not promise linear time.",
        ]
    if not lines:
        return None
    lines.append(f"Set {NO_CEL_WARNING_ENV}=1 to hide this note.")
    return "\n".join(lines) + "\n"
