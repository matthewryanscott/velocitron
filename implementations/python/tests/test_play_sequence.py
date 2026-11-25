"""Sequence diagrams: a checked path projected onto actors and hand-offs.

The trunk of ``fixtures/play/evening-shift.play`` is pinned as a golden
PlantUML file. Regenerate it with ``VELOCITRON_UPDATE_GOLDEN=1`` after an
intended change, and look at the rendered diagram before committing it.

References: spec/play-language.md; ADR 0038.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from velocitron_petrinet import merge_nets
import velocitron_cli as cli
from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import emit_petrinet
from velocitron_petrinet import (
    NetValidationError,
    parse_net,
)
from velocitron_play import (
    PlayError,
    parse_play,
    read_play,
)
from velocitron_play_check import (
    PlayTrace,
    check_play,
    render_walkthrough,
    sequence_view,
    walkthrough_document,
)
from velocitron_play_check import (
    OUTSIDE,
    Activate,
    Box,
    Deactivate,
    Delay,
    Divider,
    Failure,
    GroupClose,
    GroupOpen,
    Message,
    Note,
    SequenceEvent,
    render_plantuml,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "play"


def _trace(path: str = "trunk") -> PlayTrace:
    trace = check_play(read_play(_FIXTURES / "evening-shift.play")).trace(path)
    assert trace is not None
    return trace


def _messages(events: Sequence[SequenceEvent]) -> list[tuple[str, str, str, bool]]:
    return [
        (e.source, e.target, e.label, e.dashed)
        for e in events
        if isinstance(e, Message)
    ]


def _notes(events: Sequence[SequenceEvent]) -> list[tuple[str, tuple[str, ...]]]:
    return [(e.actor, e.lines) for e in events if isinstance(e, Note)]


def _played(tmp_path: Path, nets: dict[str, str], play: str) -> PlayTrace:
    for name, text in nets.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    source = tmp_path / "s.play"
    source.write_text(play, encoding="utf-8")
    report = check_play(read_play(source))
    (trace,) = report.traces[:1]
    return trace


# ── The projection ───────────────────────────────────────────────────────


def test_trunk_sequence_matches_the_golden_file() -> None:
    # given
    trace = _trace()

    # when
    plantuml = render_plantuml(sequence_view(trace))

    # then
    golden = _FIXTURES / "evening-shift.sequence.puml"
    if os.environ.get("VELOCITRON_UPDATE_GOLDEN"):
        golden.write_text(plantuml, encoding="utf-8")
    assert plantuml == golden.read_text(encoding="utf-8")


def test_the_diagram_pins_colors_for_dark_pages() -> None:
    # given
    plantuml = render_plantuml(sequence_view(_trace()))

    # then: a light background that PlantUML paints, and pinned ink
    lines = plantuml.splitlines()
    assert lines[:2] == ["@startuml", "skinparam backgroundColor #FEFEFE"]
    for setting in (
        "defaultFontColor #222222",
        "ParticipantBorderColor",
        "ParticipantBackgroundColor",
        "ParticipantFontColor",
        "ActorBorderColor",
        "ActorBackgroundColor",
        "ActorFontColor",
        "DatabaseBorderColor",
        "DatabaseBackgroundColor",
        "DatabaseFontColor",
        "QueueBorderColor",
        "QueueBackgroundColor",
        "QueueFontColor",
        "NoteBorderColor",
        "NoteBackgroundColor",
        "NoteFontColor",
        "SequenceGroupBorderColor",
        "BoxFontColor",
    ):
        assert any(line.startswith(f"skinparam {setting}") for line in lines)


def test_the_diagram_has_the_play_title_and_no_footbox() -> None:
    # when
    view = sequence_view(_trace())
    plantuml = render_plantuml(view)

    # then
    assert view.title == "Evening shift"
    assert "title Evening shift" in plantuml.splitlines()
    assert "hide footbox" in plantuml.splitlines()


def test_lifelines_follow_the_declared_order_kinds_and_boxes() -> None:
    # when
    view = sequence_view(_trace())

    # then: the box's members are drawn together, where the first one is
    assert [(lifeline.name, lifeline.kind) for lifeline in view.lifelines] == [
        ("Clerk", "person"),
        ("Runner", "system"),
        ("Desk", "system"),
        ("(request)", "queue"),
        ("Desk sign", "record"),
        ("annex", "system"),
    ]
    assert view.boxes == (Box("Night crew", ("Runner", "Desk")),)
    plantuml = render_plantuml(view)
    assert 'actor "Clerk" as clerk' in plantuml
    assert 'database "Desk sign" as desk_sign' in plantuml
    assert (
        'box "Night crew" #F4F4F4\n'
        'participant "Runner" as runner\n'
        'participant "Desk" as desk\n'
        "end box"
    ) in plantuml


def test_writing_into_a_lived_place_is_an_arrow_into_its_column() -> None:
    # when
    messages = _messages(sequence_view(_trace()).events)

    # then: the clerk writes the sign; the runner writes the hold on its branch.
    # The runner's title is on the hand-off into the runner, so the column
    # arrow carries the token's colour.
    assert ("Clerk", "Desk sign", "Close the desk", False) in messages
    assert ("(request)", "Runner", "Take the hold", False) in messages
    assert ("Runner", "annex", "hold", False) in messages


def test_reading_a_lived_place_is_a_dashed_arrow_with_the_value_read() -> None:
    # when
    messages = _messages(sequence_view(_trace()).events)

    # then: `reads as` computes the label from the token read
    assert ("Desk sign", "Desk", "desk shut", True) in messages
    # and: without `reads as`, the place's description
    assert ("annex", "Clerk", "a hold waiting on the clerk", True) in messages
    # and: a step that writes back into the column it reads draws no read
    assert not any(
        source == "Desk sign" and target == "Clerk"
        for source, target, _, _ in messages
    )


def test_an_unlabeled_step_that_writes_back_into_a_column_draws_the_read(
    tmp_path: Path,
) -> None:
    # given: [mark] has no title, summary or description; it consumes what
    # [put] wrote on the host and writes back onto the host
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net actor Shop\n(a) -> [put] -> (ended) -> [mark] -> (done)\n"
            "(ended) lives in Host\n(ended) reads as cel \"'put returned'\"\n"
            '(done) lives in Host\n(done) description "the file"\n'
            "marking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\nfire [put] "put the file"\nfire [mark]\n',
    )

    # when
    messages = _messages(sequence_view(trace).events)

    # then: the read splits the writes, and the write back is not drawn
    assert messages == [
        ("Shop", "Host", "put the file", False),
        ("Host", "Shop", "put returned", True),
    ]


def test_an_unlabeled_write_says_the_place_description_or_nothing(
    tmp_path: Path,
) -> None:
    net = "net actor Shop\n(a) -> [stage] -> (staged) -> [put] -> (sent)\n"
    net += "(staged) lives in Host\n(sent) lives in Host\nmarking initial (a) <- 1\n"
    for extra, expected in (
        ("", "put the file"),
        ('(staged) description "a staged file"\n', "a staged file\nput the file"),
    ):
        # given: [stage] has no label of its own; [put] writes back with a title
        trace = _played(
            tmp_path,
            {"n.petrinet": net + extra},
            'play s\nnet "n.petrinet"\nfire [stage]\nfire [put] "put the file"\n',
        )

        # when
        messages = _messages(sequence_view(trace).events)

        # then: never the humanized name "Stage"
        assert messages == [("Shop", "Host", expected, False)]


def test_a_write_without_text_draws_a_bare_arrow(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net actor Shop\n(a) -> [stage] -> (staged)\n"
            "(staged) lives in Host\nmarking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\nfire [stage]\n',
    )

    # when
    plantuml = render_plantuml(sequence_view(trace))

    # then
    assert "shop -> host\n" in plantuml


_LIVED = """person Ops
system Shop
net actor Shop
(owner) -> [set_owner] -> (owner)
(slot) -> [deliver] -> (sent)
(owner) -token->? [deliver]
[set_owner] actor Ops
(slot) actor Shop
(owner) actor Ops
(owner) lives in Owner
marking initial (owner) <- 1
"""


def test_a_read_label_falls_back_to_the_description_then_the_name(
    tmp_path: Path,
) -> None:
    # given: no `reads as`, no description; then a `reads as` that fails
    for extra, expected in (
        ("", "Owner"),
        ('(owner) description "the owner"\n', "the owner"),
        (
            '(owner) description "the owner"\n(owner) reads as cel "token.nope"\n',
            "the owner",
        ),
    ):
        trace = _played(
            tmp_path,
            {"n.petrinet": _LIVED + extra},
            'play s\nnet "n.petrinet"\ninject (slot) <- {}\nfire [deliver] "Deliver"\n',
        )

        # then
        assert ("Owner", "Shop", expected, True) in _messages(
            sequence_view(trace).events
        )


def test_a_cel_lifeline_name_comes_from_the_token(tmp_path: Path) -> None:
    # given: each file lives on its own host
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net actor Shop\n(a) -> [send] -> (files)\n(a) actor Shop\n"
            '(files) lives in cel "token.host"\n'
        },
        'play s\nnet "n.petrinet"\n'
        'inject (a) <- {"host": "one.example"}\nfire [send] "Send"\n'
        'inject (a) <- {"host": "two.example"}\nfire [send] "Send"\n',
    )

    # when
    view = sequence_view(trace)

    # then
    assert [lifeline.name for lifeline in view.lifelines] == [
        "Shop",
        "one.example",
        "two.example",
    ]


def test_a_hand_off_place_is_a_queue_beside_its_producer() -> None:
    # when
    events = sequence_view(_trace()).events

    # then: the desk files the hold into the queue, at the injection
    assert ("Desk", "(request)", "Hold filed", False) in _messages(events)
    # and: the runner takes it from the queue, and is activated while it
    # draws an arrow of its own
    start = events.index(Activate("Runner"))
    assert events[start - 1] == Message(
        "(request)", "Runner", "Take the hold", False, 14
    )
    assert Deactivate("Runner") in events[start:]


def test_own_titled_steps_are_notes_and_untitled_steps_draw_nothing() -> None:
    # when
    view = sequence_view(_trace())

    # then: no arrow goes from an actor to itself
    assert all(source != target for source, target, _, _ in _messages(view.events))
    assert _notes(view.events) == [
        ("Desk", ("Close the desk",)),
        ("Clerk", ("Check the hold",)),
    ]
    # and: [desk_opens] has no title, so it draws nothing
    assert "Open the desk again" not in render_plantuml(view)


def test_notes_of_one_actor_fold_into_one(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net actor Shop\n(a) -> [one] -> (b) -> [two] -> (c)\n"
            "marking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\nfire [one] "Pack"\nfire [two] "Label"\n',
    )

    # when
    view = sequence_view(trace)

    # then
    assert _notes(view.events) == [("Shop", ("Pack", "Label"))]
    assert "note right of shop\nPack\nLabel\nend note" in render_plantuml(view)


def test_a_hand_off_is_two_arrows_each_at_its_own_step(tmp_path: Path) -> None:
    # given: the clerk's titled step makes the token the shop consumes
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "person Clerk\nnet actor Shop\n"
            "(a) -> [accept] -> (b) -> [ship] -> (c)\n[accept] actor Clerk\n"
            "marking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\nfire [accept] "Order accepted"\nfire [ship] "Ship"\n',
    )

    # when
    view = sequence_view(trace)

    # then: the produce and the consume are each drawn where they happen,
    # and each step's title is on its own arrow
    assert [lifeline.name for lifeline in view.lifelines] == [
        "Clerk",
        "(b)",
        "Shop",
    ]
    assert _messages(view.events) == [
        ("Clerk", "(b)", "Order accepted", False),
        ("(b)", "Shop", "Ship", False),
    ]
    assert _notes(view.events) == []


def test_setup_injections_into_a_lived_place_draw_nothing(tmp_path: Path) -> None:
    # given: the owner is set before anything fires, and again after
    trace = _played(
        tmp_path,
        {"n.petrinet": _LIVED.replace("marking initial (owner) <- 1\n", "")},
        'play s\nnet "n.petrinet"\ninject (owner) <- {} "Owner set"\n'
        'inject (slot) <- {}\nfire [deliver] "Deliver"\n'
        'update (owner) <- {"who": "b"} "Owner changed"\n',
    )

    # when
    messages = _messages(sequence_view(trace).events)

    # then: the first read shows the starting value; the later update is drawn
    assert messages == [
        ("Owner", "Shop", "Owner", True),
        ("Ops", "Owner", "Owner changed", False),
    ]


def test_the_first_advance_of_a_clock_draws_nothing(tmp_path: Path) -> None:
    # given: the clock has no value until the first advance
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "(a) -> [go] -> (b)\n(clock) -advance->? [go]\n"
            '[go] timer clock (clock) cel "clock.now >= 3600"\n'
        },
        'play s\nnet "n.petrinet"\nadvance 0\ninject (a) <- {}\nadvance +1h\nfire [go]\n',
    )

    # when
    events = sequence_view(trace).events

    # then: only the second advance is a delay
    assert [e for e in events if isinstance(e, Delay)] == [Delay("1 hour later")]


_MATURING = """net poll "Hold poll with retry"

