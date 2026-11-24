"""Replay a recorded run by driving ``Engine.fire`` from the journal tape.

:class:`ReplayCursor` reads one snapshot of a journal. :class:`ReplayBase`
answers handler calls from that tape and subclasses
:class:`velocitron_netbase.VelocitronNet`. :func:`replay_run` injects the
recorded arrivals and lets the engine fire between them.

The TypeScript package names this seam and does not replay a tape.
``velocitron_replay`` re-exports these names so generated ``Replay<Net>``
modules keep loading. This package does not import ``velocitron``.
"""

from __future__ import annotations

from .replay import (
    Divergence,
    ReplayBase,
    ReplayCursor,
    ReplayNetMismatch,
    ReplayOrderError,
    ReplayResult,
    replay_run,
)

__all__ = [
    "Divergence",
    "ReplayBase",
    "ReplayCursor",
    "ReplayNetMismatch",
    "ReplayOrderError",
    "ReplayResult",
    "replay_run",
]
