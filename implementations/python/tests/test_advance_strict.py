"""Strict advance and strict fire: raise on a conflict or a failed attempt.

A net whose choices are proved (choice coverage) never enables two
transitions at once; ``advance(..., strict=True)`` turns that proof into a
run-time check instead of letting the firing policy pick one, and stops on a
failed attempt instead of retrying it. ``fire(..., strict=True)`` raises on
its failed attempt the same way. Either exception carries the marking the
run stopped at.
"""

from __future__ import annotations

import pytest

from velocitron_engine import (
    PRIORITY_FIRING_POLICY,
    Conflict,
    FailedAttempt,
    HandlerRegistry,
    Marking,
    Token,
    TransitionHandler,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_petrinet import parse_petrinet_text
from velocitron_runtime import Engine

_SPLIT = """\
net split

(asked) -job-> [a] -job-> (done)
(asked) -job-> [b] -job-> (done)
[a] handler "a"
[b] handler "b"
"""


def _moves_to(place: str) -> TransitionHandler:
    def move(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        tokens = [token for tokens in inp["inputTokens"].values() for token in tokens]
        return {
            "status": "completed",
            "outputTokens": {place: tokens},
            "error": None,
            "metadata": {},
        }

    return move


def _failed(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    del inp
    return {
        "status": "failed",
        "outputTokens": {},
        "error": {"type": "Boom", "message": "no"},
        "metadata": {},
    }


def _registry(
    a: TransitionHandler | None = None, b: TransitionHandler | None = None
) -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register_transition("a", a or _moves_to("done"))
    registry.register_transition("b", b or _moves_to("done"))
    return registry


def _asked() -> Marking:
    return Marking({"asked": [Token("job", {"n": 1})]})


def test_strict_advance_raises_on_a_conflict_and_fires_nothing():
    # given: one job that both [a] and [b] can take
    net = parse_petrinet_text(_SPLIT)
    engine = Engine(_registry())
    # when/then:
    with pytest.raises(Conflict) as raised:
        engine.advance(net, _asked(), strict=True)
    assert raised.value.transitions == ("a", "b")
    assert "split: [a], [b] are enabled at once" in str(raised.value)
    # and: the default advance still lets first-found pick
    final = engine.advance(net, _asked())
    assert [t.data for t in final["done"]] == [{"n": 1}]


def test_strict_advance_raises_on_a_failed_attempt():
    # given: [a] alone is enabled, and its handler fails
    net = parse_petrinet_text(
        _SPLIT.replace("(asked) -job-> [b]", "(other) -job-> [b]")
    )
    engine = Engine(_registry(a=_failed))
    # when/then:
    with pytest.raises(FailedAttempt) as raised:
        engine.advance(net, _asked(), strict=True)
    assert raised.value.record["transition"] == "a"
    assert raised.value.record["status"] == "failed"
    assert "split: [a] failed: Boom: no" in str(raised.value)


def test_strict_advance_fires_a_conflict_free_net_to_quiescence():
    # given: [a] then [b], one at a time
    net = parse_petrinet_text(
        "net chain\n\n"
        "(asked) -job-> [a] -job-> (middle)\n"
        "(middle) -job-> [b] -job-> (done)\n"
        '[a] handler "a"\n[b] handler "b"\n'
    )
    engine = Engine(_registry(a=_moves_to("middle")))
    # when:
    final = engine.advance(net, _asked(), strict=True)
    # then:
    assert [t.data for t in final["done"]] == [{"n": 1}]
    assert list(final.get("asked", ())) == list(final.get("middle", ())) == []


def test_strict_advance_accepts_a_conflict_the_priority_policy_resolves():
    # given: [b] outranks [a] under the priority policy
    net = parse_petrinet_text(_SPLIT + "[b] priority 1\n")
    engine = Engine(_registry(a=_failed), policy=PRIORITY_FIRING_POLICY)
    # when:
    final = engine.advance(net, _asked(), strict=True)
    # then: [b] fired, and a tie at the top would still raise
    assert [t.data for t in final["done"]] == [{"n": 1}]
    tied = parse_petrinet_text(_SPLIT + "[a] priority 1\n[b] priority 1\n")
    with pytest.raises(Conflict):
        engine.advance(tied, _asked(), strict=True)


class _Gone(Exception):
    pass


def _raised(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    del inp
    return {
        "status": "failed",
        "outputTokens": {},
        "error": {"type": "_Gone", "message": "the VM is gone"},
        "metadata": {},
        "exception": _Gone("the VM is gone"),
    }


_CHAIN = (
    "net chain\n\n"
    "(asked) -job-> [a] -job-> (middle)\n"
    "(middle) -job-> [b] -job-> (done)\n"
    '[a] handler "a"\n[b] handler "b"\n'
)


def test_strict_fire_raises_from_the_exception_the_handler_gave():
    # given: [a]'s handler fails with the caller's own error
    net = parse_petrinet_text(_CHAIN)
    engine = Engine(_registry(a=_raised))
    # when:
    with pytest.raises(FailedAttempt) as raised:
        engine.fire(net, _asked(), "a", attempt=0, strict=True)
    # then: the handler's exception is the cause, the marking is unchanged
    assert isinstance(raised.value.__cause__, _Gone)
    assert raised.value.record["transition"] == "a"
    assert raised.value.marking == _asked()
    # and: a fire that is not strict still returns the failed record
    marking, record = engine.fire(net, _asked(), "a", attempt=0)
    assert record["status"] == "failed" and marking == _asked()


def test_strict_fire_raises_on_a_transition_that_is_not_enabled():
    # given: nothing in (middle)
    net = parse_petrinet_text(_CHAIN)
    engine = Engine(_registry())
    # when/then: no handler ran, so there is no cause
    with pytest.raises(FailedAttempt) as raised:
        engine.fire(net, _asked(), "b", attempt=0, strict=True)
    assert raised.value.__cause__ is None
    error = raised.value.record["error"]
    assert error is not None
    assert error["type"] == "NotEnabled"


def test_strict_fire_returns_a_completed_firing():
    # given:
    net = parse_petrinet_text(_CHAIN)
    engine = Engine(_registry(a=_moves_to("middle")))
    # when:
    marking, record = engine.fire(net, _asked(), "a", attempt=0, strict=True)
    # then:
    assert record["status"] == "completed"
    assert [t.data for t in marking["middle"]] == [{"n": 1}]


def test_a_failed_attempt_carries_the_marking_the_advance_reached():
    # given: [a] moves the job on, then [b] fails
    net = parse_petrinet_text(_CHAIN)
    engine = Engine(_registry(a=_moves_to("middle"), b=_raised))
    # when:
    with pytest.raises(FailedAttempt) as raised:
        engine.advance(net, _asked(), strict=True)
    # then: the marking is where [a] left it, unchanged by [b]'s attempt
    assert [t.data for t in raised.value.marking["middle"]] == [{"n": 1}]
    assert list(raised.value.marking.get("asked", ())) == []


def test_a_conflict_carries_the_marking_the_advance_reached():
    # given: [a] moves the job on, then [b] and [c] both can take it
    net = parse_petrinet_text(
        _CHAIN + '(middle) -job-> [c] -job-> (done)\n[c] handler "b"\n'
    )
    engine = Engine(_registry(a=_moves_to("middle")))
    # when:
    with pytest.raises(Conflict) as raised:
        engine.advance(net, _asked(), strict=True)
    # then: nothing fired at the marking it raised on
    assert raised.value.transitions == ("b", "c")
    assert [t.data for t in raised.value.marking["middle"]] == [{"n": 1}]
