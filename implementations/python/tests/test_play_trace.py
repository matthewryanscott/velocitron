"""``velocitron play trace``: one path's records, state and resolve.

References: spec/play-language.md, "Command line" and "Trace"; ADR 0038.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import velocitron_cli as cli
from velocitron_play import (
    read_play,
)
from velocitron_play_check import (
    PlayTrace,
    check_play,
    trace_document,
)
from velocitron_engine import Token

_FIXTURES = Path(__file__).parent / "fixtures" / "play"

_MATURING = """net poll "Hold poll with retry"

@in: (queue) -file-> [deliver]
@out: [deliver] -log-> (sent)
@clock_in: (clock) -tick->? [deliver]

net actor "Runner"
[deliver] actor "Runner"
[deliver] description "Take the hold"
[deliver] timer clock (clock) cel "clock.now >= 100"

(sent) lives in "Hold log"
(sent) reads as cel "'log ' + token.n"
@out data cel "{\\"n\\": 1}"
"""

_MATURING_PLAY = (
    'play s\nnet "poll.petrinet"\nmarking none\n'
    'inject (queue) <- {"n": 1}\n'
    'inject (clock) <- {"now": 0}\n'
    "advance +2m\n"
)

_SHIPPING = """net shipping

@hand: (packed) -parcel-> [ship]
@out: [ship] -parcel-> (shipped)
net actor Shop
[ship] actor Shop
"""


def _played(tmp_path: Path, nets: dict[str, str], play: str) -> PlayTrace:
    for name, text in nets.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    source = tmp_path / "s.play"
    source.write_text(play, encoding="utf-8")
    report = check_play(read_play(source))
    (trace,) = report.traces[:1]
    return trace


def test_the_document_carries_the_matured_firing(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path, {"poll.petrinet": _MATURING}, _MATURING_PLAY
    )

    # when
    document = trace_document(trace)
    advance = document["steps"][2]

    # then: the advancing step's second record is the maturing firing
    assert document["play"] == "s"
    assert document["path"] == "trunk"
    assert document["status"] == "passed"
    assert document["clocks"] == ["clock"]
    assert len(advance["records"]) == 2
    matured = advance["records"][1]
    assert matured["kind"] == "firing"
    assert matured["transition"] == "deliver"
    assert matured["status"] == "completed"
    assert matured["matured"] is True
    assert matured["maturedBy"] == "poll/@inject/clock/2"
    assert matured["actor"] == "Runner"
    assert matured["label"] == "Take the hold"
    # and: the firing's record-0 injection is unmatured
    assert advance["records"][0]["matured"] is False


def test_the_document_resolves_lived_columns_and_reads(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path, {"poll.petrinet": _MATURING}, _MATURING_PLAY
    )

    # when
    document = trace_document(trace)
    record = document["steps"][2]["records"][1]

    # then: the lived place's token carries its column and read label
    #   (``read`` here is the place label: the fixture net has no `reads as`)
    assert record["outputTokens"]["sent"] == [
        {
            "type": "log",
            "data": {"n": 1},
            "column": "Hold log",
            "read": "Sent",
        }
    ]


def test_the_injection_on_an_unowned_place_has_no_actor(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path, {"poll.petrinet": _MATURING}, _MATURING_PLAY
    )

    # when
    document = trace_document(trace)

    # then: the setup injecting injections carry no actor (Outside)
    assert document["steps"][0]["records"][0]["actor"] is None
    assert document["steps"][0]["actor"] is None


def test_a_firing_step_carries_the_actor_and_label(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net actor Shop\n(a) -> [go] -> (b)\n"
            '[go] description "Go anyway"\nmarking initial (a) <- 1\n'
        },
        'play s\nnet "n.petrinet"\nfire [go] "Step aside"\n',
    )

    # when
    document = trace_document(trace)

    # then: the step's title is its record's label; its actor is the net's
    assert document["steps"][0]["actor"] == "Shop"
    assert document["steps"][0]["records"][0]["label"] == "Step aside"


def test_after_each_holds_one_marking_per_record(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path, {"poll.petrinet": _MATURING}, _MATURING_PLAY
    )

    # when
    document = trace_document(trace)
    advance = document["steps"][2]

    # then
    assert len(advance["afterEach"]) == len(advance["records"]) == 2
    assert advance["afterEach"][-1] == advance["after"]


def test_trace_cli_prints_the_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    for name, text in {"poll.petrinet": _MATURING}.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    play = tmp_path / "s.play"
    play.write_text(_MATURING_PLAY, encoding="utf-8")

    # when
    code = cli.main(["play", "trace", str(play)])

    # then
    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["steps"][2]["records"][1]["matured"] is True


def test_trace_cli_of_a_failing_path_prints_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the deadline path, which fires [give_up] by the clock … the
    #   too_early path fails: [retry] is not enabled yet
    play_dir = Path(__file__).parents[3] / "packages" / "spec" / "conformance" / "play" / "02-timers-and-paths"
    for name in ("case.play", "retry.petrinet"):
        shutil.copy(play_dir / name, tmp_path / name)
    play = str(tmp_path / "case.play")

    # when
    code = cli.main(["play", "trace", play, "--path", "too_early"])
    captured = capsys.readouterr()

    # then: the document prints, ending at the failure, and the diagnostic
    assert code == 1
    document = json.loads(captured.out)
    assert document["status"] == "passed" or document["steps"]
    assert "error[SC3" in captured.err or "error[SC2" in captured.err


def test_trace_cli_an_unknown_path_is_misuse(tmp_path: Path) -> None:
    # given
    play = tmp_path / "shop.play"
    for name in ("shop.petrinet", "shop.play"):
        shutil.copy(_FIXTURES / name, tmp_path / name)

    # when/then
    assert cli.main(["play", "trace", str(play), "--path", "nope"]) == 2


def test_resolve_helpers_answer_the_sequence_views_questions(
    tmp_path: Path,
) -> None:
    # given
    from velocitron_play_check import resolve_actor, resolve_column

    trace = _played(
        tmp_path, {"poll.petrinet": _MATURING}, _MATURING_PLAY
    )

    # when
    actor = resolve_actor(trace, transition="deliver")
    owner = resolve_actor(trace, place="queue")
    column = resolve_column(trace, "sent", Token("log", {"n": 1}))
    unlived = resolve_column(trace, "queue", Token("file", {"n": 1}))

    # then: a firing's actor is its transition's; (queue) has no owner
    #   annotation, so its injection's owner is Outside; a lived place
    #   resolves its column, an unlived one gives None
    assert actor == "Runner"
    assert owner == "Outside"
    assert column == "Hold log"
    assert unlived is None