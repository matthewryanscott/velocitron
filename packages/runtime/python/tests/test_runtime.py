"""The async run loop admits work through an injected registry."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from velocitron_engine import (
    Arc,
    ConsumePattern,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_runtime import HandlerSpec, Lane, Runtime, RuntimeContext, TokenArrival


class _Cel:
    def compile(self, expr: str) -> str:
        return expr

    def eval(self, compiled: str, data: dict[str, Any]) -> bool:
        del compiled, data
        return False


def _completed(place: str, token: Token):
    async def handler(
        inp: TransitionHandlerInput, ctx: RuntimeContext
    ) -> TransitionHandlerOutput:
        del inp, ctx
        return {
            "status": "completed",
            "outputTokens": {place: [token]},
            "error": None,
            "metadata": {},
        }

    return handler


def _net(*transitions: Transition, marking: Marking, arcs: list[Arc], places: list[Place]) -> Net:
    return Net(
        name="runtime",
        places=places,
        transitions=list(transitions),
        arcs=arcs,
        initial_marking=marking,
    )


def test_runtime_rejects_a_handlerless_transition() -> None:
    """Async execution requires a handler spec for every transition."""
    # given: a transition with no handler reference
    net = _net(
        Transition("traditional"),
        places=[],
        arcs=[],
        marking=Marking(),
    )
    # when: constructing a Runtime
    # then: the missing handler is reported before the spec map is compared
    with pytest.raises(ValueError, match=r"transitions without handlers: \['traditional'\]"):
        Runtime(
            net=net,
            handlers={"other": HandlerSpec(_completed("out", Token("job", {})), "main")},
            lanes={"main": 1},
            cel_adapter=_Cel(),
        )


def test_runtime_deposits_one_async_firing() -> None:
    """A reserved firing settles when its handler completes."""
    # given: one token and a handler that deposits a finished token
    net = _net(
        Transition("work", handler="work"),
        places=[Place("inbox", ["job"]), Place("outbox", ["job"])],
        arcs=[
            Arc(
                from_place="inbox",
                to_transition="work",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="work",
                to_place="outbox",
                produce=ProduceTemplate("job", "outbox"),
            ),
        ],
        marking=Marking({"inbox": [Token("job", {"id": 1})]}),
    )
    runtime = Runtime(
        net=net,
        handlers={
            "work": HandlerSpec(_completed("outbox", Token("job", {"id": 1, "done": True})), "main")
        },
        lanes={"main": Lane(1)},
        cel_adapter=_Cel(),
    )

    async def play() -> None:
        # when: the run loop admits the enabled transition
        await runtime.start()
        await runtime.wait_idle()
        await runtime.stop()

    asyncio.run(play())
    # then: the consumed token is deposited as the handler's output
    assert list(runtime.marking.get("inbox", ())) == []
    deposited = list(runtime.marking.get("outbox", ()))
    assert deposited[0].data == {"id": 1, "done": True}


def test_runtime_uses_the_injected_firing_policy() -> None:
    """Conflicting candidates are chosen by the registry's firing policy."""
    # given: two transitions that consume the same token, with priorities
    seen: list[str] = []

    def handler(name: str):
        async def run(
            inp: TransitionHandlerInput, ctx: RuntimeContext
        ) -> TransitionHandlerOutput:
            del ctx
            seen.append(inp["transitionId"])
            return {
                "status": "completed",
                "outputTokens": {"out": [Token("job", {"by": name})]},
                "error": None,
                "metadata": {},
            }

        return run

    net = _net(
        Transition("low", handler="low", priority=1),
        Transition("high", handler="high", priority=5),
        places=[Place("inbox", ["job"]), Place("out", ["job"])],
        arcs=[
            Arc(
                from_place="inbox",
                to_transition="low",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="inbox",
                to_transition="high",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="low",
                to_place="out",
                produce=ProduceTemplate("job", "out"),
            ),
            Arc(
                from_transition="high",
                to_place="out",
                produce=ProduceTemplate("job", "out"),
            ),
        ],
        marking=Marking({"inbox": [Token("job", {"id": 1})]}),
    )
    registry = HandlerRegistry()
    runtime = Runtime(
        net=net,
        handlers={
            "low": HandlerSpec(handler("low"), "main"),
            "high": HandlerSpec(handler("high"), "main"),
        },
        lanes={"main": 1},
        registry=registry,
        policy="priority",
        cel_adapter=_Cel(),
    )

    async def play() -> None:
        # when: the run loop admits one of the conflicting transitions
        await runtime.start()
        await runtime.wait_idle()
        await runtime.stop()

    asyncio.run(play())
    # then: the priority policy selects the higher-priority transition
    assert seen == ["high"]
    assert list(runtime.marking["out"])[0].data == {"by": "high"}


