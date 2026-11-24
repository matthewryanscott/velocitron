"""compare treats local names as the identity of a merged net."""

from __future__ import annotations

from velocitron_engine import Marking, Net, Place
from velocitron_equiv import Equivalence, compare


def _net(place: str) -> Net:
    return Net(
        name="n",
        places=[Place(place, ["job"])],
        transitions=[],
        arcs=[],
        initial_marking=Marking(),
    )


def test_identical_nets_are_equivalent() -> None:
    # when: two nets declare the same place
    result = compare(_net("shelf"), _net("shelf"))

    # then: behavior matches and no renaming is required
    assert result.equivalent
    assert result.renaming == ()
    assert result.counts == (1, 0, 0)
    assert isinstance(result, Equivalence)


def test_a_renamed_place_is_a_difference() -> None:
    # when: the only place has a different local name
    result = compare(_net("shelf"), _net("desk"))

    # then: the nets are not the same net up to renaming
    assert not result.equivalent
    assert result.differences
    assert result.as_json()["equivalent"] is False
