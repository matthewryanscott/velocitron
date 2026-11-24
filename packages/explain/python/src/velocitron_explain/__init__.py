"""Human-readable account of a validated net.

:func:`explain_net` quotes places, transitions, and arcs. Given a marking,
it asks :meth:`velocitron_engine.Engine.explain_enablement` and passes
:func:`velocitron_cel.get_default_adapter`, because that engine requires an
injected CEL adapter. No handler runs.

``velocitron_cli`` installs this function as the ``velocitron explain``
hook. The TypeScript package names
``explainNet`` and does not render prose. This package does not import
``velocitron``.
"""

from __future__ import annotations

from .explain import explain_net

__all__ = ["explain_net"]
