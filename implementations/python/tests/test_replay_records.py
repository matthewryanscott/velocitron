from __future__ import annotations

"""Replay from records with injection records present (issue: `replay_records`
dropped every record's ``kind``, so an injection record's own
``"inject"`` / ``"update"`` kind was lost and `_replay_event` raised
``KeyError: 'kind'``).

Rebuilds ``[inject, fire, update]`` records through ``replay_records`` and
compares against ``replay_events`` with each record wrapped as a
``StoredEvent`` on its journal channel, plus the decoded-durable-row shape
where ``kind`` already holds the channel name (``"injection"``) and the
record's own kind must come back from ``replaced``.

References: spec/firing-semantics.md (D4, D5); ADR 0022.
"""

from typing import Any

from velocitron_engine import (
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_runtime import Engine
from velocitron_journal import (
    StoredEvent,
    replay_events,
    replay_records,
)
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Arc,
    ConsumePattern,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
)


def _completed_firing_record(
    seq: int,
    net_name: str,
    transition: str,
    inputs: dict[str, list[Token]],
    outputs: dict[str, list[Token]],
) -> dict[str, Any]:
    return {
        "sequence": seq,
        "kind": "firing",
        "firingId": f"{net_name}/{transition}/0",
        "netId": net_name,
        "transition": transition,
        "attempt": 0,
        "status": "completed",
        "inputTokens": inputs,
        "outputTokens": outputs,
        "guardChecked": False,
    }


def _work_handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    return {
        "status": "completed",
        "outputTokens": {
            "out": list(inp["inputTokens"]["in"])
        },
        "error": None,
        "metadata": {},
    }


def _records(net: Net) -> list[dict[str, Any]]:
    """Drive an Engine on ``net``: inject, fire, then update the clock."""
    registry = HandlerRegistry()
    registry.register_transition("work", _work_handler)
    engine = Engine(registry)
    start = net.initial_marking
    assert start is not None
    marking, inject_record = engine.inject_token(
        net,
        start,
        "in",
        Token("task", {"n": 1}),
        attempt=0,
        replace=False,
    )
    marking, fired = engine.fire(net, marking, "work", attempt=1)
    assert fired["status"] == "completed"
    _, update_record = engine.inject_token(
        net,
        marking,
        "clock",
        Token("tick", {"now": 60}),
        attempt=2,
        replace=True,
    )
    return [
        {**inject_record, "sequence": 0},
        _completed_firing_record(
            1,
            net.name,
            "work",
            fired["inputTokens"],
            fired["outputTokens"],
        ),
        {**update_record, "sequence": 2},
    ]


def _lane_net() -> Net:
    return Net(
        name="lane",
        places=[
            Place(name="in", accepts=["task"]),
            Place(name="out", accepts=["task"]),
            Place(name="clock", accepts=["tick"]),
        ],
        transitions=[Transition(name="work", handler="work")],
        arcs=[
            Arc(
                from_place="in",
                to_transition="work",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="work",
                to_place="out",
                produce=ProduceTemplate("task", "out"),
            ),
        ],
        initial_marking=Marking({"clock": [Token("tick", {"now": 0})]}),
    )


# given: engine-emitted records for [inject, fire, update]
# when: replay_records rebuilds the marking
# then: the result matches replay_events on the channel-wrapped events
def test_replay_records_builds_same_marking_as_replay_events() -> None:
    net = _lane_net()
    records = _records(net)
    channels = ("injection", "firing", "injection")
    expected = replay_events(
        net,
        [
            StoredEvent(record["sequence"], channel, record)
            for record, channel in zip(records, channels, strict=True)
        ],
    )
    assert replay_records(net, records) == expected


# given: an injection record whose ``kind`` already names the journal channel
# (the decoded DurableJournal row shape, which lost the record's own kind)
# when: replay_records rebuilds it
# then: no KeyError and it replays as an ``inject`` (nothing replaced)
def test_channel_kind_injection_record_defaults_to_inject() -> None:
    net = _lane_net()
    engine = Engine(HandlerRegistry())
    start = net.initial_marking
    assert start is not None
    _, inject_record = engine.inject_token(
        net,
        start,
        "in",
        Token("task", {"n": 1}),
        attempt=0,
        replace=False,
    )
    durable_row = {
        **inject_record,
        "kind": "injection",
        "sequence": 0,
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }
    expected = replay_events(
        net, [StoredEvent(0, "injection", inject_record)]
    )
    assert replay_records(net, [durable_row]) == expected


# given: a decoded durable row of an ``update`` injection (``replaced`` is
# non-empty, ``kind`` carries the channel name)
# when: replay_records rebuilds it
# then: the place is set (replaced), not appended
def test_channel_kind_update_record_replays_as_update() -> None:
    net = _lane_net()
    engine = Engine(HandlerRegistry())
    start = net.initial_marking
    assert start is not None
    _, update_record = engine.inject_token(
        net,
        start,
        "clock",
        Token("tick", {"now": 60}),
        attempt=0,
        replace=True,
    )
    durable_row = {
        **update_record,
        "kind": "injection",
        "sequence": 0,
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }
    expected = replay_events(
        net, [StoredEvent(0, "injection", update_record)]
    )
    assert replay_records(net, [durable_row]) == expected