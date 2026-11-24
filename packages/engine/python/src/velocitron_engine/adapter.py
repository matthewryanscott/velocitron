"""CEL adapter boundary for the firing engine.

The engine calls ``compile`` then ``eval``. This package does not ship a
backend. Pass an adapter that implements this protocol. The language
implementation keeps its caching adapter and its default-backend selector.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CelAdapter(Protocol):
    """Compile + eval surface the engine calls.

    ``compile`` checks syntax. ``eval`` returns a host value. An evaluation
    error raises; the engine treats that as a false predicate or a failed
    produce fallback.
    """

    def compile(self, expr: str) -> Any:
        """Compile a CEL expression."""
        ...

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        """Evaluate ``compiled`` against ``data``."""
        ...
