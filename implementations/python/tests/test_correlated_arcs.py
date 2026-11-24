"""Correlated consume and read arcs (``correlate`` as a join, ADR 0030).

A consume or read arc may carry ``correlate: {cel}``. For a candidate binding,
every token the arc binds must make the expression exactly ``true`` over
``{token: <that token's data>, binding: <place-keyed bound-token data>}``.
``binding`` is the whole assembled candidate, so a correlate sees every other
arc's tokens whatever the declaration order. The check runs inside the one
binding enumeration after the single-token predicate filter and the
sub-multiset check, and before correlated inhibits, the timer, and the guard.
An eval error or a non-boolean result fails closed: the binding is rejected.

References: ADR 0030; ADR 0017; ADR 0027; spec/firing-semantics.md (a).
"""

from __future__ import annotations

from typing import Any

import pytest
from _cel_adapters import ADAPTER_IDS, adapters

from velocitron_cel import CelAdapter
from velocitron_runtime import Engine
from velocitron_engine import (
    TimerMaturity,
    _BindingRejection,
)
from velocitron_petrinet import (
    NetValidationError,
    parse_net,
)
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
)


def _tok(color: str, **data: Any) -> Token:
    return Token(type=color, data=dict(data))


def _arc(place: str, color: str, **consume: Any) -> dict[str, Any]:
    return {
        "from": {"place": place},
        "to": {"transition": "ship"},
        "consume": {"type": color, **consume},
    }


def _net(
    arcs: list[dict[str, Any]],
    *,
    transition: dict[str, Any] | None = None,
    cel_adapter: CelAdapter | None = None,
) -> Net:
    places = {
        "orders": ["order"],
        "settings": ["setting"],
        "couriers": ["courier"],
        "pauses": ["pause"],
        "clock": ["tick"],
    }
    return parse_net(
        {
            "name": "correlated-arcs",
            "places": [
                {"name": name, "accepts": colors} for name, colors in places.items()
            ],
            "transitions": [transition or {"name": "ship", "handler": "ship"}],
            "arcs": arcs,
        },
        cel_adapter=cel_adapter,
    )


_SAME_ACCOUNT = {"cel": "token.account == binding.orders[0].account"}


def _settings_net(
    correlate: dict[str, Any] = _SAME_ACCOUNT,
    *,
    mode: str = "read",
    cel_adapter: CelAdapter | None = None,
) -> Net:
    return _net(
        [
            _arc("orders", "order"),
            _arc("settings", "setting", mode=mode, correlate=correlate),
        ],
        cel_adapter=cel_adapter,
    )


def _engine(cel_adapter: CelAdapter | None = None) -> Engine:
    return Engine(HandlerRegistry(), cel_adapter=cel_adapter)


def _accounts(binding: dict[str, list[Token]] | None, place: str) -> list[Any]:
    assert binding is not None
    return [token.data["account"] for token in binding[place]]


class TestParsing:
    @pytest.mark.parametrize("mode", ["consume", "read", "inhibit"])
    def test_correlate_parses_on_every_input_mode(self, mode: str) -> None:
        # given: an input arc of each mode declaring correlate
        net = _settings_net(mode=mode)

        # then: the arc keeps its mode and carries the expression
        arc = next(arc for arc in net.arcs if arc.from_place == "settings")
        assert arc.consume is not None
        assert arc.consume.mode == mode
        assert arc.consume.correlate == _SAME_ACCOUNT["cel"]

    def test_invalid_correlate_cel_fails_at_parse_on_a_read_arc(self) -> None:
        # given/then: a malformed correlate CEL fails while parsing (D6)
        with pytest.raises(NetValidationError, match="correlate on read arc"):
            _settings_net({"cel": "token.account ==== binding"})


