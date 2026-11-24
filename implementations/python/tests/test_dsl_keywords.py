"""BDD coverage for keywords used as names in the Petri-net DSL."""

from __future__ import annotations

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import emit_petrinet
from velocitron_dsl import PetrinetDslError
from velocitron_dsl import petrinet_lexer_literals

KEYWORDS = [
    literal.strip("'")
    for literal in petrinet_lexer_literals()
    if literal.strip("'").isalpha()
    and literal.strip("'") not in {"true", "false", "null"}
]


def _timer_net(bind_name: str) -> str:
    return (
        "net timed\n"
        "(waiting) -job-> [retry] -job-> (done)\n"
        "(clock) -tick->? [retry]\n"
        '[retry] timer clock (clock) cel "clock.now >= 1"\n'
        f"[retry] timer bind {bind_name} (waiting)\n"
    )


@pytest.mark.parametrize("keyword", KEYWORDS)
def test_a_keyword_names_a_place_a_transition_and_a_color(keyword: str) -> None:
    # given: a net whose place, transition and color all use the bare keyword
    source = f"net named\n({keyword}) -{keyword}-> [{keyword}]\n"

    # when: compiling it
    compiled = compile_petrinet_text(source, "named.petrinet")

    # then: the keyword is an ordinary name everywhere
    assert compiled["places"] == [{"name": keyword, "accepts": [keyword]}]
    assert compiled["transitions"] == [{"name": keyword}]


@pytest.mark.parametrize(
    "keyword", [keyword for keyword in KEYWORDS if keyword != "clock"]
)
def test_a_keyword_names_a_timer_bind(keyword: str) -> None:
    # given: a timer that binds its input token under a keyword
    # when: compiling it
    compiled = compile_petrinet_text(_timer_net(keyword), "timed.petrinet")

    # then: the bind keeps the keyword as its name
    assert compiled["transitions"][0]["timer"]["bind"] == {keyword: "waiting"}


def test_clock_stays_reserved_as_a_timer_bind() -> None:
    # given: a timer that binds a token under the clock's own name
    # when/then: resolution rejects the bind
    with pytest.raises(PetrinetDslError, match="timer bind name 'clock' is reserved"):
        compile_petrinet_text(_timer_net("clock"), "timed.petrinet")


def test_bare_initial_after_marking_is_always_the_initial_marking() -> None:
    # given: a place named initial, an initial marking and a named marking
    source = (
        "net marked\n"
        "(initial) -> [start]\n"
        "marking initial (initial) <- 1\n"
        "marking order (initial) <- 2\n"
    )

    # when: compiling it
    compiled = compile_petrinet_text(source, "marked.petrinet")

    # then: the bare initial is the initial marking and order names a marking
    assert compiled["initialMarking"] == {"initial": [{"type": "token", "data": {}}]}
    markings = compiled["annotations"]["petrinet.dsl/v1"]["markings"]
    assert list(markings) == ["order"]


def test_a_keyword_color_survives_the_canonical_round_trip() -> None:
    # given: a compiled net whose color is the keyword order
    compiled = compile_petrinet_text(
        "net ordered\n(queue) -order-> [ship]\n", "ordered.petrinet"
    )

    # when: emitting canonical DSL and compiling it again
    again = compile_petrinet_text(emit_petrinet(compiled), "ordered.petrinet")

    # then: the net is unchanged
    assert again == compiled
