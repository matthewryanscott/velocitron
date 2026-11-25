"""Apply authored, inert views to a rendered velocitron net (ADR 0024).

A :class:`~velocitron_viz.RenderModel` carries the structural facts the
application pass needs — which statement line carries which authored element,
and where graph-level attributes may be inserted — so applying a view never
parses rendered DOT text. The pass reads the raw document's reserved payload
``annotations["petrinet.dsl/v1"]`` (ADR 0020): the selected view's
``positions`` and ``routes``, plus ``arcHandles`` for handle → arc
resolution.

Relative positions resolve here, at render time (ADR 0024): an entry whose
subject carries ``{"from": <subject>, "delta": {"x": dx, "dy": dy}}`` resolves
against the subject it names; chains resolve in dependency order; cycles,
unknown bases, and bases with no authored position reject. The relative wire
shape is *provisional* — canonical documents still reject it at
``_reserved_payload`` — until the compiler-owned presentation vocabulary
lands.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, cast

VIEW_SPLINES: Final[tuple[str, ...]] = ("ortho", "spline", "curved", "polyline", "line")
# Points. Clears a short name plus one color line on both the transition
# and the copy, in the coordinates ``inputscale=72`` reads (ADR 0067).
BESIDE_GAP: Final[int] = 130

if TYPE_CHECKING:
    from .render import RenderModel

__all__ = [
    "BESIDE_GAP",
    "DEFAULT_VIEW",
    "Decoration",
    "Decorations",
    "ViewApplicationError",
    "apply_view",
    "has_view",
    "read_decorations",
    "resolve_positions",
    "view_setting",
]

DEFAULT_VIEW = "default"
"""The view a renderer applies when the caller names none."""


class ViewApplicationError(ValueError):
    """A view could not be applied; a ValueError so callers keep one shape."""


def has_view(raw: Mapping[str, Any], view_name: str) -> bool:
    """Whether the reserved payload declares a view with this name."""
    try:
        annotations = cast(Mapping[str, Any], raw["annotations"])
        payload = cast(Mapping[str, Any], annotations["petrinet.dsl/v1"])
        views = cast(Mapping[str, Any], payload["views"])
        return view_name in views
    except (KeyError, TypeError):
        return False


def _view_facts(
    raw: Mapping[str, Any], view_name: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract a view's positions/routes from the reserved payload."""
    try:
        annotations = cast(Mapping[str, Any], raw["annotations"])
        payload = cast(Mapping[str, Any], annotations["petrinet.dsl/v1"])
        views = cast(Mapping[str, Any], payload["views"])
        view = cast(Mapping[str, Any], views[view_name])
    except (KeyError, TypeError) as error:
        raise ViewApplicationError(f"unknown view {view_name!r}") from error
    positions = view.get("positions")
    routes = view.get("routes")
    if not isinstance(positions, dict) or not isinstance(routes, dict):
        raise ViewApplicationError(f"invalid view {view_name!r}")
    return (
        cast("dict[str, Any]", positions),
        cast("dict[str, Any]", routes),
    )


def view_setting(raw: Mapping[str, Any], view_name: str, member: str) -> str | None:
    """A view's optional string setting (``splines`` or ``detail``), if authored."""
    try:
        annotations = cast(Mapping[str, Any], raw["annotations"])
        payload = cast(Mapping[str, Any], annotations["petrinet.dsl/v1"])
        view = cast(Mapping[str, Any], payload["views"][view_name])
    except (KeyError, TypeError):
        return None
    value = view.get(member)
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class Decoration:
    """One element's authored decorations. They apply with or without a view.

    ``failure`` is never authored: a play walkthrough sets it on the
    transition of a step that could not fire, and a transition drawn with
    it takes a red fill and border in place of the highlight's amber.
    ``faded`` is never authored either: a walkthrough fades the neighbor
    transitions it draws for context, and their arcs.
    """

    highlight: bool = False
    highlight_label: str | None = None
    note: str | None = None
    summary: str | None = None
    beside: bool = False
    beside_side: str | None = None
    failure: bool = False
    faded: bool = False


