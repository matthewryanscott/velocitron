"""Layout metrics over frozen Graphviz JSON, plus the arc-id stamp."""

from __future__ import annotations

import json
import math
import random
from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from velocitron_viz import (
    Arc,
    ConsumePattern,
    LayoutMetricsError,
    Net,
    Place,
    ProduceTemplate,
    Transition,
    apply_view,
    arc_handle_index,
    layout_metrics,
    net_render_model,
    stamp_arc_ids,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "metrics"
Point = tuple[float, float]
Segment = tuple[Point, Point]


def _report(name: str) -> dict[str, Any]:
    return layout_metrics((_FIXTURES / name).read_text(encoding="utf-8"))


def test_k33_pinned_has_one_crossing() -> None:
    # given: a straight-line K3,3 whose only interior crossing is u→x × v→y
    # when: the drawing is measured
    report = _report("k33.json")
    # then: one crossing, named, and the straight edges have no bends
    assert report["crossings"] == 1
    assert report["pairs"] == [
        {"a": "arc:0", "b": "arc:4", "drawn": "u→x × v→y"},
    ]
    assert report["overlaps"] == {"count": 0, "pairs": []}
    assert report["edge_node_overlaps"] == {"count": 0, "hits": []}
    assert report["edge_length"] == {
        "total": 22.9257,
        "mean": 2.5473,
        "longest": [
            {"id": "arc:2", "points": 4.4721},
            {"id": "arc:5", "points": 4.4721},
            {"id": "arc:0", "points": 3.1623},
            {"id": "arc:4", "points": 3.1623},
            {"id": "arc:8", "points": 2.0},
        ],
    }
    assert report["bends"] == {"total": 0, "mean": 0.0, "most": []}


def test_shared_endpoint_fan_has_no_crossing() -> None:
    # given: three edges that meet at one hub, plus an invisible edge that
    # would cross the hub edge if it were drawn
    # when: the drawing is measured
    report = _report("fan.json")
    # then: the shared endpoint is not a crossing, and the invisible edge is skipped
    assert report["crossings"] == 0
    assert report["pairs"] == []
    assert report["overlaps"] == {"count": 0, "pairs": []}
    assert report["edge_length"]["total"] == 278.8854
    assert report["edge_length"]["mean"] == 92.9618
    assert report["bends"]["total"] == 0


def test_ortho_shared_channel_is_an_overlap() -> None:
    # given: two orthogonal routes that share one horizontal channel
    # when: the drawing is measured
    report = _report("ortho-channel.json")
    # then: the channel is an overlap, not a crossing, and each corner is a bend
    assert report["crossings"] == 0
    assert report["pairs"] == []
    assert report["overlaps"] == {
        "count": 1,
        "pairs": [
            {"a": "arc:east", "b": "arc:west", "drawn": "c→d × a→b"},
        ],
    }
    assert report["edge_length"] == {
        "total": 11.0,
        "mean": 5.5,
        "longest": [
            {"id": "arc:west", "points": 6.0},
            {"id": "arc:east", "points": 5.0},
        ],
    }
    assert report["bends"] == {
        "total": 3,
        "mean": 1.5,
        "most": [
            {"id": "arc:east", "bends": 2},
            {"id": "arc:west", "bends": 1},
        ],
    }


def test_edge_drawn_through_a_node() -> None:
    # given: a straight edge whose ends are a and c and whose route crosses b
    # when: the drawing is measured
    report = _report("edge-through-node.json")
    # then: b is an edge-node overlap and the route does not cross itself
    assert report["crossings"] == 0
    assert report["edge_node_overlaps"] == {
        "count": 1,
        "hits": [{"edge": "arc:through", "node": "b", "drawn": "a→c"}],
    }
    assert report["edge_length"]["total"] == 164.0
    assert report["bends"]["total"] == 0


def test_adjacent_edges_that_cross_mid_route_count() -> None:
    # given: two edges that share a tail and cross away from that tail
    drawing = _graph(
        nodes=[("a", 0, 0), ("b", 80, 10), ("c", 90, -20)],
        edges=[
            ("arc:out", 0, 1, [(0, 0), (80, 10)]),
            ("arc:back", 0, 2, [(0, 0), (20, 60), (90, -20)]),
        ],
    )
    # when: the drawing is measured
    report = layout_metrics(json.dumps(drawing))
    # then: the mid-route crossing counts and the shared tail does not
    assert report["crossings"] == 1
    assert report["pairs"] == [
        {"a": "arc:back", "b": "arc:out", "drawn": "a→c × a→b"},
    ]
    assert report["overlaps"]["count"] == 0


def test_a_cubic_crosses_a_line_once() -> None:
    # given: one cubic hump and a vertical line through its middle
    drawing = _graph(
        nodes=[("s", 0, 0), ("e", 100, 0), ("p", 50, -10), ("q", 50, 150)],
        edges=[
            ("arc:curve", 0, 1, None, [0, 0, 0, 100, 100, 100, 100, 0]),
            ("arc:line", 2, 3, [(50, -10), (50, 150)]),
        ],
    )
    # when: the curve is flattened and measured
    report = layout_metrics(json.dumps(drawing))
    # then: the hump contributes one crossing
    assert report["crossings"] == 1
    assert {report["pairs"][0]["a"], report["pairs"][0]["b"]} == {
        "arc:curve",
        "arc:line",
    }


def test_pos_splines_are_measured_when_draw_is_absent() -> None:
    # given: two straight cubics carried only in the pos attribute
    drawing = {
        "objects": [
            _node(0, "a", 0, 0),
            _node(1, "b", 2, 2),
            _node(2, "c", 0, 2),
            _node(3, "d", 2, 0),
        ],
        "edges": [
            {
                "tail": 0,
                "head": 1,
                "id": "arc:0",
                "pos": "e,2,2 0,0 0,0 2,2 2,2",
            },
            {
                "tail": 2,
                "head": 3,
                "id": "arc:1",
                "pos": "e,2,0 0,2 0,2 2,0 2,0",
            },
        ],
    }
    # when: the pos strings are measured
    report = layout_metrics(json.dumps(drawing))
    # then: the two diagonals cross once
    assert report["crossings"] == 1


def test_a_tangent_is_not_an_edge_through_a_node() -> None:
    # given: a segment that touches an ellipse and does not enter it
    drawing = _graph(
        nodes=[("a", -20, 10), ("b", 20, 10), ("disk", 0, 0)],
        edges=[("arc:skim", 0, 1, [(-20, 10), (20, 10)])],
        radii={"disk": 10},
    )
    # when: the drawing is measured
    report = layout_metrics(json.dumps(drawing))
    # then: a touch at the boundary is not an overlap with the node
    assert report["edge_node_overlaps"]["count"] == 0


def test_a_segment_through_a_box_is_an_edge_node_overlap() -> None:
    # given: a transition-shaped box with a segment across it
    drawing = _graph(
        nodes=[("a", 0, 0), ("c", 100, 0)],
        edges=[("arc:cut", 0, 1, [(0, 0), (100, 0)])],
    )
    drawing["objects"].append(
        {
            "_gvid": 2,
            "name": "box",
            "pos": "50,0",
            "_draw_": [
                {
                    "op": "p",
                    "points": [[40, -10], [60, -10], [60, 10], [40, 10]],
                }
            ],
        }
    )
    # when: the drawing is measured
    report = layout_metrics(json.dumps(drawing))
    # then: the box is named
    assert report["edge_node_overlaps"]["hits"] == [
        {"edge": "arc:cut", "node": "box", "drawn": "a→c"},
    ]


def test_random_straight_layouts_match_a_brute_force_reference() -> None:
    # given: straight segments in general position
    compared = 0
    for trial in range(80):
        segments = _random_segments(random.Random(11 + trial), count=8)
        expected = _reference_crossings(segments)
        if expected is None:
            continue
        drawing = _graph(
            nodes=[
                (f"n{index}", *point)
                for index, point in enumerate(_endpoints(segments))
            ],
            edges=[
                (f"arc:{index}", index * 2, index * 2 + 1, [start, end])
                for index, (start, end) in enumerate(segments)
            ],
        )
        # when: the fast path measures the same segments
        report = layout_metrics(json.dumps(drawing))
        # then: it agrees with the exact count
        assert report["crossings"] == expected
        compared += 1
    assert compared >= 15


def test_stamp_names_handles_and_fusion_copies() -> None:
    # given: a fusion place drawn as one copy per transition
    net = Net(
        name="copies",
        places=[
            Place("lock", ["permit"], annotations={"fusion": True}),
            Place("idle", ["permit"]),
        ],
        transitions=[Transition("acquire"), Transition("release")],
        arcs=[
            Arc(
                from_place="lock",
                to_transition="acquire",
                consume=ConsumePattern("permit", None, "consume"),
            ),
            Arc(
                from_transition="release",
                to_place="lock",
                produce=ProduceTemplate("permit", "lock"),
            ),
        ],
    )
    model = net_render_model(net, include_marking=False)
    handles = arc_handle_index(
        {
            "annotations": {
                "petrinet.dsl/v1": {
                    "arcHandles": {
                        "take": {"index": 0, "fingerprint": {}},
                    }
                }
            }
        }
    )
    # when: the arc lines are stamped
    stamped = stamp_arc_ids(model, handles)
    lines = stamped.splitlines()
    # then: the copy edge carries the source arc, and the other arc uses its index
    take = lines[model.arc_lines[0]]
    give = lines[model.arc_lines[1]]
    assert "lock@acquire" in take
    assert 'id="arc:take"' in take
    assert "lock@release" in give
    assert 'id="arc:1"' in give
    assert len(stamped.splitlines()) == len(model.dot.splitlines())


def test_a_view_keeps_the_stamped_arc_id() -> None:
    # given: a stamped edge and a view that pins one place
    net = Net(
        name="placed",
        places=[Place("src", ["job"]), Place("dst", ["job"])],
        transitions=[Transition("move")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="move",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="move",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
    )
    model = net_render_model(net, include_marking=False)
    stamped = stamp_arc_ids(model, {1: "out"})
    model = replace(model, dot=stamped)
    raw = {
        "annotations": {
            "petrinet.dsl/v1": {
                "arcHandles": {},
                "views": {
                    "placed": {
                        "positions": {"place:src": {"x": 10, "y": 20}},
                        "routes": {},
                    }
                },
            }
        }
    }
    # when: the view is applied through the same line index
    dot = apply_view(model, raw, "placed")
    # then: the id survives on the edge. A view inserts graph lines, so
    # the original arc index is no longer the line number.
    src = next(line for line in dot.splitlines() if '"src" ->' in line)
    dst = next(line for line in dot.splitlines() if '-> "dst"' in line)
    assert 'id="arc:0"' in src
    assert 'id="arc:out"' in dst
    assert 'pos="10,20!"' in dot


def test_layout_metrics_rejects_text_that_is_not_json() -> None:
    # when: the text is not a JSON object
    with pytest.raises(LayoutMetricsError, match="Graphviz JSON"):
        layout_metrics("[]")
    with pytest.raises(LayoutMetricsError, match="Graphviz JSON"):
        layout_metrics("not json")


def _graph(
    *,
    nodes: Sequence[tuple[str, float, float]],
    edges: Sequence[tuple[Any, ...]],
    radii: dict[str, float] | None = None,
) -> dict[str, list[object]]:
    """A minimal Graphviz JSON object. An edge is id, tail, head, polyline or controls."""
    radii = radii or {}
    objects: list[object] = []
    for index, (name, x, y) in enumerate(nodes):
        objects.append(_node(index, name, x, y, radii.get(name, 0.05)))
    built: list[object] = []
    for index, edge in enumerate(edges):
        arc_id, tail, head = edge[0], edge[1], edge[2]
        polyline = edge[3]
        raw: dict[str, object] = {
            "_gvid": index,
            "tail": tail,
            "head": head,
            "id": arc_id,
        }
        if polyline is None:
            controls = edge[4]
            points = [
                [controls[offset], controls[offset + 1]]
                for offset in range(0, len(controls), 2)
            ]
            raw["_draw_"] = [{"op": "b", "points": points}]
        else:
            corners = [list(point) for point in polyline]
            controls = [corners[0]]
            for start, end in zip(corners, corners[1:], strict=False):
                controls.extend([start, end, end])
            raw["_draw_"] = [{"op": "b", "points": controls}]
        built.append(raw)
    return {"objects": objects, "edges": built}


def _node(
    gvid: int, name: str, x: float, y: float, radius: float = 0.05
) -> dict[str, object]:
    return {
        "_gvid": gvid,
        "name": name,
        "pos": f"{x},{y}",
        "_draw_": [{"op": "e", "rect": [x, y, radius, radius]}],
    }


def _random_segments(rng: random.Random, count: int) -> list[Segment]:
    segments: list[Segment] = []
    for _ in range(count):
        start = (rng.randrange(0, 80), rng.randrange(0, 80))
        end = (rng.randrange(0, 80), rng.randrange(0, 80))
        if start == end:
            end = (start[0] + 5, start[1] + 3)
        segments.append((start, end))
    return segments


def _endpoints(segments: Sequence[Segment]) -> list[Point]:
    points: list[Point] = []
    for start, end in segments:
        points.extend((start, end))
    return points


def _reference_crossings(segments: Sequence[Segment]) -> int | None:
    """Exact proper crossings, or None when a pair is too close to trust ε.

    The margin is wider than the drawing tolerance, so a hit the float path
    might round either way drops the whole trial instead of the comparison.
    """
    count = 0
    for left_index, (a0, a1) in enumerate(segments):
        for b0, b1 in segments[left_index + 1 :]:
            kind = _exact_kind(a0, a1, b0, b1)
            if kind == "skip":
                return None
            if kind == "cross":
                count += 1
    return count


def _exact_kind(a0: Point, a1: Point, b0: Point, b1: Point) -> str:
    ax, ay, bx, by = (Fraction(value) for value in (*a0, *a1))
    cx, cy, dx, dy = (Fraction(value) for value in (*b0, *b1))
    rx, ry = bx - ax, by - ay
    sx, sy = dx - cx, dy - cy
    denom = rx * sy - ry * sx
    if denom == 0 or (rx == 0 and ry == 0) or (sx == 0 and sy == 0):
        return "skip"
    t = ((cx - ax) * sy - (cy - ay) * sx) / denom
    u = ((cx - ax) * ry - (cy - ay) * rx) / denom
    margin = Fraction(1, 20)
    interior = margin < t < 1 - margin and margin < u < 1 - margin
    if not interior:
        if 0 < t < 1 and 0 < u < 1:
            return "skip"
        return "miss"
    span = math.hypot(float(rx), float(ry)) * math.hypot(float(sx), float(sy))
    if abs(float(denom)) < 0.05 * span:
        return "skip"
    return "cross"
