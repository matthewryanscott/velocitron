"""Durable-sqlite journal + tape replay: the sqlite log replays into a marking.

Drives a real Engine with a :class:`DurableJournal` over a temp sqlite file,
then reconstructs the marking with :func:`replay_events` (no handlers) and
asserts it equals the live marking — including at every crash-truncation point,
so a kill between firings loses nothing on reload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from velocitron_engine import (
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_journal import (
    DurableJournal,
    open_database,
    read_events,
    replay_events,
)
from velocitron_runtime import Engine
from velocitron_petrinet import parse_net
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
)

# ── A tiny two-step net: src -> [t1] -> mid -> [t2] -> dst ────────────────────

_FLOW_NET: Net = parse_net(
    {
        "name": "flow",
        "places": [
            {"name": "src", "accepts": ["task"]},
            {"name": "mid", "accepts": ["task"]},
            {"name": "dst", "accepts": ["task"]},
        ],
        "transitions": [
            {"name": "t1", "handler": "t1"},
            {"name": "t2", "handler": "t2"},
        ],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t1"},
                "consume": {"type": "task"},
            },
            {
                "from": {"transition": "t1"},
                "to": {"place": "mid"},
                "produce": {"type": "task", "destination": "mid"},
            },
            {
                "from": {"place": "mid"},
                "to": {"transition": "t2"},
                "consume": {"type": "task"},
            },
            {
                "from": {"transition": "t2"},
                "to": {"place": "dst"},
                "produce": {"type": "task", "destination": "dst"},
            },
        ],
    }
)


def _relay(destination: str):
    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        tokens = [tok for toks in inp["inputTokens"].values() for tok in toks]
        return {
            "status": "completed",
            "outputTokens": {destination: tokens},
            "error": None,
            "metadata": {},
        }

    return handler


def _registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register_transition("t1", _relay("mid"))
    registry.register_transition("t2", _relay("dst"))
    return registry


def _normalize(marking: Marking) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    normalized: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for place, tokens in marking.items():
        rendered = [(tok.type, tok.data) for tok in tokens]
        if rendered:
            normalized[place] = rendered
    return normalized


def _drive(engine: Engine) -> list[Marking]:
    """Fire a fixed firing/injection/firing sequence, returning the marking
    after each recorded event (event 0..4)."""
    net = _FLOW_NET
    marking = Marking({"src": [Token("task", {"id": "A"})]})
    after: list[Marking] = []
    # event 0/1: run the first task through both steps
    marking, _ = engine.fire(net, marking, "t1", attempt=0)
    after.append(marking)
    marking, _ = engine.fire(net, marking, "t2", attempt=1)
    after.append(marking)
    # event 2: a second task arrives from the environment
    marking, _ = engine.inject_token(
        net, marking, "src", Token("task", {"id": "B"}), attempt=2
    )
    after.append(marking)
    # event 3/4: run the injected task through both steps
    marking, _ = engine.fire(net, marking, "t1", attempt=3)
    after.append(marking)
    marking, _ = engine.fire(net, marking, "t2", attempt=4)
    after.append(marking)
    return after


def test_replay_reconstructs_live_final_marking(tmp_path: Path) -> None:
    # given: a net driven under an Engine with a DurableJournal on a temp sqlite file
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, instance="flow-1")
    engine = Engine(_registry(), journal=journal, deposit_violation="raise")

    # when: firing a full sequence that includes an injection, then replaying the log
    after = _drive(engine)
    live_final = after[-1]
    replayed = replay_events(_FLOW_NET, read_events(connection, "flow-1"))

    # then: the marking-effect events are five (two firings, an injection, two
    #       firings) — trace records (ADR 0058, Decision 6) share the log with
    #       kind "trace" and replay skips them, so read them out per kind.
    events = read_events(connection, "flow-1")
    assert [event.kind for event in events if event.kind != "trace"] == [
        "firing",
        "firing",
        "injection",
        "firing",
        "firing",
    ]
    # and: the replayed marking equals the live final marking (both tasks in dst)
    assert _normalize(replayed) == _normalize(live_final)
    assert _normalize(replayed) == {
        "dst": [("task", {"id": "A"}), ("task", {"id": "B"})]
    }


@pytest.mark.parametrize("crash_after", [1, 2, 3, 4])
def test_replay_of_truncated_log_equals_marking_at_that_point(
    tmp_path: Path, crash_after: int
) -> None:
    # given: a fully driven log and the live marking captured after each event
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, instance="flow-1")
    engine = Engine(_registry(), journal=journal, deposit_violation="raise")
    after = _drive(engine)

    # when: a crash truncates the log after `crash_after` marking-effect
    #       events (trace records carry no marking effect; they are skipped
    #       both by this prefix and by the live `_drive` bookkeeping) and we
    #       replay
    effect_events = [
        event
        for event in read_events(connection, "flow-1")
        if event.kind in ("firing", "injection")
    ]
    truncated = effect_events[:crash_after]
    replayed = replay_events(_FLOW_NET, truncated)

    # then: replay of the prefix equals the live marking after that many events
    #       (the injection at event index 2 is applied like any other effect)
    assert _normalize(replayed) == _normalize(after[crash_after - 1])


def test_net_revision_event_is_inert_on_replay(tmp_path: Path) -> None:
    # given: a journal that recorded a net-definition revision before any firing
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, instance="flow-1")
    journal.record_net_revision({"name": "flow", "revision": 1})
    engine = Engine(_registry(), journal=journal, deposit_violation="raise")

    # when: firing one task through and replaying the whole log
    marking = Marking({"src": [Token("task", {"id": "A"})]})
    marking, _ = engine.fire(_FLOW_NET, marking, "t1", attempt=0)
    live = marking
    replayed = replay_events(_FLOW_NET, read_events(connection, "flow-1"))

    # then: the net_revision event carries no marking effect — replay matches
    events = read_events(connection, "flow-1")
    assert events[0].kind == "net_revision"
    assert _normalize(replayed) == _normalize(live)


# ── records(): the public read interface (shared with JsonlJournal) ─────


def test_durable_records_returns_plain_dicts_in_numbering_order(tmp_path: Path) -> None:
    # given: a journal recording a net revision, a firing, and an injection
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, instance="flow-1")
    journal.record_net_revision({"name": "flow", "revision": 1})
    engine = Engine(_registry(), journal=journal, deposit_violation="raise")
    marking = Marking({"src": [Token("task", {"id": "A"})]})
    marking, _ = engine.inject_token(
        _FLOW_NET, marking, "src", Token("task", {"id": "B"}), attempt=1
    )
    engine.fire(_FLOW_NET, marking, "t1", attempt=2)

    # when: reading the records back through the public interface
    records = journal.records()

    # then: a tuple of plain dicts, one per event, in seq (numbering) order,
    #       each carrying the recorded payload plus kind/sequence/recorded_at
    assert isinstance(records, tuple)
    # (trace records share the seq stream; compare the marking-effect kinds)
    records = [r for r in records if r["kind"] != "trace"]
    # and: the marking-effect records keep one contiguous numbering stream in
    #      seq order (their absolute slots shift with interleaved trace rows,
    #      which carry no marking effect)
    assert [r["kind"] for r in records] == ["net_revision", "injection", "firing"]
    assert records[0]["name"] == "flow" and records[0]["revision"] == 1
    assert records[2]["transition"] == "t1"
    assert all(type(r) is dict and r["recorded_at"] for r in records)
    connection.close()


def test_durable_records_are_fresh_defensive_copies(tmp_path: Path) -> None:
    # given: a journal with one recorded firing
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, instance="flow-1")
    journal.record_firing(
        {
            "firingId": "flow/t1/0",
            "netId": "flow",
            "transition": "t1",
            "attempt": 0,
            "status": "completed",
            "inputTokens": {"src": []},
            "outputTokens": {},
            "error": None,
            "metadata": {},
            "timestamps": {"fired_at": "2026-01-01T00:00:00Z"},
        }
    )

    # when: reading twice, mutating the first read's copy between
    records = journal.records()
    records[0]["transition"] = "mutated"

    # then: the fresh read is unaffected — each read decodes fresh copies
    assert journal.records()[0]["transition"] == "t1"
    connection.close()
