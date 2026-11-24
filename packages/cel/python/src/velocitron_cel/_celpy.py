"""Import the bundled celpy on first use (ADR 0054).

celpy imports ``re2`` (the compiled ``google-re2`` package), and only uses it
for CEL's ``matches()``. ``google-re2`` has no wheel on some platforms, such as
32-bit and musl Linux, so the bundled copy falls back to
``velocitron_cel._re2_standin``, backed by Python's ``re``.
"""

from __future__ import annotations

import importlib
from types import ModuleType


def load_celpy() -> ModuleType:
    """The bundled ``celpy`` package."""
    return importlib.import_module("velocitron_cel._vendor.celpy")


def re2_standin_used() -> bool:
    """Whether celpy's ``matches()`` runs on Python's ``re`` in this process."""
    # Imported here so package init can import this module without a cycle.
    from velocitron_cel import _re2_standin

    evaluation = importlib.import_module("velocitron_cel._vendor.celpy.evaluation")
    return evaluation.re2 is _re2_standin
