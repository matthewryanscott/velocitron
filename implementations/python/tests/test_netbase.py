"""Behavioral tests for the VelocitronNet base class (N4).

Covers the 13-case plan on card V8TJERJO: the ``net_document`` round-trip,
the abc contract, the hash gate, standalone and merged-key adapters, the
failed-on-raise rule, generated handlers, the NotThisActor filter, engine
validation of guards and one-ref-one-transition, the sqlite net revision,
the ASYNC ``HandlerSpec`` path through the Runtime, and the
always-synchronous guard and predicate adapters.

References: ADR 0058 (Decisions 2 and 3); spec/petrinet-language.md.
"""

from __future__ import annotations

import abc
import asyncio
import inspect
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

import velocitron_analysis as prove_module
from velocitron_engine import (
    FiringContext,
    FiringTimestamps,
    TransitionHandlerOutput,
)
from velocitron_journal import (
    NET_REVISION,
    DurableJournal,
    open_database,
)
from velocitron_runtime import Engine
from velocitron_netbase import (
    SYNTH_HANDLER,
    HashMismatch,
    VelocitronNet,
    canonical_net_json,
    handler_spec,
    net_sha256,
)
from velocitron_petrinet import parse_net
from velocitron_engine import (
    HandlerNotFound,
    HandlerRegistry,
)
from velocitron_runtime import RuntimeContext
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

_REPOSITORY_ROOT = Path(__file__).parents[3]
_LADDER = _REPOSITORY_ROOT / "examples" / "capability-ladder"
_PYTHON_ROOT = _REPOSITORY_ROOT / "implementations" / "python"


def _petrinet_files() -> list[Path]:
    """Every checked-in ``.petrinet`` under the ladder and the test fixtures."""
    files = sorted(_LADDER.rglob("*.petrinet"))
    fixtures = (_PYTHON_ROOT / "tests" / "fixtures").rglob("*.petrinet")
    return files + sorted(fixtures)


def _token(type_: str, **data: Any) -> Token:
    return Token(type_, data)


def _registry() -> HandlerRegistry:
    return HandlerRegistry()


def _speak_net() -> Net:
    return prove_module.load_net(
        _LADDER / "12-reading-hour-fragment" / "reading_voice.petrinet"
    )


def _source_sha(net: Net) -> str:
    return net_sha256(net)


def _reading_hour_sha() -> str:
    return _source_sha(_speak_net())


class SpeaksNet(VelocitronNet):
    """A hand-made subclass with the class attrs a generated module carries.

    The net's own shape (``reading_voice.petrinet``):
    ``(request_in) -speak_req-> [start] -speak_token-> (in_flight)`` with two
    inhibits into [start], ``[start] -speak_work-> (work)`` and
    ``(work) -speak_work-> [finish] -utterance-> (utterance_out)`` plus a
    speaking token from (in_flight). Handler refs ``start@speaks`` and
    ``finish@speaks``.
    """

    NET_NAME = "reading_voice"
    SOURCE = "12-reading-hour-fragment/reading_voice.petrinet"
    SOURCE_SHA256 = _reading_hour_sha()
    GUARD_REFS: ClassVar[dict[str, str]] = {}
    PREDICATE_REFS: ClassVar[dict[str, str]] = {}
    GENERATED_METHODS: ClassVar[dict[str, str]] = {}
    INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
        "start": ("request_in", "in_flight", "work"),
        "finish": ("work", "in_flight"),
    }
    OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
        "start": ("in_flight", "work"),
        "finish": ("utterance_out",),
    }
    ASYNC: ClassVar[bool] = False
    HANDLER_REFS: ClassVar[dict[str, str]] = {
        "start@speaks": "fire_start",
        "finish@speaks": "fire_finish",
    }

    def __init__(self, **outputs: list[Token]) -> None:
        super().__init__()
        self._outputs: dict[str, list[Token]] = outputs
        self.calls: list[dict[str, Any]] = []

    def fire_start(
        self, *, request_in: list[Token], in_flight: list[Token], work: list[Token]
    ) -> dict[str, list[Token]]:
        self.calls.append(
            {
                "method": "fire_start",
                "request_in": list(request_in),
                "in_flight": list(in_flight),
                "work": list(work),
            }
        )
        return {
            "in_flight": self._outputs.get("in_flight", []),
            "work": self._outputs.get("work", []),
        }

    def fire_finish(
        self, *, work: list[Token], in_flight: list[Token]
    ) -> dict[str, list[Token]]:
        self.calls.append(
            {"method": "fire_finish", "work": list(work), "in_flight": list(in_flight)}
        )
        return {"utterance_out": self._outputs.get("utterance_out", [])}


