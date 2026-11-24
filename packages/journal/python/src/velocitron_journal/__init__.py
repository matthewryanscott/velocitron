"""Append, read, and replay a Velocitron journal.

``JsonlJournal`` buffers records in memory and can flush them as JSONL.
``DurableJournal`` appends the same records to sqlite. ``replay_events`` and
``replay_records`` rebuild a marking from those records without calling
handlers.

Record shapes (``FiringRecord``, ``InjectionRecord``, and the kind
constants) come from ``velocitron_engine``. This package does not fire a
net, run the async runtime, or import ``velocitron``.
"""

from __future__ import annotations

from .durable import DurableJournal, known_instances, open_database, read_events
from .journal import (
    DEPOSIT_VIOLATION,
    FIRING,
    INJECTION,
    NET_REVISION,
    TRACE,
    FiringRecord,
    FiringStatus,
    InjectionKind,
    InjectionRecord,
    Journal,
    JsonlJournal,
    RuntimeEvent,
    RuntimeJournal,
    RuntimeRecord,
    StoredEvent,
    TraceEvent,
    TraceJournal,
    TraceRecord,
    replay_events,
    replay_records,
    serialize_record_value,
)

__all__ = [
    "DEPOSIT_VIOLATION",
    "DurableJournal",
    "FIRING",
    "FiringRecord",
    "FiringStatus",
    "INJECTION",
    "InjectionKind",
    "InjectionRecord",
    "Journal",
    "JsonlJournal",
    "NET_REVISION",
    "RuntimeEvent",
    "RuntimeJournal",
    "RuntimeRecord",
    "StoredEvent",
    "TRACE",
    "TraceEvent",
    "TraceJournal",
    "TraceRecord",
    "known_instances",
    "open_database",
    "read_events",
    "replay_events",
    "replay_records",
    "serialize_record_value",
]
