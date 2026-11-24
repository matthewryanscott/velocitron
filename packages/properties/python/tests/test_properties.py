"""The public property seam checks a produced marking."""

from __future__ import annotations

from typing import Any

import pytest

from velocitron_engine import (
    CapacityPerColorKey,
    Marking,
    Net,
    Place,
    Token,
)
from velocitron_properties import (
    AtMostN,
    EventuallyReaches,
    FiringBinding,
    PlaceEmpty,
    capacity_properties,
    check_marking,
    check_replay,
)


class _Cel:
    def compile(self, expr: str) -> str:
        return expr

    def eval(self, compiled: str, data: dict[str, Any]) -> bool:
        del compiled, data
        return True


def _net() -> Net:
    return Net(
        name="box",
        places=[
            Place(
                "shelf",
                ["job"],
                capacity_per_color_key=CapacityPerColorKey(("id",), 1),
            )
        ],
        transitions=[],
        arcs=[],
    )


def test_check_marking_reports_a_capacity_violation() -> None:
    # given: one shelf that already holds its color key
    net = _net()
    marking = Marking({"shelf": [Token("job", {"id": "a"}), Token("job", {"id": "a"})]})

    # when: the checker reads the net's capacity declaration
    report = check_marking(net, marking, cel_adapter=_Cel())

    # then: the extra token is a finding, and firing is not involved
    assert not report.ok
    assert report.violations[0].kind == "at-most-n"
    assert report.violations[0].place == "shelf"
    assert capacity_properties(net) == [AtMostN("shelf", 1, ("id",))]


def test_check_marking_rejects_a_replay_only_property() -> None:
    # given: a property that needs a record stream
    prop = EventuallyReaches("shelf", ("shelf",), "id")

    # when / then: handing it to the single-marking checker is a programmer error
    with pytest.raises(ValueError, match="replay-only"):
        check_marking(_net(), Marking(), [prop], cel_adapter=_Cel())


def test_check_replay_sees_an_injected_token() -> None:
    # given: an empty shelf and one injection
    net = _net()
    records = [
        {
            "injectionId": "in-1",
            "place": "shelf",
            "kind": "inject",
            "tokens": [{"type": "job", "data": {"id": "a"}}],
        }
    ]

    # when: the replay walks that record
    report = check_replay(
        net,
        Marking(),
        records,
        [PlaceEmpty("shelf")],
        cel_adapter=_Cel(),
    )

    # then: the shelf is not empty at quiescence
    assert not report.ok
    assert report.violations[0].kind == "place-empty"


def test_firing_binding_requires_one_check() -> None:
    # when / then: key and cel together are a programmer error
    with pytest.raises(ValueError, match="exactly one"):
        FiringBinding("move", key="id", cel="true")