def _reading_hour_marking() -> Marking:
    return Marking({"request_in": [_token("speak_req", request=1)]})


# ── 1. net_document round-trips every checked-in net ───────────────────────


@pytest.mark.parametrize(
    "path", _petrinet_files(), ids=lambda p: str(p.relative_to(_REPOSITORY_ROOT))
)
def test_net_document_round_trips_byte_equal(path: Path) -> None:
    # given: a checked-in net and the canonical document bytes it stands for
    net = prove_module.load_net(path)

    # when: rendered canonically, re-parsed, rendered again
    first = canonical_net_json(net)
    again = canonical_net_json(parse_net(first))

    # then: the two renders are byte-equal and the parsed net matches
    assert again == first
    assert parse_net(first) == net
    assert first.endswith("\n")
    assert not first.startswith("﻿")


def test_net_sha256_is_stable_across_loads() -> None:
    # given: the same net file loaded twice
    one = prove_module.load_net(_LADDER / "01-coin-deposit" / "coin-deposit.petrinet")
    two = prove_module.load_net(_LADDER / "01-coin-deposit" / "coin-deposit.petrinet")

    # when: hashed separately
    # then: one digest
    assert net_sha256(one) == net_sha256(two)
    assert len(net_sha256(one)) == 64


# ── 2. the abc contract ────────────────────────────────────────────────────


def test_missing_abstract_method_is_type_error_at_instantiation() -> None:
    # given: the base with one abstract method and a subclass that skips it
    class Base(VelocitronNet):
        @abc.abstractmethod
        def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]: ...

    class SkipsIt(Base):
        pass

    # when: instantiated
    # then: TypeError at construction, naming the missing method
    with pytest.raises(TypeError, match="fire_start"):
        SkipsIt()  # pyright: ignore[reportAbstractUsage] - that IS the test


# ── 3. the hash gate ───────────────────────────────────────────────────────


def test_wrong_sha_raises_hash_mismatch_and_registers_nothing() -> None:
    # given: a subclass whose SOURCE_SHA256 names a different net
    class Wrong(VelocitronNet):
        NET_NAME = "wrong"
        SOURCE = "reading_voice.petrinet"
        SOURCE_SHA256 = "0" * 64
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}

    registry = _registry()
    net = _speak_net()

    # when: registered
    # then: HashMismatch, and the registry still holds only the built-ins
    with pytest.raises(HashMismatch, match="regenerate"):
        Wrong().register_into(registry, net)
    # the registry still holds only the built-ins: any transition lookup misses
    with pytest.raises(HandlerNotFound):
        registry.resolve_transition("anything-that-might-have-landed")


# ── helpers for tests 7-13 ─────────────────────────────────────────────────


def _generated_net() -> Net:
    """A minimal net with one handlerless transition: request_in -> [start]."""

    return Net(
        name="generated",
        places=[
            Place(name="request_in", accepts=["task"]),
            Place(name="done", accepts=["task"]),
        ],
        transitions=[Transition(name="start")],
        arcs=[
            Arc(
                from_place="request_in",
                to_transition="start",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="start",
                to_place="done",
                produce=ProduceTemplate("task", "done"),
            ),
        ],
        initial_marking=Marking({"request_in": [_token("task", n=1)]}),
    )


# ── 4. a standalone leaf fires through the subclass ────────────────────────


