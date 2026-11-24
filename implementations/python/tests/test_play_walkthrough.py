"""Walkthroughs: the touched subnet, twin before/after graphs per step,
scopes, chosen fields, checks and prose.

The trunk of ``fixtures/play/shop.play`` is pinned as a golden
Markdown file. Regenerate it with ``VELOCITRON_UPDATE_GOLDEN=1`` after an
intended change, and look at the result before committing it.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from velocitron_play import (
    PlayError,
    ShowDecl,
    parse_play,
    read_play,
)
from velocitron_play_check import (
    check_play,
    render_walkthrough,
    walkthrough_document,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "play"


def _report():
    return check_play(read_play(_FIXTURES / "shop.play"))


def test_trunk_walkthrough_matches_the_golden_file() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    markdown = render_walkthrough(trace)

    # then
    golden = _FIXTURES / "shop.walkthrough.md"
    if os.environ.get("VELOCITRON_UPDATE_GOLDEN"):
        golden.write_text(markdown, encoding="utf-8")
    assert markdown == golden.read_text(encoding="utf-8")


def test_the_document_has_one_section_per_marking_change() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    document = walkthrough_document(trace)

    # then: two firings; each expect's checks join the step before it
    assert [s["heading"] for s in document["steps"]] == [
        "Step 1 — the shop accepts the purchase",
        "Step 2 — the purchase ships",
    ]
    first = document["steps"][0]
    assert [c["text"] for c in first["checks"]] == [
        "(accepted) == $o1",
        "enabled [ship]",
    ]
    assert first["prose_md"] == (
        "Accepting moves the purchase; the carry rule keeps its data."
    )
    assert document["prose_md"].startswith("A purchase arrives")
    assert document["status"] == "passed"


def test_the_subnet_is_what_the_path_touches() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    stage = walkthrough_document(trace)["stage"]["dot"]

    # then: fired transitions and the places on their arcs; nothing else
    for node in ('"accept"', '"ship"', '"holds"', '"stock"', '"receipts"'):
        assert node in stage
    for node in ('"expire"', '"split"', '"copy"', '"audit"', '"lane_a"'):
        assert node not in stage


def test_a_step_draws_before_and_after_as_twin_graphs() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    step = walkthrough_document(trace)["steps"][0]

    # then: two graphs with the same nodes; only marks and highlights differ
    before, after = step["before_dot"], step["after_dot"]
    assert "<b>before</b>" in before and "<b>after</b>" in after
    assert "<b>fires</b>" in before and "<b>fired</b>" in after
    assert "<i>consumed</i>" in before and "<i>produced</i>" in after
    assert _nodes(before) == _nodes(after)


def _nodes(dot: str) -> set[str]:
    return {
        line.split()[0].strip('"') for line in dot.splitlines() if "[shape=" in line
    }


def test_the_step_scope_draws_the_transition_and_its_places() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    first, second = walkthrough_document(trace)["steps"]

    # then: accept with inbox and accepted; ship with every place on its arcs
    assert _nodes(first["before_dot"]) == {"inbox", "accept", "accepted"}
    assert _nodes(second["before_dot"]) == {
        "accepted",
        "stock",
        "holds",
        "ship",
        "shipped",
        "receipts",
    }


def test_the_neighbors_scope_adds_faded_transitions_and_no_further() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    first = walkthrough_document(trace, scope="neighbors")["steps"][0]

    # then: the other transitions on inbox and accepted, faded; not their places
    dot = first["before_dot"]
    assert _nodes(dot) == {
        "inbox",
        "accept",
        "accepted",
        "ship",
        "expire",
        "split",
        "audit",
    }
    assert '"ship" [shape=box, style="filled,dashed"' in dot
    assert '"accept" [shape=box, style=filled' in dot


def test_the_subnet_scope_draws_the_whole_touched_subnet() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    document = walkthrough_document(trace, scope="subnet")

    # then
    assert _nodes(document["steps"][0]["before_dot"]) == _nodes(
        document["stage"]["dot"]
    )
    assert document["scope"] == "subnet"


def test_an_injection_draws_its_place_alone() -> None:
    # given
    trace = _report().trace("held")
    assert trace is not None

    # when
    injection = walkthrough_document(trace)["steps"][0]

    # then: the before half carries the after label as a transparent ghost
    assert _nodes(injection["before_dot"]) == {"holds"}
    assert "<b>injected</b>" in injection["after_dot"]
    assert 'color="#00000000"><b>injected</b>' in injection["before_dot"]


def test_a_play_scope_setting_is_the_default_the_caller_overrides() -> None:
    # given
    play = read_play(_FIXTURES / "shop.play")
    scoped = replace(play, scope="subnet")
    trace = check_play(scoped).trace("trunk")
    assert trace is not None

    # when / then
    assert walkthrough_document(trace)["scope"] == "subnet"
    assert walkthrough_document(trace, scope="step")["scope"] == "step"


def test_a_step_emphasizes_the_fields_it_changed() -> None:
    # given: a second advance changes the clock's now
    source = 'play s\nnet "shop.petrinet"\nshow tick now\nadvance 100\nadvance +50\n'
    play = parse_play(source, origin=_FIXTURES)
    trace = check_play(play).trace("trunk")
    assert trace is not None

    # when
    advance = walkthrough_document(trace)["steps"][1]

    # then: old and new values, each emphasized
    assert "<u>now=100</u>" in advance["before_dot"]
    assert "<u>now=150</u>" in advance["after_dot"]


_WAIT_NET = """net waits
(ended) -result-> [wait] -hold-> (waiting)
@unlock: [wait] -lock-> (free)
@unlock data cel "{'id': binding.ended[0].hold.branch, 'isbn': binding.ended[0].hold.isbn}"
"""

_WAIT_SOURCE = """play s
net "waits.petrinet"
show hold id
show lock id
inject (ended) <- result {"outcome": "failed", "hold": {"id": "d-1", "isbn": "f", "branch": "g"}}
fire [wait] -> (waiting) hold {"id": "d-1", "isbn": "f", "branch": "g", "remindAt": 5400}
"""


def test_a_new_color_carries_forward_the_object_it_keeps_most_fields_of(
    tmp_path: Path,
) -> None:
    # given: wait turns a result back into the hold embedded in it, adds
    # remindAt, and makes a new lock that shares only isbn with it
    (tmp_path / "waits.petrinet").write_text(_WAIT_NET, encoding="utf-8")
    play = parse_play(_WAIT_SOURCE, origin=tmp_path)
    trace = check_play(play).trace("trunk")
    assert trace is not None

    # when
    wait = walkthrough_document(trace)["steps"][1]

    # then: the hold's new field is emphasized; the lock is new, so none is
    assert "<u>remindAt=5400</u>" in wait["after_dot"]
    assert "<u>id=d-1</u>" not in wait["after_dot"]
    assert "<u>id=g</u>" not in wait["after_dot"]
    assert "<u>" not in wait["before_dot"].replace('color="#00000000"><b><u>', "")


def test_show_settings_choose_the_fields_of_a_color() -> None:
    # given
    play = read_play(_FIXTURES / "shop.play")
    shown = replace(play, shows=(ShowDecl("purchase", ("id",), play.position),))
    trace = check_play(shown).trace("trunk")
    assert trace is not None

    # when
    step = walkthrough_document(trace)["steps"][0]

    # then
    assert "● purchase id=o-1" in step["before_dot"]
    assert "dueAt" not in step["before_dot"].split("tooltip")[0]


def test_a_branch_starts_from_its_branch_point() -> None:
    # given
    trace = _report().trace("late")
    assert trace is not None

    # when
    document = walkthrough_document(trace)

    # then: the inherited step is listed and numbering continues
    assert document["stage"]["inherited"] == ["Step 1 — the shop accepts the purchase"]
    ((inherited,), own) = (
        document["stage"]["inherited_steps"],
        document["steps"],
    )
    assert inherited == {
        "number": 1,
        "heading": "Step 1 — the shop accepts the purchase",
        "title": "the shop accepts the purchase",
        "statement": "fire [accept]",
        "line": 10,
        "caption": (
            "Fired [accept] · consumed 1 in (inbox) · "
            "outputs (accepted) purchase: carried over."
        ),
        "prose_md": "Accepting moves the purchase; the carry rule keeps its data.",
        "status": "inherited",
    }
    assert [s["number"] for s in own] == [2, 3]
    assert document["stage"]["dot"].count("● purchase") == 1
    assert document["steps"][0]["checks"][0]["detail"].startswith(
        "the priority policy picks [expire]"
    )


def test_a_failing_path_ends_with_the_failure() -> None:
    # given
    trace = _report().trace("held")
    assert trace is not None

    # when
    document = walkthrough_document(trace)
    markdown = render_walkthrough(trace)

    # then: the broken step shows its before graph in the failure style
    broken = document["steps"][-1]
    assert broken["status"] == "failed"
    assert "after_dot" not in broken
    assert "✗ not enabled" in broken["before_dot"]
    assert 'fillcolor="#FDE2E1"' in broken["before_dot"]
    assert document["failure"]["code"] == "SC301"
    assert markdown.rstrip().endswith("```")
    assert "## The check stops here" in markdown
    assert "error[SC301]: [ship] is not enabled" in markdown


def test_json_format_is_the_walkthrough_document() -> None:
    # given
    trace = _report().trace("trunk")
    assert trace is not None

    # when
    parsed = json.loads(render_walkthrough(trace, format="json"))

    # then
    assert set(parsed) == {
        "play",
        "title",
        "path",
        "path_title",
        "branch_from",
        "net",
        "status",
        "scope",
        "direction",
        "prose_md",
        "sequence",
        "stage",
        "steps",
        "failure",
    }
    assert parsed["sequence"] is None
    assert set(parsed["steps"][0]) >= {
        "number",
        "title",
        "prose_md",
        "before_dot",
        "after_dot",
        "checks",
        "status",
    }


def test_left_to_right_direction() -> None:
    trace = _report().trace("trunk")
    assert trace is not None
    assert "rankdir=LR;" in render_walkthrough(trace, rankdir="LR")


def test_show_of_a_color_no_place_takes_is_sc214() -> None:
    # given
    play = parse_play(
        'play s\nnet "shop.petrinet"\nshow ghost id\n', origin=_FIXTURES
    )

    # when
    with pytest.raises(PlayError) as caught:
        check_play(play)

    # then
    assert caught.value.diagnostic.code == "SC214"
    assert caught.value.diagnostic.position.line == 3
