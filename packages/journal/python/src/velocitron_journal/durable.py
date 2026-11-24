"""Durable sqlite event store and journal.

A :class:`DurableJournal` implements the engine ``Journal`` protocol and
appends each firing / injection to a sqlite event log. The engine calls the
hook synchronously during ``fire`` and ``inject_token``.
:func:`velocitron_journal.replay_events` rebuilds a marking from a recorded
log without invoking handlers: it applies each event's recorded token
effects — consume the recorded consume-mode inputs, deposit the recorded
outputs, apply injections. The state is the event log: replayed once into a
live marking at startup, never rebuilt while a process runs.

The handler-free replay machinery (:class:`~velocitron_journal.StoredEvent`,
the event-kind constants, :func:`~velocitron_journal.replay_events`) lives in
:mod:`velocitron_journal.journal`. It reads recorded effects, not sqlite.
The package root re-exports both. This module does not import ``velocitron``.

This realizes the **tape-replay** that ``spec/firing-semantics.md`` D5 defers as
a test convenience — advancing the net from recorded outputs without re-invoking
handlers. It is distinct from D5's replay-determinism contract (re-run the
engine with identical handlers and assert journal equality record-for-record):
tape-replay reconstructs a marking, it does not verify determinism.

The crash window — an external effect performed, its event row not yet written —
is the caller's concern, not this module's: a check-before-do handler re-fires on
resume and adopts the pre-existing effect. One monotonic ``seq`` per instance,
single-writer, WAL — many readers may replay concurrently.

References: spec/firing-semantics.md (D5); ADR 0022.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .journal import (
    DEPOSIT_VIOLATION,
    FIRING,
    INJECTION,
    NET_REVISION,
    TRACE,
    FiringRecord,
    InjectionRecord,
    StoredEvent,
    TraceRecord,
    replay_events,
    serialize_record_value,
)

__all__ = [
    "DEPOSIT_VIOLATION",
    "DurableJournal",
    "FIRING",
    "INJECTION",
    "NET_REVISION",
    "TRACE",
    "StoredEvent",
    "known_instances",
    "open_database",
    "read_events",
    "replay_events",
]


# ── The event store: schema and connection helpers ───────────────────────────


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    instance    TEXT    NOT NULL,
    seq         INTEGER NOT NULL,
    kind        TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    recorded_at TEXT    NOT NULL,
    PRIMARY KEY (instance, seq)
);
"""


def open_database(database_path: Path) -> sqlite3.Connection:
    """Open (creating if absent) the event-log database in WAL mode."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(_SCHEMA)
    connection.commit()
    return connection


def read_events(connection: sqlite3.Connection, instance: str) -> list[StoredEvent]:
    """Read one instance's events in sequence order, payloads decoded from JSON."""
    rows = connection.execute(
        "SELECT seq, kind, payload FROM events WHERE instance = ? ORDER BY seq",
        (instance,),
    ).fetchall()
    return [
        StoredEvent(row["seq"], row["kind"], json.loads(row["payload"])) for row in rows
    ]


def known_instances(connection: sqlite3.Connection) -> list[str]:
    """Every instance that has at least one recorded event."""
    rows = connection.execute(
        "SELECT DISTINCT instance FROM events ORDER BY instance"
    ).fetchall()
    return [row["instance"] for row in rows]


# ── The durable journal ──────────────────────────────────────────────────────



class DurableJournal:
    """A velocitron ``Journal`` that appends one instance's records to sqlite.

    Single-writer discipline: the owning process is the sole writer for its
    instance, and every record is committed as it is appended, so a kill between
    firings never loses a committed event. The instance name is caller-supplied
    and namespaces one net's log within a shared database.
    """

    def __init__(self, connection: sqlite3.Connection, instance: str) -> None:
        self._connection = connection
        self._instance = instance
        row = connection.execute(
            "SELECT MAX(seq) AS max_seq FROM events WHERE instance = ?", (instance,)
        ).fetchone()
        self._seq = 0 if row["max_seq"] is None else row["max_seq"] + 1

    def record_firing(self, record: FiringRecord) -> None:
        self._append(FIRING, record)

    def record_deposit_violation(self, record: FiringRecord) -> None:
        self._append(DEPOSIT_VIOLATION, record)

    def record_injection(self, record: InjectionRecord) -> None:
        self._append(INJECTION, record)

    def record_trace(self, record: TraceRecord) -> None:
        """Append a trace record (ADR 0058, Decision 6) to the event log.

        Stored with kind ``TRACE`` so readers can filter it; carries no
        marking effect, so :func:`replay_events` ignores it.
        """
        self._append(TRACE, record)

    def record_net_revision(self, net_document: dict[str, Any]) -> None:
        """Record a net-definition revision so the log is self-describing."""
        self._append(NET_REVISION, net_document)

    def _append(self, kind: str, record: Any) -> None:
        self._connection.execute(
            "INSERT INTO events(instance, seq, kind, payload, recorded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                self._instance,
                self._seq,
                kind,
                json.dumps(record, default=serialize_record_value),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._connection.commit()
        self._seq += 1

    def records(self) -> tuple[dict[str, Any], ...]:
        """Read back this instance's recorded events in numbering order.

        The same public read interface as :meth:`JsonlJournal.records`: a
        tuple of plain dict records, in ``seq`` order, each a fresh copy
        freshly decoded from its stored JSON payload. Durable rows carry the
        event vocabulary on columns, so each dict is the payload plus the
        record's ``kind``, ``sequence`` (from the ``seq`` column) and
        ``recorded_at`` timestamp.
        """
        rows = self._connection.execute(
            "SELECT seq, kind, payload, recorded_at FROM events "
            "WHERE instance = ? ORDER BY seq",
            (self._instance,),
        ).fetchall()
        return tuple(
            {
                **json.loads(row["payload"]),
                "kind": row["kind"],
                "sequence": row["seq"],
                "recorded_at": row["recorded_at"],
            }
            for row in rows
        )

