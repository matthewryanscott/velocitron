"""The ``.play`` language: statements, prose, paths and syntax errors.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import pytest

from velocitron_play import (
    TRUNK,
    PlayError,
    parse_play,
)
from velocitron_play import (
    ExpectBody,
    FireBody,
    InjectBody,
    NameRef,
    AdvanceBody,
    TokenLiteral,
    UpdateBody,
)


def _error(text: str) -> PlayError:
    with pytest.raises(PlayError) as caught:
        parse_play(text, "t.play")
    return caught.value


def test_header_settings_templates_and_prose() -> None:
    # given: a header, settings, a template spread over lines, and prose
    text = """play shop "A small shop"
/// Header prose, right under the header line.
net "shop.petrinet"
marking rush

$o1: purchase {"id": "o-1",
               "sku": "a"}

/// Prose for the first step.
// a comment never reaches the walkthrough
inject (inbox) <- $o1 "an order arrives"
"""

    # when
    play = parse_play(text, "t.play")

    # then
    assert (play.name, play.title) == ("shop", "A small shop")
    assert play.prose == "Header prose, right under the header line."
    assert play.net == "shop.petrinet"
    assert play.marking == "rush"
    assert play.templates["o1"].data == {"id": "o-1", "sku": "a"}
    (trunk,) = play.paths
    assert trunk.name == TRUNK
    (step,) = trunk.steps
    assert step.kind == "inject"
    assert step.title == "an order arrives"
    assert step.prose == "Prose for the first step."
    assert step.statement == "inject (inbox) <- $o1"
    assert (step.position.line, step.position.column) == (11, 1)


def test_prose_followed_by_a_setting_belongs_to_the_header() -> None:
    # given: prose, then a template, then a step
    text = """play s
net "n.petrinet"

/// About the whole play.
$t: c {}

/// About the step.
inject (p) <- $t
"""

    # when
    play = parse_play(text)

    # then
    assert play.prose == "About the whole play."
    assert play.paths[0].steps[0].prose == "About the step."


def test_every_step_kind() -> None:
    # given
    text = """play s
net "n.petrinet"
inject (p) <- c {"a": 1}, {"b": 2}, $t
update (clock) <- advance {"now": 0}
advance +90m
advance (clock) 1h30m
@go: fire [t] with (p) {"a": 1} with (q) $t with (r) #2 -> (out) c {"x": 1} -> (more) +{"y": 2} -> (none) nothing "the title"
expect (p) == $t, c {"a": 1}, (q) empty, (r) count 2, (s) has {"a": 1}, enabled [t] [u], not enabled [v], next [t], quiescent
"""

    # when
    steps = parse_play(text).paths[0].steps

    # then
    inject = steps[0].body
    assert isinstance(inject, InjectBody)
    assert [type(t) for t in inject.tokens] == [TokenLiteral, TokenLiteral, NameRef]
    assert inject.tokens[1] == TokenLiteral(None, {"b": 2}, inject.tokens[1].position)
    assert isinstance(steps[1].body, UpdateBody)
    advance = steps[2].body
    assert isinstance(advance, AdvanceBody)
    assert (advance.place, advance.seconds, advance.relative) == (None, 5400, True)
    absolute = steps[3].body
    assert isinstance(absolute, AdvanceBody)
    assert absolute.place is not None and absolute.place.name == "clock"
    assert (absolute.seconds, absolute.relative) == (5400, False)
    fire = steps[4].body
    assert isinstance(fire, FireBody)
    assert steps[4].label == "go" and steps[4].title == "the title"
    assert [w.subset for w in fire.withs] == [{"a": 1}, None, None]
    assert fire.withs[1].template is not None and fire.withs[2].index == 2
    assert [o.place.name for o in fire.outputs] == ["out", "more", "none"]
    assert fire.outputs[1].merge == {"y": 2} and fire.outputs[2].nothing
    expect = steps[5].body
    assert isinstance(expect, ExpectBody)
    assert [c.kind for c in expect.conditions] == [
        "equals",
        "empty",
        "count",
        "has",
        "enabled",
        "not-enabled",
        "next",
        "quiescent",
    ]
    assert len(expect.conditions[0].tokens) == 2
    assert [t.name for t in expect.conditions[4].transitions] == ["t", "u"]
    assert expect.conditions[0].text == '(p) == $t, c {"a": 1}'


@pytest.mark.parametrize(
    ("written", "seconds"),
    [
        ("5400", 5400),
        ("5400.5", 5400.5),
        ("90s", 90),
        ("90m", 5400),
        ("22.5h", 81000),
        ("1h30m", 5400),
        ("1d", 86400),
    ],
)
def test_durations_lower_to_seconds(written: str, seconds: float) -> None:
    # when
    body = parse_play(f"play s\nadvance {written}\n").paths[0].steps[0].body

    # then
    assert isinstance(body, AdvanceBody)
    assert body.seconds == seconds


def test_paths_and_labels() -> None:
    # given
    text = """play s