@in: (queue) -file-> [deliver]
@out: [deliver] -log-> (sent)
@clock_in: (clock) -tick->? [deliver]

net actor "Runner"
[deliver] actor "Runner"
[deliver] description "Take the hold"
[deliver] timer clock (clock) cel "clock.now >= 100"

(sent) lives in "Hold log"
@out data cel "{\\"n\\": 1}"
"""


def test_an_advance_draws_the_firings_it_matured(tmp_path: Path) -> None:
    # given: a net whose timed transition's outputs the net determines
    trace = _played(
        tmp_path,
        {"poll.petrinet": _MATURING},
        'play s\nnet "poll.petrinet"\nmarking none\n'
        'inject (queue) <- {"n": 1}\n'
        'inject (clock) <- {"now": 0}\n'
        "advance +2m\n"
        'expect (sent) has {"n": 1}\n',
    )

    # when
    view = sequence_view(trace)

    # then: the matured firing draws after the delay, under its transition's
    #   actor, labeled with the transition's description and marked on time
    assert [e for e in view.events if isinstance(e, Delay)] == [
        Delay("2 minutes later")
    ]
    assert _messages(view.events) == [
        ("Runner", "Hold log", "Take the hold (on time)", False)
    ]
    message = next(e for e in view.events if isinstance(e, Message))
    assert message.matured


def test_a_matured_firing_is_not_labelled_with_the_advance_title(
    tmp_path: Path,
) -> None:
    # given: the advance has its own title; the timed transition has a description
    trace = _played(
        tmp_path,
        {"poll.petrinet": _MATURING},
        'play s\nnet "poll.petrinet"\nmarking none\n'
        'inject (queue) <- {"n": 1}\n'
        'inject (clock) <- {"now": 0}\n'
        'advance +2m "the clock jumps"\n',
    )

    # when
    plantuml = render_plantuml(sequence_view(trace))

    # then: the matured firing says the transition's label, plus on time
    assert "Take the hold (on time)" in plantuml
    assert "the clock jumps" not in plantuml


def test_sequence_json_carries_the_matured_mark(tmp_path: Path) -> None:
    # given: the same maturing play, as JSON
    trace = _played(
        tmp_path,
        {"poll.petrinet": _MATURING},
        'play s\nnet "poll.petrinet"\nmarking none\n'
        'inject (queue) <- {"n": 1}\n'
        'inject (clock) <- {"now": 0}\n'
        "advance +2m\n",
    )

    # when
    from velocitron_play_check import sequence_json

    events = [
        event
        for event in sequence_json(sequence_view(trace))["events"]
        if event["kind"] == "message"
    ]

    # then
    assert events == [
        {
            "kind": "message",
            "from": "Runner",
            "to": "Hold log",
            "label": "Take the hold (on time)",
            "dashed": False,
            "line": 6,
            "matured": True,
        }
    ]


def test_an_advance_that_matures_an_unlabeled_firing_draws_a_bare_arrow(
    tmp_path: Path,
) -> None:
    # given: the transition has no summary or description; its humanized
    #   name labels the arrow, still marked on time
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "(a) -> [go] -> (b)\n(clock) -advance->? [go]\n"
            "net actor Shop\n[go] actor Shop\n"
            '[go] timer clock (clock) cel "clock.now >= 10"\n'
            "@out: [go] -b-> (b)\n"
            '@out data cel "{}"\n(b) lives in Ledger\n'
        },
        'play s\nnet "n.petrinet"\nadvance 0\ninject (a) <- {}\nadvance +60s\n',
    )

    # when
    messages = _messages(sequence_view(trace).events)

    # then: no authored label — a bare matured arrow (a firing without one
    #   uses its name only in a failure note)
    assert messages == [("Shop", "Ledger", "", False)]


def test_an_advance_that_matures_nothing_is_only_a_delay(tmp_path: Path) -> None:
    # given: the clock moves, but nothing is due
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "(a) -> [go] -> (b)\n(clock) -advance->? [go]\n"
            "net actor Shop\n[go] actor Shop\n"
            '[go] timer clock (clock) cel "clock.now >= 3600"\n'
        },
        'play s\nnet "n.petrinet"\nadvance 0\ninject (a) <- {}\nadvance +1s\n',
    )

    # when
    events = sequence_view(trace).events

    # then
    assert list(events) == [Delay("1 second later")]


def test_advances_with_nothing_drawn_between_them_are_one_delay(tmp_path: Path) -> None:
    # given: two clocks advance at the same moment
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "(a) -> [go] -> (b)\n(one) -advance->? [go]\n(two) -advance->? [go]\n"
            '[go] timer clock (one) cel "one.now >= 0"\n'
        },
        'play s\nnet "n.petrinet"\nadvance (one) 0\nadvance (two) 0\n'
        "advance (one) 3600\nadvance (two) 7200\n",
    )

    # when
    events = sequence_view(trace).events

    # then: one delay, the longest of the two clocks
    assert list(events) == [Delay("2 hours later")]


def test_back_to_back_ticks_of_one_clock_show_the_total(tmp_path: Path) -> None:
    # given: the clock moves 0 → 29 → 30, and nothing is drawn between the ticks
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "(a) -> [go] -> (b)\n(clock) -advance->? [go]\n"
            '[go] timer clock (clock) cel "clock.now >= 3600"\n'
        },
        'play s\nnet "n.petrinet"\nadvance 0\nadvance 29\nadvance 30\n',
    )

    # when
    events = sequence_view(trace).events

    # then: the merged delay is the total time that passed, not the longer tick
    assert list(events) == [Delay("30 seconds later")]


_HANDOFF = """\
net handoff "A hands B an item; C does something in between"
system "A"
system "B"
system "C"
(raw) -item-> [make]
[make] -item-> (tray)
(tray) -item-> [use]
[use] -item-> (done)
(idle) -call-> [ring]
[ring] -call-> (rung)
[make] actor "A"
[use]  actor "B"
[ring] actor "C"
marking initial (raw) <- $p
marking initial (idle) <- $c
$p: item {}
$c: call {}
"""

_LATE = """\
play late "A makes an item, C rings, then B uses the item"
net "handoff.petrinet"
fire [make] "1. A makes the item"
fire [ring] "2. C rings the bell"
fire [use]  "3. B uses the item"
"""


def test_a_late_hand_off_is_drawn_in_step_order(tmp_path: Path) -> None:
    # given: A makes an item, C rings, then B uses the item
    trace = _played(
        tmp_path,
        {"handoff.petrinet": _HANDOFF},
        _LATE,
    )

    # when
    view = sequence_view(trace)
    plantuml = render_plantuml(view)

    # then: the queue sits beside A, who produces into it, and the steps
    # read 1, then 2, then 3
    assert [(lifeline.name, lifeline.kind) for lifeline in view.lifelines] == [
        ("A", "system"),
        ("(tray)", "queue"),
        ("B", "system"),
        ("C", "system"),
    ]
    assert _messages(view.events) == [
        ("A", "(tray)", "1. A makes the item", False),
        ("(tray)", "B", "3. B uses the item", False),
    ]
    assert _notes(view.events) == [("C", ("2. C rings the bell",))]
    body = plantuml.split("@enduml")[0]
    assert body.index("1. A makes the item") < body.index("2. C rings the bell")
    assert body.index("2. C rings the bell") < body.index("3. B uses the item")
    assert 'queue "(tray)" as tray' in plantuml


def test_a_queue_caption_is_the_place_description(tmp_path: Path) -> None:
    # given: the hand-off place has a description
    trace = _played(
        tmp_path,
        {"handoff.petrinet": _HANDOFF + '(tray) description "the tray"\n'},
        _LATE,
    )

    # when
    plantuml = render_plantuml(sequence_view(trace))

    # then: the caption is the description, not the parenthesized id
    assert 'queue "the tray" as the_tray' in plantuml
    assert 'queue "(tray)"' not in plantuml


def test_a_same_actor_token_in_a_hand_off_place_draws_no_arrow(
    tmp_path: Path,
) -> None:
    # given: (bin) is a queue because B takes one item, and A also makes an
    # item that only A uses
    trace = _played(
        tmp_path,
        {
            "n.petrinet": 'system "A"\nsystem "B"\n'
            "(raw) -item-> [hand]\n[hand] -item-> (bin)\n"
            "(raw) -item-> [keep]\n[keep] -item-> (bin)\n"
            "(bin) -item-> [take]\n(bin) -item-> [use]\n"
            '[hand] actor "A"\n[keep] actor "A"\n'
            '[take] actor "B"\n[use] actor "A"\n'
            "marking initial (raw) <- $cross\nmarking initial (raw) <- $own\n"
            '$cross: item {"id": "cross"}\n$own: item {"id": "own"}\n'
        },
        'play s\nnet "n.petrinet"\n'
        'fire [hand] with (raw) {"id": "cross"} "A hands one over"\n'
        'fire [keep] with (raw) {"id": "own"} "A sets one aside"\n'
        'fire [use] with (bin) {"id": "own"} "A uses its own"\n'
        'fire [take] with (bin) {"id": "cross"} "B takes the other"\n',
    )

    # when
    view = sequence_view(trace)

    # then: only the token that crosses draws arrows; A's own item is notes
    assert _messages(view.events) == [
        ("A", "(bin)", "A hands one over", False),
        ("(bin)", "B", "B takes the other", False),
    ]
    assert _notes(view.events) == [("A", ("A sets one aside", "A uses its own"))]


def test_an_unconsumed_token_in_a_hand_off_place_is_still_drawn(
    tmp_path: Path,
) -> None:
    # given: A returns an item to a place B has taken from, and nobody takes
    # this one
    trace = _played(
        tmp_path,
        {
            "n.petrinet": 'system "A"\nsystem "B"\n'
            "(raw) -item-> [hand] -item-> (bin)\n"
            "(raw) -item-> [leave] -item-> (bin)\n"
            "(bin) -item-> [take]\n"
            '[hand] actor "A"\n[take] actor "B"\n[leave] actor "A"\n'
            "marking initial (raw) <- $a\nmarking initial (raw) <- $b\n"
            "$a: item {}\n$b: item {}\n"
        },
        'play s\nnet "n.petrinet"\n'
        'fire [hand] "A hands one over"\n'
        'fire [take] "B takes it"\n'
        'fire [leave] "A leaves one behind"\n',
    )

    # when
    events = sequence_view(trace).events

    # then: the return is drawn even though nothing consumes it
    assert _messages(events) == [
        ("A", "(bin)", "A hands one over", False),
        ("(bin)", "B", "B takes it", False),
        ("A", "(bin)", "A leaves one behind", False),
    ]


def test_headings_are_dividers_and_level_three_opens_a_group() -> None:
    # when
    events = sequence_view(_trace()).events

    # then: the group runs until the next heading
    markers = [
        e for e in events if isinstance(e, Delay | Divider | GroupOpen | GroupClose)
    ]
    assert markers == [
        Divider("Close"),
        GroupOpen("First hold"),
        Delay("1 hour 30 minutes later"),
        GroupClose(),
        Divider("Check and reopen"),
    ]
    plantuml = render_plantuml(sequence_view(_trace()))
    assert "group First hold" in plantuml
    assert "...1 hour 30 minutes later..." in plantuml
    assert "== Check and reopen ==" in plantuml


def test_a_group_closes_at_the_end_of_the_path(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net actor Shop\n(a) -> [go] -> (b)\nmarking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\n/// ### Slot 1\nfire [go] "Go"\n',
    )

    # when
    events = sequence_view(trace).events

    # then
    assert events[0] == GroupOpen("Slot 1")
    assert events[-1] == GroupClose()


def test_a_failing_path_ends_with_a_failure_note() -> None:
    # when
    view = sequence_view(_trace("early_check"))

    # then: the branch is marked, and the check fails on the clerk
    assert view.status == "failed"
    assert Divider("Check too early") in view.events
    failure = view.events[-1]
    assert isinstance(failure, Failure)
    assert (failure.actor, failure.label, failure.code) == (
        "Clerk",
        "Check the hold",
        "SC301",
    )
    plantuml = render_plantuml(view)
    assert "note over clerk #FDE2E2" in plantuml
    assert "timer `clock.now >= 3600` is false (clock.now = 0)" in plantuml


def test_a_failing_expect_is_a_note_across(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "(a) -> [go] -> (b)\n[go] actor Ops\nmarking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\nfire [go]\nexpect (b) empty\n',
    )

    # when
    view = sequence_view(trace)

    # then: a passing expect draws nothing; a failing one draws a note
    failure = view.events[-1]
    assert isinstance(failure, Failure)
    assert failure.actor is None
    assert "note across #FDE2E2" in render_plantuml(view)


def test_injections_into_a_place_without_owner_come_from_outside(
    tmp_path: Path,
) -> None:
    # given
    trace = _played(
        tmp_path,
        {"n.petrinet": "(a) -> [go] -> (b)\nnet actor Shop\n"},
        'play s\nnet "n.petrinet"\ninject (a) <- {} "Nudge"\nfire [go] "Go"\n',
    )

    # when
    view = sequence_view(trace)

    # then: the net default actor does the firing; a titled injection into
    # an unowned place is an outside event, drawn into the hand-off queue
    # at the injection, and the firing takes it from there
    assert [lifeline.name for lifeline in view.lifelines] == [
        OUTSIDE,
        "(a)",
        "Shop",
    ]
    assert _messages(view.events) == [
        (OUTSIDE, "(a)", "Nudge", False),
        ("(a)", "Shop", "Go", False),
    ]


def test_an_untitled_setup_injection_hands_over_nothing(tmp_path: Path) -> None:
    # given: the same play without the title
    trace = _played(
        tmp_path,
        {"n.petrinet": "(a) -> [go] -> (b)\nnet actor Shop\n"},
        'play s\nnet "n.petrinet"\ninject (a) <- {}\nfire [go] "Go"\n',
    )

    # when
    view = sequence_view(trace)

    # then: the setup injection before the first firing draws nothing —
    # not even the Outside lifeline — and the firing draws its own note
    assert [lifeline.name for lifeline in view.lifelines] == ["Shop"]
    assert _messages(view.events) == []
    assert _notes(view.events) == [("Shop", ("Go",))]


def test_an_untitled_update_of_a_clock_place_draws_no_hand_off(
    tmp_path: Path,
) -> None:
    """Issue #43: moving a clock without maturing timers draws nothing."""
    # given: the clock is topped up between firings, by `update`
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "person Operator\nnet actor Shop\n"
            "(a) -> [go] -> (b)\n[go] actor Operator\n"
            "(clock) -advance->? [go]\n"
            '[go] timer clock (clock) cel "clock.now >= 3600"\n'
        },
        'play s\nnet "n.petrinet"\nadvance 3600\ninject (a) <- {}\n'
        'fire [go] "Go"\nupdate (clock) <- {"now": 7200}\n'
        'inject (a) <- {}\nfire [go] "Go again"\n',
    )

    # when
    events = sequence_view(trace).events

    # then: the clock's update draws no Outside arrow; the firings keep
    # their own notes, and no hand-off is drawn at all
    assert [lifeline.name for lifeline in sequence_view(trace).lifelines] == [
        "Operator"
    ]
    assert _notes(events) == [("Operator", ("Go", "Go again"))]
    assert _messages(events) == []


