"""Sync engine wired to the default CEL adapter.

``velocitron_engine.Engine`` requires ``cel_adapter``. This subclass fills
``get_default_adapter()`` when the caller omits one. Pass ``cel_adapter``
to select a backend. The firing core stays in ``velocitron_engine``.
"""

from __future__ import annotations

from velocitron_cel import get_default_adapter
from velocitron_engine import DEFAULT_FIRING_POLICY, CelAdapter, HandlerRegistry, Journal
from velocitron_engine import Engine as PackageEngine

__all__ = ["Engine"]


class Engine(PackageEngine):
    """``velocitron_engine.Engine`` with ``get_default_adapter()`` as the default."""

    def __init__(
        self,
        registry: HandlerRegistry,
        *,
        policy: str = DEFAULT_FIRING_POLICY,
        journal: Journal | None = None,
        deposit_violation: str = "raise",
        cel_adapter: CelAdapter | None = None,
        max_consecutive_failures: int | None = None,
    ) -> None:
        super().__init__(
            registry,
            policy=policy,
            journal=journal,
            deposit_violation=deposit_violation,
            cel_adapter=(
                cel_adapter if cel_adapter is not None else get_default_adapter()
            ),
            max_consecutive_failures=max_consecutive_failures,
        )