@dataclass(frozen=True)
class Decorations:
    """Decorations by render subject: nodes by ``place:``/``transition:`` key,
    arcs by arc index, the colors whose arc type labels stay hidden, and the
    token field paths to show for each color that names them."""

    nodes: Mapping[str, Decoration] = field(default_factory=dict[str, Decoration])
    arcs: Mapping[int, Decoration] = field(default_factory=dict[int, Decoration])
    quiet_colors: frozenset[str] = frozenset()
    shown_fields: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def read_decorations(raw: Mapping[str, Any]) -> Decorations:
    """Read the reserved payload's decorations, resolving arc handles to indexes."""
    try:
        annotations = cast(Mapping[str, Any], raw["annotations"])
        payload = cast(Mapping[str, Any], annotations["petrinet.dsl/v1"])
    except (KeyError, TypeError):
        return Decorations()
    raw_decorations = payload.get("decorations", {})
    if not isinstance(raw_decorations, Mapping):
        raise ViewApplicationError("invalid decorations")
    nodes: dict[str, Decoration] = {}
    arcs: dict[int, Decoration] = {}
    quiet_colors: set[str] = set()
    shown_fields: dict[str, tuple[str, ...]] = {}
    for subject, raw_entry in cast(Mapping[str, Any], raw_decorations).items():
        kind, _, name = subject.partition(":")
        if not isinstance(raw_entry, Mapping):
            raise ViewApplicationError(f"invalid decoration {subject!r}")
        entry = cast(Mapping[str, Any], raw_entry)
        if kind == "color":
            if entry.get("quiet") is True:
                quiet_colors.add(name)
            shown = entry.get("show")
            if shown is not None:
                if not isinstance(shown, list) or not all(
                    isinstance(path, str) for path in cast(list[Any], shown)
                ):
                    raise ViewApplicationError(f"invalid decoration {subject!r}")
                shown_fields[name] = tuple(cast(list[str], shown))
            continue
        highlight = entry.get("highlight")
        beside = entry.get("beside")
        decoration = Decoration(
            highlight=isinstance(highlight, Mapping),
            highlight_label=_optional_text(
                cast(Mapping[str, Any], highlight).get("label")
                if isinstance(highlight, Mapping)
                else None
            ),
            note=_optional_text(entry.get("note")),
            summary=_optional_text(entry.get("summary")),
            beside=isinstance(beside, Mapping),
            beside_side=_optional_text(
                cast(Mapping[str, Any], beside).get("side")
                if isinstance(beside, Mapping)
                else None
            ),
        )
        if kind in ("place", "transition"):
            nodes[subject] = decoration
        elif kind == "arc":
            try:
                handles = cast(Mapping[str, Any], payload["arcHandles"])
                index = cast(Mapping[str, Any], handles[name])["index"]
                if not isinstance(index, int) or isinstance(index, bool):
                    raise TypeError
            except (KeyError, TypeError) as error:
                raise ViewApplicationError(
                    f"decoration references unknown arc handle {name!r}"
                ) from error
            arcs[index] = decoration
        else:
            raise ViewApplicationError(f"invalid decoration subject {subject!r}")
    return Decorations(
        nodes=nodes,
        arcs=arcs,
        quiet_colors=frozenset(quiet_colors),
        shown_fields=shown_fields,
    )


def _point(value: object, context: str) -> tuple[float | int, float | int]:
    """Validate one {x, y} point: both axes finite, non-boolean numbers."""
    if (
        not isinstance(value, Mapping)
        or set(cast(Mapping[str, Any], value)) != {"x", "y"}
        or any(
            not isinstance(cast(Mapping[str, Any], value).get(axis), (int, float))
            or isinstance(cast(Mapping[str, Any], value).get(axis), bool)
            or not math.isfinite(cast(Mapping[str, Any], value)[axis])
            for axis in ("x", "y")
        )
    ):
        raise ViewApplicationError(context)
    point = cast(Mapping[str, Any], value)
    return point["x"], point["y"]


def _validate_subject(subject: str, view_name: str) -> None:
    """A subject key is ``"<kind>:<name>"`` for kind place or transition."""
    kind, _, name = subject.partition(":")
    if not name or kind not in ("place", "transition"):
        raise ViewApplicationError(
            f"view {view_name!r} has invalid view subject {subject!r}"
            " (expected 'place:<name>' or 'transition:<name>')"
        )