def test_an_untitled_injection_into_an_unowned_place_draws_nothing(
    tmp_path: Path,
) -> None:
    """Issue #43: an outside injection is setup, wherever it sits."""
    # given: an untitled injection into an unowned place after a firing; the
    # firing before it gives the actor its own titled step
    trace = _played(
        tmp_path,
        {"n.petrinet": "(a) -> [go] -> (b)\nnet actor Shop\n"},
        'play s\nnet "n.petrinet"\ninject (a) <- {}\nfire [go] "Go"\n'
        'inject (b) <- {}\nfire [go] "Go again"\n',
    )

    # when
    view = sequence_view(trace)

    # then: no Outside lifeline, and the setup injection drew no hand-off —
    # the second firing draws nothing of its own but the first firing's note
    assert [lifeline.name for lifeline in view.lifelines] == ["Shop"]
    assert _messages(view.events) == []


def test_a_token_an_unowned_injection_produced_draws_no_hand_off(
    tmp_path: Path,
) -> None:
    """Issue #43: consuming that token later draws only the consumer's step."""
    # given: an untitled unowned injection keeps a record alive between
    # drawn steps, on a lived place; a later step consumes it
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "person Operator\nnet actor Shop\n"
            "(copy) lives in Shelf\n(a) -> [set] -> (copy)\n"
            "(copy) -token-> [go] -> (b)\n[set] actor Operator\n"
            "[go] actor Shop\n"
        },
        'play s\nnet "n.petrinet"\ninject (a) <- {}\nfire [set] "Set"\n'
        'update (copy) <- {"isbn": "b"}\nfire [go] "Go"\n',
    )

    # when
    view = sequence_view(trace)

    # then: the untitled update drew no Outside arrow; the consumer of its
    # token draws only the read of the column, not a hand-off from Outside
    assert [lifeline.name for lifeline in view.lifelines] == [
        "Operator",
        "Shelf",
        "Shop",
    ]
    assert _messages(view.events) == [
        ("Operator", "Shelf", "Set", False),
        ("Shelf", "Shop", "Copy", True),
    ]


