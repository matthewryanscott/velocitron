"""Per-token row marks, the failure style, and the before/after twin render.

A play walkthrough marks what one step did to single tokens (consumed,
produced, read, replaced, injected), styles a transition that could not
fire, and draws a net twice, before and after, as two graphs with one
layout. A color may show chosen fields, and a step's changed fields.

References: ADR 0024; ADR 0028; ADR 0031; ADR 0033.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from velocitron_petrinet import parse_net
from velocitron_engine import (
    Marking,
    Net,
    Token,
)
from velocitron_viz import (
    PairSide,
    RenderStyle,
    net_to_dot,
    net_twin_dots,
)
from velocitron_viz import (
    Decoration,
    Decorations,
)


def _net() -> Net:
    return parse_net(
        {
            "name": "marks",
            "places": [
                {"name": "inbox", "accepts": ["job"]},
                {"name": "done", "accepts": ["job"]},
                {"name": "env", "accepts": ["flag"], "annotations": {"fusion": True}},
            ],
            "transitions": [{"name": "work"}],
            "arcs": [
                {
                    "from": {"place": "inbox"},
                    "to": {"transition": "work"},
                    "consume": {"type": "job"},
                },
                {
                    "from": {"place": "env"},
                    "to": {"transition": "work"},
                    "consume": {"type": "flag", "mode": "read"},
                },
                {
                    "from": {"transition": "work"},
                    "to": {"place": "done"},
                    "produce": {"type": "job", "destination": "done"},
                },
            ],
        }
    )


def _job(n: int) -> Token:
    return Token("job", {"n": n})


def test_a_marked_token_gets_its_own_styled_row() -> None:
    # given: two equal jobs, one of them consumed
    marking = Marking({"inbox": [_job(1), _job(1)]})

    # when
    dot = net_to_dot(_net(), marking=marking, token_marks={"inbox": ["consumed", None]})

    # then: the twins split into an unmarked row and a struck, pink row
    assert 'bgcolor="#FBCFE8"' in dot
    assert '<s>● job {"n":1}</s> <i>consumed</i>' in dot
    assert dot.count("● job") == 2


def test_plain_labels_name_the_mark() -> None:
    # when
    dot = net_to_dot(
        _net(),
        marking=Marking({"done": [_job(2)]}),
        token_marks={"done": ["produced"]},
        style=RenderStyle(html_labels=False),
    )

    # then
    assert "[produced]" in dot


def test_without_marks_the_render_is_unchanged() -> None:
    marking = Marking({"inbox": [_job(1)]})
    assert net_to_dot(_net(), marking=marking) == net_to_dot(
        _net(), marking=marking, token_marks={}
    )


def test_failure_style_overrides_the_highlight() -> None:
    # when
    dot = net_to_dot(
        _net(),
        decorations=Decorations(
            nodes={
                "transition:work": Decoration(
                    highlight=True, highlight_label="✗ not enabled", failure=True
                )
            }
        ),
    )

    # then
    assert 'fillcolor="#FDE2E1", color="#B42318"' in dot
    assert '<font point-size="9" color="#B42318"><b>✗ not enabled</b></font>' in dot


def _pair() -> tuple[str, str]:
    before = Marking({"inbox": [_job(1)], "env": [Token("flag", {})]})
    after = Marking({"done": [_job(1)], "env": [Token("flag", {})]})
    work = "transition:work"
    return net_twin_dots(
        _net(),
        PairSide(
            "before",
            before,
            Decorations(
                nodes={work: Decoration(highlight=True, highlight_label="fires")}
            ),
            {"inbox": ["consumed"], "env": ["read"]},
        ),
        PairSide(
            "after",
            after,
            Decorations(
                nodes={work: Decoration(highlight=True, highlight_label="fired")}
            ),
            {"done": ["produced"], "env": ["read"]},
        ),
        splines="spline",
    )


def _geometry(dot: str) -> str:
    """The DOT text without what does not change a node's size: colors,
    fills, line styles, tooltips, the graph title and the highlight words."""
    dot = re.sub(r' ?(bg)?color="[^"]*"', "", dot)
    dot = re.sub(r', tooltip="(?:[^"\\]|\\.)*"', "", dot)
    dot = re.sub(r'style="?[a-z,]*"?', "", dot)
    dot = re.sub(r"<b>(before|after)</b>", "", dot)
    return re.sub(r"<b>fire[sd]</b>", "", dot)


def test_twin_graphs_give_every_node_the_size_of_its_twin() -> None:
    # when
    before, after = _pair()

    # then: both graphs draw the same nodes with the same label geometry
    assert _geometry(before) == _geometry(after)
    assert "splines=spline;" in before and "splines=spline;" in after
    # and: each half shows its own token and a transparent ghost of the other's
    assert before.count("<i>produced</i>") == 1
    assert after.count("<i>consumed</i>") == 1
    assert '<td align="left"><font point-size="9" color="#00000000"><b>● job' in before
    assert '<td align="left"><font point-size="9" color="#00000000"><s>● job' in after
    # and: the differing highlight labels sit in cells of one fixed width
    assert before.count('fixedsize="true" width="34"') == 1
    assert after.count('fixedsize="true" width="34"') == 1


def test_a_read_row_has_a_dashed_outline_not_a_fill() -> None:
    # when
    before, _ = _pair()

    # then
    assert 'border="1" style="dashed"' in before


@pytest.mark.skipif(shutil.which("dot") is None, reason="needs Graphviz dot")
def test_twin_graphs_get_one_layout_from_dot() -> None:
    # given
    before, after = _pair()

    # when
    def layout(dot: str) -> dict[str, tuple[str, str, str]]:
        # plain text: Graphviz 2.42's -Tjson can embed raw image bytes.
        out = subprocess.run(
            ["dot", "-Tplain"], input=dot, capture_output=True, text=True, check=True
        ).stdout
        found: dict[str, tuple[str, str, str]] = {}
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0] == "node":
                name = parts[1].strip('"')
                found[name] = (f"{parts[2]},{parts[3]}", parts[4], parts[5])
        return found

    # then
    assert layout(before) == layout(after)


def test_a_shown_color_lists_only_its_chosen_fields() -> None:
    # given
    token = Token("job", {"n": 1, "id": "j-1", "owner": {"id": "o-7", "x": 2}})
    style = RenderStyle(shown_fields={"job": ("id", "owner.id")})

    # when
    dot = net_to_dot(_net(), marking=Marking({"inbox": [token]}), style=style)

    # then: the chosen fields, a dotted path into a nested object, no others
    assert "● job id=j-1 · owner.id=o-7" in dot
    assert "n=1" not in dot
    # and: the tooltip holds the full data
    assert 'tooltip="job {\\"id\\":\\"j-1\\",\\"n\\":1' in dot


def test_a_changed_field_is_shown_and_emphasized() -> None:
    # given: n is not chosen, but the step changed it
    token = Token("job", {"n": 2, "id": "j-1"})
    style = RenderStyle(shown_fields={"job": ("id",)})

    # when
    dot = net_to_dot(
        _net(),
        marking=Marking({"done": [token]}),
        style=style,
        token_marks={"done": ["produced"]},
        token_changes={"done": [frozenset({"n"})]},
    )

    # then
    assert "id=j-1 · " in dot
    assert '<font color="#B45309"><b><u>n=2</u></b></font>' in dot


def test_a_color_without_chosen_fields_keeps_its_full_data() -> None:
    # when
    dot = net_to_dot(
        _net(),
        marking=Marking({"inbox": [_job(1)]}),
        style=RenderStyle(shown_fields={"flag": ("on",)}),
    )

    # then
    assert '● job {"n":1}' in dot
