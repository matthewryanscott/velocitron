"""Measure a Graphviz drawing: crossings, overlaps, length, and bends.

``layout_metrics`` reads Graphviz ``-Tjson`` text. It flattens each visible
edge to a polyline and measures that geometry. It does not run Graphviz and
it does not guess a layout from DOT.

Curves are cubic Béziers (Graphviz writes them in ``_draw_`` or ``pos``).
They are flattened until the controls sit within a fixed tolerance of the
chord, not by taking a fixed number of steps. Segment tests use orientation
and a tolerance ε that grows with the drawing. Hits closer than ε are one
hit. A hit within ε of an endpoint two edges share is not a crossing;
adjacent edges that cross away from that endpoint still are. A collinear
overlap, the usual ortho shared channel, is an overlap. An edge that passes
through a node other than its own ends is an edge-node overlap.

``stamp_arc_ids`` writes ``id="arc:<handle>"`` onto the edge statements
``RenderModel.arc_lines`` names, so a later report can name the source arc
of a fusion copy.

Compare the numbers only across drawings measured with the same Graphviz
version. One version lays the same DOT out the same way every run, and a
different version may not.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from .render import RenderModel

__all__ = [
    "FLATTEN_TOLERANCE_PT",
    "LONGEST_EDGES",
    "LayoutMetricsError",
    "arc_handle_index",
    "layout_metrics",
    "stamp_arc_ids",
]

# A curve is flat when its controls are this close to the chord, in points.
FLATTEN_TOLERANCE_PT = 0.25
# How many longest arcs, and how many most-bent arcs, the report names.
LONGEST_EDGES = 5
# A kept vertex is a bend when the route turns at least this far.
_BEND_ANGLE = math.radians(20)
# ε is at least the flatten tolerance, and grows with the drawing.
_RELATIVE_EPS = 1e-4
_MAX_FLATTEN_DEPTH = 16
Point = tuple[float, float]


class LayoutMetricsError(ValueError):
    """The text is not Graphviz ``-Tjson`` this pass can read."""


@dataclass(frozen=True)
class _Edge:
    """One visible or invisible edge, already named."""

    id: str
    tail: str
    head: str
    invisible: bool
    polylines: tuple[tuple[Point, ...], ...]

    def endpoints(self) -> tuple[tuple[str, Point], ...]:
        """The tail point and the head point, when the curve has them."""
        found: list[tuple[str, Point]] = []
        if self.polylines and self.polylines[0]:
            found.append((self.tail, self.polylines[0][0]))
        if self.polylines and self.polylines[-1]:
            found.append((self.head, self.polylines[-1][-1]))
        return tuple(found)


@dataclass(frozen=True)
class _Ellipse:
    center: Point
    radius: Point


@dataclass(frozen=True)
class _Polygon:
    points: tuple[Point, ...]


@dataclass(frozen=True)
class _Node:
    name: str
    shape: _Ellipse | _Polygon


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    """A JSON object, or None. ``isinstance`` alone would drop the key type."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return None


def _as_list(value: object) -> list[Any] | None:
    if isinstance(value, list):
        return cast(list[Any], value)
    return None


def arc_handle_index(document: Mapping[str, Any]) -> dict[int, str]:
    """Map an arc's declaration index to its authored handle.

    Arcs with no ``arcHandles`` entry are absent. A caller stamps those
    with the declaration index instead.
    """
    annotations = _as_mapping(document.get("annotations"))
    if annotations is None:
        return {}
    payload = _as_mapping(annotations.get("petrinet.dsl/v1"))
    if payload is None:
        return {}
    handles = _as_mapping(payload.get("arcHandles"))
    if handles is None:
        return {}
    found: dict[int, str] = {}
    for name, raw_spec in sorted(handles.items()):
        spec = _as_mapping(raw_spec)
        if spec is None:
            continue
        index = spec.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            found[index] = name
    return found


def stamp_arc_ids(
    model: RenderModel,
    handles: Mapping[int, str] | None = None,
) -> str:
    """Return ``model.dot`` with ``id="arc:<handle>"`` on each arc edge.

    ``handles`` maps a declaration index to the arc's authored handle. An
    arc with no handle is stamped with that index, so a fusion copy still
    names its source arc. The stamp rewrites the statements
    ``model.arc_lines`` indexes and does not insert or remove lines.
    """
    named = handles or {}
    lines = model.dot.splitlines()
    for index, line_index in enumerate(model.arc_lines):
        token = named.get(index, str(index))
        lines[line_index] = _insert_id(lines[line_index], f"arc:{token}")
    return "\n".join(lines) + ("\n" if model.dot.endswith("\n") else "")