def test_a_titled_injection_into_an_unowned_place_still_hands_over(
    tmp_path: Path,
) -> None:
    """Issue #43: a titled outside event is drawn, as before."""
    # given: a titled injection into an unowned place before the first
    # firing — the author is showing the event on purpose
    trace = _played(
        tmp_path,
        {"n.petrinet": "(a) -> [go] -> (b)\nnet actor Shop\n"},
        'play s\nnet "n.petrinet"\ninject (a) <- {} "Kick off"\nfire [go] "Go"\n',
    )

    # when
    view = sequence_view(trace)

    # then: the arrow stays, from Outside into the hand-off queue, and the
    # firing takes the token out of it
    assert [lifeline.name for lifeline in view.lifelines] == [
        OUTSIDE,
        "(a)",
        "Shop",
    ]
    assert _messages(view.events) == [
        (OUTSIDE, "(a)", "Kick off", False),
        ("(a)", "Shop", "Go", False),
    ]


def test_a_net_without_actors_is_one_lifeline_named_after_it(tmp_path: Path) -> None:
    # given
    trace = _played(
        tmp_path,
        {
            "n.petrinet": "net shop\n(a) -> [go] -> (b) -> [stop] -> (c)\n"
            "marking initial (a) <- 1\n"
        },
        'play s\nnet "n.petrinet"\nfire [go] "Go"\nfire [stop] "Stop"\n',
    )

    # when
    view = sequence_view(trace)

    # then: one actor, no hand-off, so one note with both steps
    assert [lifeline.name for lifeline in view.lifelines] == ["shop"]
    assert _notes(view.events) == [("shop", ("Go", "Stop"))]


