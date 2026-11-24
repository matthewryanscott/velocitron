"""The packaged engine agrees with the implementation on fire and symbolic advance."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from velocitron_runtime import Engine as RuntimeEngine
import velocitron_engine as impl_engine
import velocitron_engine as impl_outputs
import velocitron_engine as impl_registry
import velocitron_engine as impl_schema

_PKG_SRC = (
    Path(__file__).resolve().parents[3] / "packages" / "engine" / "python" / "src"
)
sys.path.insert(0, str(_PKG_SRC))
import velocitron_engine as packaged  # noqa: E402


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


def _dump(marking: Any) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    return {
        place: [(token.type, dict(token.data)) for token in tokens]
        for place, tokens in marking.items()
    }


def _api(source: Any, registry: Any, outputs: Any) -> SimpleNamespace:
    return SimpleNamespace(
        Arc=source.Arc,
        ConsumePattern=source.ConsumePattern,
        Engine=source.Engine if hasattr(source, "Engine") else None,
        HandlerRegistry=registry.HandlerRegistry,
        Marking=source.Marking,
        Net=source.Net,
        Place=source.Place,
        Predicate=source.Predicate,
        ProduceTemplate=source.ProduceTemplate,
        Token=source.Token,
        Transition=source.Transition,
        symbolic_outputs=outputs.symbolic_outputs,
    )


def _move(token_type: Any, inp: dict[str, Any]) -> dict[str, Any]:
    token = inp["inputTokens"]["src"][0]
    return {
        "status": "completed",
        "outputTokens": {
            "dst": [
                token_type(
                    "job",
                    {"id": token.data["id"], "kind": token.data["kind"], "done": True},
                )
            ]
        },
        "error": None,
        "metadata": {},
    }


def _run(api: SimpleNamespace) -> dict[str, Any]:
    plain_adapter = _CountingCel()
    predicate_adapter = _CountingCel()
    symbolic_adapter = _CountingCel()
    places = [api.Place("src", ["job"]), api.Place("dst", ["job"])]
    consume = api.Arc(
        from_place="src",
        to_transition="move",
        consume=api.ConsumePattern("job", None, "consume"),
    )
    produce = api.Arc(
        from_transition="move",
        to_place="dst",
        produce=api.ProduceTemplate("job", "dst"),
    )
    plain = api.Net(
        name="move",
        places=places,
        transitions=[api.Transition("move", handler="move")],
        arcs=[consume, produce],
    )
    filtered = api.Net(
        name="move",
        places=places,
        transitions=[api.Transition("move", handler="move")],
        arcs=[
            api.Arc(
                from_place="src",
                to_transition="move",
                consume=api.ConsumePattern(
                    "job", api.Predicate(cel='kind == "go"', handler=None), "consume"
                ),
            ),
            produce,
        ],
    )
    carry = api.Net(
        name="carry",
        places=places,
        transitions=[api.Transition("go")],
        arcs=[
            api.Arc(
                from_place="src",
                to_transition="go",
                consume=api.ConsumePattern("job", None, "consume"),
            ),
            api.Arc(
                from_transition="go",
                to_place="dst",
                produce=api.ProduceTemplate("job", "dst"),
            ),
        ],
    )
    registry = api.HandlerRegistry()
    registry.register_transition("move", lambda inp: _move(api.Token, inp))
    engine = api.Engine(registry, cel_adapter=plain_adapter)
    moved, record = engine.fire(
        plain,
        api.Marking({"src": [api.Token("job", {"id": 1, "kind": "go"})]}),
        "move",
        attempt=0,
    )
    filtered_engine = api.Engine(api.HandlerRegistry(), cel_adapter=predicate_adapter)
    filtered_engine.registry.register_transition(
        "move", lambda inp: _move(api.Token, inp)
    )
    stay = api.Token("job", {"id": 2, "kind": "stay"})
    go = api.Token("job", {"id": 1, "kind": "go"})
    chosen, chosen_record = filtered_engine.fire(
        filtered,
        api.Marking({"src": [stay, go]}),
        "move",
        attempt=0,
    )
    outcome = api.Engine(api.HandlerRegistry(), cel_adapter=symbolic_adapter).advance(
        carry,
        api.Marking({"src": [api.Token("job", {"id": 7})]}),
        outputs=api.symbolic_outputs,
    )
    return {
        "plain": _dump(moved),
        "plain_status": record["status"],
        "plain_calls": plain_adapter.calls,
        "filtered": _dump(chosen),
        "filtered_status": chosen_record["status"],
        "filtered_calls": predicate_adapter.calls,
        "symbolic": _dump(outcome.marking),
        "symbolic_status": outcome.firings[0][0]["status"],
        "symbolic_steps": len(outcome.firings),
        "symbolic_calls": symbolic_adapter.calls,
    }


def test_packaged_engine_matches_the_implementation() -> None:
    # given: the same three nets on the implementation engine and the package
    implementation = _api(impl_schema, impl_registry, impl_outputs)
    implementation.Engine = RuntimeEngine
    package = _api(packaged, packaged, packaged)
    package.Engine = packaged.Engine
    # when: both fire, filter by exact string equality, and advance symbolically
    left = _run(implementation)
    right = _run(package)
    # then: markings, statuses, and the unused-adapter counts agree
    assert left == right
    assert left["plain_status"] == "completed"
    assert left["plain"]["dst"] == [("job", {"id": 1, "kind": "go", "done": True})]
    assert left["filtered"]["src"] == [("job", {"id": 2, "kind": "stay"})]
    assert left["symbolic"]["dst"] == [("job", {"id": 7})]
    assert left["symbolic_steps"] == 1
    assert left["plain_calls"] == 0
    assert left["filtered_calls"] == 0
    assert left["symbolic_calls"] == 0
