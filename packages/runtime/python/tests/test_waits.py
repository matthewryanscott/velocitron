"""Intended waits are an annotation the engine does not read."""

from __future__ import annotations

from typing import Any

from velocitron_engine import Net, Place, Transition
from velocitron_runtime import holds, intended_waits, wait_problems


class _Cel:
    def __init__(self) -> None:
        self.compiled: list[str] = []

    def compile(self, expr: str) -> str:
        if expr == "???":
            raise ValueError("syntax")
        self.compiled.append(expr)
        return expr

    def eval(self, compiled: str, data: dict[str, Any]) -> bool:
        del data
        return compiled == "true"


def test_intended_wait_holds_when_the_condition_is_true() -> None:
    """A well-formed wait is reported only when its CEL condition is true."""
    # given: one wait whose condition the adapter accepts
    transition = Transition(
        "start",
        handler="start",
        annotations={"wait": {"when": "true", "for": "a reply"}},
    )
    adapter = _Cel()
    # when: the wait is read and evaluated
    found = intended_waits(transition)
    held = holds(found[0], {}, {}, adapter=adapter)
    # then: the annotation is the wait, and the true condition holds
    assert [(item.when, item.reason) for item in found] == [("true", "a reply")]
    assert held is True
    assert adapter.compiled == ["true"]


def test_a_malformed_wait_is_a_problem_and_declares_no_wait() -> None:
    """Validation reports a bad shape, and coverage still sees a gap."""
    # given: a wait entry missing the reason
    transition = Transition(
        "start",
        handler="start",
        annotations={"wait": {"when": "true"}},
    )
    net = Net(
        name="waits",
        places=[Place("inbox", ["job"])],
        transitions=[transition],
        arcs=[],
    )
    # when: the annotation is read and checked
    # then: it declares no wait, and the problem names the transition
    assert intended_waits(transition) == []
    problems = wait_problems(net, adapter=_Cel())
    assert problems[0][0] == "start"
    assert "when" in problems[0][1]


def test_wait_problems_report_cel_that_does_not_compile() -> None:
    """A condition that fails to compile is a problem on that transition."""
    # given: a well-shaped wait whose CEL the adapter rejects
    net = Net(
        name="waits",
        places=[],
        transitions=[
            Transition(
                "start",
                annotations={"wait": {"when": "???", "for": "a reply"}},
            )
        ],
        arcs=[],
    )
    # when: the annotation is checked
    problems = wait_problems(net, adapter=_Cel())
    # then: the message says the CEL is not valid
    assert problems == [("start", problems[0][1])]
    assert "not valid CEL" in problems[0][1]


def test_holds_is_false_when_evaluation_fails() -> None:
    """A condition that does not evaluate does not hold."""
    # given: a wait whose adapter raises while evaluating
    transition = Transition(
        "start",
        annotations={"wait": [{"when": "true", "for": "a reply"}]},
    )

    class _Boom:
        def compile(self, expr: str) -> str:
            return expr

        def eval(self, compiled: str, data: dict[str, Any]) -> bool:
            del compiled, data
            raise RuntimeError("eval")

    # when: the condition is evaluated
    held = holds(intended_waits(transition)[0], {}, {}, adapter=_Boom())
    # then: the failure does not count as the wait holding
    assert held is False


def test_an_empty_wait_list_declares_no_wait() -> None:
    """An empty wait list is malformed, so the case stays a gap."""
    # given: an empty list
    transition = Transition("start", annotations={"wait": []})
    net = Net(name="waits", places=[], transitions=[transition], arcs=[])
    # when: the annotation is read and checked
    # then: it declares no wait, and validation names the transition
    assert intended_waits(transition) == []
    assert wait_problems(net, adapter=_Cel())[0][0] == "start"
