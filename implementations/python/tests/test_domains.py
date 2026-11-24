"""Declared domains are a runtime contract; proof facts are claims (ADR 0037).

A net's ``domains`` name the closed values of a token field. The engine
rejects a deposit (a deposit-contract violation, D3) or an injection
(``ValueError``) of a token of that color whose field is missing or holds
another value. ``proofs`` (final places, declared invariants) only parse and
merge here; ``velocitron prove`` checks them.
"""

from __future__ import annotations

from typing import Any

import pytest
from _journal_fixtures import CapturingJournal

from velocitron_petrinet import merge_nets
from velocitron_engine import (
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_runtime import Engine
from velocitron_engine import DepositViolation
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


def _verdict_net(**extra: Any) -> dict[str, Any]:
    return {
        "name": "gate",
        "places": [
            {"name": "inbox", "accepts": ["job"]},
            {"name": "verdicts", "accepts": ["verdict"]},
        ],
        "transitions": [{"name": "judge", "handler": "judge"}],
        "arcs": [
            {
                "from": {"place": "inbox"},
                "to": {"transition": "judge"},
                "consume": {"type": "job"},
            },
            {
                "from": {"transition": "judge"},
                "to": {"place": "verdicts"},
                "produce": {"type": "verdict", "destination": "verdicts"},
            },
        ],
        "domains": {"verdict.result": ["pass", "hold"], "verdict.meta.level": [1, 2]},
        **extra,
    }


def _judge(data: dict[str, Any]) -> HandlerRegistry:
    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        return {
            "status": "completed",
            "outputTokens": {"verdicts": [Token("verdict", data)]},
            "error": None,
            "metadata": {},
        }

    registry = HandlerRegistry()
    registry.register_transition("judge", handler)
    return registry


def _fire(net: Net, data: dict[str, Any], mode: str = "raise") -> Marking:
    journal = CapturingJournal() if mode != "raise" else None
    engine = Engine(_judge(data), deposit_violation=mode, journal=journal)
    marking = Marking({"inbox": [Token("job", {})]})
    after, _ = engine.fire(net, marking, "judge", attempt=0)
    return after


class TestParsing:
    def test_domains_and_proofs_parse_onto_the_net(self) -> None:
        # given: a net document with domains and proof facts
        document = _verdict_net(
            proofs={
                "final": ["verdicts"],
                "invariants": [{"name": "one", "weights": {"inbox": 1}, "constant": 1}],
            }
        )
        # when: it is parsed
        net = parse_net(document)
        # then: both members land on the model
        assert net.domains == {
            "verdict.result": ["pass", "hold"],
            "verdict.meta.level": [1, 2],
        }
        assert net.proofs is not None
        assert net.proofs.final == [("verdicts",)]
        assert net.proofs.invariants is not None
        assert net.proofs.invariants[0].weights == {"inbox": 1}
        assert net.proofs.invariants[0].constant == 1

    def test_a_domain_must_name_an_accepted_color(self) -> None:
        # given: a domain of a color no place accepts
        document = _verdict_net(domains={"switch.owner": ["main"]})
        # when/then: parsing fails
        with pytest.raises(NetValidationError, match="no place accepts"):
            parse_net(document)

    @pytest.mark.parametrize(
        "proofs",
        [{"final": ["gone"]}, {"invariants": [{"weights": {"gone": 1}}]}],
    )
    def test_proof_facts_must_name_declared_places(self, proofs: Any) -> None:
        # given: a proof fact naming an unknown place
        # when/then: parsing fails
        with pytest.raises(NetValidationError, match="'gone' is not declared"):
            parse_net(_verdict_net(proofs=proofs))

    def test_the_schema_rejects_an_empty_or_repeated_value_list(self) -> None:
        # given/when/then: an empty list and a repeated value are shape errors
        with pytest.raises(NetValidationError):
            parse_net(_verdict_net(domains={"verdict.result": []}))
        with pytest.raises(NetValidationError):
            parse_net(_verdict_net(domains={"verdict.result": ["pass", "pass"]}))


class TestDeposit:
    def test_a_token_inside_every_domain_is_deposited(self) -> None:
        # given: a handler that returns a verdict inside both domains
        net = parse_net(_verdict_net())
        # when: the transition fires
        after = _fire(net, {"result": "hold", "meta": {"level": 2.0}})
        # then: the verdict is deposited (2.0 is the JSON number 2)
        assert [t.data["result"] for t in after["verdicts"]] == ["hold"]

    @pytest.mark.parametrize(
        ("data", "message"),
        [
            (
                {"result": "maybe", "meta": {"level": 1}},
                'holds result = "maybe", outside domain verdict.result: "pass", "hold"',
            ),
            (
                {"meta": {"level": 1}},
                "has no result, which domain verdict.result requires",
            ),
            ({"result": "pass", "meta": {"level": True}}, "holds meta.level = true"),
            ({"result": "pass", "meta": 3}, "has no meta.level"),
        ],
    )
    def test_a_token_outside_a_domain_is_a_deposit_violation(
        self, data: dict[str, Any], message: str
    ) -> None:
        # given: a handler output outside a declared domain
        net = parse_net(_verdict_net())
        # when/then: the deposit is a contract violation naming the field
        with pytest.raises(DepositViolation, match=message.replace("(", r"\(")):
            _fire(net, data)

    def test_record_then_drop_rolls_the_firing_back(self) -> None:
        # given: a net and a handler output outside the domain
        net = parse_net(_verdict_net())
        # when: the engine records and drops violations
        after = _fire(
            net, {"result": "maybe", "meta": {"level": 1}}, "record_then_drop"
        )
        # then: the job token is back and nothing was deposited
        assert len(after["inbox"]) == 1
        assert not after.get("verdicts")


class TestInjection:
    def test_an_injection_outside_a_domain_is_rejected(self) -> None:
        # given: a net with a closed verdict.result
        net = parse_net(_verdict_net())
        engine = Engine(HandlerRegistry())
        # when/then: injecting another value raises before the marking changes
        with pytest.raises(ValueError, match="outside domain verdict.result"):
            engine.inject_token(
                net,
                Marking(),
                "verdicts",
                Token("verdict", {"result": "fail", "meta": {"level": 1}}),
                attempt=0,
            )

    def test_an_injection_inside_the_domains_is_accepted(self) -> None:
        # given: a net with closed verdict fields
        net = parse_net(_verdict_net())
        # when: a valid verdict is injected
        marking, _ = Engine(HandlerRegistry()).inject_token(
            net,
            Marking(),
            "verdicts",
            Token("verdict", {"result": "pass", "meta": {"level": 1}}),
            attempt=0,
        )
        # then: it is in the place
        assert len(marking["verdicts"]) == 1


def _port_net(name: str, direction: str, **extra: Any) -> Net:
    return parse_net(
        {
            "name": name,
            "places": [
                {
                    "name": "edge",
                    "accepts": ["verdict"],
                    "port": {"direction": direction, "type": "verdict"},
                },
                {"name": "inner", "accepts": ["verdict"]},
            ],
            "transitions": [{"name": "move"}],
            "arcs": [
                {
                    "from": {"place": "inner" if direction == "output" else "edge"},
                    "to": {"transition": "move"},
                    "consume": {"type": "verdict"},
                },
                {
                    "from": {"transition": "move"},
                    "to": {"place": "edge" if direction == "output" else "inner"},
                    "produce": {
                        "type": "verdict",
                        "destination": "edge" if direction == "output" else "inner",
                    },
                },
            ],
            **extra,
        }
    )


class TestComposition:
    def test_merge_keeps_domains_and_qualifies_proof_facts(self) -> None:
        # given: a producer and a consumer that declare the same domain
        domains = {"verdict.result": ["pass", "hold"]}
        producer = _port_net(
            "producer",
            "output",
            domains=domains,
            proofs={
                "final": ["edge"],
                "invariants": [{"name": "one", "weights": {"inner": 1, "edge": 1}}],
            },
        )
        consumer = _port_net(
            "consumer", "input", domains=domains, proofs={"final": ["inner"]}
        )
        # when: they are merged with the producer's port wired to the consumer's
        merged = merge_nets(
            {"a": producer, "b": consumer}, [Wire("a", "edge", "b", "edge")]
        )
        # then: one domain stays; the wired final place is no longer final
        assert merged.domains == domains
        assert merged.proofs is not None
        assert merged.proofs.final == [("b.inner",)]
        assert merged.proofs.invariants is not None
        assert merged.proofs.invariants[0].name == "a.one"
        assert merged.proofs.invariants[0].weights == {"a.inner": 1, "a.edge": 1}

    def test_merge_rejects_two_value_sets_for_one_field(self) -> None:
        # given: two nets that disagree about verdict.result
        producer = _port_net("producer", "output", domains={"verdict.result": ["pass"]})
        consumer = _port_net(
            "consumer", "input", domains={"verdict.result": ["pass", "hold"]}
        )
        # when/then: the merge fails and names both nets
        with pytest.raises(
            NetValidationError, match="domain verdict.result differs between a and b"
        ):
            merge_nets({"a": producer, "b": consumer}, [Wire("a", "edge", "b", "edge")])
