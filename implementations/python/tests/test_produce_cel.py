"""Computed produce fallback (``cel`` on produce templates, ADR 0023) tests.

The red-phase test contract for ADR 0023. A produce template may declare
``cel`` (mutually exclusive with literal ``data``): an inline CEL expression
over the single name ``binding`` — the ADR 0017 place-keyed bound-token-data
map (consume- and read-mode arcs) — evaluated at deposit for a template whose
destination/type pair received no handler-supplied token. The object result
becomes the emitted token's ``data``.

These tests pin:

- **Parsing/validation** — ``data`` XOR ``cel`` fails at *parse*
  (``NetValidationError``, validation rule 14), and invalid ``cel`` fails at
  *parse* like every other inline CEL surface (D6) — never at fire.
- **Computed fallback** — the Reisig counter: a transition consuming
  ``{"n": 5}`` with a ``cel`` template emitting ``{"n": binding.… - 1}``
  deposits ``{"n": 4}`` with no handler-supplied tokens.
- **Binding topology** — the environment is place-keyed over consume- AND
  read-mode arcs: a cel referencing two consume places and one read place
  resolves all three; read tokens stay in the marking.
- **Fallback precedence** — a handler token for the pair suppresses the
  computed fallback, exactly like the literal one (Q3: routing contract).
- **Literal regression** — a literal ``data`` template alongside a ``cel``
  template still emits its fixed token.
- **Failure posture** — an eval error (missing field) or a non-object result
  is a deposit-contract violation (D3): atomic rollback, ``DepositViolation``
  raised under the default mode, recorded-and-dropped under
  ``record_then_drop`` with the marking unchanged.

The tests fail until ``cel`` lands in the schema/model, the parser enforces
rule 14 and compiles the expression, and the engine's deposit phase evaluates
it over the binding.

References: ADR 0023; spec/net-schema.md (Q3, rule 14);
spec/firing-semantics.md (b) step 3, D3.
"""

from __future__ import annotations

from typing import Any

import pytest
from _cel_adapters import ADAPTER_IDS, adapters

from velocitron_cel import CelAdapter, get_default_adapter
from velocitron_runtime import Engine
from velocitron_engine import DepositViolation, evaluate_produce_cel

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

from _journal_fixtures import CapturingJournal

# ── Shared helpers ──────────────────────────────────────────────────────


def _tok(t: str, **data: Any) -> Token:
    return Token(type=t, data=dict(data))


def _completed_no_output(inp: Any) -> dict[str, Any]:
    """A completed handler supplying no tokens — every deposit falls back."""
    return {"status": "completed", "outputTokens": {}, "error": None, "metadata": {}}


def _registry_with(
    transition: str, handler: Any = _completed_no_output
) -> HandlerRegistry:
    reg = HandlerRegistry()
    reg.register_transition(transition, handler)
    return reg


# The Reisig vending-machine counter (research note: Figs 1.9-1.11): sell
# consumes the counter token and re-produces it decremented. The produce cel
# is the feature's motivating expression shape.
_DECREMENT = '{"n": binding.counter[0].n - 1}'


def _counter_net(
    *,
    cel: str | None = _DECREMENT,
    data: dict[str, Any] | None = None,
    cel_adapter: CelAdapter | None = None,
) -> Net:
    produce: dict[str, Any] = {"type": "count", "destination": "counter"}
    if cel is not None:
        produce["cel"] = cel
    if data is not None:
        produce["data"] = data
    return parse_net(
        {
            "name": "counter-net",
            "places": [{"name": "counter", "accepts": ["count"]}],
            "transitions": [{"name": "sell", "handler": "sell"}],
            "arcs": [
                {
                    "from": {"place": "counter"},
                    "to": {"transition": "sell"},
                    "consume": {"type": "count"},
                },
                {
                    "from": {"transition": "sell"},
                    "to": {"place": "counter"},
                    "produce": produce,
                },
            ],
        },
        cel_adapter=cel_adapter,
    )


# ── Parsing / validation (rule 14) ──────────────────────────────────────