def resolve_positions(
    view_name: str,
    positions: Mapping[str, Any],
) -> dict[str, tuple[float | int, float | int]]:
    """Resolve one view's position facts to ``subject → (x, y)``.

    Absolute entries are exactly ``{"x", "y"}``. Relative entries are exactly
    ``{"from", "delta"}`` (provisional shape, ADR 0024): ``from`` names a
    base subject which itself must carry a position in this view, ``delta``
    is a point. Chains resolve in dependency order; a cycle rejects, as does
    a base that names a subject without a position in this view.
    """
    resolved: dict[str, tuple[float | int, float | int]] = {}
    pending: dict[str, tuple[str, float | int, float | int]] = {}
    for subject, entry in positions.items():
        entry_dict = cast("dict[str, Any]", entry) if isinstance(entry, dict) else None
        if entry_dict is not None and "from" in entry_dict:
            context = f"invalid relative position for {subject!r} in view {view_name!r}"
            if set(entry_dict) != {"from", "delta"} or not isinstance(
                entry_dict["from"], str
            ):
                raise ViewApplicationError(context)
            base = entry_dict["from"]
            _validate_subject(base, view_name)
            delta = _point(entry_dict["delta"], context)
            pending[subject] = (base, delta[0], delta[1])
        else:
            resolved[subject] = _point(
                entry_dict, f"invalid position in view {view_name!r}"
            )
    while pending:
        progressed = False
        for subject in list(pending):
            base, dx, dy = pending[subject]
            if base in resolved:
                base_x, base_y = resolved[base]
                resolved[subject] = (base_x + dx, base_y + dy)
                del pending[subject]
                progressed = True
            elif base not in positions:
                raise ViewApplicationError(
                    f"view {view_name!r} relative position for {subject!r}"
                    f" references unpositioned subject {base!r}"
                )
        if not progressed:
            cycle = ", ".join(sorted(pending))
            raise ViewApplicationError(
                f"view {view_name!r} has a relative position cycle among: {cycle}"
            )
    return resolved


def _validate_routes(
    view_name: str,
    routes: Mapping[str, Any],
    handles: Mapping[str, Any],
) -> dict[int, tuple[str, list[tuple[float | int, float | int]]]]:
    """Validate every route and map it to an arc index, before mutating text."""
    route_by_arc: dict[int, tuple[str, list[tuple[float | int, float | int]]]] = {}
    for handle, raw_route in routes.items():
        if not isinstance(raw_route, dict):
            raise ViewApplicationError(f"invalid route in view {view_name!r}")
        route = cast(Mapping[str, Any], raw_route)
        raw_points = route.get("points")
        if (
            route.get("style") != "orthogonal"
            or not isinstance(raw_points, list)
            or not raw_points
        ):
            raise ViewApplicationError(f"invalid route in view {view_name!r}")
        points: list[tuple[float | int, float | int]] = [
            _point(
                raw_point,
                f"invalid route in view {view_name!r}",
            )
            for raw_point in cast(list[Any], raw_points)
        ]
        try:
            handle_value = cast(Mapping[str, Any], handles[handle])
            handle_index = handle_value["index"]
            if not isinstance(handle_index, int) or isinstance(handle_index, bool):
                raise TypeError
        except (KeyError, TypeError) as error:
            raise ViewApplicationError(
                f"view {view_name!r} route references unknown arc handle {handle!r}"
            ) from error
        route_by_arc[handle_index] = (handle, points)
    return route_by_arc


def _format_coord(value: float | int) -> str:
    """A coordinate the way both renderers spell an integral value."""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def _pin_beside_copies(
    lines: list[str],
    model: "RenderModel",
    resolved: Mapping[str, tuple[float | int, float | int]],
) -> None:
    """Pin each unpositioned ``beside`` copy next to its pinned transition.

    A whole-place position already wrote the same point onto every copy, so
    those copies are left as the author placed them. A shared copy whose
    two transitions are both pinned sits on the segment between them.
    """
    for placement in model.beside_placements:
        if placement.place in resolved:
            continue
        anchor = resolved.get(placement.anchor)
        other = resolved.get(placement.also) if placement.also is not None else None
        if placement.also is not None and anchor is not None and other is not None:
            span = placement.between_count + 1
            fraction = (placement.between_index + 1) / span
            point = (
                anchor[0] + fraction * (other[0] - anchor[0]),
                anchor[1] + fraction * (other[1] - anchor[1]),
            )
        elif anchor is not None:
            point = (anchor[0] + placement.slots * BESIDE_GAP, anchor[1])
        elif other is not None and placement.also_slots is not None:
            point = (other[0] + placement.also_slots * BESIDE_GAP, other[1])
        else:
            continue
        rendered = f"{_format_coord(point[0])},{_format_coord(point[1])}!"
        lines[placement.line] = _pos_statement_line(lines[placement.line], rendered)


