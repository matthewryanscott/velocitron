"""``Engine.reserve(choose=)``, ``Engine.reservations`` and
``Engine.explain_enablement``.

``choose`` narrows the first-success consumer to the bindings a caller wants;
it never makes a rejected binding viable. ``reservations`` reserves every
viable binding of every enabled transition from one walk of the enumeration.
``explain_enablement`` takes its verdict from the one binding enumeration
(ADR 0027) and names, with values, the gate that turned each candidate away.

References: ADR 0027; ADR 0030; spec/firing-semantics.md (a).
"""

from __future__ import annotations

from typing import Any

from velocitron_cel import get_default_adapter
from velocitron_engine import GuardHandlerInput
from velocitron_runtime import Engine
from velocitron_petrinet import parse_net
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
)


def _tok(color: str, **data: Any) -> Token:
    return Token(type=color, data=dict(data))


def _net(
    places: dict[str, list[str]],
    arcs: list[dict[str, Any]],
    transition: dict[str, Any] | None = None,
) -> Net:
    return parse_net(
        {
            "name": "explain",
            "places": [{"name": n, "accepts": c} for n, c in places.items()],
            "transitions": [transition or {"name": "go"}],
            "arcs": arcs,
        }
    )


def _in(place: str, color: str, **consume: Any) -> dict[str, Any]:
    return {
        "from": {"place": place},
        "to": {"transition": "go"},
        "consume": {"type": color, **consume},
    }


def _gates(engine: Engine, net: Net, marking: Marking) -> list[str]:
    return [r.gate for r in engine.explain_enablement(net, marking, "go").reasons]


def test_reserve_choose_takes_the_first_binding_it_accepts() -> None:
    # given: two orders, the second one wanted
    net = _net({"orders": ["order"]}, [_in("orders", "order")])
    marking = Marking({"orders": [_tok("order", id=1), _tok("order", id=2)]})
    engine = Engine(HandlerRegistry())

    # when: reserving with a choice for id 2
    reservation = engine.reserve(
        net,
        marking,
        "go",
        attempt=0,
        choose=lambda b: b["orders"][0].data["id"] == 2,
    )

    # then: order 2 is reserved and order 1 stays
    assert reservation is not None
    assert reservation.consumed_tokens == {"orders": [_tok("order", id=2)]}
    assert list(reservation.reserved_marking["orders"]) == [_tok("order", id=1)]


def test_reserve_choose_that_accepts_nothing_is_not_enabled() -> None:
    # given: one order
    net = _net({"orders": ["order"]}, [_in("orders", "order")])
    marking = Marking({"orders": [_tok("order", id=1)]})

    # when: the choice rejects every binding
    reservation = Engine(HandlerRegistry()).reserve(
        net, marking, "go", attempt=0, choose=lambda _b: False
    )

    # then: nothing is reserved
    assert reservation is None


def test_reserve_choose_runs_before_the_guard() -> None:
    # given: a guard that counts its calls
    calls: list[Any] = []

    def guard(inp: GuardHandlerInput) -> bool:
        calls.append(inp["inputTokens"])
        return True

    registry = HandlerRegistry()
    registry.register_guard("count", guard)
    net = _net(
        {"orders": ["order"]},
        [_in("orders", "order")],
        {"name": "go", "guard": "count"},
    )
    marking = Marking({"orders": [_tok("order", id=1), _tok("order", id=2)]})

    # when: choosing the second order
    Engine(registry).reserve(
        net, marking, "go", attempt=0, choose=lambda b: b["orders"][0].data["id"] == 2
    )

    # then: the guard saw only the chosen binding
    assert calls == [{"orders": [_tok("order", id=2)]}]


def test_explain_an_enabled_transition_agrees_with_select_binding() -> None:
    # given: two orders
    net = _net({"orders": ["order"]}, [_in("orders", "order")])
    marking = Marking({"orders": [_tok("order", id=1), _tok("order", id=2)]})
    engine = Engine(HandlerRegistry())

    # when: explaining
    explanation = engine.explain_enablement(net, marking, "go")

    # then: the verdict and binding are select_binding's; both are viable
    assert explanation.enabled
    assert explanation.binding == engine.select_binding(net, "go", marking)
    assert len(explanation.viable) == 2
    assert explanation.reasons == ()