def test_standalone_leaf_fires_through_subclass() -> None:
    # given: the reading_voice leaf registered via its subclass
    registry = _registry()
    instance = SpeaksNet(
        in_flight=[_token("speak_token", n=1)],
        work=[_token("speak_work", n=1)],
        utterance_out=[_token("utterance", text="hello")],
    )
    net = instance.register_into(registry, _speak_net()).net
    engine = Engine(registry)

    # when: the engine runs the copy to quiescence
    final = engine.advance(net, _reading_hour_marking())

    # then: both transitions fired through the subclass, and the parameter
    # names the class declared hold the tokens the engine bound
    assert [call["method"] for call in instance.calls] == ["fire_start", "fire_finish"]
    start = instance.calls[0]
    assert [t.data for t in start["request_in"]] == [{"request": 1}]
    # and: the utterance came out the output place
    assert len(final.get("utterance_out", [])) == 1


# ── 5. merged-key translation ──────────────────────────────────────────────


def test_merged_keys_translate_through_binding_names() -> None:
    # given: the wired_pulse composition merged, and a sink subclass that
    # declares its LOCAL input place
    class PulseSinkNet(VelocitronNet):
        NET_NAME = "pulse_sink"
        SOURCE = "10-wired-pulse/pulse_sink.petrinet"
        SOURCE_SHA256 = net_sha256(
            prove_module.load_net(_LADDER / "10-wired-pulse" / "pulse_sink.petrinet")
        )
        HANDLER_REFS: ClassVar[dict[str, str]] = {"receive@sink": "fire_receive"}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"receive": ("pulse_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"receive": ("received",)}
        ASYNC: ClassVar[bool] = False

        def fire_receive(self, *, pulse_in: list[Token]) -> dict[str, list[Token]]:
            self.received_params = {"pulse_in": list(pulse_in)}
            return {
                "received": [
                    Token("receipt", {"echoed": token.data.get("n")})
                    for token in pulse_in
                ]
            }

    merged = prove_module.load_net(_LADDER / "10-wired-pulse" / "wired_pulse.petrinet")
    instance = PulseSinkNet()
    registry = _registry()
    registration = instance.register_into(registry, merged, alias="sink")
    engine = Engine(registry)
    copy = registration.net

    # when: a pulse token arrives at the fused place (the source member's
    # `emit` is another actor's transition in this one-member test; the
    # adapter under test is the sink's), then sink.receive fires
    marking = Marking({"source.pulse_out": [_token("pulse", n=7)]})
    _, record = engine.fire(copy, marking, "sink.receive", attempt=1)

    # then: the method received the tokens the engine keyed under
    # `source.pulse_out` (the one-to-one wire keeps the output port's name)
    # as the local parameter `pulse_in`
    assert record["status"] == "completed"
    assert [t.data for t in instance.received_params["pulse_in"]] == [{"n": 7}]
    # and: the returned `received` tokens landed on the merged destination
    assert [t.data for t in record["outputTokens"]["sink.received"]] == [{"echoed": 7}]


# ── 6. a raise from a method is a failed firing ───────────────────────────


def test_method_raise_becomes_failed_and_keeps_marking() -> None:
    # given: a subclass whose fire_start always raises
    class RaisingNet(SpeaksNet):
        def fire_start(self, **inputs: Any) -> dict[str, list[Token]]:
            raise ValueError("the speaker is muted")

    registry = _registry()
    instance = RaisingNet()
    net = instance.register_into(registry, _speak_net()).net
    engine = Engine(registry)
    marking = _reading_hour_marking()

    # when: start fired
    new_marking, record = engine.fire(net, marking, "start", attempt=1)

    # then: failed with the method's exception type; nothing propagates
    assert record["status"] == "failed"
    assert record["error"] is not None and record["error"]["type"] == "ValueError"
    # and: the marking is unchanged
    assert new_marking.get("request_in", []) == marking.get("request_in", [])


# ── 7. generated handlers fire through the synthesized ref ────────────────


def test_generated_method_fires_through_synth_ref() -> None:
    # given: a net whose `start` has no handler fact, and a subclass with a
    # GENERATED_METHODS entry for it
    class SourceNet(VelocitronNet):
        NET_NAME = "generated"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(_generated_net())
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {"start": "fire_start"}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = False

        def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
            self.saw = list(request_in)
            return {"done": list(request_in)}

    registry = _registry()
    instance = SourceNet()
    net = instance.register_into(registry, _generated_net()).net
    engine = Engine(registry)

    # when: start fired
    _, record = engine.fire(
        net, Marking({"request_in": [_token("task", n=1)]}), "start", attempt=1
    )

    # then: the synthesized ref served it, and the record names the
    # transition, never the ref
    assert record["status"] == "completed"
    assert record["transition"] == "start"
    assert str(SYNTH_HANDLER) not in str(record)
    assert [t.data for t in instance.saw] == [{"n": 1}]


# ── 8. NotThisActor ────────────────────────────────────────────────────────


def test_foreign_transition_fails_not_this_actor() -> None:
    # given: a transition in neither HANDLER_REFS nor GENERATED_METHODS
    class ActorNet(VelocitronNet):
        NET_NAME = "generated"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(_generated_net())
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = False

    registry = _registry()
    net = ActorNet().register_into(registry, _generated_net()).net
    engine = Engine(registry)
    marking = Marking({"request_in": [_token("task", n=1)]})

    # when: the foreign transition fires
    new_marking, record = engine.fire(net, marking, "start", attempt=1)

    # then: failed with the actor-filter error, marking unchanged
    assert record["status"] == "failed"
    assert record["error"] is not None and record["error"]["type"] == "NotThisActor"
    assert new_marking.get("request_in", []) == marking.get("request_in", [])


# ── 9. Engine.validate runs through register_into ─────────────────────────


def test_missing_guard_method_raises_handler_not_found() -> None:
    # given: a net with a guarded transition whose guard method is absent
    class Incomplete(VelocitronNet):
        NET_NAME = "guarded"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(_guarded_net())
        HANDLER_REFS: ClassVar[dict[str, str]] = {"start@guarded": "fire_start"}
        GUARD_REFS: ClassVar[dict[str, str]] = {
            "needs_review": "guard_start"
        }  # no method
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = False

        def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
            return {"done": list(request_in)}

    registry = _registry()

    # when: registered
    # then: HandlerNotFound names the guard ref
    with pytest.raises(HandlerNotFound) as exc:
        Incomplete().register_into(registry, _guarded_net())
    assert exc.value.name == "needs_review"


# ── 10. one ref, one transition ───────────────────────────────────────────


def test_two_transitions_sharing_a_ref_raise_value_error() -> None:
    # given: a hand-built net where two transitions name one handler ref
    class SharedRef(VelocitronNet):
        NET_NAME = "shared"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(_shared_ref_net())
        HANDLER_REFS: ClassVar[dict[str, str]] = {"one_handler": "fire_start"}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
            "start": ("request_in",),
            "finish": ("done",),
        }
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
            "start": ("done",),
            "finish": (),
        }
        ASYNC: ClassVar[bool] = False

        def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
            return {"done": list(request_in)}

    registry = _registry()

    # when: registered
    # then: ValueError naming both transitions
    with pytest.raises(ValueError) as exc:
        SharedRef().register_into(registry, _shared_ref_net())
    message = str(exc.value)
    assert "start" in message and "finish" in message