_ORDERS = """\
net orders
person Clerk
net actor "Order desk"
(new_order) -> [accept] -> (accepted)
(accepted) -> [hand_over] -> (outbox)
[accept] actor Clerk
(outbox) port output token
(new_order) actor Customer
"""

_SHIPPING = """\
net shipping
(inbox) -> [ship] -> (shipped)
(inbox) port input token
"""


def test_actors_survive_composition(tmp_path: Path) -> None:
    # given: shipping has no actors, so its lifeline is its alias
    trace = _played(
        tmp_path,
        {"orders.petrinet": _ORDERS, "shipping.petrinet": _SHIPPING},
        'play s\nuse "orders.petrinet" as orders\n'
        'use "shipping.petrinet" as shipping\n'
        "wire orders.(outbox) -> shipping.(inbox)\n"
        "system Customer\n"
        'inject (orders.new_order) <- {} "Order placed"\n'
        'fire [orders.accept] "Order accepted"\nfire [orders.hand_over] "Handed over"\n'
        "fire [shipping.ship]\n",
    )

    # when
    view = sequence_view(trace)

    # then: the play's declaration comes first, then the net's, and each
    # hand-off place sits beside the actor that produces into it
    assert [(lifeline.name, lifeline.kind) for lifeline in view.lifelines] == [
        ("Customer", "system"),
        ("(orders.new_order)", "queue"),
        ("Clerk", "person"),
        ("(orders.accepted)", "queue"),
        ("Order desk", "system"),
        ("(orders.outbox)", "queue"),
        ("shipping", "system"),
    ]
    assert _messages(view.events) == [
        ("Customer", "(orders.new_order)", "Order placed", False),
        ("(orders.new_order)", "Clerk", "Order accepted", False),
        ("Clerk", "(orders.accepted)", "token", False),
        ("(orders.accepted)", "Order desk", "Handed over", False),
        ("Order desk", "(orders.outbox)", "token", False),
        ("(orders.outbox)", "shipping", "token", False),
    ]


