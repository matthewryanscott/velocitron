"""Append-only journal and handler-free replay to a marking.

The engine emits ``FiringRecord`` objects through the ``Journal`` protocol
and does not assign ``sequence``, pick storage, or require a journal.
``JsonlJournal`` is the default implementation. Sqlite durability lives in
:mod:`velocitron_journal.durable`. This module does not import ``velocitron``.

References: spec/firing-semantics.md (D4, D5).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from velocitron_engine import (
    DEPOSIT_VIOLATION,
    FIRING,
    FiringRecord,
    FiringStatus,
    INJECTION,
    InjectionKind,
    InjectionRecord,
    Journal,
    Marking,
    NET_REVISION,
    Net,
    RuntimeEvent,
    RuntimeJournal,
    RuntimeRecord,
    TRACE,
    Token,
    TraceEvent,
    TraceJournal,
    TraceRecord,
)

__all__ = [
    "DEPOSIT_VIOLATION",
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
    "TRACE",
    "TraceEvent",
    "TraceJournal",
    "TraceRecord",
    "StoredEvent",
    "replay_events",
    "replay_records",
    "serialize_record_value",
]


# ── Record serialization (the single vocabulary for ALL journals) ────────


def serialize_record_value(obj: Any) -> Any:
    """The record-payload serializer shared by every journal implementation.

    One vocabulary, one failure mode: a :class:`~velocitron_engine.Token`
    serializes to ``{"type": ..., "data": ...}`` so it round-trips
    through ``json.dumps``/``json.loads``; any other dataclass instance falls
    back to ``dataclasses.asdict``; anything else raises ``TypeError`` rather
    than being silently degraded to ``repr`` — a payload that cannot be
    replayed must fail loudly, not masquerade as data.

    Both :class:`JsonlJournal` (JSONL lines) and
    :class:`DurableJournal` (SQL rows) pass this as ``json.dumps(default=...)``,
    so record payloads carry the same vocabulary regardless of backend.
    """
    if isinstance(obj, Token):
        return {"type": obj.type, "data": obj.data}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    raise TypeError(f"cannot serialize {type(obj)!r} into a record payload")


# ── JsonlJournal — the default implementation ────────────────────────────


class JsonlJournal:
    """The default journal: appends each record to a timestamped ``.jsonl`` file.

    The journal assigns each record a monotonic 0-based ``sequence`` itself.
    With ``prefix=None`` (the default) records accumulate in memory only and
    nothing is written to disk; ``flush`` is a no-op. With ``prefix`` set,
    ``flush`` writes all buffered records to
    ``f"{prefix}-{ISO8601_UTC}.jsonl"``, one JSON object per line.

    Reading back uses the public :meth:`records` interface, shared with
    :class:`~velocitron_journal.DurableJournal`.
    """

    def __init__(self, prefix: str | None = None) -> None:
        self._prefix = prefix
        self._records: list[dict[str, Any]] = []
        self._sequence = 0

    def record_firing(self, record: FiringRecord) -> None:
        """Append a firing record, assigning the next monotonic sequence."""
        self._append(record)

    def record_deposit_violation(self, record: FiringRecord) -> None:
        """Append a deposit-violation record, assigning the next sequence.

        Same numbering stream as ``record_firing`` — both are firings.
        """
        self._append(record)

    def record_injection(self, record: InjectionRecord) -> None:
        """Append a token-injection record, assigning the next sequence.

        Same monotonic numbering stream as ``record_firing`` — so a firing and
        an interleaved injection (any environment arrival) occupy consecutive
        sequence slots, and replay across injected tokens is deterministic.
        """
        self._append(record)

    def record_runtime(self, record: RuntimeRecord) -> None:
        """Append a Runtime lifecycle event in the shared sequence stream."""
        self._append(record)

    def record_trace(self, record: TraceRecord) -> None:
        """Append a trace record in the shared monotonic sequence stream."""
        self._append(record)

    def record_net_revision(self, net_document: dict[str, Any]) -> None:
        """Record a net-definition revision so the log is self-describing.

        Appended to the same shared sequence stream as every other record:
        the stored record IS the net document's own keys (plus the journal's
        ``sequence``), so a JSONL line carries the document itself with no
        wrapper. Replay's cursor identifies the record by the document's key
        shape — the ``net_revision`` channel name is a durable-log column,
        not a JSONL record key — so the JSONL format changes nothing.
        """
        self._append(net_document)  # type: ignore[arg-type]

    def _append(
        self, record: FiringRecord | InjectionRecord | RuntimeRecord | TraceRecord
    ) -> None:
        """Buffer a record with the next monotonic 0-based ``sequence``."""
        rec = {**record, "sequence": self._sequence}
        self._sequence += 1
        self._records.append(rec)

    def records(self) -> tuple[dict[str, Any], ...]:
        """Read back every buffered record in numbering order.

        Returns a tuple of plain dict records (the journal's own vocabulary —
        ``sequence``, ``timestamps`` and all), each a fresh shallow copy so
        callers cannot mutate the journal's buffer. Record payloads are
        serialized later, at ``flush`` time, via
        :func:`serialize_record_value` — the one vocabulary shared with
        :class:`DurableJournal`.
        """
        return tuple(dict(record) for record in self._records)

    def flush(self) -> None:
        """Write all buffered records to a timestamped ``.jsonl`` file.

        No-op when no ``prefix`` was given. Creates parent directories as
        needed. Each record is one
        ``json.dumps(rec, default=serialize_record_value)`` line.
        """
        if self._prefix is None:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = Path(f"{self._prefix}-{stamp}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for rec in self._records:
                fh.write(json.dumps(rec, default=serialize_record_value))
                fh.write("\n")


# ── Handler-free tape replay (moved from durable_sqlite, ADR 0022) ───────


@dataclasses.dataclass(frozen=True)
class StoredEvent:
    """One decoded row of an event log, in sequence order for one instance.

    The vocabulary :func:`replay_events` folds into a marking — recorded by
    :class:`DurableJournal` rows or handed to :func:`replay_records` as plain
    dicts. sqlite is not implied: an event is a payload dictionary plus its
    channel kind and monotonic sequence number.
    """

    seq: int
    kind: str
    payload: Mapping[str, Any]


def _token(token_dict: dict[str, Any]) -> Token:
    if isinstance(token_dict, Token):
        return token_dict
    return Token(type=token_dict["type"], data=token_dict["data"])


def _consume_sources(net: Net) -> dict[str, set[str]]:
    """Map each transition to the source places it consumes (not read/inhibit).

    A firing record's ``inputTokens`` includes read-arc tokens (they bind but are
    not removed), so replay must consult the net to remove only consume-mode
    inputs — otherwise a read clock token would be wrongly consumed.
    """
    sources: dict[str, set[str]] = {}
    for arc in net.arcs:
        if (
            arc.to_transition is not None
            and arc.from_place is not None
            and arc.consume is not None
            and arc.consume.mode == "consume"
        ):
            sources.setdefault(arc.to_transition, set()).add(arc.from_place)
    return sources


def _remove_tokens(
    marking: Marking, place: str, token_dicts: list[dict[str, Any]]
) -> Marking:
    remaining = list(marking.get(place, []))
    for token_dict in token_dicts:
        target = _token(token_dict)
        for index, existing in enumerate(remaining):
            if existing == target:
                del remaining[index]
                break
    return marking.set(place, remaining)


def _append_tokens(marking: Marking, place: str, tokens: Iterable[Token]) -> Marking:
    return marking.set(place, [*marking.get(place, []), *tokens])


def _replay_event(
    marking: Marking, consume_sources: dict[str, set[str]], event: StoredEvent
) -> Marking:
    """One recorded event's marking effect (or none) on ``marking``."""
    if event.kind == FIRING:
        record = event.payload
        if record.get("status") != "completed":
            return marking
        sources = consume_sources.get(record["transition"], set())
        for place, token_dicts in record["inputTokens"].items():
            if place in sources:
                marking = _remove_tokens(marking, place, token_dicts)
        for place, token_dicts in record["outputTokens"].items():
            marking = _append_tokens(marking, place, [_token(t) for t in token_dicts])
    elif event.kind == INJECTION:
        record = event.payload
        tokens = [_token(t) for t in record["tokens"]]
        if record["kind"] == "update":
            marking = marking.set(record["place"], tokens)
        else:
            marking = _append_tokens(marking, record["place"], tokens)
    # DEPOSIT_VIOLATION and NET_REVISION carry no marking effect. TRACE
    # (ADR 0058, Decision 6) is a timing/observability record — also no
    # marking effect, so replay skips it the same way.
    return marking