# ── 11. the sqlite journal gets the net revision ──────────────────────────


def test_durable_journal_records_the_copy(tmp_path: Path) -> None:
    # given: a subclass for a net with a handlerless transition (so the
    # copy carries a synthesized ref) and a DurableJournal
    net = _generated_net()

    class SourceNet(VelocitronNet):
        NET_NAME = "generated"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {"start": "fire_start"}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = False

        def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
            return {"done": list(request_in)}

    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, instance="test")

    # when: registered with the journal attached
    registration = SourceNet().register_into(_registry(), net, journal=journal)

    # then: one net_revision record whose payload parses to the copy (the
    # synthesized ref is an ordinary `handler` value in it)
    revisions = [r for r in journal.records() if r["kind"] == NET_REVISION]
    assert len(revisions) == 1
    reparsed = parse_net(canonical_net_json(registration.net))
    assert reparsed == registration.net
    # and: the recorded payload carries the copy's synthesized ref
    assert any(
        t["handler"].startswith(SYNTH_HANDLER) for t in revisions[0]["transitions"]
    )


# ── 12. the ASYNC HandlerSpec path ────────────────────────────────────────


def _guarded_net() -> Net:
    """A minimal net whose start carries a guard ref."""

    return Net(
        name="guarded",
        places=[
            Place(name="request_in", accepts=["task"]),
            Place(name="done", accepts=["task"]),
        ],
        transitions=[
            Transition(name="start", handler="start@guarded", guard="needs_review")
        ],
        arcs=[
            Arc(
                from_place="request_in",
                to_transition="start",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="start",
                to_place="done",
                produce=ProduceTemplate("task", "done"),
            ),
        ],
        initial_marking=Marking({"request_in": [_token("task", n=1)]}),
    )


