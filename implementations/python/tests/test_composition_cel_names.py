"""CEL inside a merged composition reads ``binding`` by local names (ADR 0032).

The merge renames places (``inbox`` becomes ``shipping.inbox``, or the fused
``orders.accepted``). Each merged transition records ``binding_names``, so its
``correlate`` and ``data cel`` expressions keep the meaning they had in the
constituent net. Timers already use ``bind`` and need no names.
"""

from __future__ import annotations

from typing import Any

import pytest

from velocitron_petrinet import merge_nets
from velocitron_engine import (
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_petrinet import (
    compile_petrinet_text,
    parse_petrinet_text,
)
from velocitron_dsl import emit_petrinet
from velocitron_dsl import PetrinetDslError
from velocitron_runtime import Engine
from velocitron_petrinet import (
    NetValidationError,
    parse_net,
)
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
    Wire,
)

_ORDERS = """net orders
(incoming) -purchase-> [accept]
@forward: [accept] -purchase-> (accepted)
@forward data cel "binding.incoming[0]"
(accepted) port output purchase
[accept] handler "noop"
"""

_SHIPPING = """net shipping
(inbox) -purchase-> [pack] -parcel-> (packed)
(inbox) port input purchase
@courier: (couriers) -courier->? [pack]
@courier correlate cel "token.region == binding.inbox[0].region"
@held: (holds) -hold->0 [pack]
@held correlate cel "token.order == binding.inbox[0].id"
@receipt: [pack] -receipt-> (receipts)
@receipt data cel "{\\"order\\": binding.inbox[0].id, \\"courier\\": binding.couriers[0].name}"
@clock: (clock) -clock->? [pack]
[pack] handler "noop"
[pack] timer clock (clock) cel "clock.now >= request.due"
[pack] timer bind request (inbox)
"""


