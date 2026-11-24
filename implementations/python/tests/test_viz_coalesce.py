# Shared fusion copies between neighbor siblings (viz.py, ADR 0035).

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_petrinet import parse_net
from velocitron_play import (
    parse_play,
)
from velocitron_play_check import (
    check_play,
    walkthrough_document,
)
from velocitron_engine import Net
from velocitron_viz import (
    fusion_layout,
    net_to_dot,
    sibling_groups,
)
from velocitron_viz import (
    Decorations,
    read_decorations,
)

# A choice on (pending): hold, skip and send each consume from it.
_CHOICE = """
net choice

(pending) -delivery-> [hold] -delivery-> (held)
(pending) -delivery-> [skip] -delivery-> (skipped)
(pending) -delivery-> [send] -delivery-> (sending)
(sending) -delivery-> [attempt] -delivery-> (done)
"""


def _compile(arcs: str, decorations: str = "") -> tuple[Net, Decorations]:
    fusion = "".join(
        f"({place}) annotation fusion true\n"
        for place in ("switch", "verdicts")
        if f"({place})" in arcs
    )
    document = compile_petrinet_text(
        _CHOICE + arcs + fusion + decorations, "choice.petrinet"
    )
    return parse_net(document), read_decorations(document)


def _fusion(net: Net) -> set[str]:
    return {p.name for p in net.places if (p.annotations or {}).get("fusion")}


def test_sibling_groups_are_transitions_with_the_same_one_input_place() -> None:
    # given: a choice on pending, and a transition with a second drawn input
    net, _ = _compile(
        "(switch) -switch->? [hold]\n"
        "(held) -delivery-> [release] -delivery-> (pending)\n"
        "(pending) -delivery-> [cancel]\n(held) -delivery->? [cancel]\n"
    )
    # when: the siblings are discovered
    groups = sibling_groups(net, _fusion(net))
    # then: the choice in arc order; a fusion input does not count, a second
    # drawn input does, and a lone transition makes no group
    assert groups == [("hold", "skip", "send")]


def test_two_neighbor_siblings_share_one_copy_between_them() -> None:
    # given: hold and skip both read switch, beside with no side
    net, decorations = _compile(
        "(switch) -switch->? [hold]\n(switch) -switch->? [skip]\n",
        "decorate (switch) beside\n",
    )
    # when
    layout = fusion_layout(net, _fusion(net), decorations)
    # then: one copy for both, drawn between them in one row
    assert layout.copies == {
        ("switch", "hold"): "switch@hold+skip",
        ("switch", "skip"): "switch@hold+skip",
    }
    assert layout.rows == (("hold", "switch@hold+skip", "skip"),)


def test_both_arcs_go_to_the_shared_copy_with_their_own_labels() -> None:
    # given
    net, decorations = _compile(
        "@h: (switch) -switch->? [hold]\n@h predicate cel \"owner == 'a'\"\n"
        "@s: (switch) -switch->? [skip]\n@s predicate cel \"owner == 'b'\"\n",
        "decorate (switch) beside\n",
    )
    # when
    dot = net_to_dot(net, decorations=decorations)
    # then: the copy is drawn once, and each arc keeps its own label
    assert dot.count('"switch@hold+skip" [shape=ellipse') == 1
    hold_arc = [
        line
        for line in dot.splitlines()
        if line.startswith('    "switch@hold+skip" -> "hold" [label')
    ]
    skip_arc = [
        line
        for line in dot.splitlines()
        if line.startswith('    "switch@hold+skip" -> "skip" [label')
    ]
    assert len(hold_arc) == 1 and len(skip_arc) == 1
    assert "owner == 'a'" in hold_arc[0] and "owner == 'b'" in skip_arc[0]
    # and: the row is ranked as one, without dot's last crossing pass
    assert "    newrank=true;" in dot.splitlines()
    assert "    remincross=false;" in dot.splitlines()
    assert '    "hold" -> "switch@hold+skip" -> "skip" [style=invis];' in dot


def test_a_run_of_three_pairs_from_the_left_and_the_last_copy_goes_right() -> None:
    # given: hold, skip and send all read switch
    net, decorations = _compile(
        "(switch) -switch->? [hold]\n(switch) -switch->? [skip]\n"
        "(switch) -switch->? [send]\n",
        "decorate (switch) beside\n",
    )
    # when
    layout = fusion_layout(net, _fusion(net), decorations)
    # then: hold and skip share a copy; send keeps its own, on its far side
    assert layout.rows == (("hold", "switch@hold+skip", "skip", "send", "switch@send"),)


