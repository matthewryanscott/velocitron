"""The packaged play parser lowers statements and reports SC1xx."""

from __future__ import annotations

import json
import os
from pathlib import Path

from velocitron_play import (
    GRAMMAR_FILE_NAME,
    AdvanceBody,
    PlayError,
    grammar_text,
    parse_play,
    project_source,
)

_REPO = Path(__file__).resolve().parents[4]
_FIXTURES = _REPO / "packages" / "play" / "fixtures"


def test_grammar_text_reads_the_canonical_grammar() -> None:
    # given: a checkout of this package
    text = grammar_text()
    # then: the text is the statement grammar, not a net grammar
    assert "grammar VelocitronPlay;" in text
    assert GRAMMAR_FILE_NAME == "VelocitronPlay.g4"
    assert text == (_REPO / "packages" / "play" / GRAMMAR_FILE_NAME).read_text(
        encoding="utf-8"
    )


def test_duplicate_json_key_is_sc102() -> None:
    # when: a token object repeats a key
    try:
        parse_play('play s\ninject (p) <- c {"a": 1, "a": 2}\n')
    except PlayError as error:
        diagnostic = error.diagnostic
    else:
        raise AssertionError("duplicate key parsed")
    # then: the diagnostic names the duplicate key
    assert diagnostic.code == "SC102"
    assert "duplicate key" in diagnostic.message


def test_a_kebab_case_play_name_says_a_name_is_an_identifier() -> None:
    # when: the header names the play the way its file is named
    try:
        parse_play("play step-warning\n")
    except PlayError as error:
        diagnostic = error.diagnostic
    else:
        raise AssertionError("kebab-case name parsed")
    # then: SC101 at the dash, with the identifier to write instead
    assert diagnostic.code == "SC101"
    assert (diagnostic.position.line, diagnostic.position.column) == (1, 10)
    assert diagnostic.message == (
        "a play name is an identifier (letters, digits, `_`): write `step_warning`"
    )


def test_durations_lower_to_seconds() -> None:
    # when: each duration form is one step
    play = parse_play(
        (_FIXTURES / "syntax" / "durations.play").read_text(encoding="utf-8")
    )
    seconds = [
        step.body.seconds
        for step in play.paths[0].steps
        if isinstance(step.body, AdvanceBody)
    ]
    # then: ordered duration parts become seconds, and a whole value stays an int
    assert seconds == [5400, 5400.5, 90, 5400, 81000, 5400, 86400]


def test_projection_matches_the_shared_agreement() -> None:
    # given: the shared fixture manifest
    manifest = json.loads((_FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    actual = {
        case["name"]: project_source((_REPO / case["path"]).read_text(encoding="utf-8"))
        for case in manifest
    }
    path = _FIXTURES / "agreement.json"
    if os.environ.get("PLAY_AGREEMENT_WRITE") == "1":
        path.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    # when: the committed oracle is loaded
    expected = json.loads(path.read_text(encoding="utf-8"))
    # then: this package still produces it
    assert actual == expected