def _noop(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    return {"status": "completed", "outputTokens": {}, "error": None, "metadata": {}}


def _engine() -> Engine:
    registry = HandlerRegistry()
    registry.register_transition("noop", _noop)
    return Engine(registry)


def _shop() -> Net:
    return merge_nets(
        {
            "orders": parse_petrinet_text(_ORDERS),
            "shipping": parse_petrinet_text(_SHIPPING),
        },
        [Wire("orders", "accepted", "shipping", "inbox")],
    )


def _accepted_order(net: Net, engine: Engine, **extra: list[Token]) -> Marking:
    marking = Marking(
        {
            "orders.incoming": [
                Token("purchase", {"id": "o-1", "region": "eu", "due": 5})
            ],
            "shipping.clock": [Token("clock", {"now": 10})],
            "shipping.couriers": [
                Token("courier", {"region": "us", "name": "sam"}),
                Token("courier", {"region": "eu", "name": "eva"}),
            ],
            **extra,
        }
    )
    marking, record = engine.fire(net, marking, "orders.accept", attempt=0)
    assert record["status"] == "completed"
    return marking


def test_merge_records_local_names_for_each_binding_place() -> None:
    # when
    net = _shop()

    # then: fused and aliased places map back to the constituent's names
    pack = next(t for t in net.transitions if t.name == "shipping.pack")
    assert pack.binding_names == {
        "inbox": "orders.accepted",
        "couriers": "shipping.couriers",
        "clock": "shipping.clock",
    }
    accept = next(t for t in net.transitions if t.name == "orders.accept")
    assert accept.binding_names == {"incoming": "orders.incoming"}


def test_correlate_and_data_cel_use_local_names_after_merge() -> None:
    # given
    net, engine = _shop(), _engine()
    marking = _accepted_order(net, engine)

    # when
    marking, record = engine.fire(net, marking, "shipping.pack", attempt=0)

    # then: the read-arc join picked the eu courier, and data cel saw both
    assert record["status"] == "completed"
    assert record["inputTokens"]["shipping.couriers"] == [
        Token("courier", {"region": "eu", "name": "eva"})
    ]
    assert list(marking["shipping.receipts"]) == [
        Token("receipt", {"order": "o-1", "courier": "eva"})
    ]


def test_correlated_inhibit_uses_local_names_after_merge() -> None:
    # given: a hold for this order blocks it, a hold for another does not
    net, engine = _shop(), _engine()
    blocked = _accepted_order(
        net, engine, **{"shipping.holds": [Token("hold", {"order": "o-1"})]}
    )
    free = _accepted_order(
        net, engine, **{"shipping.holds": [Token("hold", {"order": "o-2"})]}
    )

    # when
    enabled_blocked = engine.enabled_transitions(net, blocked, attempt=0)
    enabled_free = engine.enabled_transitions(net, free, attempt=0)

    # then
    assert "shipping.pack" not in enabled_blocked
    assert "shipping.pack" in enabled_free


def test_timer_bind_reads_a_fused_place_after_merge() -> None:
    # given: the order is due at 5; the clock reads 3
    net, engine = _shop(), _engine()
    marking = _accepted_order(net, engine).set(
        "shipping.clock", [Token("clock", {"now": 3})]
    )

    # when
    early = engine.enabled_transitions(net, marking, attempt=0)
    late = engine.enabled_transitions(
        net, marking.set("shipping.clock", [Token("clock", {"now": 5})]), attempt=0
    )

    # then
    assert "shipping.pack" not in early
    assert "shipping.pack" in late


def test_a_merge_of_a_merge_keeps_the_innermost_names() -> None:
    # given: the shop composed again under the alias `site`
    inner = _shop()

    # when
    outer = merge_nets({"site": inner}, [])

    # then
    pack = next(t for t in outer.transitions if t.name == "site.shipping.pack")
    assert pack.binding_names == {
        "inbox": "site.orders.accepted",
        "couriers": "site.shipping.couriers",
        "clock": "site.shipping.clock",
    }
    engine = _engine()
    marking = Marking(
        {
            "site.orders.incoming": [
                Token("purchase", {"id": "o-1", "region": "eu", "due": 0})
            ],
            "site.shipping.clock": [Token("clock", {"now": 0})],
            "site.shipping.couriers": [
                Token("courier", {"region": "eu", "name": "eva"})
            ],
        }
    )
    marking, _ = engine.fire(outer, marking, "site.orders.accept", attempt=0)
    marking, record = engine.fire(outer, marking, "site.shipping.pack", attempt=0)
    assert record["status"] == "completed"
    assert list(marking["site.shipping.receipts"]) == [
        Token("receipt", {"order": "o-1", "courier": "eva"})
    ]


@pytest.mark.parametrize(
    "binding_names",
    [
        {"inbox": "a"},
        {"inbox": "a", "b": "b", "c": "c"},
        {"inbox": "a", "b": "nowhere"},
    ],
    ids=["missing-source", "produce-destination", "undeclared-place"],
)
def test_binding_names_must_name_exactly_the_binding_sources(
    binding_names: dict[str, str],
) -> None:
    # given: [go] binds from a and b
    document: dict[str, Any] = {
        "name": "n",
        "places": [
            {"name": "a", "accepts": ["t"]},
            {"name": "b", "accepts": ["t"]},
            {"name": "c", "accepts": ["t"]},
        ],
        "transitions": [{"name": "go", "bindingNames": binding_names}],
        "arcs": [
            {
                "from": {"place": "a"},
                "to": {"transition": "go"},
                "consume": {"type": "t"},
            },
            {
                "from": {"place": "b"},
                "to": {"transition": "go"},
                "consume": {"type": "t", "mode": "read"},
            },
            {
                "from": {"transition": "go"},
                "to": {"place": "c"},
                "produce": {"type": "t", "destination": "c"},
            },
        ],
    }

    # when / then
    with pytest.raises(NetValidationError, match="bindingNames"):
        parse_net(document)


_MERGED: dict[str, Any] = {
    "name": "composition",
    "places": [
        {"name": "x.a", "accepts": ["t"]},
        {"name": "x.b", "accepts": ["t"]},
    ],
    "transitions": [{"name": "x.go", "bindingNames": {"a": "x.a"}}],
    "arcs": [
        {
            "from": {"place": "x.a"},
            "to": {"transition": "x.go"},
            "consume": {"type": "t"},
        },
        {
            "from": {"transition": "x.go"},
            "to": {"place": "x.b"},
            "produce": {"type": "t", "destination": "x.b"},
        },
    ],
    "initialMarking": {},
}


def test_binding_names_round_trip_through_the_dsl() -> None:
    # given: a merged net written out as JSON
    # when
    text = emit_petrinet(_MERGED)

    # then: each key is a bind fact, and compiling the text gives the net back
    assert '["x.go"] bind a ("x.a")' in text.splitlines()
    assert compile_petrinet_text(text) == _MERGED


@pytest.mark.parametrize(
    ("fact", "message"),
    [
        ("[nowhere] bind a (a)", "binding name refers to unknown transition [nowhere]"),
        (
            "[go] bind a (b)",
            "binding names on transition [go] must name exactly the places it "
            "consumes or reads",
        ),
        (
            "[go] bind a (a)\n[go] bind a (c)",
            "conflicting binding name facts for 'a' on transition [go]",
        ),
    ],
    ids=["unknown-transition", "produce-destination", "conflict"],
)
def test_bind_facts_are_checked_against_the_net(fact: str, message: str) -> None:
    # given: [go] consumes a and produces b
    text = f"net n\n(a) -> [go] -> (b)\n(c)\n{fact}\n"

    # when / then
    with pytest.raises(PetrinetDslError) as error:
        compile_petrinet_text(text)
    assert error.value.diagnostic.code == "PN202"
    assert error.value.diagnostic.message == message
