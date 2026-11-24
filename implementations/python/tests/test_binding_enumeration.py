"""Consumption contracts over THE one binding enumeration (ADR 0027).

``Engine._binding_candidates`` is the single internal walk under
``select_binding`` (first-success) and ``timer_maturities`` (first-wake);
these tests pin the walk through the public surfaces only: enumeration-order
stability across repeated calls and attempts, first-success and first-failure
consumption equivalence, and ``Runtime._footprint`` equality with the old
per-arc derivation on every conformance-corpus net.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from velocitron_runtime import Engine
from velocitron_engine import TimerMaturity
from velocitron_petrinet import parse_net
from velocitron_engine import HandlerRegistry
from velocitron_runtime import Runtime
from velocitron_engine import (
    Marking,
    Net,
    Token,
    Transition,
)

_REPO_ROOT = Path(__file__).parents[3]
_CORPUS_ROOT = _REPO_ROOT / "packages" / "spec" / "conformance" / "petrinet"
_MANIFEST_PATH = _CORPUS_ROOT / "manifest.json"

_SINGLE_NET_CASES: list[tuple[str, dict[str, Any]]] = []
for _case in cast(
    dict[str, Any], json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
)["cases"]:
    _valid = _case.get("valid")
    if _valid is not None and "canonicalNet" in _valid:
        _document = cast(
            dict[str, Any],
            json.loads(
                (_CORPUS_ROOT / str(_valid["canonicalNet"])).read_text(encoding="utf-8")
            ),
        )
        _SINGLE_NET_CASES.append((cast(str, _case["id"]), _document))


def _net(
    name: str,
    places: list[str],
    transitions: list[dict[str, Any]],
    arcs: list[dict[str, Any]],
    accepts: dict[str, list[str]] | None = None,
) -> Net:
    place_dicts = [{"name": p, "accepts": (accepts or {}).get(p, [p])} for p in places]
    return parse_net(
        {"name": name, "places": place_dicts, "transitions": transitions, "arcs": arcs}
    )


def _tok(t: str = "task", **data: Any) -> Token:
    return Token(type=t, data=dict(data))


def _ids(tokens: list[Token]) -> list[str]:
    return [t.data["id"] for t in tokens]


def _guard_accepts_a_c(inp: Any) -> bool:
    """A guard that accepts only the (a, c) pair over place ``items``."""
    return _ids(cast(list[Token], inp["inputTokens"]["items"])) == ["a", "c"]


# ── Enumeration order stability ─────────────────────────────────────────


def test_select_binding_is_order_stable_across_calls_and_attempts() -> None:
    """Repeated ``select_binding`` calls return the same binding, whatever the
    attempt — the enumeration is deterministic, and re-deriving it never
    reorders the product."""
    # given: three tokens and two same-place arcs, with a guard accepting only
    # the (a, c) pair — so the walk skips (a, a) as sub-multiset-invalid and
    # (a, b) as guard-rejected before surviving at (a, c)
    net = _net(
        "stable-order",
        places=["items"],
        transitions=[{"name": "pick", "handler": "pick", "guard": "pick_ac"}],
        arcs=[
            {
                "from": {"place": "items"},
                "to": {"transition": "pick"},
                "consume": {"type": "task", "mode": "consume", "weight": 1},
            },
            {
                "from": {"place": "items"},
                "to": {"transition": "pick"},
                "consume": {"type": "task", "mode": "consume", "weight": 1},
            },
        ],
        accepts={"items": ["task"]},
    )
    registry = HandlerRegistry()
    registry.register_guard("pick_ac", _guard_accepts_a_c)
    engine = Engine(registry)
    marking = Marking(
        {"items": [_tok("task", id="a"), _tok("task", id="b"), _tok("task", id="c")]}
    )

    # when: selecting with several attempts, repeatedly
    attempts = [
        engine.select_binding(net, "pick", marking, attempt=n) for n in (0, 1, 9)
    ]
    again = [engine.select_binding(net, "pick", marking, attempt=0) for _ in range(3)]

    # then: every call yields the identical first surviving binding
    assert attempts == again
    assert all(b is not None for b in attempts)
    assert [_ids(b["items"]) for b in attempts if b is not None] == [["a", "c"]] * 3


def test_select_binding_survives_only_after_the_annotated_skips() -> None:
    """The walk's candidate-level rejections (sub-multiset, correlated-inhibit)
    are skipped, never a reorder: with a correlated inhibit blocking the (a, b)
    pair, ``select_binding`` returns the (b, c) pair — the first pair past it."""
    # given: three tokens, two same-place arcs, and a correlated inhibit that
    # blocks every binding whose first id is 'a' — (a, b) and (a, c) are
    # correlated-blocked; (b, c) is the first surviving pair
    net = _net(
        "skip-annotated",
        places=["items", "seen"],
        transitions=[
            {"name": "pick", "handler": "pick"},
            {"name": "seen", "handler": "seen"},
        ],
        arcs=[
            {
                "from": {"place": "items"},
                "to": {"transition": "pick"},
                "consume": {"type": "task", "mode": "consume", "weight": 1},
            },
            {
                "from": {"place": "items"},
                "to": {"transition": "pick"},
                "consume": {"type": "task", "mode": "consume", "weight": 1},
            },
            {
                "from": {"place": "seen"},
                "to": {"transition": "seen"},
                "consume": {"type": "task", "mode": "consume", "weight": 1},
            },
            {
                "from": {"place": "seen"},
                "to": {"transition": "pick"},
                "consume": {
                    "type": "task",
                    "mode": "inhibit",
                    "correlate": {"cel": "token.id == binding.items[0].id"},
                },
            },
        ],
        accepts={"items": ["task"], "seen": ["task"]},
    )
    seen = _tok("task", id="a")
    engine = Engine(HandlerRegistry())
    marking = Marking(
        {
            "items": [_tok("task", id="a"), _tok("task", id="b"), _tok("task", id="c")],
            "seen": [seen],
        }
    )

    # when: selecting a binding for pick
    # then: the first pair past the correlated-blocked ones is (b, c)
    binding = engine.select_binding(net, "pick", marking)
    assert binding is not None
    assert [t.data["id"] for t in binding["items"]] == ["b", "a"]


# ── First-success and first-failure consumption ─────────────────────────


def _poll_net(order: str) -> Net:
    """The shared poll/two-waiter net: clock at 20 with two waiters stamped
    ``next_poll_at`` 30 and 100, timers bound over the ``waiting`` read arc."""
    arcs = [
        {
            "from": {"place": "waiting"},
            "to": {"transition": "poll"},
            "consume": {"type": "work", "mode": "read", "weight": 1},
        },
        {
            "from": {"place": "clock"},
            "to": {"transition": "poll"},
            "consume": {"type": "tick", "mode": "read", "weight": 1},
        },
    ]
    if order == "clock-first":
        arcs.reverse()
    return _net(
        "two-waiters",
        places=["clock", "waiting"],
        transitions=[
            {
                "name": "poll",
                "handler": "poll",
                "timer": {
                    "clock": "clock",
                    "cel": "clock.now >= work.next_poll_at",
                    "bind": {"work": "waiting"},
                    "maturity": "work.next_poll_at",
                },
            }
        ],
        arcs=arcs,
        accepts={"clock": ["tick"], "waiting": ["work"]},
    )


def _waiter_marking() -> Marking:
    return Marking(
        {
            "clock": [_tok("tick", now=20)],
            "waiting": [
                _tok("work", next_poll_at=30),
                _tok("work", next_poll_at=100),
            ],
        }
    )


def test_timer_maturities_stops_at_the_first_timer_predicate_failure() -> None:
    """The walk consumes the enumeration to the FIRST cel-failing binding and
    stops: one wake candidate per timed transition — the first lexicographic
    unmatured token's stamped maturity, not the whole product's.

    Reversion-verified bite: the pre-card walk appended a ``TimerMaturity`` for
    every cel-failing binding (here both 30 and 100) and fails this test."""
    # given: a poll reading two waiters with distinct stamped poll times, in
    # declaration order [30, 100], against a clock at 20 — both unmatured
    net = _poll_net("waiting-first")
    engine = Engine(HandlerRegistry())
    marking = _waiter_marking()

    # when: reading the wake candidates
    maturities = engine.timer_maturities(net, marking)

    # then: exactly the first unmatured binding's maturity, once
    assert maturities == (TimerMaturity("poll", "clock", 30.0),)
    # and: re-reading is order-stable
    assert engine.timer_maturities(net, marking) == maturities


def test_timer_maturities_walk_continues_past_ready_bindings() -> None:
    """A binding whose timer cel HOLDS is a viable step, not a wake candidate —
    the first-failure walk skips it and stops at the first unmatured one."""
    # given: the same two-waiter net with a matured first waiter (poll time in
    # the past) and a future second waiter
    net = _poll_net("waiting-first")
    engine = Engine(HandlerRegistry())
    marking = Marking(
        {
            "clock": [_tok("tick", now=20)],
            "waiting": [_tok("work", next_poll_at=1), _tok("work", next_poll_at=100)],
        }
    )

    # when: reading the wake candidates
    # then: only the unmatured second waiter is scheduled
    assert engine.timer_maturities(net, marking) == (
        TimerMaturity("poll", "clock", 100.0),
    )


def test_timer_maturities_arc_declaration_order_drives_the_first_failure() -> None:
    """The clock-read binding arc is part of the enumeration: declaring [clock,
    waiting] reorders the product's outer loop, but the single wake stays the
    first unmatured waiter's stamped time — the shared primitive's order is the
    two implementations' identical semantics."""
    # given: the same timers with the clock arc declared first
    net = _poll_net("clock-first")
    engine = Engine(HandlerRegistry())
    marking = _waiter_marking()

    # when: reading the wake candidates
    # then: the same single record survives
    assert engine.timer_maturities(net, marking) == (
        TimerMaturity("poll", "clock", 30.0),
    )