class TestProduceCelValidation:
    def test_data_and_cel_together_fail_at_parse(self):
        """Rule 14: ``data`` XOR ``cel`` — a template carrying both is
        rejected at ``parse_net``, before any engine work."""
        # given: a counter net whose produce template declares both fallbacks
        # when/then: parsing fails with a NetValidationError
        with pytest.raises(NetValidationError):
            _counter_net(cel=_DECREMENT, data={"n": 0})

    def test_invalid_cel_fails_at_parse_not_fire(self):
        """Rule 14 timing: produce ``cel`` compiles at *parse* (D6) — a
        malformed expression never reaches the engine."""
        # given: a produce cel with a syntax error
        # when/then: parse_net itself raises
        with pytest.raises(NetValidationError):
            _counter_net(cel='{"n": binding.counter[0].n -')

    def test_cel_round_trips_onto_the_template(self):
        """A valid produce ``cel`` parses and lands on the template model."""
        # given/when: a parsed counter net
        net = _counter_net()
        # then: the produce arc's template carries the expression
        produce_arcs = [a for a in net.arcs if a.produce is not None]
        assert len(produce_arcs) == 1
        template = produce_arcs[0].produce
        assert template is not None
        # getattr keeps the red phase type-clean; the field lands in green.
        assert getattr(template, "cel", None) == _DECREMENT
        # and: literal data stays absent (XOR held)
        assert template.data is None


# ── Deposit-phase evaluation ────────────────────────────────────────────


@pytest.mark.parametrize("cel_adapter", adapters(), ids=ADAPTER_IDS)
class TestComputedFallback:
    def test_counter_decrements(self, cel_adapter: CelAdapter):
        """The computed fallback emits a token whose data is the evaluated
        object — the Reisig counter goes 5 -> 4 with a no-output handler."""
        # given: the counter net, a no-output handler, and n=5 on the counter
        net = _counter_net(cel_adapter=cel_adapter)
        engine = Engine(_registry_with("sell"), cel_adapter=cel_adapter)
        marking = Marking({"counter": [_tok("count", n=5)]})

        # when: firing sell
        new_marking, record = engine.fire(net, marking, "sell", attempt=0)

        # then: the consumed token is replaced by the computed one
        assert record["status"] == "completed"
        assert [t.data for t in new_marking["counter"]] == [{"n": 4}]

    def test_binding_covers_consume_and_read_arcs(self, cel_adapter: CelAdapter):
        """The environment is the ADR 0017 binding map: place-keyed lists of
        bound-token data across consume- AND read-mode arcs."""
        # given: a join net — consume from orders and rates, read from config
        net = parse_net(
            {
                "name": "join-net",
                "places": [
                    {"name": "orders", "accepts": ["order"]},
                    {"name": "rates", "accepts": ["rate"]},
                    {"name": "config", "accepts": ["config"]},
                    {"name": "totals", "accepts": ["total"]},
                ],
                "transitions": [{"name": "price", "handler": "price"}],
                "arcs": [
                    {
                        "from": {"place": "orders"},
                        "to": {"transition": "price"},
                        "consume": {"type": "order"},
                    },
                    {
                        "from": {"place": "rates"},
                        "to": {"transition": "price"},
                        "consume": {"type": "rate"},
                    },
                    {
                        "from": {"place": "config"},
                        "to": {"transition": "price"},
                        "consume": {"type": "config", "mode": "read"},
                    },
                    {
                        "from": {"transition": "price"},
                        "to": {"place": "totals"},
                        "produce": {
                            "type": "total",
                            "destination": "totals",
                            "cel": (
                                '{"amount": binding.orders[0].qty * '
                                "binding.rates[0].per_unit + "
                                "binding.config[0].fee}"
                            ),
                        },
                    },
                ],
            },
            cel_adapter=cel_adapter,
        )
        engine = Engine(_registry_with("price"), cel_adapter=cel_adapter)
        marking = Marking(
            {
                "orders": [_tok("order", qty=3)],
                "rates": [_tok("rate", per_unit=10)],
                "config": [_tok("config", fee=7)],
            }
        )

        # when: firing price
        new_marking, record = engine.fire(net, marking, "price", attempt=0)

        # then: all three places resolved in the binding environment
        assert record["status"] == "completed"
        assert [t.data for t in new_marking["totals"]] == [{"amount": 37}]
        # and: the read token was not consumed (ADR 0012)
        assert [t.data for t in new_marking["config"]] == [{"fee": 7}]

    def test_handler_token_wins_over_computed_fallback(self, cel_adapter: CelAdapter):
        """Q3 precedence: a handler-supplied token for the pair suppresses the
        computed fallback, exactly like the literal one."""
        # given: the counter net with a handler that supplies the pair itself
        net = _counter_net(cel_adapter=cel_adapter)

        def _supplies_pair(inp: Any) -> dict[str, Any]:
            return {
                "status": "completed",
                "outputTokens": {"counter": [_tok("count", n=99)]},
                "error": None,
                "metadata": {},
            }

        engine = Engine(_registry_with("sell", _supplies_pair), cel_adapter=cel_adapter)
        marking = Marking({"counter": [_tok("count", n=5)]})

        # when: firing sell
        new_marking, _ = engine.fire(net, marking, "sell", attempt=0)

        # then: only the handler token lands — no computed sibling
        assert [t.data for t in new_marking["counter"]] == [{"n": 99}]

    def test_literal_fallback_regression_alongside_cel(self, cel_adapter: CelAdapter):
        """A literal ``data`` template on another pair still emits its fixed
        token when a ``cel`` template is present on the transition."""
        # given: a net with one cel template and one literal template
        net = parse_net(
            {
                "name": "mixed-net",
                "places": [
                    {"name": "counter", "accepts": ["count"]},
                    {"name": "audit", "accepts": ["mark"]},
                ],
                "transitions": [{"name": "sell", "handler": "sell"}],
                "arcs": [
                    {
                        "from": {"place": "counter"},
                        "to": {"transition": "sell"},
                        "consume": {"type": "count"},
                    },
                    {
                        "from": {"transition": "sell"},
                        "to": {"place": "counter"},
                        "produce": {
                            "type": "count",
                            "destination": "counter",
                            "cel": _DECREMENT,
                        },
                    },
                    {
                        "from": {"transition": "sell"},
                        "to": {"place": "audit"},
                        "produce": {
                            "type": "mark",
                            "destination": "audit",
                            "data": {"fixed": True},
                        },
                    },
                ],
            },
            cel_adapter=cel_adapter,
        )
        engine = Engine(_registry_with("sell"), cel_adapter=cel_adapter)
        marking = Marking({"counter": [_tok("count", n=5)]})

        # when: firing sell
        new_marking, _ = engine.fire(net, marking, "sell", attempt=0)

        # then: both fallbacks emit — computed and literal
        assert [t.data for t in new_marking["counter"]] == [{"n": 4}]
        assert [t.data for t in new_marking["audit"]] == [{"fixed": True}]


