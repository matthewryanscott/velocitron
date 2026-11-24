"""explain_net quotes a net and can say what a marking enables."""

from __future__ import annotations

import pytest

from velocitron_engine import Marking, Net, Place, Transition
from velocitron_explain import explain_net


def _net() -> Net:
    return Net(
        name="loan",
        places=[Place("desk", ["book"])],
        transitions=[Transition("lend")],
        arcs=[],
    )


def test_explain_net_quotes_the_declaration() -> None:
    # when: a net is rendered with no marking
    document = explain_net(_net())

    # then: the account names the declaration and ends with one LF
    assert 'Net: "loan"' in document
    assert "1 places, 1 transitions, and 0 arcs." in document
    assert document.endswith("\n")
    assert not document.endswith("\n\n")


def test_explain_net_is_deterministic() -> None:
    # when: the same net is rendered twice
    first = explain_net(_net(), format="text", level="newcomer")
    second = explain_net(_net(), format="text", level="newcomer")

    # then: the bytes match
    assert first == second
    assert "HOW TO READ" in first


def test_explain_net_with_a_marking_uses_enablement() -> None:
    # when: a marking is supplied
    document = explain_net(_net(), marking=Marking(), marking_label="the open desk")

    # then: the enablement section names that marking
    assert "What can happen from the open desk" in document
    assert "[lend]" in document


def test_explain_net_rejects_an_unknown_format() -> None:
    # when / then: format is a closed set
    with pytest.raises(ValueError, match="format"):
        explain_net(_net(), format="html")  # type: ignore[arg-type]
