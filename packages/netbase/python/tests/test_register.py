"""A hand-written VelocitronNet registers without the umbrella."""

from __future__ import annotations

from typing import Any

import pytest

from velocitron_codegen import net_sha256 as codegen_net_sha256
from velocitron_engine import (
    Arc,
    ConsumePattern,
    Engine,
    FailedAttempt,
    HandlerNotFound,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
)
from velocitron_netbase import (
    SYNTH_HANDLER,
    HashMismatch,
    VelocitronNet,
    net_sha256,
)


class _Cel:
    def compile(self, expr: str) -> str:
        return expr

    def eval(self, compiled: str, data: dict[str, Any]) -> bool:
        del compiled, data
        return False


def _net() -> Net:
    return Net(
        name="move",
        places=[Place("src", ["job"]), Place("dst", ["job"])],
        transitions=[Transition("move", handler="move@move")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="move",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="move",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
        initial_marking=Marking(),
    )


class _Move(VelocitronNet):
    NET_NAME = "move"
    SOURCE = "move.petrinet"
    SOURCE_SHA256 = net_sha256(_net())
    HANDLER_REFS = {"move@move": "fire_move"}
    INPUT_PLACES = {"move": ("src",)}
    OUTPUT_PLACES = {"move": ("dst",)}

    def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
        self.saw = list(src)
        return {"dst": [Token("job", {"done": True})]}


def test_digest_matches_the_generator() -> None:
    # given: one net
    net = _net()

    # then: registration and codegen share the prefix and the digest
    assert SYNTH_HANDLER == "velocitron:synth:"
    assert net_sha256(net) == codegen_net_sha256(net)
    assert net_sha256 is codegen_net_sha256


def test_wrong_digest_registers_nothing() -> None:
    # given: a subclass whose digest does not match the net
    class Wrong(_Move):
        SOURCE_SHA256 = "0" * 64

    registry = HandlerRegistry()

    # when: registered
    # then: HashMismatch, and no transition handler landed
    with pytest.raises(HashMismatch, match="regenerate"):
        Wrong().register_into(registry, _net())
    with pytest.raises(HandlerNotFound):
        registry.resolve_transition("move@move")


def test_register_into_serves_the_method() -> None:
    # given: a subclass whose digest matches the net
    registry = HandlerRegistry()
    instance = _Move()

    # when: registered and fired
    copy = instance.register_into(registry, _net()).net
    engine = Engine(registry, cel_adapter=_Cel())
    final = engine.advance(copy, Marking({"src": [Token("job", {"n": 1})]}))

    # then: the method saw the consumed token and the produce place holds the result
    assert [token.data for token in instance.saw] == [{"n": 1}]
    assert [token.data for token in final["dst"]] == [{"done": True}]
    assert list(final.get("src", ())) == []


def test_a_subclass_that_skips_the_base_init_still_evaluates_data_cel() -> None:
    # given: a subclass with its own __init__, which a generated pure body
    #   (a `data cel` output) evaluates through the default adapter
    class Own(_Move):
        def __init__(self) -> None:
            self.state = "own"

        def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
            data = self._cel("{'n': binding.src[0].n, 'done': true}", {"src": src})
            return {"dst": [Token("job", data)]}

    registry = HandlerRegistry()
    copy = Own().register_into(registry, _net()).net
    engine = Engine(registry, cel_adapter=_Cel())

    # when: fired
    final = engine.advance(copy, Marking({"src": [Token("job", {"n": 1})]}))

    # then: the firing completed with the evaluated data
    assert [token.data for token in final.get("dst", ())] == [{"n": 1, "done": True}]


class _Gone(Exception):
    """A caller's own error type."""


def test_a_strict_advance_raises_from_the_exception_the_method_raised() -> None:
    # given: a method that raises the caller's own error
    class Raises(_Move):
        def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
            raise _Gone("the VM is gone")

    registry = HandlerRegistry()
    copy = Raises().register_into(registry, _net()).net
    engine = Engine(registry, cel_adapter=_Cel())
    marking = Marking({"src": [Token("job", {"n": 1})]})

    # when: a strict advance fires it
    with pytest.raises(FailedAttempt) as raised:
        engine.advance(copy, marking, strict=True)

    # then: the method's own exception is the cause, and the record says what
    #   the journal got (no exception object in it)
    cause = raised.value.__cause__
    assert isinstance(cause, _Gone) and str(cause) == "the VM is gone"
    assert raised.value.record["error"] == {
        "type": "_Gone",
        "message": "the VM is gone",
    }
    assert "exception" not in raised.value.record


def test_a_generated_body_adding_an_int_to_a_double_names_both_fields() -> None:
    # given: a pure body whose `data cel` adds the token's int to its double
    class Adds(_Move):
        def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
            data = self._cel(
                "{'n': binding.src[0].n + binding.src[0].step}", {"src": src}
            )
            return {"dst": [Token("job", data)]}

    registry = HandlerRegistry()
    copy = Adds().register_into(registry, _net()).net
    engine = Engine(registry, cel_adapter=_Cel())
    marking = Marking({"src": [Token("job", {"n": 0, "step": 600.0})]})

    # when: fired
    _, record = engine.fire(copy, marking, "move", attempt=0)

    # then: the failed record names each field with its type
    assert record["error"] is not None
    message = record["error"]["message"]
    assert "binding.src[0].n is int 0" in message, message
    assert "binding.src[0].step is double 600.0" in message, message