def layout_metrics(json_text: str) -> dict[str, Any]:
    """Measure one Graphviz ``-Tjson`` drawing.

    The result carries ``crossings``, ``pairs``, ``overlaps``,
    ``edge_node_overlaps``, ``edge_length``, and ``bends``. Lengths are in
    points. ``pairs`` names each crossing as ``a→b × c→d`` and gives the
    arc ids stamped on the edges. ``engine`` is the JSON ``layout`` field
    when Graphviz wrote one, otherwise ``None``. The Graphviz version is
    not in the JSON; the command that ran Graphviz adds it.
    """
    payload = _load_layout(json_text)
    nodes = _read_nodes(payload)
    edges = _read_edges(payload, nodes)
    eps = _drawing_eps(edges, nodes)
    crossings, overlaps = _relate_edges(edges, eps)
    node_hits = _edges_through_nodes(edges, nodes, eps)
    visible = [edge for edge in edges if not edge.invisible and edge.polylines]
    lengths = [_polyline_length(edge) for edge in visible]
    bend_counts = [_bend_count(edge, eps) for edge in visible]
    engine = payload.get("layout")
    return {
        "crossings": len(crossings),
        "pairs": crossings,
        "overlaps": {"count": len(overlaps), "pairs": overlaps},
        "edge_node_overlaps": {"count": len(node_hits), "hits": node_hits},
        "edge_length": _length_report(visible, lengths),
        "bends": _bend_report(visible, bend_counts),
        "engine": engine if isinstance(engine, str) and engine else None,
    }