def test_own_copies_balance_against_the_shared_copy() -> None:
    # given: hold also reads verdicts, and send reads both places
    net, decorations = _compile(
        "(verdicts) -verdict->? [hold]\n(switch) -switch->? [hold]\n"
        "(switch) -switch->? [skip]\n"
        "(switch) -switch->? [send]\n(verdicts) -verdict->? [send]\n",
        "decorate (switch) beside\ndecorate (verdicts) beside\n",
    )
    # when
    layout = fusion_layout(net, _fusion(net), decorations)
    # then: hold's verdicts goes left, away from the shared copy; send's
    # switch goes right (the run's last), so its verdicts goes left
    assert layout.rows == (
        (
            "verdicts@hold",
            "hold",
            "switch@hold+skip",
            "skip",
            "verdicts@send",
            "send",
            "switch@send",
        ),
    )


def test_copies_on_siblings_that_are_not_neighbors_stay_apart() -> None:
    # given: hold and send read switch; skip, between them, does not
    net, decorations = _compile(
        "(switch) -switch->? [hold]\n(switch) -switch->? [send]\n",
        "decorate (switch) beside\n",
    )
    # when
    layout = fusion_layout(net, _fusion(net), decorations)
    # then: one copy each, in a row of its own
    assert layout.rows == (("switch@hold", "hold"), ("switch@send", "send"))


def test_a_place_beside_one_side_or_not_beside_keeps_one_copy_per_transition() -> None:
    # given: switch beside left, verdicts not beside; both read by hold and skip
    net, decorations = _compile(
        "(switch) -switch->? [hold]\n(switch) -switch->? [skip]\n"
        "(verdicts) -verdict->? [hold]\n(verdicts) -verdict->? [skip]\n",
        "decorate (switch) beside left\n",
    )
    # when
    layout = fusion_layout(net, _fusion(net), decorations)
    # then
    assert "+" not in "".join(layout.copies.values())
    assert layout.rows == (("switch@hold", "hold"), ("switch@skip", "skip"))


def test_consume_and_inhibit_arcs_share_a_copy_too() -> None:
    # given: hold consumes a switch token; skip requires there is none
    net, decorations = _compile(
        "(switch) -switch-> [hold]\n(switch) -switch->0 [skip]\n",
        "decorate (switch) beside\n",
    )
    # when
    dot = net_to_dot(net, decorations=decorations)
    # then
    assert '    "switch@hold+skip" -> "hold" [' in dot
    assert '    "switch@hold+skip" -> "skip" [' in dot


_PLAY_NET = _CHOICE + (
    "(switch) -switch->? [hold]\n(switch) -switch->? [skip]\n"
    "(switch) annotation fusion true\n"
    "decorate (switch) beside\n"
    "marking initial (pending) <- $d1\nmarking initial (pending) <- $d2\n"
    '$d1: delivery {"id": "d-1"}\n$d2: delivery {"id": "d-2"}\n'
)


def _walkthrough(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "choice.petrinet").write_text(_PLAY_NET, encoding="utf-8")
    play = parse_play(
        'play s\nnet "choice.petrinet"\n'
        'inject (switch) <- switch {"owner": "annex"}\n'
        "fire [hold]\nfire [skip]\n",
        origin=tmp_path,
    )
    trace = check_play(play).trace("trunk")
    assert trace is not None
    return walkthrough_document(trace, scope="subnet")


def test_a_walkthrough_draws_the_shared_copy_once_with_its_marking(
    tmp_path: Path,
) -> None:
    # when: the subnet scope draws hold and skip in every step
    document = _walkthrough(tmp_path)
    injection = document["steps"][0]
    # then: one switch copy, and its injected token shows once
    for dot in (injection["before_dot"], injection["after_dot"]):
        assert dot.count('"switch@hold+skip" [shape=ellipse') == 1
        assert '"switch@hold" ' not in dot
    assert injection["after_dot"].count("<i>injected</i>") == 1


@pytest.mark.skipif(shutil.which("dot") is None, reason="needs Graphviz dot")
def test_twin_graphs_with_a_shared_copy_get_one_layout(tmp_path: Path) -> None:
    # given
    steps: list[dict[str, str]] = _walkthrough(tmp_path)["steps"]

    def layout(dot: str) -> dict[str, tuple[str, str, str]]:
        out = subprocess.run(
            ["dot", "-Tjson"], input=dot, capture_output=True, text=True, check=True
        ).stdout
        return {
            o["name"]: (o["pos"], o["width"], o["height"])
            for o in json.loads(out)["objects"]
            if "pos" in o
        }

    # when / then: every step's halves are laid out alike, the copy between
    for step in steps:
        before, after = layout(step["before_dot"]), layout(step["after_dot"])
        assert before == after
        x = {name: float(pos.split(",")[0]) for name, (pos, _, _) in before.items()}
        assert x["hold"] < x["switch@hold+skip"] < x["skip"]