class TestReadArcJoin:
    @pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
    def test_binds_the_settings_of_the_orders_account(
        self, adapter: CelAdapter
    ) -> None:
        # given: an order for account B and settings for A then B
        net = _settings_net(cel_adapter=adapter)
        marking = Marking(
            {
                "orders": [_tok("order", account="B")],
                "settings": [
                    _tok("setting", account="A"),
                    _tok("setting", account="B"),
                ],
            }
        )

        # when: selecting a binding
        binding = _engine(adapter).select_binding(net, "ship", marking)

        # then: the A settings are skipped and the B settings are bound
        assert _accounts(binding, "orders") == ["B"]
        assert _accounts(binding, "settings") == ["B"]

    def test_no_matching_settings_means_not_enabled(self) -> None:
        # given: an order whose account has no settings token
        net = _settings_net()
        marking = Marking(
            {
                "orders": [_tok("order", account="C")],
                "settings": [_tok("setting", account="A")],
            }
        )

        # when/then: no binding survives, so the transition is not enabled
        engine = _engine()
        assert engine.select_binding(net, "ship", marking) is None
        assert engine.enabled_transitions(net, marking) == []

    def test_each_order_finds_its_own_settings(self) -> None:
        # given: two orders, and settings only for the second order's account
        net = _settings_net()
        marking = Marking(
            {
                "orders": [_tok("order", account="A"), _tok("order", account="B")],
                "settings": [_tok("setting", account="B")],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: the walk skips the unmatched first order instead of failing
        assert _accounts(binding, "orders") == ["B"]

    def test_fire_keeps_the_read_settings_token(self) -> None:
        # given: a handler that completes with no output
        net = _settings_net()
        registry = HandlerRegistry()
        registry.register_transition(
            "ship",
            lambda inp: {
                "status": "completed",
                "outputTokens": {},
                "error": None,
                "metadata": {},
            },
        )
        settings = [_tok("setting", account="A"), _tok("setting", account="B")]
        marking = Marking(
            {"orders": [_tok("order", account="B")], "settings": settings}
        )

        # when: firing
        after, record = Engine(registry).fire(net, marking, "ship", attempt=0)

        # then: the order is consumed, the matched settings were in the binding and stay
        assert record["status"] == "completed"
        assert after.get("orders", []) == []
        assert after["settings"] == settings
        assert [t.data["account"] for t in record["inputTokens"]["settings"]] == ["B"]


class TestConsumeArcJoin:
    def test_consumes_the_courier_for_the_orders_region(self) -> None:
        # given: a correlated consume arc on couriers
        net = _net(
            [
                _arc("orders", "order"),
                _arc(
                    "couriers",
                    "courier",
                    correlate={"cel": "token.region == binding.orders[0].region"},
                ),
            ]
        )
        marking = Marking(
            {
                "orders": [_tok("order", account="A", region="west")],
                "couriers": [
                    _tok("courier", region="east"),
                    _tok("courier", region="west"),
                ],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: the west courier is bound
        assert binding is not None
        assert [t.data["region"] for t in binding["couriers"]] == ["west"]

    def test_correlate_on_an_earlier_arc_sees_a_later_arc(self) -> None:
        # given: the correlated arc is declared BEFORE the arc it refers to
        net = _net(
            [
                _arc(
                    "couriers",
                    "courier",
                    correlate={"cel": "token.region == binding.orders[0].region"},
                ),
                _arc("orders", "order"),
            ]
        )
        marking = Marking(
            {
                "orders": [_tok("order", account="A", region="west")],
                "couriers": [
                    _tok("courier", region="east"),
                    _tok("courier", region="west"),
                ],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: the whole binding is assembled before the check, so the join holds
        assert binding is not None
        assert [t.data["region"] for t in binding["couriers"]] == ["west"]

    def test_weighted_arc_needs_every_bound_token_to_correlate(self) -> None:
        # given: a weight-2 correlated consume arc and three couriers
        net = _net(
            [
                _arc("orders", "order"),
                _arc(
                    "couriers",
                    "courier",
                    weight=2,
                    correlate={"cel": "token.region == binding.orders[0].region"},
                ),
            ]
        )
        marking = Marking(
            {
                "orders": [_tok("order", region="west")],
                "couriers": [
                    _tok("courier", id=1, region="west"),
                    _tok("courier", id=2, region="east"),
                    _tok("courier", id=3, region="west"),
                ],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: (1, 2) and the east courier are skipped; (1, 3) is the first pair
        assert binding is not None
        assert [t.data["id"] for t in binding["couriers"]] == [1, 3]

    def test_weighted_arc_with_one_correlated_token_is_not_enabled(self) -> None:
        # given: a weight-2 correlated arc with only one matching courier
        net = _net(
            [
                _arc("orders", "order"),
                _arc(
                    "couriers",
                    "courier",
                    weight=2,
                    correlate={"cel": "token.region == binding.orders[0].region"},
                ),
            ]
        )
        marking = Marking(
            {
                "orders": [_tok("order", region="west")],
                "couriers": [
                    _tok("courier", region="west"),
                    _tok("courier", region="east"),
                ],
            }
        )

        # when/then: no pair has two west couriers
        assert _engine().select_binding(net, "ship", marking) is None


class TestPredicateInterplay:
    def test_predicate_filters_before_the_correlate(self) -> None:
        # given: a courier arc with a single-token predicate AND a correlate
        net = _net(
            [
                _arc("orders", "order"),
                _arc(
                    "couriers",
                    "courier",
                    predicate={"cel": "available"},
                    correlate={"cel": "token.region == binding.orders[0].region"},
                ),
            ]
        )
        marking = Marking(
            {
                "orders": [_tok("order", region="west")],
                "couriers": [
                    _tok("courier", id=1, available=False, region="west"),
                    _tok("courier", id=2, available=True, region="east"),
                    _tok("courier", id=3, available=True, region="west"),
                ],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: courier 1 fails the predicate, courier 2 fails the correlate
        assert binding is not None
        assert [t.data["id"] for t in binding["couriers"]] == [3]

    def test_correlate_sees_only_predicate_survivors_of_other_arcs(self) -> None:
        # given: an order predicate and a settings correlate on the order's account
        net = _net(
            [
                _arc("orders", "order", predicate={"cel": "status == 'ready'"}),
                _arc("settings", "setting", mode="read", correlate=_SAME_ACCOUNT),
            ]
        )
        marking = Marking(
            {
                "orders": [
                    _tok("order", account="A", status="draft"),
                    _tok("order", account="B", status="ready"),
                ],
                "settings": [
                    _tok("setting", account="A"),
                    _tok("setting", account="B"),
                ],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: the draft order is never bound, so the B settings join the B order
        assert _accounts(binding, "orders") == ["B"]
        assert _accounts(binding, "settings") == ["B"]


class TestFailClosed:
    @pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
    def test_eval_error_rejects_the_binding(self, adapter: CelAdapter) -> None:
        # given: a correlate naming a field no token carries
        net = _settings_net(
            {"cel": "token.missing == binding.orders[0].account"}, cel_adapter=adapter
        )
        marking = Marking(
            {
                "orders": [_tok("order", account="A")],
                "settings": [_tok("setting", account="A")],
            }
        )

        # when/then: the error rejects the binding; nothing crashes
        assert _engine(adapter).select_binding(net, "ship", marking) is None

    @pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
    def test_non_boolean_result_rejects_the_binding(self, adapter: CelAdapter) -> None:
        # given: a correlate that yields a string, which is truthy in Python
        net = _settings_net({"cel": "token.account"}, cel_adapter=adapter)
        marking = Marking(
            {
                "orders": [_tok("order", account="A")],
                "settings": [_tok("setting", account="A")],
            }
        )

        # when/then: only exact true passes
        assert _engine(adapter).select_binding(net, "ship", marking) is None

    def test_correlate_miss_is_its_own_rejection_reason(self) -> None:
        # given: an order with settings for another account only
        net = _settings_net()
        marking = Marking(
            {
                "orders": [_tok("order", account="A")],
                "settings": [_tok("setting", account="B")],
            }
        )
        engine = _engine()
        ctx = engine._make_ctx(net, "ship", attempt=0)  # pyright: ignore[reportPrivateUsage]

        # when: walking the binding enumeration
        steps = list(engine._binding_candidates(net, "ship", marking, ctx))  # pyright: ignore[reportPrivateUsage]

        # then: the one candidate is a correlate miss, then the walk closes
        assert [step.rejected for step in steps] == [
            _BindingRejection.CORRELATE_MISS,
            _BindingRejection.PRODUCT_MISS,
        ]


class TestInhibitInterplay:
    def test_inhibit_correlate_sees_the_joined_read_token(self) -> None:
        # given: settings joined to the order, and a pause keyed by carrier
        net = _net(
            [
                _arc("orders", "order"),
                _arc("settings", "setting", mode="read", correlate=_SAME_ACCOUNT),
                _arc(
                    "pauses",
                    "pause",
                    mode="inhibit",
                    correlate={"cel": "token.carrier == binding.settings[0].carrier"},
                ),
            ]
        )
        marking = Marking(
            {
                "orders": [_tok("order", account="A"), _tok("order", account="B")],
                "settings": [
                    _tok("setting", account="A", carrier="post"),
                    _tok("setting", account="B", carrier="van"),
                ],
                "pauses": [_tok("pause", carrier="post")],
            }
        )

        # when: selecting a binding
        binding = _engine().select_binding(net, "ship", marking)

        # then: (A, B-settings) misses the join; (A, A-settings) is paused; B ships
        assert _accounts(binding, "orders") == ["B"]
        assert _accounts(binding, "settings") == ["B"]


class TestTimerInterplay:
    def _timed_net(self) -> Net:
        return _net(
            [
                _arc("orders", "order", mode="read"),
                _arc("settings", "setting", mode="read", correlate=_SAME_ACCOUNT),
                _arc("clock", "tick", mode="read"),
            ],
            transition={
                "name": "ship",
                "handler": "ship",
                "timer": {
                    "clock": "clock",
                    "cel": "clock.now >= settings.ship_at",
                    "bind": {"settings": "settings"},
                    "maturity": "settings.ship_at",
                },
            },
        )

    def test_timer_bind_reads_the_correlated_token(self) -> None:
        # given: the A settings mature at 10, the B settings at 50, order B, clock 20
        net = self._timed_net()
        marking = Marking(
            {
                "orders": [_tok("order", account="B")],
                "settings": [
                    _tok("setting", account="A", ship_at=10),
                    _tok("setting", account="B", ship_at=50),
                ],
                "clock": [_tok("tick", now=20)],
            }
        )
        engine = _engine()

        # when: asking for enablement and the next wake
        enabled = engine.enabled_transitions(net, marking)
        maturities = engine.timer_maturities(net, marking)

        # then: the matured A settings never reach the timer; B's 50 is the wake
        assert enabled == []
        assert maturities == (TimerMaturity("ship", "clock", 50),)