def test_lived_places_survive_composition(tmp_path: Path) -> None:
    # given: the switch lives on a column in the net that owns it
    trace = _played(
        tmp_path,
        {
            "owner.petrinet": "record Switch\n(switch) -> [flip] -> (switch)\n"
            "(switch) port output token\n(switch) lives in Switch\n"
            "(switch) actor Ops\n[flip] actor Ops\n",
            "shop.petrinet": "net actor Shop\n(slot) -> [deliver] -> (sent)\n(slot) actor Shop\n"
            "(switch) -token->? [deliver]\n(switch) port input token\n",
        },
        'play s\nuse "owner.petrinet" as owner\nuse "shop.petrinet" as shop\n'
        "wire owner.(switch) -> shop.(switch)\n"
        'inject (owner.switch) <- {}\nfire [owner.flip] "Flip"\n'
        'inject (shop.slot) <- {}\nfire [shop.deliver] "Deliver"\n',
    )

    # when
    view = sequence_view(trace)

    # then
    assert ("Switch", "record") in [(ll.name, ll.kind) for ll in view.lifelines]
    assert _messages(view.events) == [
        ("Ops", "Switch", "Flip", False),
        ("Switch", "Shop", "Switch", True),
    ]


# ── The language ─────────────────────────────────────────────────────────


