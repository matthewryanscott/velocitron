"""Shared journal fixtures: make/parametrize helpers for BOTH journals.

One fixture module so a single ``_CapturingJournal`` stub serves every test
that only needs to capture emitted records (previously each test file carried
its own copy), alongside the two real journal backends:

- ``make_jsonl`` — an in-memory :class:`JsonlJournal` (``prefix=None``), which
  numbers records itself (monotonic 0-based ``sequence``) and writes nothing.
- ``make_durable`` — a :class:`DurableJournal` over a temp sqlite database;
  returns the journal and its connection so callers can close or read the log.
- ``journal_makers`` / ``JOURNAL_MAKER_IDS`` — a parametrize helper driving one
  test over both real backends.

Reading records back tests the PUBLIC ``records()`` interface, never a private
buffer attribute. Mirrors ``_cel_adapters.py``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from velocitron_journal import (
    DurableJournal,
    open_database,
)
from velocitron_journal import (
    FiringRecord,
    InjectionRecord,
    JsonlJournal,
    TraceRecord,
)


# ── The one capturing stub ───────────────────────────────────────────────


class CapturingJournal:
    """In-memory Journal capturing records, assigning no ``sequence`` (D4).

    A hook-level stub storing exactly what the engine hands over, per channel
    (``firings``, ``violations``, ``injections``, ``traces``), without
    numbering — unlike
    :class:`JsonlJournal`, which is itself a capturing journal WITH numbering.
    For tests asserting captured-record content only, this isolates the hook
    contract from the numbering contract. Each stored record is a fresh copy.
    """

    def __init__(self) -> None:
        self.firings: list[FiringRecord] = []
        self.violations: list[FiringRecord] = []
        self.injections: list[InjectionRecord] = []
        self.traces: list[TraceRecord] = []

    def record_firing(self, record: FiringRecord) -> None:
        self.firings.append({**record})

    def record_deposit_violation(self, record: FiringRecord) -> None:
        self.violations.append({**record})

    def record_injection(self, record: InjectionRecord) -> None:
        self.injections.append({**record})

    def record_trace(self, record: TraceRecord) -> None:
        self.traces.append({**record})


def make_capturing() -> CapturingJournal:
    """A fresh capturing stub per test (or per journal slot)."""
    return CapturingJournal()


# ── The two real backends ────────────────────────────────────────────────


def make_jsonl(prefix: str | None = None) -> JsonlJournal:
    """An in-memory :class:`JsonlJournal` (records buffered, nothing written)."""
    return JsonlJournal(prefix=prefix)


def make_durable(
    tmp_path: Path,
) -> tuple[DurableJournal, sqlite3.Connection]:
    """A :class:`DurableJournal` over a temp sqlite file plus its connection.

    One journal per database file under ``tmp_path``, instance
    ``"test-instance"``. The caller owns (and may close) the connection.
    """
    connection = open_database(tmp_path / "journal-events.db")
    return DurableJournal(connection, instance="test-instance"), connection


# ── Parametrize helper: one test, both real backends ─────────────────────


def journal_makers(
    tmp_path: Path,
) -> list[tuple[str, Callable[[], JsonlJournal | DurableJournal]]]:
    """``(id, maker)`` pairs for parametrizing a test over both journals.

    Each ``maker`` is a zero-argument callable building a fresh journal of the
    named backend. Usage::

        @pytest.mark.parametrize("journal_id, maker", journal_makers(tmp_path),
                                 ids=[j for j, _ in journal_makers(tmp_path)])
        def test_...(journal_id, maker): ...

    (Helper re-computation is fine; the file is a temp path local to a test.)
    """

    def durable() -> DurableJournal:
        journal, _connection = make_durable(tmp_path)
        return journal

    return [
        ("jsonl", lambda: make_jsonl()),
        ("durable", durable),
    ]


JOURNAL_MAKER_IDS = ["jsonl", "durable"]

__all__ = [
    "JOURNAL_MAKER_IDS",
    "CapturingJournal",
    "make_capturing",
    "make_durable",
    "make_jsonl",
    "journal_makers",
]
