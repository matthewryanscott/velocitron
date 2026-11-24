"""Run a net asynchronously and evaluate intended waits.

``Runtime`` reserves consume-mode inputs, runs the transition's handler,
and settles the reservation. It injects a :class:`~velocitron_engine.HandlerRegistry`
for guards, predicates, and firing policy. It does not call ``Engine.fire``.

``intended_waits`` reads a transition's ``wait`` annotation. The engine
ignores that annotation. Pass a CEL adapter, or let the call use
``get_default_adapter``.

``Engine`` is ``velocitron_engine.Engine`` with ``cel_adapter`` defaulting
to ``get_default_adapter()``. Pass an adapter to select a backend. The
firing core stays in ``velocitron_engine`` and still requires one.

Journal storage stays in ``velocitron_journal``. Engine-driven tape replay
(``ReplayCursor``, ``replay_run``) lives in ``velocitron_replay``. This
package does not import ``velocitron``.
"""

from __future__ import annotations

from .default_engine import Engine
from .runtime import (
    AsyncTransitionHandler,
    Cancellation,
    Clock,
    HandlerSpec,
    Lane,
    Runtime,
    RuntimeContext,
    ScopeResolver,
    SourceFactory,
    SourceHealth,
    SourceItem,
    SourcePolicy,
    TokenArrival,
    TokenBatch,
    TokenSource,
)
from .waits import KEY, Wait, holds, intended_waits, wait_problems

__all__ = [
    "KEY",
    "AsyncTransitionHandler",
    "Cancellation",
    "Clock",
    "Engine",
    "HandlerSpec",
    "Lane",
    "Runtime",
    "RuntimeContext",
    "ScopeResolver",
    "SourceFactory",
    "SourceHealth",
    "SourceItem",
    "SourcePolicy",
    "TokenArrival",
    "TokenBatch",
    "TokenSource",
    "Wait",
    "holds",
    "intended_waits",
    "wait_problems",
]