net "n.petrinet"
@a: inject (p) <- {}

path refused "Refused" from @a
/// Prose of the path, right under its line.

/// Prose of the path's first step.
fire [t]
"""

    # when
    play = parse_play(text)

    # then
    assert [p.name for p in play.paths] == [TRUNK, "refused"]
    branch = play.paths[1]
    assert branch.title == "Refused"
    assert branch.from_label is not None and branch.from_label.name == "a"
    assert branch.prose == "Prose of the path, right under its line."
    assert branch.steps[0].prose == "Prose of the path's first step."


def test_composition_settings() -> None:
    # when
    play = parse_play(
        'play s\nuse "a.petrinet" as a\nuse "b.petrinet" as b\n'
        "wire a.(out) -> b.(in)\nfire [a.go]\n"
    )

    # then
    assert [(u.ref, u.alias) for u in play.uses] == [
        ("a.petrinet", "a"),
        ("b.petrinet", "b"),
    ]
    wire = play.wires[0]
    assert (wire.from_alias, wire.from_place, wire.to_alias, wire.to_place) == (
        "a",
        "out",
        "b",
        "in",
    )
    body = play.paths[0].steps[0].body
    assert isinstance(body, FireBody) and body.transition.name == "a.go"


def test_unknown_statement_is_sc101_with_position() -> None:
    error = _error('play s\nnet "n"\nlaunch [t]\n')
    assert error.diagnostic.code == "SC101"
    assert (error.diagnostic.position.line, error.diagnostic.position.column) == (3, 1)
    assert error.diagnostic.render().startswith("t.play:3:1: error[SC101]:")


def test_duplicate_json_key_is_sc102() -> None:
    error = _error('play s\ninject (p) <- c {"a": 1, "a": 2}\n')
    assert error.diagnostic.code == "SC102"
    assert "duplicate key" in error.diagnostic.message


def test_bad_duration_is_sc103() -> None:
    assert _error("play s\nadvance +soon\n").diagnostic.code == "SC103"


def test_missing_header_is_sc104() -> None:
    assert _error('net "n.petrinet"\n').diagnostic.code == "SC104"


def test_duplicate_label_is_sc105() -> None:
    error = _error("play s\n@a: advance 1\n@a: advance 2\n")
    assert error.diagnostic.code == "SC105"
    assert error.diagnostic.position.line == 3


def test_a_path_may_not_be_called_trunk() -> None:
    assert _error("play s\n@a: advance 1\npath trunk from @a\n").diagnostic.code == (
        "SC105"
    )


def test_an_indented_first_line_is_rejected() -> None:
    assert _error("  play s\n").diagnostic.code == "SC101"


def test_prose_after_a_blank_line_below_a_path_belongs_to_the_next_step() -> None:
    # given: a blank line between the path line and the prose
    text = (
        "play s\n@a: advance 1\n\npath p from @a\n\n"
        "/// The desk is closed, and the\n/// hold waits.\n"
        "advance 2\n"
    )

    # when
    path = parse_play(text).paths[1]

    # then
    assert path.prose == ""
    assert path.steps[0].prose == "The desk is closed, and the\nhold waits."


def test_consecutive_prose_lines_under_a_header_form_one_block() -> None:
    # given: prose right under the path line, wrapped over lines, then a paragraph
    text = (
        "play s\n@a: advance 1\npath p from @a\n"
        "/// One sentence that goes on\n/// over two lines.\n///\n/// A second paragraph.\n"
        "advance 2\n"
    )

    # when
    path = parse_play(text).paths[1]

    # then: single newlines inside a block; an empty /// line makes a paragraph
    assert path.prose == (
        "One sentence that goes on\nover two lines.\n\nA second paragraph."
    )


def test_scope_and_show_settings() -> None:
    # when
    play = parse_play(
        "play s\nscope neighbors\nshow hold id, remindAt\n"
        'show loan outcome, hold.id, "edition"\n'
    )

    # then
    assert play.scope == "neighbors"
    assert [(s.color, s.fields) for s in play.shows] == [
        ("hold", ("id", "remindAt")),
        ("loan", ("outcome", "hold.id", "edition")),
    ]


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("play s\nscope everything\n", "SC101"),
        ("play s\nscope step\nscope subnet\n", "SC104"),
        ("play s\nshow d id\nshow d other\n", "SC104"),
        ("play s\nshow d id, id\n", "SC101"),
        ('play s\nshow d "a..b"\n', "SC101"),
    ],
)
def test_bad_scope_and_show_settings(text: str, code: str) -> None:
    assert _error(text).diagnostic.code == code