def replay_events(
    net: Net,
    events: Iterable[StoredEvent],
    *,
    initial: Marking | None = None,
) -> Marking:
    """Rebuild a marking by applying recorded event effects, invoking no handlers.

    No sqlite implied: ``events`` is any iterable of :class:`StoredEvent` —
    the decoded rows of a durable log (:func:`read_events`) or records
    converted by :func:`replay_records`.

    With ``initial`` the rebuild starts from that marking instead of the
    net's declared initial one — a play step replays its own records from
    its ``before`` marking this way (one marking per record, ADR 0060's
    advance).

    Realizes the **tape-replay** that ``spec/firing-semantics.md`` D5 defers
    as a test convenience — advancing the net from recorded outputs without
    re-invoking handlers. The state IS the event log: replayed once into a
    live marking at startup, never rebuilt while a process runs.

    References: spec/firing-semantics.md (D5); ADR 0022.
    """
    marking = initial if initial is not None else net.initial_marking or Marking()
    consume_sources = _consume_sources(net)
    for event in events:
        marking = _replay_event(marking, consume_sources, event)
    return marking


def replay_records(net: Net, records: Iterable[Mapping[str, Any]]) -> Marking:
    """Rebuild a marking directly from journal records, invoking no handlers.

    The journal-record view of :func:`replay_events`: takes the plain dicts
    :meth:`JsonlJournal.records` / :meth:`DurableJournal.records` read back
    (an engine-emitted ``FiringRecord`` / ``InjectionRecord`` TypedDict, or a
    decoded JSONL line / durable row with the journal's own metadata keys —
    ``sequence``, ``kind``, ``recorded_at`` — which are ignored), classifies
    each by its keys the same way the run-replay cursor does, and applies
    the recorded token effects.

    References: spec/firing-semantics.md (D4, D5); ADR 0022.
    """
    events: list[StoredEvent] = []
    for record in records:
        if "event" in record:
            kind = TRACE
        elif "injectionId" in record:
            kind = INJECTION
        elif "firingId" in record:
            kind = FIRING
        else:
            kind = NET_REVISION
        # ``kind`` is journal metadata on a decoded line / durable row — but
        # the record body itself may also carry ``kind``: an
        # ``InjectionRecord`` distinguishes ``"inject"`` / ``"update"`` and
        # :func:`_replay_event` reads it. Drop the key only when it names the
        # journal channel; for an injection, keep or restore the record's own
        # kind (a decoded durable row carries the channel name in ``kind`` and
        # loses the original, so read it from ``replaced``, which only an
        # ``update`` fills — the same rule the play records use).
        if kind == INJECTION:
            own_kind = record.get("kind")
            if own_kind not in ("inject", "update"):
                own_kind = "update" if record.get("replaced") else "inject"
            payload = {
                key: value
                for key, value in record.items()
                if key not in ("sequence", "recorded_at")
            }
            payload["kind"] = own_kind
        else:
            payload = {
                key: value
                for key, value in record.items()
                if key not in ("kind", "sequence", "recorded_at")
            }
        raw_sequence = payload.get("sequence", 0)
        sequence = (
            raw_sequence
            if isinstance(raw_sequence, int) and not isinstance(raw_sequence, bool)
            else 0
        )
        events.append(StoredEvent(sequence, kind, payload))
    return replay_events(net, events)
