"""The engine primer's Python samples run as written."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from velocitron_engine import (
    HandlerRegistry,
    Marking,
    Token,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_petrinet import parse_petrinet_text
from velocitron_runtime import Engine

_PRIMER = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "velocitron"
    / "engine-runtime-primer.md"
)

_TIMED = """\
net timed "A review escalates at its deadline"
(review) -doc-> [escalate] -doc-> (escalated)
@escalate_clock: (clock) -tick->? [escalate]
[escalate] timer clock (clock) cel "clock.now >= doc.dueAt"
[escalate] timer bind doc (review)
[escalate] timer maturity cel "doc.dueAt"
[escalate] handler "escalate"
"""


def _escalate(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    return {
        "status": "completed",
        "outputTokens": {"escalated": list(inp["inputTokens"]["review"])},
        "error": None,
        "metadata": {},
    }


def _sample(section: str) -> str:
    text = _PRIMER.read_text(encoding="utf-8")
    body = text.split(f"## {section}\n", 1)[1].split("\n## ", 1)[0]
    match = re.search(r"```python\n(.*?)```", body, re.DOTALL)
    assert match is not None, section
    return match.group(1)


def test_the_timed_transitions_sample_runs(capsys: pytest.CaptureFixture[str]):
    # given: a review due at 500 and one due at 2000
    net = parse_petrinet_text(_TIMED)
    marking = Marking(
        {
            "review": [Token("doc", {"dueAt": 500}), Token("doc", {"dueAt": 2000})],
            "clock": [Token("tick", {"now": 0})],
        }
    )
    registry = HandlerRegistry()
    registry.register_transition("escalate", _escalate)
    scope: dict[str, Any] = {
        "engine": Engine(registry),
        "net": net,
        "marking": marking,
        "Token": Token,
    }
    # when: the primer's sample runs on it
    exec(_sample("Timed transitions with the synchronous Engine"), scope)
    # then: the first deadline fired, and the sample prints the next one
    assert [t.data for t in scope["marking"]["escalated"]] == [{"dueAt": 500}]
    transition, at = capsys.readouterr().out.split()
    assert (transition, float(at)) == ("escalate", 2000)