def test_show_sequence_sets_the_play_and_path_modes() -> None:
    # when
    play = read_play(_FIXTURES / "evening-shift.play")

    # then
    assert play.sequence == "beside"
    early = play.path("early_check")
    assert early is not None and early.sequence == "only"


def test_a_quoted_sequence_is_still_a_color() -> None:
    # when
    play = parse_play(
        'play s\nnet "n.petrinet"\nshow "sequence" id\nperson Ops\n'
    )

    # then
    assert play.sequence is None
    assert play.shows[0].color == "sequence"
    assert [(a.name, a.kind) for a in play.actors] == [("Ops", "person")]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("show sequence\nshow sequence only\n", "SC104"),
        ("show sequence twice\n", "SC101"),
        ("person Ops\nsystem Ops\n", "SC105"),
        ("box Team A B\nbox Other B\n", "SC105"),
        ("box Team\n", "SC101"),
    ],
)
def test_sequence_and_actor_settings_reject_repeats(body: str, code: str) -> None:
    with pytest.raises(PlayError) as raised:
        parse_play('play s\nnet "n.petrinet"\n' + body)
    assert raised.value.diagnostic.code == code


def test_record_and_box_lines_parse() -> None:
    # when
    play = parse_play(
        'play s\nnet "n.petrinet"\nrecord "Branch home"\n'
        'box "Night crew" Runner Desk\n'
    )

    # then
    assert [(a.name, a.kind) for a in play.actors] == [("Branch home", "record")]
    assert [(b.title, b.members) for b in play.boxes] == [
        ("Night crew", ("Runner", "Desk"))
    ]


# ── The walkthrough and the command line ─────────────────────────────────


def test_a_walkthrough_carries_the_sequence_beside_its_steps() -> None:
    # when
    document = walkthrough_document(_trace())
    markdown = render_walkthrough(_trace())

    # then
    assert document["sequence"]["mode"] == "beside"
    assert document["sequence"]["plantuml"].startswith("@startuml\n")
    assert document["steps"]
    assert "## Sequence\n\n```plantuml\n@startuml" in markdown
    assert "```dot" in markdown


def test_sequence_only_drops_the_graphs() -> None:
    # when
    document = walkthrough_document(_trace("early_check"))
    markdown = render_walkthrough(_trace("early_check"))

    # then
    assert document["sequence"]["mode"] == "only"
    assert document["stage"] is None
    assert document["steps"] == []
    assert document["failure"]["code"] == "SC301"
    assert "```dot" not in markdown
    assert "## The check stops here" in markdown