def _shared_ref_net() -> Net:
    """A minimal net whose two transitions both name handler ref `one_handler`."""

    return Net(
        name="shared",
        places=[
            Place(name="request_in", accepts=["task"]),
            Place(name="done", accepts=["task"]),
        ],
        transitions=[
            Transition(name="start", handler="one_handler"),
            Transition(name="finish", handler="one_handler"),
        ],
        arcs=[
            Arc(
                from_place="request_in",
                to_transition="start",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="start",
                to_place="done",
                produce=ProduceTemplate("task", "done"),
            ),
            Arc(
                from_place="done",
                to_transition="finish",
                consume=ConsumePattern("task", None, "consume"),
            ),
        ],
        initial_marking=Marking({"request_in": [_token("task", n=1)]}),
    )


def _minimal_async_net(guard: str | None = None) -> Net:
    from velocitron_engine import (
        Arc,
        ConsumePattern,
        Place,
        ProduceTemplate,
        Transition,
    )

    return Net(
        name="async_net",
        places=[
            Place(name="request_in", accepts=["task"]),
            Place(name="done", accepts=["task"]),
        ],
        transitions=[Transition(name="start", handler="start@async", guard=guard)],
        arcs=[
            Arc(
                from_place="request_in",
                to_transition="start",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="start",
                to_place="done",
                produce=ProduceTemplate("task", "done"),
            ),
        ],
        initial_marking=Marking({"request_in": [_token("task", n=1)]}),
    )


def _firing_context() -> FiringContext:
    return FiringContext(
        firingId="async_net/start/1",
        netId="async_net",
        attempt=1,
        timestamps=FiringTimestamps(fired_at=datetime.now(UTC).isoformat()),
    )


def test_async_spec_table_and_runtime_running(tmp_path: Path) -> None:
    # given: a minimal ASYNC subclass
    net = _minimal_async_net()

    class AsyncNet(VelocitronNet):
        NET_NAME = "async_net"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {"start@async": "fire_start"}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = True

        async def fire_start(
            self, *, request_in: list[Token], context: RuntimeContext
        ) -> dict[str, list[Token]]:
            self.context = context
            self.saw = list(request_in)
            return {"done": list(request_in)}

    registry = _registry()
    instance = AsyncNet()

    # when: registered with a default lane
    registration = instance.register_into(registry, net, default_lane="default")

    # then: one spec per ref, the default lane, not blocking
    assert set(registration.handler_specs) == {"start@async"}
    spec = registration.handler_specs["start@async"]
    assert spec.lane == "default"
    assert spec.blocking is False

    # and: the Runtime adapter carries the method's qualname
    adapter_function = spec.handler
    assert "fire_start" in getattr(adapter_function, "__qualname__", "")

    # and: the adapter awaits the method with context as a keyword
    awaited = spec.handler(
        {
            "transitionId": "start",
            "inputTokens": {"request_in": [_token("task", n=1)]},
            "firingContext": _firing_context(),
        },
        RuntimeContext(None, None),  # pyright: ignore[reportArgumentType]
    )
    output: TransitionHandlerOutput = asyncio.run(
        cast(Awaitable[TransitionHandlerOutput], awaited)
    )
    assert output["status"] == "completed"
    done_tokens: list[Token] = output["outputTokens"]["done"]
    assert [token.data for token in done_tokens] == [{"n": 1}]
    assert instance.context is not None