# ── Footprint equality with the old derivation on corpus nets ───────────


def _legacy_footprint(
    net: Net, transition: Transition
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """The pre-card per-arc re-derivation of consumed/read/written places."""
    consume: set[str] = set()
    read: set[str] = set()
    write: set[str] = set()
    for arc in net.arcs:
        if arc.to_transition == transition.name and arc.consume is not None:
            if arc.consume.mode == "consume":
                assert arc.from_place is not None
                consume.add(arc.from_place)
            elif arc.consume.mode == "read":
                assert arc.from_place is not None
                read.add(arc.from_place)
        elif arc.from_transition == transition.name and arc.produce is not None:
            assert arc.produce is not None
            write.add(arc.produce.destination)
    return frozenset(consume), frozenset(read), frozenset(write)


def test_footprint_matches_the_old_derivation_on_every_corpus_net() -> None:
    """``Runtime._footprint`` now classifies from the engine's topology index —
    it must equal the old ``net.arcs`` walk for every transition of every
    single-net corpus case."""
    # given: every single-net case in the conformance corpus
    engine = Engine(HandlerRegistry())
    for case_id, document in _SINGLE_NET_CASES:
        net = parse_net(document)
        # when: classifying each transition via the topology-index consumer and
        # via the old per-arc re-derivation
        for transition in net.transitions:
            footprint = Runtime._footprint(net, engine, transition)  # pyright: ignore[reportPrivateUsage]
            legacy = _legacy_footprint(net, transition)
            # then: the classification is identical — no consumed, read, or
            # written place differs
            assert (footprint.consume, footprint.read, footprint.write) == legacy, (
                case_id
            )