def test_cancel_scope_fails_the_other_firing_and_restores_its_token() -> None:
    """ctx.cancel stops other firings in that scope."""
    # given: two independent firings that share a scope
    release = asyncio.Event()
    started = asyncio.Event()

    async def slow(
        inp: TransitionHandlerInput, ctx: RuntimeContext
    ) -> TransitionHandlerOutput:
        del inp, ctx
        started.set()
        await release.wait()
        return {
            "status": "completed",
            "outputTokens": {"slow_out": [Token("job", {"done": True})]},
            "error": None,
            "metadata": {},
        }

    async def stopper(
        inp: TransitionHandlerInput, ctx: RuntimeContext
    ) -> TransitionHandlerOutput:
        del inp
        await started.wait()
        cancelled = ctx.cancel(scope="job")
        assert cancelled.cancelled == 1
        return {
            "status": "completed",
            "outputTokens": {"stop_out": [Token("job", {"done": True})]},
            "error": None,
            "metadata": {},
        }

    def scope(_inp: TransitionHandlerInput) -> str:
        return "job"

    net = _net(
        Transition("slow", handler="slow"),
        Transition("stop", handler="stop"),
        places=[
            Place("slow_in", ["job"]),
            Place("stop_in", ["job"]),
            Place("slow_out", ["job"]),
            Place("stop_out", ["job"]),
        ],
        arcs=[
            Arc(
                from_place="slow_in",
                to_transition="slow",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="stop_in",
                to_transition="stop",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="slow",
                to_place="slow_out",
                produce=ProduceTemplate("job", "slow_out"),
            ),
            Arc(
                from_transition="stop",
                to_place="stop_out",
                produce=ProduceTemplate("job", "stop_out"),
            ),
        ],
        marking=Marking({
            "slow_in": [Token("job", {"id": "slow"})],
            "stop_in": [Token("job", {"id": "stop"})],
        }),
    )
    runtime = Runtime(
        net=net,
        handlers={
            "slow": HandlerSpec(slow, "main", scope=scope),
            "stop": HandlerSpec(stopper, "main", scope=scope),
        },
        lanes={"main": 2},
        cel_adapter=_Cel(),
    )

    async def play() -> None:
        # when: the stopper cancels the other firing in the scope
        await runtime.start()
        await runtime.wait_idle()
        await runtime.stop()

    asyncio.run(play())
    # then: the cancelled firing's token is restored and the stopper deposits
    assert list(runtime.marking.get("slow_out", ())) == []
    assert list(runtime.marking["slow_in"])[0].data == {"id": "slow"}
    assert list(runtime.marking["stop_out"])[0].data == {"done": True}


def test_inject_admits_a_later_arrival() -> None:
    """An external arrival is admitted once no firing writes that place."""
    # given: an empty inbox and a handler for the arrival
    net = _net(
        Transition("work", handler="work"),
        places=[Place("inbox", ["job"]), Place("outbox", ["job"])],
        arcs=[
            Arc(
                from_place="inbox",
                to_transition="work",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="work",
                to_place="outbox",
                produce=ProduceTemplate("job", "outbox"),
            ),
        ],
        marking=Marking(),
    )
    runtime = Runtime(
        net=net,
        handlers={
            "work": HandlerSpec(_completed("outbox", Token("job", {"id": 7, "done": True})), "main")
        },
        lanes={"main": 1},
        cel_adapter=_Cel(),
    )

    async def play() -> None:
        await runtime.start()
        # when: the caller injects the token the transition consumes
        await runtime.inject(TokenArrival("inbox", Token("job", {"id": 7})))
        await runtime.wait_idle()
        await runtime.stop()

    asyncio.run(play())
    # then: the injected token was consumed and the output deposited
    assert list(runtime.marking.get("inbox", ())) == []
    assert list(runtime.marking["outbox"])[0].data["id"] == 7
