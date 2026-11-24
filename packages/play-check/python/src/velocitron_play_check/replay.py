"""Marking fold for one play step's records.

Journal durability and ``replay_events`` ship in ``velocitron_journal``.
A checked step still needs the marking after each of its own records, and
that fold must match the journal tape for firing and injection (D5). This
module is that fold. It does not store a journal and it does not import
``velocitron`` or ``velocitron_journal``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from velocitron_engine import FIRING, INJECTION, Marking, Net, Token


@dataclass(frozen=True)
class StoredEvent:
    """One firing or injection payload, plus its channel kind."""

    seq: int
    kind: str
    payload: Mapping[str, Any]


def _token(token_dict: Any) -> Token:
    if isinstance(token_dict, Token):
        return token_dict
    return Token(type=token_dict["type"], data=token_dict["data"])


def _consume_sources(net: Net) -> dict[str, set[str]]:
    """Map each transition to the source places it consumes (not read/inhibit)."""
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


def _remove_tokens(marking: Marking, place: str, token_dicts: Sequence[Any]) -> Marking:
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
            marking = _append_tokens(marking, place, [_token(token) for token in token_dicts])
    elif event.kind == INJECTION:
        record = event.payload
        tokens = [_token(token) for token in record["tokens"]]
        if record["kind"] == "update":
            marking = marking.set(record["place"], tokens)
        else:
            marking = _append_tokens(marking, record["place"], tokens)
    return marking


def replay_events(
    net: Net,
    events: Iterable[StoredEvent],
    *,
    initial: Marking | None = None,
) -> Marking:
    """Rebuild a marking by applying recorded firing and injection effects.

    With ``initial`` the rebuild starts from that marking instead of the
    net's declared initial one. No handlers run.
    """
    marking = initial if initial is not None else net.initial_marking or Marking()
    consume_sources = _consume_sources(net)
    for event in events:
        marking = _replay_event(marking, consume_sources, event)
    return marking


def markings_after_records(
    net: Net,
    before: Marking,
    records: Sequence[Mapping[str, Any]],
) -> tuple[Marking, ...]:
    """One marking per record, each replayed from ``before`` through that record."""
    markings: list[Marking] = []
    for position in range(len(records)):
        events = [
            StoredEvent(
                earlier_index,
                FIRING if "firingId" in earlier else INJECTION,
                earlier,
            )
            for earlier_index, earlier in enumerate(records[: position + 1])
        ]
        markings.append(replay_events(net, events, initial=before))
    return tuple(markings)