# ── Failure posture (D3) ────────────────────────────────────────────────


@pytest.mark.parametrize("cel_adapter", adapters(), ids=ADAPTER_IDS)
class TestProduceCelViolation:
    def test_eval_error_is_deposit_violation_with_rollback(
        self, cel_adapter: CelAdapter
    ):
        """A ``cel`` eval error (missing field) is a deposit-contract
        violation: DepositViolation raised under the default mode, and the
        marking is unchanged (atomic rollback of the tentative consume).

        Construction-bite: the deposit-phase try/except around the produce
        cel evaluation is the only barrier between a backend raise and
        ``fire`` propagating it un-rolled-back; without the violation
        routing, this test errors rather than fails.
        """
        # given: a counter token missing the field the cel dereferences
        net = _counter_net(cel_adapter=cel_adapter)
        engine = Engine(_registry_with("sell"), cel_adapter=cel_adapter)
        marking = Marking({"counter": [_tok("count", wrong_field=5)]})

        # when/then: firing raises DepositViolation
        with pytest.raises(DepositViolation):
            engine.fire(net, marking, "sell", attempt=0)
        # and: the marking is untouched (atomicity)
        assert [t.data for t in marking["counter"]] == [{"wrong_field": 5}]

    def test_non_object_result_is_deposit_violation(self, cel_adapter: CelAdapter):
        """A ``cel`` result that is not a JSON object (here: an int) violates
        the produce contract — token data must be an object."""
        # given: a cel evaluating to a bare integer
        net = _counter_net(cel="binding.counter[0].n - 1", cel_adapter=cel_adapter)
        engine = Engine(_registry_with("sell"), cel_adapter=cel_adapter)
        marking = Marking({"counter": [_tok("count", n=5)]})

        # when/then: firing raises DepositViolation
        with pytest.raises(DepositViolation):
            engine.fire(net, marking, "sell", attempt=0)

    def test_record_then_drop_records_and_leaves_marking(self, cel_adapter: CelAdapter):
        """Under ``record_then_drop`` the violation is recorded through the
        deposit-violation hook and the marking is returned unchanged."""
        # given: an engine with a journal and the drop mode
        net = _counter_net(cel_adapter=cel_adapter)
        journal = CapturingJournal()
        engine = Engine(
            _registry_with("sell"),
            journal=journal,
            deposit_violation="record_then_drop",
            cel_adapter=cel_adapter,
        )
        marking = Marking({"counter": [_tok("count", wrong_field=5)]})

        # when: firing with the eval-error-provoking token
        new_marking, record = engine.fire(net, marking, "sell", attempt=0)

        # then: the violation is recorded, no raise, marking unchanged
        assert record["status"] == "failed"
        assert record["error"] is not None
        assert record["error"]["type"] == "DepositViolation"
        assert [t.data for t in new_marking["counter"]] == [{"wrong_field": 5}]
        # and: it routed through the deposit-violation hook, not record_firing
        assert len(journal.violations) == 1
        assert journal.firings == []

    def test_an_int_plus_a_double_names_both_fields(self, cel_adapter: CelAdapter):
        """CEL never adds an int to a double. The violation names the fields
        whose types differ, so a caller sees which token to change."""
        # given: an int count plus a double step
        net = _counter_net(
            cel='{"n": binding.counter[0].n + binding.counter[0].step}',
            cel_adapter=cel_adapter,
        )
        engine = Engine(_registry_with("sell"), cel_adapter=cel_adapter)
        marking = Marking({"counter": [_tok("count", n=0, step=600.0)]})

        # when: firing
        with pytest.raises(DepositViolation) as raised:
            engine.fire(net, marking, "sell", attempt=0)

        # then: the message names each field with its type
        message = str(raised.value)
        assert "binding.counter[0].n is int 0" in message, message
        assert "binding.counter[0].step is double 600.0" in message, message