def _load_layout(json_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise LayoutMetricsError("layout metrics expected Graphviz JSON") from error
    if not isinstance(payload, dict):
        raise LayoutMetricsError("layout metrics expected a Graphviz JSON object")
    return cast(dict[str, Any], payload)


def _insert_id(line: str, arc_id: str) -> str:
    """Append an id attribute to one DOT edge statement."""
    attr = f'id="{_dot_string(arc_id)}"'
    if line.endswith("];"):
        return f"{line[:-2]}, {attr}];"
    if line.endswith(";"):
        return f"{line[:-1]} [{attr}];"
    raise LayoutMetricsError(
        f"render model arc line does not end a DOT statement: {line!r}"
    )


def _dot_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _read_nodes(payload: Mapping[str, Any]) -> dict[int, _Node]:
    """Nodes keyed by Graphviz ``_gvid``. Clusters have no ``pos``."""
    objects = _as_list(payload.get("objects"))
    if objects is None:
        return {}
    nodes: dict[int, _Node] = {}
    for item in objects:
        obj = _as_mapping(item)
        if obj is None or "pos" not in obj:
            continue
        gvid = obj.get("_gvid")
        name = obj.get("name")
        if not isinstance(gvid, int) or isinstance(gvid, bool):
            continue
        if not isinstance(name, str) or _style_has_invis(obj.get("style")):
            continue
        shape = _node_shape(obj)
        if shape is not None:
            nodes[gvid] = _Node(name=name, shape=shape)
    return nodes


def _node_shape(obj: Mapping[str, Any]) -> _Ellipse | _Polygon | None:
    draw = _as_list(obj.get("_draw_"))
    if draw is not None:
        for item in draw:
            op = _as_mapping(item)
            if op is None:
                continue
            kind = op.get("op")
            if kind in {"p", "P"}:
                points = _point_list(op.get("points"))
                if len(points) >= 3:
                    return _Polygon(tuple(points))
            if kind in {"e", "E"}:
                ellipse = _ellipse_rect(op.get("rect"))
                if ellipse is not None:
                    return ellipse
    center = _pair(obj.get("pos"))
    if center is None:
        return None
    width = _as_float(obj.get("width"))
    height = _as_float(obj.get("height"))
    if width is None or height is None:
        return None
    # Graphviz stores width and height in inches. Points are 72 per inch.
    return _Ellipse(center=center, radius=(width * 36.0, height * 36.0))


def _ellipse_rect(value: object) -> _Ellipse | None:
    """Graphviz ellipse ``rect`` is center x, center y, x-radius, y-radius."""
    items = _as_list(value)
    if items is None or len(items) != 4:
        return None
    numbers = [_as_float(item) for item in items]
    if any(item is None for item in numbers):
        return None
    cx, cy, rx, ry = (float(item) for item in numbers if item is not None)
    if rx <= 0 or ry <= 0:
        return None
    return _Ellipse(center=(cx, cy), radius=(rx, ry))


def _read_edges(payload: Mapping[str, Any], nodes: Mapping[int, _Node]) -> list[_Edge]:
    raw_edges = _as_list(payload.get("edges"))
    if raw_edges is None:
        return []
    names = {gvid: node.name for gvid, node in nodes.items()}
    # A node can be invisible and still be an endpoint. Names live on every
    # object that has one, not only the measured shapes.
    for item in _as_list(payload.get("objects")) or []:
        obj = _as_mapping(item)
        if obj is None:
            continue
        gvid = obj.get("_gvid")
        name = obj.get("name")
        if (
            isinstance(gvid, int)
            and not isinstance(gvid, bool)
            and isinstance(name, str)
        ):
            names.setdefault(gvid, name)
    edges: list[_Edge] = []
    for index, item in enumerate(raw_edges):
        raw = _as_mapping(item)
        if raw is None:
            continue
        tail = _endpoint_name(raw.get("tail"), names)
        head = _endpoint_name(raw.get("head"), names)
        if tail is None or head is None:
            continue
        arc_id = raw.get("id")
        edges.append(
            _Edge(
                id=arc_id if isinstance(arc_id, str) and arc_id else f"arc:{index}",
                tail=tail,
                head=head,
                invisible=_style_has_invis(raw.get("style")),
                polylines=tuple(_edge_polylines(raw)),
            )
        )
    return edges


def _endpoint_name(value: object, names: Mapping[int, str]) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return names.get(value, str(value))
    return None


def _edge_polylines(raw: Mapping[str, Any]) -> list[tuple[Point, ...]]:
    """The painted curve. ``_draw_`` omits the arrowhead; ``pos`` is the fallback."""
    polylines = _polylines_from_draw(raw.get("_draw_"))
    if polylines:
        return polylines
    pos = raw.get("pos")
    if isinstance(pos, str):
        return _polylines_from_pos(pos)
    return []


def _polylines_from_draw(draw: object) -> list[tuple[Point, ...]]:
    ops = _as_list(draw)
    if ops is None:
        return []
    polylines: list[tuple[Point, ...]] = []
    for item in ops:
        op = _as_mapping(item)
        if op is None:
            continue
        kind = op.get("op")
        points = _point_list(op.get("points"))
        if kind in {"b", "B"} and points:
            flattened = _dedupe(_bezier_controls_to_polyline(points))
            if len(flattened) >= 2:
                polylines.append(tuple(flattened))
        elif kind == "L" and len(points) >= 2:
            flattened = _dedupe(points)
            if len(flattened) >= 2:
                polylines.append(tuple(flattened))
    return polylines


def _polylines_from_pos(pos: str) -> list[tuple[Point, ...]]:
    """Parse an edge ``pos`` spline. ``e,`` and ``s,`` are the arrow tips."""
    polylines: list[tuple[Point, ...]] = []
    for spline in pos.split(";"):
        points: list[Point] = []
        for token in spline.split():
            if token.startswith(("e,", "s,")):
                continue
            pair = _pair(token)
            if pair is not None:
                points.append(pair)
        flattened = _dedupe(_bezier_controls_to_polyline(points))
        if len(flattened) >= 2:
            polylines.append(tuple(flattened))
    return polylines


def _bezier_controls_to_polyline(points: Sequence[Point]) -> list[Point]:
    """Flatten Graphviz cubics: a start point plus triples of controls and end."""
    if len(points) < 4 or (len(points) - 1) % 3 != 0:
        return list(points)
    polyline = [points[0]]
    index = 1
    while index + 2 < len(points):
        span = _flatten_cubic(
            polyline[-1],
            points[index],
            points[index + 1],
            points[index + 2],
        )
        polyline.extend(span[1:])
        index += 3
    return polyline


def _flatten_cubic(
    p0: Point, p1: Point, p2: Point, p3: Point, depth: int = 0
) -> list[Point]:
    """Subdivide until the controls are within the flatten tolerance of the chord."""
    if depth >= _MAX_FLATTEN_DEPTH or _bezier_flat(p0, p1, p2, p3):
        return [p0, p3]
    left, right = _split_cubic(p0, p1, p2, p3)
    return _flatten_cubic(*left, depth + 1)[:-1] + _flatten_cubic(*right, depth + 1)


def _bezier_flat(p0: Point, p1: Point, p2: Point, p3: Point) -> bool:
    return (
        _distance_to_segment(p1, p0, p3) <= FLATTEN_TOLERANCE_PT
        and _distance_to_segment(p2, p0, p3) <= FLATTEN_TOLERANCE_PT
    )


def _split_cubic(
    p0: Point, p1: Point, p2: Point, p3: Point
) -> tuple[tuple[Point, Point, Point, Point], tuple[Point, Point, Point, Point]]:
    """De Casteljau split at one half."""
    p01 = _mid(p0, p1)
    p12 = _mid(p1, p2)
    p23 = _mid(p2, p3)
    p012 = _mid(p01, p12)
    p123 = _mid(p12, p23)
    p0123 = _mid(p012, p123)
    return (p0, p01, p012, p0123), (p0123, p123, p23, p3)


def _drawing_eps(edges: Sequence[_Edge], nodes: Mapping[int, _Node]) -> float:
    """ε in points: the flatten tolerance, or a fraction of the drawing's span."""
    xs: list[float] = []
    ys: list[float] = []
    for edge in edges:
        for polyline in edge.polylines:
            for point in polyline:
                xs.append(point[0])
                ys.append(point[1])
    for node in nodes.values():
        if isinstance(node.shape, _Ellipse):
            xs.append(node.shape.center[0])
            ys.append(node.shape.center[1])
        else:
            for point in node.shape.points:
                xs.append(point[0])
                ys.append(point[1])
    if not xs:
        return FLATTEN_TOLERANCE_PT
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    return max(FLATTEN_TOLERANCE_PT, span * _RELATIVE_EPS)


def _relate_edges(
    edges: Sequence[_Edge], eps: float
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    visible = [edge for edge in edges if not edge.invisible and edge.polylines]
    crossings: list[dict[str, str]] = []
    overlaps: list[dict[str, str]] = []
    for left_index, left in enumerate(visible):
        for right in visible[left_index + 1 :]:
            points, intervals = _pair_hits(left, right, eps)
            record = _pair_record(left, right)
            crossings.extend([record] * _cluster_count(points, eps))
            overlaps.extend([record] * _merged_interval_count(intervals, eps))
    crossings.sort(key=lambda item: (item["a"], item["b"]))
    overlaps.sort(key=lambda item: (item["a"], item["b"]))
    return crossings, overlaps


def _pair_hits(
    left: _Edge, right: _Edge, eps: float
) -> tuple[list[Point], list[tuple[float, float]]]:
    """Interior crossings, and collinear overlaps measured along ``left``."""
    points: list[Point] = []
    intervals: list[tuple[float, float]] = []
    for left_segment, left_prefix in _segments(left):
        for right_segment, _right_prefix in _segments(right):
            point = _proper_crossing(*left_segment, *right_segment, eps)
            if point is not None and not _near_shared_endpoint(left, right, point, eps):
                points.append(point)
            interval = _collinear_overlap(*left_segment, *right_segment, eps)
            if interval is not None:
                start, end = interval
                intervals.append((left_prefix + start, left_prefix + end))
    # A flatten joint can sit on the other edge, so neither open segment
    # contains the hit. Count it when the route actually changes sides.
    for point in _vertex_crossings(left, right):
        if not _near_shared_endpoint(left, right, point, eps):
            points.append(point)
    return points, intervals


def _vertex_crossings(left: _Edge, right: _Edge) -> list[Point]:
    """Places where one route passes through a joint of the other and changes sides."""
    return _vertices_through(left, right) + _vertices_through(right, left)


def _vertices_through(edge: _Edge, other: _Edge) -> list[Point]:
    hits: list[Point] = []
    for polyline in edge.polylines:
        for index in range(1, len(polyline) - 1):
            vertex = polyline[index]
            previous = polyline[index - 1]
            nxt = polyline[index + 1]
            for start, end in _bare_segments(other):
                if _distance_to_segment(vertex, start, end) > 1e-6:
                    continue
                side_previous = _orient(start, end, previous)
                side_next = _orient(start, end, nxt)
                if side_previous * side_next < 0.0:
                    hits.append(vertex)
                break
    return hits


def _segments(edge: _Edge) -> list[tuple[tuple[Point, Point], float]]:
    found: list[tuple[tuple[Point, Point], float]] = []
    for polyline in edge.polylines:
        walked = 0.0
        for start, end in zip(polyline, polyline[1:], strict=False):
            found.append(((start, end), walked))
            walked += _distance(start, end)
    return found


def _proper_crossing(
    a0: Point, a1: Point, b0: Point, b1: Point, eps: float
) -> Point | None:
    """A crossing of the two open segments. Endpoints and collinear runs are not."""
    rx, ry = a1[0] - a0[0], a1[1] - a0[1]
    sx, sy = b1[0] - b0[0], b1[1] - b0[1]
    alen = math.hypot(rx, ry)
    if alen <= eps or math.hypot(sx, sy) <= eps:
        return None
    denom = rx * sy - ry * sx
    # The whole of b stays within ε of a's direction: an overlap, not a cross.
    if abs(denom) <= eps * alen:
        return None
    qpx, qpy = b0[0] - a0[0], b0[1] - a0[1]
    parameter_a = (qpx * sy - qpy * sx) / denom
    parameter_b = (qpx * ry - qpy * rx) / denom
    if not (1e-9 < parameter_a < 1.0 - 1e-9 and 1e-9 < parameter_b < 1.0 - 1e-9):
        return None
    return (a0[0] + parameter_a * rx, a0[1] + parameter_a * ry)


def _collinear_overlap(
    a0: Point, a1: Point, b0: Point, b1: Point, eps: float
) -> tuple[float, float] | None:
    """Overlap length along ``a``, in points from ``a0``, when the segments share a channel."""
    alen = _distance(a0, a1)
    if alen <= eps or _distance(b0, b1) <= eps:
        return None
    if _distance_to_line(a0, a1, b0) > eps or _distance_to_line(a0, a1, b1) > eps:
        return None
    ux, uy = (a1[0] - a0[0]) / alen, (a1[1] - a0[1]) / alen

    def project(point: Point) -> float:
        return (point[0] - a0[0]) * ux + (point[1] - a0[1]) * uy

    low, high = sorted((project(b0), project(b1)))
    start = max(0.0, low)
    end = min(alen, high)
    if end - start <= eps:
        return None
    return start, end


def _near_shared_endpoint(left: _Edge, right: _Edge, point: Point, eps: float) -> bool:
    shared = {left.tail, left.head} & {right.tail, right.head}
    if not shared:
        return False
    for edge in (left, right):
        for name, endpoint in edge.endpoints():
            if name in shared and _distance(point, endpoint) <= eps:
                return True
    return False


def _cluster_count(points: Sequence[Point], eps: float) -> int:
    """How many hits remain once points within ε of each other are one hit."""
    parent = list(range(len(points)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left_index, left in enumerate(points):
        for right_index in range(left_index + 1, len(points)):
            if _distance(left, points[right_index]) <= eps:
                parent[find(right_index)] = find(left_index)
    return len({find(index) for index in range(len(points))})


def _merged_interval_count(intervals: Sequence[tuple[float, float]], eps: float) -> int:
    """Contiguous pieces of one shared channel count once."""
    if not intervals:
        return 0
    ordered = sorted(intervals)
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + eps:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(1 for start, end in merged if end - start > eps)


def _pair_record(left: _Edge, right: _Edge) -> dict[str, str]:
    first, second = sorted((left, right), key=lambda edge: edge.id)
    return {
        "a": first.id,
        "b": second.id,
        "drawn": f"{first.tail}→{first.head} × {second.tail}→{second.head}",
    }


def _edges_through_nodes(
    edges: Sequence[_Edge], nodes: Mapping[int, _Node], eps: float
) -> list[dict[str, str]]:
    shapes = list(nodes.values())
    hits: list[dict[str, str]] = []
    for edge in edges:
        if edge.invisible or not edge.polylines:
            continue
        ends = {edge.tail, edge.head}
        seen: set[str] = set()
        for node in shapes:
            if node.name in ends or node.name in seen:
                continue
            if _edge_cuts_node(edge, node, eps):
                seen.add(node.name)
                hits.append(
                    {
                        "edge": edge.id,
                        "node": node.name,
                        "drawn": f"{edge.tail}→{edge.head}",
                    }
                )
    hits.sort(key=lambda item: (item["edge"], item["node"]))
    return hits


def _edge_cuts_node(edge: _Edge, node: _Node, eps: float) -> bool:
    for start, end in _bare_segments(edge):
        if isinstance(node.shape, _Ellipse):
            cut = _segment_cuts_ellipse(start, end, node.shape, eps)
        else:
            cut = _segment_cuts_polygon(start, end, node.shape.points, eps)
        if cut:
            return True
    return False


def _bare_segments(edge: _Edge) -> list[tuple[Point, Point]]:
    return [segment for segment, _prefix in _segments(edge)]


def _segment_cuts_ellipse(
    start: Point, end: Point, ellipse: _Ellipse, eps: float
) -> bool:
    """The part of the segment inside the ellipse is longer than ε."""
    cx, cy = ellipse.center
    rx, ry = ellipse.radius
    ax, ay = (start[0] - cx) / rx, (start[1] - cy) / ry
    bx, by = (end[0] - cx) / rx, (end[1] - cy) / ry
    dx, dy = bx - ax, by - ay
    quadratic_a = dx * dx + dy * dy
    quadratic_b = 2.0 * (ax * dx + ay * dy)
    quadratic_c = ax * ax + ay * ay - 1.0
    if quadratic_a <= 1e-18:
        inside = ax * ax + ay * ay < 1.0
        return inside and _distance(start, end) > eps
    discriminant = quadratic_b * quadratic_b - 4.0 * quadratic_a * quadratic_c
    if discriminant < 0.0:
        return False
    root = math.sqrt(discriminant)
    first = (-quadratic_b - root) / (2.0 * quadratic_a)
    second = (-quadratic_b + root) / (2.0 * quadratic_a)
    low, high = max(min(first, second), 0.0), min(max(first, second), 1.0)
    if high - low <= 0.0:
        return False
    return (high - low) * _distance(start, end) > eps


def _segment_cuts_polygon(
    start: Point, end: Point, polygon: Sequence[Point], eps: float
) -> bool:
    """The part of the segment strictly inside the polygon is longer than ε."""
    if len(polygon) < 3:
        return False
    parameters = [0.0, 1.0]
    for index, corner in enumerate(polygon):
        nxt = polygon[(index + 1) % len(polygon)]
        crossed = _boundary_parameter(start, end, corner, nxt)
        if crossed is not None:
            parameters.append(crossed)
    parameters.sort()
    length = _distance(start, end)
    inside = 0.0
    for lower, upper in zip(parameters, parameters[1:], strict=False):
        if upper - lower <= 1e-12:
            continue
        midpoint = _lerp(start, end, (lower + upper) / 2.0)
        if _strictly_inside(midpoint, polygon):
            inside += (upper - lower) * length
    return inside > eps


def _boundary_parameter(
    start: Point, end: Point, corner: Point, nxt: Point
) -> float | None:
    """Where ``start``–``end`` crosses the polygon edge, as a parameter in (0, 1)."""
    point = _proper_crossing(start, end, corner, nxt, eps=1e-9)
    if point is None:
        return None
    length = _distance(start, end)
    if length <= 1e-12:
        return None
    return _distance(start, point) / length


def _strictly_inside(point: Point, polygon: Sequence[Point]) -> bool:
    """Even-odd interior test. A point on the boundary is outside."""
    for index, corner in enumerate(polygon):
        if (
            _distance_to_segment(point, corner, polygon[(index + 1) % len(polygon)])
            <= 1e-9
        ):
            return False
    inside = False
    previous = polygon[-1]
    for corner in polygon:
        if (corner[1] > point[1]) != (previous[1] > point[1]):
            crossing_x = previous[0] + (corner[0] - previous[0]) * (
                (point[1] - previous[1]) / (corner[1] - previous[1])
            )
            if point[0] < crossing_x:
                inside = not inside
        previous = corner
    return inside


def _length_report(edges: Sequence[_Edge], lengths: Sequence[float]) -> dict[str, Any]:
    total = sum(lengths)
    count = len(lengths)
    ranked = [
        {"id": edge.id, "points": _round(length)}
        for edge, length in zip(edges, lengths, strict=True)
    ]
    ranked.sort(key=lambda item: (-float(item["points"]), str(item["id"])))
    return {
        "total": _round(total),
        "mean": _round(total / count) if count else 0.0,
        "longest": ranked[:LONGEST_EDGES],
    }


def _bend_report(edges: Sequence[_Edge], counts: Sequence[int]) -> dict[str, Any]:
    total = sum(counts)
    count = len(counts)
    ranked = sorted(
        (
            {"id": edge.id, "bends": bends}
            for edge, bends in zip(edges, counts, strict=True)
            if bends
        ),
        key=lambda item: (-int(item["bends"]), str(item["id"])),
    )
    return {
        "total": total,
        "mean": _round(total / count) if count else 0.0,
        "most": ranked[:LONGEST_EDGES],
    }


def _polyline_length(edge: _Edge) -> float:
    return sum(_distance(start, end) for start, end in _bare_segments(edge))


def _bend_count(edge: _Edge, eps: float) -> int:
    """Corners of the route. Samples along a smooth curve are not corners."""
    total = 0
    for polyline in edge.polylines:
        simplified = _rdp(list(polyline), eps)
        for index in range(1, len(simplified) - 1):
            turn = _turn(
                simplified[index - 1], simplified[index], simplified[index + 1]
            )
            if turn >= _BEND_ANGLE:
                total += 1
    return total


def _rdp(points: Sequence[Point], tolerance: float) -> list[Point]:
    """Ramer–Douglas–Peucker. Points within the tolerance of the chord go away."""
    if len(points) < 3:
        return list(points)
    farthest = 0.0
    index_at = 0
    for index in range(1, len(points) - 1):
        distance = _distance_to_segment(points[index], points[0], points[-1])
        if distance > farthest:
            farthest = distance
            index_at = index
    if farthest <= tolerance:
        return [points[0], points[-1]]
    left = _rdp(points[: index_at + 1], tolerance)
    right = _rdp(points[index_at:], tolerance)
    return left[:-1] + right


def _turn(before: Point, corner: Point, after: Point) -> float:
    inbound = (corner[0] - before[0], corner[1] - before[1])
    outbound = (after[0] - corner[0], after[1] - corner[1])
    in_len = math.hypot(*inbound)
    out_len = math.hypot(*outbound)
    if in_len <= 1e-12 or out_len <= 1e-12:
        return 0.0
    dot = inbound[0] * outbound[0] + inbound[1] * outbound[1]
    cross = inbound[0] * outbound[1] - inbound[1] * outbound[0]
    return abs(math.atan2(cross, dot))


def _style_has_invis(style: object) -> bool:
    return "invis" in _style_tokens(style)


def _style_tokens(style: object) -> set[str]:
    if isinstance(style, str):
        return {part.strip() for part in style.split(",") if part.strip()}
    items = _as_list(style)
    if items is None:
        return set()
    tokens: set[str] = set()
    for item in items:
        tokens.update(_style_tokens(item))
    return tokens


def _point_list(value: object) -> list[Point]:
    items = _as_list(value)
    if items is None:
        return []
    points: list[Point] = []
    for item in items:
        pair = _pair(item)
        if pair is not None:
            points.append(pair)
    return points


def _pair(value: object) -> Point | None:
    if isinstance(value, str):
        parts = value.split(",")
        if len(parts) != 2:
            return None
        x, y = _as_float(parts[0]), _as_float(parts[1])
    else:
        items = _as_list(value)
        if items is None or len(items) != 2:
            return None
        x, y = _as_float(items[0]), _as_float(items[1])
    if x is None or y is None:
        return None
    return (x, y)


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _dedupe(points: Sequence[Point]) -> list[Point]:
    if not points:
        return []
    kept = [points[0]]
    for point in points[1:]:
        if _distance(point, kept[-1]) > 1e-9:
            kept.append(point)
    return kept


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _distance(start: Point, end: Point) -> float:
    return math.hypot(end[0] - start[0], end[1] - start[1])


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-18:
        return _distance(point, start)
    parameter = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2
    parameter = min(1.0, max(0.0, parameter))
    return _distance(point, (start[0] + parameter * dx, start[1] + parameter * dy))


def _distance_to_line(start: Point, end: Point, point: Point) -> float:
    length = _distance(start, end)
    if length <= 1e-12:
        return _distance(point, start)
    cross = (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (
        point[0] - start[0]
    )
    return abs(cross) / length


def _mid(start: Point, end: Point) -> Point:
    return ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)


def _lerp(start: Point, end: Point, parameter: float) -> Point:
    return (
        start[0] + (end[0] - start[0]) * parameter,
        start[1] + (end[1] - start[1]) * parameter,
    )


def _round(value: float) -> float:
    return round(value, 4)