def test_async_missing_lane_raises_value_error(tmp_path: Path) -> None:
    # given: an ASYNC subclass with no decorator and the caller passing no
    # default_lane
    net = _minimal_async_net()

    class AsyncNet(VelocitronNet):
        NET_NAME = "async_net"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {"start@async": "fire_start"}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = True

        async def fire_start(
            self, *, request_in: list[Token], context: RuntimeContext
        ) -> dict[str, list[Token]]:
            return {"done": list(request_in)}

    registry = _registry()

    # when: registered
    # then: ValueError naming the method
    with pytest.raises(ValueError, match="fire_start"):
        AsyncNet().register_into(registry, net)


def test_handler_spec_decorator_overrides_lane(tmp_path: Path) -> None:
    # given: an ASYNC subclass whose method is decorated for the desk lane, blocking
    net = _minimal_async_net()

    class AsyncNet(VelocitronNet):
        NET_NAME = "async_net"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {"start@async": "fire_start"}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = True

        @handler_spec(lane="desk", blocking=True)
        async def fire_start(
            self, *, request_in: list[Token], context: RuntimeContext
        ) -> dict[str, list[Token]]:
            return {"done": list(request_in)}

    registry = _registry()

    # when: registered with a default lane
    registration = AsyncNet().register_into(registry, net, default_lane="default")

    # then: the decorator's facts win
    spec = registration.handler_specs["start@async"]
    assert spec.lane == "desk"
    assert spec.blocking is True


# ── 13. guards stay synchronous under ASYNC ───────────────────────────────


def test_guards_stay_synchronous_under_async(tmp_path: Path) -> None:
    # given: an ASYNC net with a guard, and a class with a plain-def guard
    net = _minimal_async_net(guard="needs_review")

    class AsyncGuarded(VelocitronNet):
        NET_NAME = "async_net"
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {"start@async": "fire_start"}
        GUARD_REFS: ClassVar[dict[str, str]] = {"needs_review": "guard_start"}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("request_in",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"start": ("done",)}
        ASYNC: ClassVar[bool] = True

        async def fire_start(
            self, *, request_in: list[Token], context: RuntimeContext
        ) -> dict[str, list[Token]]:
            return {"done": list(request_in)}

        def guard_start(self, *, request_in: list[Token]) -> bool:
            return True

    registry = _registry()
    instance = AsyncGuarded()
    registration = instance.register_into(registry, net, default_lane="default")

    # when: the guard ref resolved from the registry
    guard = registration.net.transitions[0].guard
    assert guard is not None
    resolved = registry.resolve_guard(guard)

    # then: the guard adapter is a synchronous callable returning the bool
    assert not inspect.iscoroutinefunction(resolved)
    assert (
        resolved(
            {
                "transitionId": "start",
                "inputTokens": {"request_in": [_token("task", n=1)]},
                "firingContext": _firing_context(),
            }
        )
        is True
    )

    # and: an async def guard method is rejected at registration (the
    # stated choice: reject with TypeError — a wrong method KIND is a
    # programming error, not a configuration choice; a missing method
    # raises HandlerNotFound instead)

    async def _async_guard_stub(*, request_in: list[Token]) -> bool:
        return True

    AsyncGuardDef = type(  # pyright: ignore[reportIncompatibleMethodOverride]
        "AsyncGuardDef",
        (AsyncGuarded,),
        {"guard_start": staticmethod(_async_guard_stub)},
    )

    with pytest.raises(TypeError, match="guard_start"):
        AsyncGuardDef().register_into(_registry(), net, default_lane="default")