# ── Compilation (one program per expression) ───────────────────────────


class _CountingCompiles(CelAdapter):
    """The default backend, counting how often each expression compiles."""

    def __init__(self) -> None:
        self.inner = get_default_adapter()
        self.compiled: list[str] = []

    def compile(self, expr: str) -> Any:
        self.compiled.append(expr)
        return self.inner.compile(expr)

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        return self.inner.eval(compiled, data)


def test_a_produce_cel_compiles_once_across_firings():
    """The deposit evaluates a template's ``cel`` on every firing; the
    program is compiled the first time only."""
    # given: the counter net and an engine whose adapter counts compiles
    counting = _CountingCompiles()
    net = _counter_net()
    engine = Engine(_registry_with("sell"), cel_adapter=counting)
    marking = Marking({"counter": [_tok("count", n=5)]})

    # when: firing sell three times
    for _ in range(3):
        marking, record = engine.fire(net, marking, "sell", attempt=0)
        assert record["status"] == "completed"

    # then: every firing computed its token from one compiled program
    assert [t.data for t in marking["counter"]] == [{"n": 2}]
    assert counting.compiled.count(_DECREMENT) == 1


def test_evaluate_produce_cel_compiles_once_per_adapter():
    """Generated handlers call ``evaluate_produce_cel`` per firing too; each
    adapter compiles an expression once and keeps its own program."""
    # given: two counting adapters
    first, second = _CountingCompiles(), _CountingCompiles()
    binding = {"counter": [{"n": 5}]}

    # when: evaluating the same expression three times with the first
    # and once with the second
    results = [
        evaluate_produce_cel(_DECREMENT, binding, cel_adapter=first) for _ in range(3)
    ]
    other = evaluate_produce_cel(_DECREMENT, binding, cel_adapter=second)

    # then: each adapter compiled it once, and the results agree
    assert results == [{"n": 4}] * 3 and other == {"n": 4}
    assert first.compiled == [_DECREMENT]
    assert second.compiled == [_DECREMENT]
