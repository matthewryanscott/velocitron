"""Handler-free replay rebuilds a marking from recorded effects."""

from __future__ import annotations

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
from velocitron_journal import StoredEvent, replay_events, replay_records


def _lane() -> Net:
    return Net(
        name="lane",
        places=[
            Place("src", ["job"]),
            Place("dst", ["job"]),
            Place("clock", ["tick"]),
        ],
        transitions=[Transition("move", handler="move")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="move",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="clock",
                to_transition="move",
                consume=ConsumePattern("tick", None, "read"),
            ),
            Arc(
                from_transition="move",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
        initial_marking=Marking(
            {
                "src": [Token("job", {"id": 1})],
                "clock": [Token("tick", {"n": 0})],
            }
        ),
    )


def _firing(*, status: str = "completed") -> dict[str, object]:
    return {
        "firingId": "lane/move/0",
        "netId": "lane",
        "transition": "move",
        "attempt": 0,
        "status": status,
        "inputTokens": {
            "src": [Token("job", {"id": 1})],
            "clock": [Token("tick", {"n": 0})],
        },
        "outputTokens": {"dst": [Token("job", {"id": 1, "done": True})]},
        "error": None,
        "metadata": {},
        "timestamps": {"fired_at": "2026-01-01T00:00:00Z"},
    }


def test_replay_consumes_only_consume_arcs_and_deposits_outputs() -> None:
    # given: a completed firing whose inputs include a read-arc clock token
    net = _lane()

    # when: replay applies that firing from the net's initial marking
    marking = replay_records(net, [_firing()])

    # then: the consumed job is gone, the clock stays, and the output is deposited
    assert list(marking["src"]) == []
    assert list(marking["clock"]) == [Token("tick", {"n": 0})]
    assert list(marking["dst"]) == [Token("job", {"id": 1, "done": True})]


def test_failed_firing_trace_and_net_revision_leave_the_marking() -> None:
    # given: a failed firing, a trace, and a net revision
    net = _lane()
    initial = net.initial_marking
    assert initial is not None

    # when: replay reads them
    marking = replay_records(
        net,
        [
            _firing(status="failed"),
            {"event": "handler_started", "firingId": "lane/move/0"},
            {"name": "lane", "kind": "net_revision"},
        ],
    )

    # then: the initial marking is unchanged
    assert marking == initial


def test_injection_append_and_update() -> None:
    # given: an inject followed by an update of the same place
    net = _lane()
    records = [
        {
            "injectionId": "lane/@inject/src/0",
            "place": "src",
            "kind": "inject",
            "tokens": [Token("job", {"id": 2})],
            "replaced": [],
        },
        {
            "injectionId": "lane/@inject/clock/1",
            "place": "clock",
            "kind": "update",
            "tokens": [Token("tick", {"n": 5})],
            "replaced": [Token("tick", {"n": 0})],
        },
    ]

    # when: replay_records folds them
    marking = replay_records(net, records)

    # then: src gained a token and clock was replaced
    assert list(marking["src"]) == [Token("job", {"id": 1}), Token("job", {"id": 2})]
    assert list(marking["clock"]) == [Token("tick", {"n": 5})]


def test_channel_kind_on_a_durable_row_restores_update_from_replaced() -> None:
    # given: a decoded sqlite row whose kind column overwrote the injection kind
    net = _lane()
    row = {
        "injectionId": "lane/@inject/clock/0",
        "place": "clock",
        "kind": "injection",
        "tokens": [{"type": "tick", "data": {"n": 5}}],
        "replaced": [{"type": "tick", "data": {"n": 0}}],
        "sequence": 4,
        "recorded_at": "2026-01-01T00:00:00+00:00",
    }

    # when: replay_records rebuilds from that row, starting at the initial marking
    marking = replay_records(net, [row])
    direct = replay_events(
        net,
        [
            StoredEvent(
                0,
                "injection",
                {
                    "injectionId": row["injectionId"],
                    "place": "clock",
                    "kind": "update",
                    "tokens": row["tokens"],
                    "replaced": row["replaced"],
                },
            )
        ],
    )

    # then: the place is replaced, matching an explicit update event
    assert marking == direct
    assert list(marking["clock"]) == [Token("tick", {"n": 5})]


def test_replay_events_can_start_from_a_caller_marking() -> None:
    # given: a marking that is not the net's initial one
    net = _lane()
    start = Marking({"src": [Token("job", {"id": 9})]})

    # when: replay applies an injection from that marking
    marking = replay_events(
        net,
        [
            StoredEvent(
                0,
                "injection",
                {
                    "place": "src",
                    "kind": "inject",
                    "tokens": [Token("job", {"id": 8})],
                },
            )
        ],
        initial=start,
    )

    # then: the caller's tokens remain and the injected token is appended
    assert list(marking["src"]) == [Token("job", {"id": 9}), Token("job", {"id": 8})]