def test_explain_arc_short_names_each_token_and_the_cel_error() -> None:
    # given: a predicate that is false for one token and errors on another
    net = _net(
        {"orders": ["order", "note"]},
        [_in("orders", "order", predicate={"cel": "total > 10"})],
    )
    marking = Marking(
        {
            "orders": [
                _tok("order", total=5),
                _tok("order", id=1),
                _tok("note", text="x"),
            ]
        }
    )

    # when: explaining
    explanation = Engine(HandlerRegistry()).explain_enablement(net, marking, "go")

    # then: one arc-short reason with a verdict per token
    assert not explanation.enabled
    (reason,) = explanation.reasons
    assert reason.gate == "arc-short"
    assert reason.place == "orders"
    assert reason.arc == 0
    assert "(orders) -order-> [go] needs 1 order token" in reason.message
    assert "holds 0 that match, of 3" in reason.message
    assert reason.details[0] == 'order {"total": 5}: predicate `total > 10` is false'
    assert reason.details[1].startswith(
        'order {"id": 1}: predicate `total > 10` failed to evaluate'
    )
    assert reason.details[2] == 'note {"text": "x"}: color note, the arc takes order'


def test_explain_names_an_inhibit_hit() -> None:
    # given: an inhibit arc whose place holds a pause
    net = _net(
        {"orders": ["order"], "pauses": ["pause"]},
        [_in("orders", "order"), _in("pauses", "pause", mode="inhibit")],
    )
    marking = Marking({"orders": [_tok("order")], "pauses": [_tok("pause", why="x")]})

    # when / then: the reason names the blocking token
    (reason,) = Engine(HandlerRegistry()).explain_enablement(net, marking, "go").reasons
    assert reason.gate == "inhibit-hit"
    assert reason.message == (
        'inhibit arc (pauses) -pause->0 [go] forbids pause {"why": "x"}, '
        "and (pauses) holds it"
    )


def test_explain_names_a_correlate_miss_with_values() -> None:
    # given: the switch for another title
    net = _net(
        {"pending": ["delivery"], "switches": ["switch"]},
        [
            _in("pending", "delivery"),
            _in(
                "switches",
                "switch",
                mode="read",
                correlate={"cel": "token.isbn == binding.pending[0].isbn"},
            ),
        ],
    )
    marking = Marking(
        {
            "pending": [_tok("delivery", isbn="f1")],
            "switches": [_tok("switch", isbn="f2")],
        }
    )

    # when: explaining
    (reason,) = Engine(HandlerRegistry()).explain_enablement(net, marking, "go").reasons

    # then: the arc, the expression, its result and the selected values
    assert reason.gate == "correlate-miss"
    assert reason.message == (
        "correlate on (switches) -switch->? [go] "
        "`token.isbn == binding.pending[0].isbn` is false "
        '(token.isbn = "f2", binding.pending[0].isbn = "f1") '
        'for switch {"isbn": "f2"}'
    )


def test_explain_names_a_correlated_inhibit() -> None:
    # given: a newer run for the same destination
    net = _net(
        {"pending": ["delivery"], "newer": ["run"]},
        [
            _in("pending", "delivery"),
            _in(
                "newer",
                "run",
                mode="inhibit",
                correlate={"cel": "token.dest == binding.pending[0].dest"},
            ),
        ],
    )
    marking = Marking(
        {"pending": [_tok("delivery", dest="g")], "newer": [_tok("run", dest="g")]}
    )

    # when / then
    (reason,) = Engine(HandlerRegistry()).explain_enablement(net, marking, "go").reasons
    assert reason.gate == "correlated-inhibit"
    assert '(newer) holds run {"dest": "g"}' in reason.message
    assert "is true" in reason.message


def _timed_net() -> Net:
    return _net(
        {"waiting": ["delivery"], "clock": ["tick"]},
        [_in("waiting", "delivery"), _in("clock", "tick", mode="read")],
        {
            "name": "go",
            "timer": {
                "clock": "clock",
                "cel": "clock.now >= delivery.nextAt",
                "bind": {"delivery": "waiting"},
            },
        },
    )


def test_explain_a_timer_hold_prints_the_clock_and_bound_values() -> None:
    # given: the clock before the deadline
    marking = Marking(
        {"waiting": [_tok("delivery", nextAt=5400)], "clock": [_tok("tick", now=3000)]}
    )

    # when / then
    (reason,) = (
        Engine(HandlerRegistry())
        .explain_enablement(_timed_net(), marking, "go")
        .reasons
    )
    assert reason.gate == "timer-hold"
    assert reason.message == (
        "timer `clock.now >= delivery.nextAt` is false "
        "(clock.now = 3000, delivery.nextAt = 5400)"
    )


