"""Fire, enablement, and symbolic advance without the umbrella package."""

from __future__ import annotations

from typing import Any

import pytest

from velocitron_engine import (
    Arc,
    ConsumePattern,
    Engine,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    Predicate,
    ProduceTemplate,
    Token,
    Transition,
    TransitionHandlerInput,
    TransitionHandlerOutput,
    symbolic_outputs,
)
from velocitron_engine import journal as journal_mod


class _CountingCel:
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, expr: str) -> str:
        self.calls += 1
        return expr

    def eval(self, compiled: str, data: dict[str, Any]) -> bool:
        self.calls += 1
        del compiled, data
        return False


def _dump(marking: Marking) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    return {
        place: [(token.type, dict(token.data)) for token in tokens]
        for place, tokens in marking.items()
    }


def _move(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    token = inp["inputTokens"]["src"][0]
    return {
        "status": "completed",
        "outputTokens": {
            "dst": [
                Token(
                    "job",
                    {"id": token.data["id"], "kind": token.data["kind"], "done": True},
                )
            ]
        },
        "error": None,
        "metadata": {},
    }


def _places() -> list[Place]:
    return [Place("src", ["job"]), Place("dst", ["job"])]


def _move_net(predicate: Predicate | None) -> Net:
    return Net(
        name="move",
        places=_places(),
        transitions=[Transition("move", handler="move")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="move",
                consume=ConsumePattern("job", predicate, "consume"),
            ),
            Arc(
                from_transition="move",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
    )


def test_fire_moves_the_token_without_calling_cel() -> None:
    # given: a bound transition and an adapter that records every call
    adapter = _CountingCel()
    registry = HandlerRegistry()
    registry.register_transition("move", _move)
    engine = Engine(registry, cel_adapter=adapter)
    net = _move_net(None)
    marking = Marking({"src": [Token("job", {"id": 1, "kind": "go"})]})
    # when: the engine fires the only enabled transition
    enabled = engine.enabled_transitions(net, marking)
    moved, record = engine.fire(net, marking, "move", attempt=0)
    # then: the token is deposited and the adapter was not consulted
    assert enabled == ["move"]
    assert record["status"] == "completed"
    assert _dump(moved)["src"] == []
    assert _dump(moved)["dst"] == [("job", {"id": 1, "kind": "go", "done": True})]
    assert adapter.calls == 0


def test_string_equality_filters_without_a_backend() -> None:
    # given: two tokens and an exact string predicate
    adapter = _CountingCel()
    registry = HandlerRegistry()
    registry.register_transition("move", _move)
    engine = Engine(registry, cel_adapter=adapter)
    net = _move_net(Predicate(cel='kind == "go"', handler=None))
    stay = Token("job", {"id": 2, "kind": "stay"})
    go = Token("job", {"id": 1, "kind": "go"})
    marking = Marking({"src": [stay, go]})
    # when: enablement and fire use the string-equality fast path
    blocked = engine.enabled_transitions(net, Marking({"src": [stay]}))
    enabled = engine.enabled_transitions(net, marking)
    moved, record = engine.fire(net, marking, "move", attempt=0)
    # then: only the matching token moves, and the adapter is unused
    assert blocked == []
    assert enabled == ["move"]
    assert record["status"] == "completed"
    assert _dump(moved)["src"] == [("job", {"id": 2, "kind": "stay"})]
    assert _dump(moved)["dst"] == [("job", {"id": 1, "kind": "go", "done": True})]
    assert adapter.calls == 0


def test_symbolic_advance_carries_the_consumed_token() -> None:
    # given: a handlerless transition whose produce template is not net-filled
    adapter = _CountingCel()
    engine = Engine(HandlerRegistry(), cel_adapter=adapter)
    net = Net(
        name="carry",
        places=_places(),
        transitions=[Transition("go")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="go",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="go",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
    )
    marking = Marking({"src": [Token("job", {"id": 7})]})
    # when: advance asks the symbolic provider for outputs
    outcome = engine.advance(net, marking, outputs=symbolic_outputs)
    # then: the consumed token is carried and no CEL backend ran
    assert len(outcome.firings) == 1
    assert outcome.firings[0][0]["status"] == "completed"
    assert _dump(outcome.marking)["src"] == []
    assert _dump(outcome.marking)["dst"] == [("job", {"id": 7})]
    assert adapter.calls == 0


def test_engine_requires_an_injected_adapter() -> None:
    # given: a registry and no adapter
    registry = HandlerRegistry()
    # when: the engine is constructed without one
    # then: construction fails before any firing
    with pytest.raises(ValueError, match="cel_adapter is required"):
        Engine(registry)


def test_journal_durability_is_not_in_this_package() -> None:
    # given: the journal module copied into the package
    # then: record shapes are present and storage/replay are not
    assert hasattr(journal_mod, "Journal")
    assert hasattr(journal_mod, "FiringRecord")
    assert not hasattr(journal_mod, "JsonlJournal")
    assert not hasattr(journal_mod, "replay_events")
    assert not hasattr(journal_mod, "replay_records")