def test_the_walk_option_overrides_the_play() -> None:
    # when
    document = walkthrough_document(_trace(), sequence="none")
    only = walkthrough_document(_trace(), sequence="only")

    # then
    assert document["sequence"] is None
    assert only["stage"] is None


def test_play_sequence_prints_plantuml_or_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    for name in ("evening-shift.petrinet", "evening-shift.play"):
        shutil.copy(_FIXTURES / name, tmp_path / name)
    play = str(tmp_path / "evening-shift.play")

    # when
    code = cli.main(["play", "sequence", play])
    plantuml = capsys.readouterr().out
    json_code = cli.main(
        ["play", "sequence", play, "--path", "early_check", "--format", "json"]
    )
    captured = capsys.readouterr()

    # then
    assert code == 0
    assert plantuml == (_FIXTURES / "evening-shift.sequence.puml").read_text()
    assert json_code == 1
    document = json.loads(captured.out)
    assert document["status"] == "failed"
    assert document["events"][-1]["kind"] == "failure"
    assert document["title"] == "Evening shift"
    assert document["boxes"] == [
        {"title": "Night crew", "lifelines": ["Runner", "Desk"]}
    ]
    assert {event["kind"] for event in document["events"]} >= {
        "message",
        "note",
        "activate",
        "deactivate",
        "divider",
        "failure",
    }
    assert {
        "from": "Desk",
        "to": "(request)",
        "label": "Hold filed",
    }.items() <= (
        next(
            e
            for e in document["events"]
            if e["kind"] == "message" and e["from"] == "Desk"
        ).items()
    )
    assert "error[SC301]" in captured.err


def test_walk_takes_a_sequence_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    for name in ("evening-shift.petrinet", "evening-shift.play"):
        shutil.copy(_FIXTURES / name, tmp_path / name)

    # when
    code = cli.main(
        [
            "play",
            "walk",
            str(tmp_path / "evening-shift.play"),
            "--sequence",
            "only",
            "--format",
            "json",
        ]
    )

    # then
    assert code == 0
    assert json.loads(capsys.readouterr().out)["stage"] is None


# ── Actor facts in the net language ──────────────────────────────────────


def test_actor_facts_lower_to_annotations_and_round_trip() -> None:
    # given
    source = (
        "net desk\nperson Operator\nsystem Platform\nnet actor Platform\n"
        "(a) -> [flip] -> (b)\n[flip] actor Operator\n(a) actor Operator\n"
    )

    # when
    document = compile_petrinet_text(source)
    emitted = emit_petrinet(document)

    # then
    assert document["annotations"] == {
        "actor": "Platform",
        "actors": [
            {"name": "Operator", "kind": "person"},
            {"name": "Platform", "kind": "system"},
        ],
    }
    assert document["transitions"][0]["annotations"] == {"actor": "Operator"}
    assert document["places"][0]["annotations"] == {"actor": "Operator"}
    for line in (
        "net actor Platform",
        "[flip] actor Operator",
        "(a) actor Operator",
        "person Operator",
        "system Platform",
    ):
        assert line in emitted.splitlines()
    assert compile_petrinet_text(emitted) == document


def test_the_merge_fills_in_default_actors_and_carries_declarations() -> None:
    # given
    orders = parse_net(compile_petrinet_text(_ORDERS))
    shipping = parse_net(compile_petrinet_text(_SHIPPING + "person Clerk\n"))

    # when
    merged = merge_nets({"orders": orders, "shipping": shipping}, [])

    # then
    actors = {t.name: (t.annotations or {}).get("actor") for t in merged.transitions}
    assert actors == {
        "orders.accept": "Clerk",
        "orders.hand_over": "Order desk",
        "shipping.ship": None,
    }
    assert merged.annotations == {"actors": [{"name": "Clerk", "kind": "person"}]}


def test_the_merge_rejects_an_actor_of_two_kinds() -> None:
    # given
    orders = parse_net(compile_petrinet_text(_ORDERS))
    shipping = parse_net(compile_petrinet_text(_SHIPPING + "system Clerk\n"))

    # then
    with pytest.raises(NetValidationError, match="Clerk is a person"):
        merge_nets({"orders": orders, "shipping": shipping}, [])


def test_lived_place_facts_lower_to_annotations_and_round_trip() -> None:
    # given
    source = (
        'record "Branch home"\n(a) -> [flip] -> (a)\n(b) -> [send] -> (c)\n'
        '(a) lives in "Branch home"\n(a) reads as cel "token.owner"\n'
        '(c) lives in cel "token.host"\n'
    )

    # when
    document = compile_petrinet_text(source)
    emitted = emit_petrinet(document)

    # then
    annotations = {p["name"]: p.get("annotations") for p in document["places"]}
    assert annotations["a"] == {
        "lives": "Branch home",
        "reads_as": {"cel": "token.owner"},
    }
    assert annotations["c"] == {"lives": {"cel": "token.host"}}
    assert document["annotations"] == {
        "actors": [{"name": "Branch home", "kind": "record"}]
    }
    for line in (
        '(a) lives in "Branch home"',
        '(a) reads as cel "token.owner"',
        '(c) lives in cel "token.host"',
        'record "Branch home"',
    ):
        assert line in emitted.splitlines()
    assert compile_petrinet_text(emitted) == document