def test_explain_an_empty_clock() -> None:
    # given: no clock token
    marking = Marking({"waiting": [_tok("delivery", nextAt=0)]})

    # when / then
    gates = _gates(Engine(HandlerRegistry()), _timed_net(), marking)
    assert gates == ["clock-empty"]


def test_explain_an_unresolved_guard() -> None:
    # given: a guard with no registered handler
    net = _net(
        {"orders": ["order"]}, [_in("orders", "order")], {"name": "go", "guard": "ok"}
    )
    marking = Marking({"orders": [_tok("order")]})

    # when
    explanation = Engine(HandlerRegistry()).explain_enablement(net, marking, "go")

    # then: not enabled, though the binding itself is viable
    assert not explanation.enabled
    assert [r.gate for r in explanation.reasons] == ["guard-unresolved"]
    assert len(explanation.viable) == 1


def test_explain_a_sub_multiset_rejection() -> None:
    # given: two arcs from one place holding one token
    net = _net(
        {"orders": ["order"]},
        [_in("orders", "order"), _in("orders", "order")],
    )
    marking = Marking({"orders": [_tok("order")]})

    # when / then
    gates = _gates(Engine(HandlerRegistry()), net, marking)
    assert gates == ["sub-multiset"]


# ── Engine.reservations: every firing of every enabled transition ──────


class _CountingEvals:
    """The default backend, counting evaluations."""

    def __init__(self) -> None:
        self.inner = get_default_adapter()
        self.evals = 0

    def compile(self, expr: str) -> Any:
        return self.inner.compile(expr)

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        self.evals += 1
        return self.inner.eval(compiled, data)


def _two_transitions() -> Net:
    return parse_net(
        {
            "name": "reservations",
            "places": [
                {"name": "orders", "accepts": ["order"]},
                {"name": "held", "accepts": ["order"]},
            ],
            "transitions": [{"name": "go"}, {"name": "release"}],
            "arcs": [
                _in("orders", "order", predicate={"cel": "id != 3"}),
                {
                    "from": {"place": "held"},
                    "to": {"transition": "release"},
                    "consume": {"type": "order"},
                },
            ],
        }
    )


def _orders(*ids: int) -> Marking:
    return Marking({"orders": [_tok("order", id=i) for i in ids]})


def test_reservations_hold_one_reservation_per_viable_binding() -> None:
    # given: orders 1 to 3, the predicate turning order 3 away, and an
    # empty place under the second transition
    net = _two_transitions()
    marking = _orders(1, 2, 3)
    engine = Engine(HandlerRegistry())

    # when
    found = engine.reservations(net, marking)

    # then: the enabled transitions, each with its bindings in order
    assert list(found) == engine.enabled_transitions(net, marking) == ["go"]
    assert [r.consumed_tokens for r in found["go"]] == [
        {"orders": [_tok("order", id=1)]},
        {"orders": [_tok("order", id=2)]},
    ]
    # and: each is the reservation `reserve` makes for that binding (the
    # firing context aside: it carries the time it was made)
    for reservation in found["go"]:
        chosen = reservation.input_tokens
        reserved = engine.reserve(
            net, marking, "go", attempt=0, choose=lambda b, c=chosen: b == c
        )
        assert reserved is not None
        assert reservation == reserved._replace(context=reservation.context)


def test_reservations_ask_the_guard_about_each_binding() -> None:
    # given: a guard that takes order 2 only
    registry = HandlerRegistry()
    registry.register_guard(
        "two", lambda inp: inp["inputTokens"]["orders"][0].data["id"] == 2
    )
    net = _net(
        {"orders": ["order"]}, [_in("orders", "order")], {"name": "go", "guard": "two"}
    )

    # when
    found = Engine(registry).reservations(net, _orders(1, 2, 3))

    # then
    assert [r.consumed_tokens for r in found["go"]] == [
        {"orders": [_tok("order", id=2)]}
    ]


def test_reservations_leave_out_a_transition_with_an_unresolved_guard() -> None:
    # given: a guard with no registered handler
    net = _net(
        {"orders": ["order"]}, [_in("orders", "order")], {"name": "go", "guard": "ok"}
    )

    # when / then
    assert Engine(HandlerRegistry()).reservations(net, _orders(1)) == {}


def test_reservations_walk_the_binding_enumeration_once() -> None:
    # given: an adapter that counts evaluations, and three orders
    counting = _CountingEvals()
    engine = Engine(HandlerRegistry(), cel_adapter=counting)

    # when
    engine.reservations(_two_transitions(), _orders(1, 2, 3))

    # then: the predicate ran once per token
    assert counting.evals == 3