def _pos_statement_line(line: str, rendered: str) -> str:
    """Rewrite one statement line to carry a ``pos`` attribute."""
    if line.endswith("];"):
        return f'{line[:-2]}, pos="{rendered}"];'
    if line.endswith(";"):
        return f'{line[:-1]} [pos="{rendered}"];'
    raise ViewApplicationError(
        f"render model statement line does not end a statement: {line!r}"
    )


def apply_view(
    model: "RenderModel",
    raw: Mapping[str, Any],
    view_name: str,
) -> str:
    """Apply one authored view to the model's rendered DOT and return it.

    Errors name their subject or handle; the pass mutates statement lines
    through the model's structural index and inserts ``splines=ortho``
    semantically (``model.graph_attr_line``) after any view is applied, or
    the view's own ``splines`` style. A
    view that positions any node also selects ``layout=neato`` with
    ``inputscale=72``. The ``beside`` rank clusters are removed, because
    ``neato`` ignores them. A ``beside`` copy whose transition is pinned,
    and whose place the view does not position, is pinned beside that
    transition (ADR 0067).
    """
    positions, routes = _view_facts(raw, view_name)
    resolved = resolve_positions(view_name, positions)
    try:
        handles = cast(
            Mapping[str, Any], raw["annotations"]["petrinet.dsl/v1"]["arcHandles"]
        )  # noqa: E501
    except (KeyError, TypeError) as error:
        raise ViewApplicationError(
            f"view {view_name!r} references no arcHandle map"
        ) from error
    route_by_arc = _validate_routes(view_name, routes, handles)

    lines = model.dot.splitlines()
    for subject, point in resolved.items():
        _validate_subject(subject, view_name)
        line_index_set = model.node_lines.get(subject)
        if not line_index_set:
            raise ViewApplicationError(
                f"view {view_name!r} positions unknown subject {subject!r}"
            )
        rendered = f"{point[0]},{point[1]}!"
        for line_index in line_index_set:
            lines[line_index] = _pos_statement_line(lines[line_index], rendered)
    for arc_index, (handle, points) in route_by_arc.items():
        if arc_index < 0 or arc_index >= len(model.arc_lines):
            raise ViewApplicationError(
                f"view {view_name!r} route {handle!r} references arc index"
                f" {arc_index} beyond the rendered arcs"
            )
        rendered = " ".join(f"{point[0]},{point[1]}" for point in points)
        line_index = model.arc_lines[arc_index]
        lines[line_index] = _pos_statement_line(lines[line_index], rendered)
    splines = view_setting(raw, view_name, "splines") or "ortho"
    if splines not in VIEW_SPLINES:
        raise ViewApplicationError(
            f"view {view_name!r} has invalid splines {splines!r}"
        )
    graph_attrs = [f"    splines={splines};"]
    if resolved:
        # Graphviz's default `dot` engine ignores `pos`. `neato` keeps pinned
        # nodes where they are and places the other nodes around them, and
        # `inputscale=72` reads the coordinates as points with y pointing up.
        # Without overlap removal neato drops ortho edges back to straight
        # lines; `overlap=scale` removes overlaps by scaling the whole layout
        # evenly, so the authored arrangement keeps its proportions.
        graph_attrs = [
            "    layout=neato;",
            "    inputscale=72;",
            "    overlap=scale;",
            *graph_attrs,
        ]
        # Rank clusters are for ``dot``. ``neato`` ignores them, and the
        # invisible edges would stay as springs. The offsets below place
        # the copies whose transitions this view pins.
        _pin_beside_copies(lines, model, resolved)
        for line_index in sorted(model.beside_lines, reverse=True):
            del lines[line_index]
    lines[model.graph_attr_line : model.graph_attr_line] = graph_attrs
    return "\n".join(lines) + "\n"
