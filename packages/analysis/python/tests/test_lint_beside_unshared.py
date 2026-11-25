"""The redundant beside-unshared lint (ADR 0068)."""

from __future__ import annotations

from velocitron_analysis import RULE_BESIDE_UNSHARED_REDUNDANT, lint_net
from velocitron_engine import (
    Arc,
    ConsumePattern,
    Net,
    Place,
    ProduceTemplate,
    Transition,
)


def _clock(beside: dict[str, object], *, suppress: list[str] | None = None) -> Net:
    annotations: dict[str, object] = {"fusion": True}
    if suppress is not None:
        annotations["lint"] = {"suppress": suppress}
    return Net(
        name="clock",
        places=[
            Place("idle", ["job"]),
            Place("clock", ["now"], annotations=annotations),
        ],
        transitions=[Transition("commit"), Transition("expire")],
        arcs=[
            Arc(
                from_place="idle",
                to_transition="commit",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="idle",
                to_transition="expire",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="clock",
                to_transition="commit",
                consume=ConsumePattern("now", None, "read"),
            ),
            Arc(
                from_place="clock",
                to_transition="expire",
                consume=ConsumePattern("now", None, "read"),
            ),
            Arc(
                from_transition="commit",
                to_place="idle",
                produce=ProduceTemplate("job", "idle"),
            ),
            Arc(
                from_transition="expire",
                to_place="idle",
                produce=ProduceTemplate("job", "idle"),
            ),
        ],
        annotations={
            "petrinet.dsl/v1": {
                "decorations": {"place:clock": {"beside": beside}},
            }
        },
    )


def test_a_fixed_side_with_unshared_warns() -> None:
    # given: beside left unshared, and beside right unshared
    left = _clock({"side": "left", "share": False})
    right = _clock({"side": "right", "share": False})
    # when: linting
    left_findings = lint_net(left)
    right_findings = lint_net(right)
    # then: each is a warning that names the side, and the net was accepted
    assert [finding.rule for finding in left_findings] == [
        RULE_BESIDE_UNSHARED_REDUNDANT
    ]
    assert left_findings[0].place == "clock"
    assert "beside left unshared" in left_findings[0].message
    assert "beside right unshared" in right_findings[0].message


def test_unshared_without_a_side_and_a_side_without_unshared_are_clean() -> None:
    # given: the two shapes that are not redundant
    unshared = _clock({"share": False})
    sided = _clock({"side": "left"})
    # when / then
    assert lint_net(unshared) == []
    assert lint_net(sided) == []


def test_the_place_can_suppress_the_redundant_unshared_warning() -> None:
    # given: the place acknowledges the rule
    net = _clock(
        {"side": "left", "share": False},
        suppress=[RULE_BESIDE_UNSHARED_REDUNDANT],
    )
    # when / then
    assert lint_net(net) == []
