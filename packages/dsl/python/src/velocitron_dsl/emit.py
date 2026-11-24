"""Canonical ``.petrinet`` text for a net or composition document.

``emit_petrinet`` renders that text. Compilation stays in
``velocitron_petrinet``. This module does not import ``velocitron``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any, cast

from .lower import (
    VIEW_DETAILS,
    VIEW_SPLINES,
    json_values_equal,
    valid_field_path,
)
from velocitron_viz import render_canonical_json

__all__ = ["emit_petrinet"]


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED = frozenset(
    {
        "net",
        "handler",
        "guard",
        "order",
        "data",
        "predicate",
        "accepts",
        "capacityPerColorKey",
        "weight",
        "cel",
        "correlate",
        "marking",
        "initial",
        "true",
        "false",
        "null",
    }
)
_ALIAS_RESERVED = _RESERVED | {
    "composition",
    "use",
    "as",
    "wire",
    "share",
    "refine",
    "by",
    "port",
    "input",
    "output",
    "timer",
    "clock",
    "bind",
    "priority",
}



def _name(name: str) -> str:
    return (
        name
        if _IDENTIFIER.fullmatch(name) and name not in _RESERVED
        else render_canonical_json(name)
    )


def _valid_capacity_key(value: object) -> bool:
    if isinstance(value, str):
        return bool(value)
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(part, str) and bool(part) for part in cast(list[object], value)
    )


def _json(value: Any) -> str:
    return render_canonical_json(value)


def _predicate_fact(predicate: object, *, handle: str) -> str:
    if not isinstance(predicate, Mapping):
        raise ValueError("not a resolved net document")
    typed_predicate = cast(Mapping[str, Any], predicate)
    if len(typed_predicate) != 1:
        raise ValueError("not a resolved net document")
    if "cel" in typed_predicate:
        kind = "cel"
    elif "handler" in typed_predicate:
        kind = "handler"
    else:
        raise ValueError("not a resolved net document")
    value = typed_predicate[kind]
    if not isinstance(value, str):
        raise ValueError("not a resolved net document")
    return f"@{handle} predicate {kind} {_json(value)}"


def _correlate_fact(correlate: object, *, handle: str) -> str:
    if not isinstance(correlate, Mapping):
        raise ValueError("not a resolved net document")
    typed_correlate = cast(Mapping[str, Any], correlate)
    cel = typed_correlate.get("cel")
    if set(typed_correlate) != {"cel"} or not isinstance(cel, str) or not cel:
        raise ValueError("not a resolved net document")
    return f"@{handle} correlate cel {_json(cel)}"


def _is_authoritative_coin_deposit(document: Mapping[str, Any]) -> bool:
    """Recognize the sole historical canonical template-name exception."""
    return document == {
        "name": "coin_deposit",
        "description": "Coin deposit",
        "places": [
            {"name": "coin_slot", "accepts": ["coin"]},
            {"name": "cash_box", "accepts": ["coin"]},
        ],
        "transitions": [{"name": "accept_coin", "handler": "accept_coin"}],
        "arcs": [
            {
                "from": {"place": "coin_slot"},
                "to": {"transition": "accept_coin"},
                "consume": {"type": "coin"},
            },
            {
                "from": {"transition": "accept_coin"},
                "to": {"place": "cash_box"},
                "produce": {"destination": "cash_box", "type": "coin"},
            },
        ],
        "initialMarking": {
            "coin_slot": [{"type": "coin", "data": {}}],
        },
    }


def _emit_composition(document: Mapping[str, Any]) -> str:
    if not (
        {"nets", "wires"}
        <= set(document)
        <= {"name", "nets", "wires", "shares", "refinements", "final"}
    ):
        raise ValueError("not a resolved composition document")
    name = document.get("name", "composition")
    if not isinstance(name, str) or not name:
        raise ValueError("not a resolved composition document")
    raw_nets, raw_wires = document["nets"], document["wires"]
    raw_refinements = document.get("refinements", [])
    raw_shares = document.get("shares", [])
    raw_final = document.get("final", [])
    if (
        not isinstance(raw_nets, list)
        or not isinstance(raw_wires, list)
        or not isinstance(raw_refinements, list)
        or not isinstance(raw_shares, list)
        or not isinstance(raw_final, list)
    ):
        raise ValueError("not a resolved composition document")
    net_items = cast(list[object], raw_nets)
    wire_items = cast(list[object], raw_wires)
    aliases: set[str] = set()
    uses: list[str] = []
    for raw_entry in net_items:
        if not isinstance(raw_entry, Mapping):
            raise ValueError("not a resolved composition document")
        entry = cast(Mapping[str, Any], raw_entry)
        ref, alias = entry.get("ref"), entry.get("alias")
        if (
            set(entry) != {"ref", "alias"}
            or not isinstance(ref, str)
            or not ref
            or not isinstance(alias, str)
            or not _IDENTIFIER.fullmatch(alias)
            or alias in _ALIAS_RESERVED
            or alias in aliases
        ):
            raise ValueError("not a resolved composition document")
        aliases.add(alias)
        uses.append(f"use {_json(ref)} as {alias}")
    wires: list[str] = []
    seen_wires: set[tuple[str, str, str, str]] = set()
    for raw_wire in wire_items:
        if not isinstance(raw_wire, Mapping):
            raise ValueError("not a resolved composition document")
        wire = cast(Mapping[str, Any], raw_wire)
        raw_from, raw_to = wire.get("from"), wire.get("to")
        if (
            set(wire) != {"from", "to"}
            or not isinstance(raw_from, Mapping)
            or not isinstance(raw_to, Mapping)
        ):
            raise ValueError("not a resolved composition document")
        typed_from = cast(Mapping[str, Any], raw_from)
        typed_to = cast(Mapping[str, Any], raw_to)
        endpoints: list[tuple[str, str]] = []
        for endpoint in (typed_from, typed_to):
            alias, port = endpoint.get("net"), endpoint.get("port")
            if (
                set(endpoint) != {"net", "port"}
                or not isinstance(alias, str)
                or alias not in aliases
                or not isinstance(port, str)
                or not port
            ):
                raise ValueError("not a resolved composition document")
            endpoints.append((alias, port))
        source, destination = endpoints
        key = (source[0], source[1], destination[0], destination[1])
        if key in seen_wires:
            raise ValueError("not a resolved composition document")
        seen_wires.add(key)
        wires.append(
            f"wire {source[0]}.({_name(source[1])}) -> "
            f"{destination[0]}.({_name(destination[1])})"
        )
    shares: list[str] = []
    for raw_share in cast(list[object], raw_shares):
        if not isinstance(raw_share, Mapping):
            raise ValueError("not a resolved composition document")
        share = cast(Mapping[str, Any], raw_share)
        raw_places = share.get("places")
        if set(share) != {"places"} or not isinstance(raw_places, list):
            raise ValueError("not a resolved composition document")
        members: list[str] = []
        for raw_member in cast(list[object], raw_places):
            if not isinstance(raw_member, Mapping):
                raise ValueError("not a resolved composition document")
            member = cast(Mapping[str, Any], raw_member)
            alias, place = member.get("net"), member.get("place")
            if (
                set(member) != {"net", "place"}
                or not isinstance(alias, str)
                or alias not in aliases
                or not isinstance(place, str)
                or not place
            ):
                raise ValueError("not a resolved composition document")
            members.append(f"{alias}.({_name(place)})")
        if len(members) < 2:
            raise ValueError("not a resolved composition document")
        shares.append("share " + " ~ ".join(members))
    refines: list[str] = []
    refined: set[tuple[str, str]] = set()
    for raw_refinement in cast(list[object], raw_refinements):
        if not isinstance(raw_refinement, Mapping):
            raise ValueError("not a resolved composition document")
        refinement = cast(Mapping[str, Any], raw_refinement)
        alias = refinement.get("net")
        transition = refinement.get("transition")
        by = refinement.get("by")
        if (
            set(refinement) != {"net", "transition", "by"}
            or not isinstance(alias, str)
            or alias not in aliases
            or not isinstance(transition, str)
            or not transition
            or not isinstance(by, str)
            or by not in aliases
            or by == alias
            or (alias, transition) in refined
        ):
            raise ValueError("not a resolved composition document")
        refined.add((alias, transition))
        refines.append(f"refine {alias}.[{_name(transition)}] by {by}")
    markings: list[str] = []
    for raw_marking in cast(list[object], raw_final):
        if not isinstance(raw_marking, list) or not raw_marking:
            raise ValueError("not a resolved composition document")
        places: list[str] = []
        for raw_member in cast(list[object], raw_marking):
            if not isinstance(raw_member, Mapping):
                raise ValueError("not a resolved composition document")
            member = cast(Mapping[str, Any], raw_member)
            alias, place = member.get("net"), member.get("place")
            if (
                set(member) != {"net", "place"}
                or not isinstance(alias, str)
                or alias not in aliases
                or not isinstance(place, str)
                or not place
            ):
                raise ValueError("not a resolved composition document")
            places.append(f"{alias}.({_name(place)})")
        markings.append(" + ".join(places))
    final = ["final " + ", ".join(markings)] if markings else []
    lines = [
        f"composition {_name(name)}",
        "",
        *uses,
        *wires,
        *shares,
        *refines,
        *final,
        "",
    ]
    return "\n".join(lines)


_DSL_METADATA_KEY = "petrinet.dsl/v1"


def _unsupported_fields(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    extra = set(value) - allowed
    if extra:
        field = sorted(extra)[0]
        raise ValueError(f"{path} has unsupported field {field!r}")


def _reserved_payload(
    document: Mapping[str, Any],
    arcs: list[dict[str, Any]],
    places: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[int, str]]:
    raw_annotations = document.get("annotations")
    if raw_annotations is None:
        return None, {}
    if not isinstance(raw_annotations, Mapping):
        raise ValueError("not a resolved net document")
    annotations_map = cast(Mapping[str, Any], raw_annotations)
    raw_payload = annotations_map.get(_DSL_METADATA_KEY)
    if raw_payload is None:
        return None, {}
    path = "annotations['petrinet.dsl/v1']"
    if not isinstance(raw_payload, Mapping):
        raise ValueError(f"{path} must be an object")
    payload = cast(dict[str, Any], raw_payload)
    _unsupported_fields(
        payload,
        {"arcHandles", "markings", "views", "extensions", "decorations"},
        path,
    )
    if not {"arcHandles", "markings", "views", "extensions"} <= set(payload):
        raise ValueError(
            f"{path} must contain arcHandles, markings, views, and extensions"
        )
    if not all(isinstance(payload[key], Mapping) for key in payload):
        raise ValueError(f"{path} sections must be objects")

    handles_by_index: dict[int, str] = {}
    for handle, raw_handle in cast(Mapping[Any, Any], payload["arcHandles"]).items():
        handle_path = f"{path}.arcHandles.{handle}"
        if not isinstance(handle, str) or not isinstance(raw_handle, Mapping):
            raise ValueError(f"{handle_path} must be an object")
        handle_value = cast(Mapping[str, Any], raw_handle)
        _unsupported_fields(handle_value, {"index", "fingerprint"}, handle_path)
        if set(handle_value) != {"index", "fingerprint"}:
            raise ValueError(f"{handle_path} must contain index and fingerprint")
        index = handle_value["index"]
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError(f"{handle_path}.index must be an integer")
        if index < 0 or index >= len(arcs):
            raise ValueError(
                f"{handle_path}.index {index} is outside arcs[0:{len(arcs)}]"
            )
        fingerprint = handle_value["fingerprint"]
        if not isinstance(fingerprint, Mapping):
            raise ValueError(f"{handle_path}.fingerprint must be an object")
        fingerprint_value = cast(Mapping[str, Any], fingerprint)
        _unsupported_fields(
            fingerprint_value,
            {"from", "to", "type", "mode"},
            f"{handle_path}.fingerprint",
        )
        arc = arcs[index]
        if "consume" in arc:
            actual = {
                "from": arc.get("from"),
                "to": arc.get("to"),
                "type": arc["consume"].get("type"),
                "mode": arc["consume"].get("mode", "consume"),
            }
        elif "produce" in arc:
            actual = {
                "from": arc.get("from"),
                "to": arc.get("to"),
                "type": arc["produce"].get("type"),
                "mode": "produce",
            }
        else:
            actual = {}
        if dict(fingerprint_value) != actual:
            raise ValueError(f"{handle_path}.fingerprint does not match arcs[{index}]")
        if index in handles_by_index:
            raise ValueError(f"{handle_path}.index duplicates another arc handle")
        handles_by_index[index] = handle

    place_names = {
        item.get("name") for item in places if isinstance(item.get("name"), str)
    }
    transition_names = {
        item.get("name") for item in transitions if isinstance(item.get("name"), str)
    }
    for marking_name, raw_marking in cast(
        Mapping[Any, Any], payload["markings"]
    ).items():
        marking_path = f"{path}.markings.{marking_name}"
        if not isinstance(marking_name, str) or not isinstance(raw_marking, Mapping):
            raise ValueError(f"{marking_path} must be an object")
        marking_value = cast(Mapping[str, Any], raw_marking)
        unknown: set[str] = set(marking_value) - place_names
        if unknown:
            field = sorted(unknown)[0]
            raise ValueError(f"{marking_path} has unsupported field {field!r}")
        for place, raw_tokens in marking_value.items():
            if not isinstance(raw_tokens, list):
                raise ValueError(f"{marking_path}.{place} is not a token array")
            for raw_token in cast(list[Any], raw_tokens):
                if not isinstance(raw_token, Mapping):
                    raise ValueError(f"{marking_path}.{place} is not a token array")
                token = cast(Mapping[str, Any], raw_token)
                if set(token) != {"type", "data"} or not isinstance(
                    token.get("type"), str
                ):
                    raise ValueError(f"{marking_path}.{place} is not a token array")

    for view_name, raw_view in cast(Mapping[Any, Any], payload["views"]).items():
        view_path = f"{path}.views.{view_name}"
        if not isinstance(view_name, str) or not isinstance(raw_view, Mapping):
            raise ValueError(f"{view_path} must be an object")
        view_value = cast(Mapping[str, Any], raw_view)
        _unsupported_fields(
            view_value, {"positions", "routes", "splines", "detail"}, view_path
        )
        if not {"positions", "routes"} <= set(view_value):
            raise ValueError(f"{view_path} must contain positions and routes")
        for member, allowed in (("splines", VIEW_SPLINES), ("detail", VIEW_DETAILS)):
            if member in view_value and view_value[member] not in allowed:
                raise ValueError(f"{view_path}.{member} is invalid")
        positions, view_routes = view_value["positions"], view_value["routes"]
        if not isinstance(positions, Mapping) or not isinstance(view_routes, Mapping):
            raise ValueError(f"{view_path} positions and routes must be objects")
        position_values = cast(Mapping[str, Any], positions)
        route_values = cast(Mapping[str, Any], view_routes)
        for subject, raw_position in position_values.items():
            position_path = f"{view_path}.positions.{subject}"
            if not isinstance(raw_position, Mapping):
                raise ValueError(f"{position_path} is invalid")
            position = cast(Mapping[str, Any], raw_position)
            subject_parts = subject.split(":", 1)
            if (
                len(subject_parts) != 2
                or subject_parts[0]
                not in {
                    "place",
                    "transition",
                }
                or not subject_parts[1]
            ):
                raise ValueError(
                    f"{position_path} must target place:<name> or transition:<name>"
                )
            subject_kind, subject_name = subject_parts
            known_names = place_names if subject_kind == "place" else transition_names
            if subject_name not in known_names:
                raise ValueError(
                    f"{position_path} references unknown {subject_kind} {subject_name!r}"
                )
            if "from" in position:
                _unsupported_fields(position, {"from", "delta"}, position_path)
                if set(position) != {"from", "delta"}:
                    raise ValueError(f"{position_path} is invalid")
                raw_base = position["from"]
                base = raw_base.split(":", 1) if isinstance(raw_base, str) else []
                base_kind, base_name = (
                    (base[0], base[1])
                    if len(base) == 2 and base[0] in {"place", "transition"} and base[1]
                    else (None, None)
                )
                if base_kind is None:
                    raise ValueError(
                        f"{position_path} must use from: place:<name> "
                        + "or transition:<name>"
                    )
                base_known = place_names if base_kind == "place" else transition_names
                if base_name not in base_known:
                    raise ValueError(
                        f"{position_path} references unknown {base_kind} {base_name!r}"
                    )
                delta = position["delta"]
                if not isinstance(delta, Mapping):
                    raise ValueError(f"{position_path} is invalid")
                delta = cast(Mapping[str, Any], delta)
                delta_path = f"{position_path}.delta"
                _unsupported_fields(delta, {"x", "y"}, delta_path)
                if set(delta) != {"x", "y"} or any(
                    not isinstance(delta.get(axis), (int, float))
                    or isinstance(delta.get(axis), bool)
                    or not math.isfinite(delta[axis])
                    for axis in ("x", "y")
                ):
                    raise ValueError(f"{delta_path} is invalid")
            else:
                _unsupported_fields(position, {"x", "y"}, position_path)
                if set(position) != {"x", "y"} or any(
                    not isinstance(position.get(axis), (int, float))
                    or isinstance(position.get(axis), bool)
                    or not math.isfinite(position[axis])
                    for axis in ("x", "y")
                ):
                    raise ValueError(f"{position_path} is invalid")
        for handle, raw_route in route_values.items():
            route_path = f"{view_path}.routes.{handle}"
            if handle not in payload["arcHandles"]:
                raise ValueError(f"{route_path} references unknown arc handle")
            if not isinstance(raw_route, Mapping):
                raise ValueError(f"{route_path} must be an object")
            route = cast(Mapping[str, Any], raw_route)
            _unsupported_fields(route, {"style", "points"}, route_path)
            if (
                set(route) != {"style", "points"}
                or route.get("style") != "orthogonal"
                or not isinstance(route.get("points"), list)
                or not route["points"]
            ):
                raise ValueError(f"{route_path} is invalid")
            points = cast(list[Any], route["points"])
            for point_index, raw_point in enumerate(points):
                point_path = f"{route_path}.points[{point_index}]"
                if not isinstance(raw_point, Mapping):
                    raise ValueError(f"{point_path} is invalid")
                point = cast(Mapping[str, Any], raw_point)
                _unsupported_fields(point, {"x", "y"}, point_path)
                if set(point) != {"x", "y"} or any(
                    not isinstance(point.get(axis), (int, float))
                    or isinstance(point.get(axis), bool)
                    or not math.isfinite(point[axis])
                    for axis in ("x", "y")
                ):
                    raise ValueError(f"{point_path} is invalid")

    colors = {
        color
        for item in places
        if isinstance(item.get("accepts"), list)
        for color in cast(list[Any], item["accepts"])
    }
    fusion_place_names = {
        item.get("name")
        for item in places
        if isinstance(item.get("annotations"), Mapping)
        and cast(Mapping[str, Any], item["annotations"]).get("fusion") is True
    }
    for subject, raw_decoration in cast(
        Mapping[Any, Any], payload.get("decorations", {})
    ).items():
        decoration_path = f"{path}.decorations.{subject}"
        subject_kind, _, subject_name = str(subject).partition(":")
        known_names = {
            "place": place_names,
            "transition": transition_names,
            "arc": set(payload["arcHandles"]),
            "color": colors,
        }.get(subject_kind)
        if known_names is None or not subject_name:
            raise ValueError(
                f"{decoration_path} must target place:, transition:, arc:, or color:"
            )
        if subject_name not in known_names:
            raise ValueError(
                f"{decoration_path} references unknown {subject_kind} {subject_name!r}"
            )
        if not isinstance(raw_decoration, Mapping) or not raw_decoration:
            raise ValueError(f"{decoration_path} must be a non-empty object")
        decoration = cast(Mapping[str, Any], raw_decoration)
        if subject_kind == "color":
            _unsupported_fields(decoration, {"quiet", "show"}, decoration_path)
            if "quiet" in decoration and decoration["quiet"] is not True:
                raise ValueError(f"{decoration_path}.quiet must be true")
            if "show" in decoration:
                shown = decoration["show"]
                if (
                    not isinstance(shown, list)
                    or not shown
                    or not all(
                        valid_field_path(path) for path in cast(list[Any], shown)
                    )
                    or len(set(cast(list[str], shown))) != len(cast(list[str], shown))
                ):
                    raise ValueError(
                        f"{decoration_path}.show must be a non-empty list of "
                        "distinct field paths"
                    )
            continue
        allowed = (
            {"highlight", "note", "beside"}
            if subject_kind == "place"
            else {"highlight", "note", "summary"}
        )
        _unsupported_fields(decoration, allowed, decoration_path)
        highlight = decoration.get("highlight", {})
        if (
            not isinstance(highlight, Mapping)
            or set(cast(Mapping[str, Any], highlight)) - {"label"}
            or not isinstance(cast(Mapping[str, Any], highlight).get("label", ""), str)
        ):
            raise ValueError(f"{decoration_path}.highlight is invalid")
        if "beside" in decoration:
            beside = decoration["beside"]
            if (
                not isinstance(beside, Mapping)
                or set(cast(Mapping[str, Any], beside)) - {"side"}
                or cast(Mapping[str, Any], beside).get("side", "left")
                not in ("left", "right")
            ):
                raise ValueError(f"{decoration_path}.beside is invalid")
            if subject_name not in fusion_place_names:
                raise ValueError(
                    f"{decoration_path}.beside needs a place annotated fusion true"
                )
        for member in ("note", "summary"):
            if member in decoration and not isinstance(decoration[member], str):
                raise ValueError(f"{decoration_path}.{member} must be a string")
    return payload, handles_by_index


def _compact_arc_indexes(
    places: Sequence[Mapping[str, object]],
    arcs: Sequence[Mapping[str, object]],
    *,
    compact: bool,
) -> set[int]:
    """Choose only default arcs whose color remains uniquely recoverable."""
    if not compact:
        return set()

    sole_color_by_place: dict[str, str] = {}
    anchored_colors_by_place: dict[str, set[str]] = {}

    for place in places:
        name, raw_accepts = place.get("name"), place.get("accepts")
        if not isinstance(name, str) or not isinstance(raw_accepts, list):
            continue
        accepts = cast(list[object], raw_accepts)
        accepted = [color for color in accepts if isinstance(color, str)]
        if len(accepted) == 1 and len(accepts) == 1:
            sole_color_by_place[name] = accepted[0]

    eligible: dict[int, tuple[str, str]] = {}
    for index, arc in enumerate(arcs):
        raw_inscription: object
        raw_endpoint: object
        default = False
        if "consume" in arc:
            raw_endpoint = arc.get("from")
            raw_inscription = arc.get("consume")
            if isinstance(raw_inscription, Mapping):
                inscription = cast(Mapping[str, object], raw_inscription)
                weight = inscription.get("weight", 1)
                default = bool(
                    inscription.get("mode", "consume") == "consume"
                    and weight == 1
                    and not isinstance(weight, bool)
                    and "predicate" not in inscription
                    and "data" not in inscription
                    and "correlate" not in inscription
                )
        elif "produce" in arc:
            raw_endpoint = arc.get("to")
            raw_inscription = arc.get("produce")
            if isinstance(raw_inscription, Mapping):
                inscription = cast(Mapping[str, object], raw_inscription)
                default = not any(
                    field in inscription
                    for field in (
                        "weight",
                        "predicate",
                        "data",
                        "cel",
                        "correlate",
                        "mode",
                    )
                )
        else:
            continue
        if not isinstance(raw_endpoint, Mapping) or not isinstance(
            raw_inscription, Mapping
        ):
            continue
        endpoint = cast(Mapping[str, object], raw_endpoint)
        inscription = cast(Mapping[str, object], raw_inscription)
        place = endpoint.get("place")
        color = inscription.get("type")
        if not isinstance(place, str) or not isinstance(color, str):
            continue
        if default and sole_color_by_place.get(place) == color:
            eligible[index] = (place, color)
        else:
            anchored_colors_by_place.setdefault(place, set()).add(color)

    elided: set[int] = set()
    for index, (place, color) in eligible.items():
        place_anchors = anchored_colors_by_place.setdefault(place, set())
        if color in place_anchors:
            elided.add(index)
            continue
        place_anchors.add(color)
    return elided


def _topology_place_accepts(
    arcs: Sequence[Mapping[str, object]],
) -> list[tuple[str, list[str]]]:
    """Reconstruct place order and accepted colors contributed by topology."""
    ordered: list[tuple[str, list[str]]] = []
    by_name: dict[str, list[str]] = {}
    for arc in arcs:
        if "consume" in arc:
            endpoint, inscription = arc.get("from"), arc.get("consume")
        elif "produce" in arc:
            endpoint, inscription = arc.get("to"), arc.get("produce")
        else:
            raise ValueError("not a resolved net document")
        if not isinstance(endpoint, Mapping) or not isinstance(inscription, Mapping):
            raise ValueError("not a resolved net document")
        typed_endpoint = cast(Mapping[str, object], endpoint)
        typed_inscription = cast(Mapping[str, object], inscription)
        place, color = typed_endpoint.get("place"), typed_inscription.get("type")
        if not isinstance(place, str) or not isinstance(color, str):
            raise ValueError("not a resolved net document")
        colors = by_name.get(place)
        if colors is None:
            colors = []
            by_name[place] = colors
            ordered.append((place, cast(list[str], colors)))
        if color not in colors:
            colors.append(color)
    return ordered


def _annotation_facts(target: str, key: str, value: Any) -> list[str]:
    """One annotation as DSL; the well-known actor keys get their own facts."""
    if key == "actor" and isinstance(value, str) and value:
        return [f"{target} actor {_name(value)}"]
    if key in ("lives", "reads_as") and target.startswith("("):
        keyword = "lives in" if key == "lives" else "reads as"
        if key == "lives" and isinstance(value, str) and value:
            return [f"{target} lives in {_name(value)}"]
        if (
            isinstance(value, Mapping)
            and set(cast(Mapping[str, Any], value)) == {"cel"}
            and isinstance(cast(Mapping[str, Any], value)["cel"], str)
        ):
            cel = cast(Mapping[str, Any], value)["cel"]
            return [f"{target} {keyword} cel {_json(cel)}"]
    if key == "kept" and target.startswith("(") and isinstance(value, Mapping):
        fields = cast(Mapping[str, Any], value)
        by, start = fields.get("by"), fields.get("start")
        cel = (
            cast(Mapping[str, Any], start).get("cel")
            if isinstance(start, Mapping)
            and set(cast(Mapping[str, Any], start)) == {"cel"}
            else None
        )
        if set(fields) == {"by", "start"} and isinstance(by, str) and by:
            if isinstance(cel, str):
                return [f"{target} kept by {_name(by)} starts as cel {_json(cel)}"]
    if key == "actors" and target == "net" and isinstance(value, list) and value:
        declared: list[str] = []
        for entry in cast(list[Any], value):
            fields: Mapping[str, Any] = (
                cast(Mapping[str, Any], entry) if isinstance(entry, Mapping) else {}
            )
            name, kind = fields.get("name"), fields.get("kind")
            if (
                set(fields) != {"name", "kind"}
                or not isinstance(name, str)
                or not name
                or kind not in ("person", "system", "record")
                or any(line.endswith(f" {_name(name)}") for line in declared)
            ):
                break
            declared.append(f"{kind} {_name(name)}")
        else:
            return declared
    return [f"{target} annotation {_name(key)} {_json(value)}"]


def _documented(arc: Mapping[str, Any]) -> bool:
    return "description" in arc or "annotations" in arc


def _arc_documentation_facts(arc: Mapping[str, Any], handle: str) -> list[str]:
    facts: list[str] = []
    description_value = arc.get("description")
    if isinstance(description_value, str):
        facts.append(f"@{_name(handle)} description {_json(description_value)}")
    raw_annotations = arc.get("annotations")
    if raw_annotations is not None:
        if not isinstance(raw_annotations, Mapping):
            raise TypeError
        annotation_values = cast(Mapping[str, Any], raw_annotations)
        facts.extend(
            f"@{_name(handle)} annotation {_name(key)} {_json(value)}"
            for key, value in sorted(annotation_values.items())
        )
    return facts


def _proof_facts(document: Mapping[str, Any]) -> list[str]:
    """``domain``, ``final`` and ``invariant`` lines for a net's domains and proofs."""
    facts: list[str] = []
    raw_domains = document.get("domains")
    if raw_domains is not None:
        if not isinstance(raw_domains, Mapping):
            raise ValueError("not a resolved net document")
        for key, values in cast(Mapping[str, Any], raw_domains).items():
            if (
                not valid_field_path(key)
                or "." not in key
                or not isinstance(values, list)
                or not values
            ):
                raise ValueError("not a resolved net document")
            color, *path = key.split(".")
            facts.append(
                f"domain {_name(color)}."
                + ".".join(_name(part) for part in path)
                + " "
                + " ".join(_json(value) for value in cast(list[Any], values))
            )
    raw_proofs = document.get("proofs")
    if raw_proofs is None:
        return facts
    if not isinstance(raw_proofs, Mapping):
        raise ValueError("not a resolved net document")
    proofs = cast(Mapping[str, Any], raw_proofs)
    final = proofs.get("final")
    if final:
        facts.append(
            "final "
            + ", ".join(
                " + ".join(
                    f"({_name(place)})"
                    for place in ([entry] if isinstance(entry, str) else entry)
                )
                for entry in cast(list[str | list[str]], final)
            )
        )
    for raw_invariant in cast(list[Any], proofs.get("invariants") or []):
        invariant = cast(Mapping[str, Any], raw_invariant)
        terms = " + ".join(
            f"({_name(place)})" if weight == 1 else f"{weight} * ({_name(place)})"
            for place, weight in cast(Mapping[str, int], invariant["weights"]).items()
        )
        name = invariant.get("name")
        constant = invariant.get("constant")
        facts.append(
            "invariant "
            + (f"{_json(name)} " if name is not None else "")
            + terms
            + (f" = {constant}" if constant is not None else "")
        )
    return facts


def emit_petrinet(document: Mapping[str, Any], compact: bool = False) -> str:
    """Emit deterministic DSL, optionally eliding only inferable default colors."""
    if "nets" in document:
        return _emit_composition(document)
    name = document.get("name")
    places = document.get("places")
    transitions = document.get("transitions")
    arcs = document.get("arcs")
    marking = document.get("initialMarking", {})
    if (
        not isinstance(name, str)
        or not isinstance(places, list)
        or not isinstance(transitions, list)
        or not isinstance(arcs, list)
        or not isinstance(marking, Mapping)
    ):
        raise ValueError("not a resolved net document")

    typed_places = cast(list[dict[str, Any]], places)
    typed_transitions = cast(list[dict[str, Any]], transitions)
    typed_arcs = cast(list[dict[str, Any]], arcs)
    typed_marking = cast(dict[str, Any], marking)
    compact_arc_indexes = _compact_arc_indexes(
        typed_places, typed_arcs, compact=compact
    )
    metadata, metadata_handles = _reserved_payload(
        document, typed_arcs, typed_places, typed_transitions
    )
    description = document.get("description")
    header = f"net {_name(name)}" + (
        f" {_json(description)}" if isinstance(description, str) else ""
    )
    documentation_facts: list[str] = []
    raw_document_annotations = document.get("annotations")
    if raw_document_annotations is not None:
        annotation_values = cast(Mapping[str, Any], raw_document_annotations)
        for key, value in sorted(annotation_values.items()):
            if key != _DSL_METADATA_KEY:
                documentation_facts.extend(_annotation_facts("net", key, value))

    transition_names: list[str] = []
    handlers: list[str] = []
    guards: list[str] = []
    timer_facts: list[str] = []
    binding_name_facts: list[str] = []
    priority_facts: list[str] = []
    for item in typed_transitions:
        transition = item.get("name")
        if not isinstance(transition, str):
            raise ValueError("not a resolved net document")
        transition_names.append(transition)
        if "bindingNames" in item:
            raw_keys = item["bindingNames"]
            if not isinstance(raw_keys, Mapping) or not raw_keys:
                raise ValueError("not a resolved net document")
            keys = cast(Mapping[Any, Any], raw_keys)
            if any(
                not isinstance(key, str)
                or not key
                or not isinstance(place, str)
                or not place
                for key, place in keys.items()
            ):
                raise ValueError("not a resolved net document")
            binding_name_facts.extend(
                f"[{_name(transition)}] bind {_name(key)} ({_name(keys[key])})"
                for key in sorted(cast(dict[str, Any], keys))
            )
        if "handler" in item:
            handler = item["handler"]
            if not isinstance(handler, str) or not handler:
                raise ValueError("not a resolved net document")
            handlers.append(f"[{_name(transition)}] handler {_json(handler)}")
        if "guard" in item:
            guard = item["guard"]
            if not isinstance(guard, str) or not guard:
                raise ValueError("not a resolved net document")
            guards.append(f"[{_name(transition)}] guard {_json(guard)}")
        raw_timer = item.get("timer")
        if raw_timer is not None:
            if not isinstance(raw_timer, Mapping):
                raise ValueError("not a resolved net document")
            timer = cast(Mapping[str, Any], raw_timer)
            clock = timer.get("clock")
            cel = timer.get("cel")
            maturity = timer.get("maturity")
            if (
                set(timer) - {"clock", "cel", "bind", "maturity"}
                or not isinstance(clock, str)
                or not clock
                or not isinstance(cel, str)
                or not cel
                or (
                    maturity is not None
                    and (not isinstance(maturity, str) or not maturity)
                )
            ):
                raise ValueError("not a resolved net document")
            timer_facts.append(
                f"[{_name(transition)}] timer clock ({_name(clock)}) cel {_json(cel)}"
            )
            if maturity is not None:
                timer_facts.append(
                    f"[{_name(transition)}] timer maturity cel {_json(maturity)}"
                )
            raw_binds = timer.get("bind")
            if raw_binds is not None:
                if not isinstance(raw_binds, Mapping):
                    raise ValueError("not a resolved net document")
                binds = cast(Mapping[Any, Any], raw_binds)
                if any(
                    not isinstance(bind_name, str)
                    or not bind_name
                    or not isinstance(place, str)
                    or not place
                    for bind_name, place in binds.items()
                ):
                    raise ValueError("not a resolved net document")
                timer_facts.extend(
                    f"[{_name(transition)}] timer bind {_name(bind_name)} "
                    f"({_name(cast(str, binds[bind_name]))})"
                    for bind_name in sorted(cast(dict[str, Any], binds))
                )
        if "priority" in item:
            priority = item["priority"]
            if (
                not isinstance(priority, int)
                or isinstance(priority, bool)
                or priority < 0
            ):
                raise ValueError("not a resolved net document")
            if priority:
                priority_facts.append(f"[{_name(transition)}] priority {priority}")
        if isinstance(item.get("description"), str):
            documentation_facts.append(
                f"[{_name(transition)}] description {_json(item['description'])}"
            )
        raw_annotations = item.get("annotations")
        if raw_annotations is not None:
            if not isinstance(raw_annotations, Mapping):
                raise ValueError("not a resolved net document")
            annotation_values = cast(Mapping[str, Any], raw_annotations)
            for key, value in sorted(annotation_values.items()):
                documentation_facts.extend(
                    _annotation_facts(f"[{_name(transition)}]", key, value)
                )

    declared_places: list[tuple[str, list[str]]] = []
    for item in typed_places:
        place, raw_accepts = item.get("name"), item.get("accepts")
        if (
            not isinstance(place, str)
            or not isinstance(raw_accepts, list)
            or not raw_accepts
            or any(
                not isinstance(color, str) or not color
                for color in cast(list[object], raw_accepts)
            )
            or len(cast(list[object], raw_accepts))
            != len(set(cast(list[object], raw_accepts)))
        ):
            raise ValueError("not a resolved net document")
        declared_places.append((place, cast(list[str], raw_accepts)))
    place_accept_facts = (
        [
            f"({_name(place)}) accepts [{', '.join(_name(color) for color in colors)}]"
            for place, colors in declared_places
        ]
        if _topology_place_accepts(typed_arcs) != declared_places
        else []
    )

    port_facts: list[str] = []
    for item in typed_places:
        place = item.get("name")
        if not isinstance(place, str):
            raise ValueError("not a resolved net document")
        raw_port = item.get("port")
        if raw_port is not None:
            if not isinstance(raw_port, Mapping):
                raise ValueError("not a resolved net document")
            port = cast(Mapping[str, Any], raw_port)
            direction, type_ = port.get("direction"), port.get("type")
            accepts = item.get("accepts")
            if (
                set(port) != {"direction", "type"}
                or direction not in {"input", "output"}
                or not isinstance(type_, str)
                or not isinstance(accepts, list)
                or type_ not in accepts
            ):
                raise ValueError("not a resolved net document")
            port_facts.append(f"({_name(place)}) port {direction} {_name(type_)}")
        if isinstance(item.get("description"), str):
            documentation_facts.append(
                f"({_name(place)}) description {_json(item['description'])}"
            )
        raw_annotations = item.get("annotations")
        if raw_annotations is not None:
            if not isinstance(raw_annotations, Mapping):
                raise ValueError("not a resolved net document")
            annotation_values = cast(Mapping[str, Any], raw_annotations)
            for key, value in sorted(annotation_values.items()):
                documentation_facts.extend(
                    _annotation_facts(f"({_name(place)})", key, value)
                )
    capacity_facts: list[str] = []
    for item in typed_places:
        place = item.get("name")
        if not isinstance(place, str):
            raise ValueError("not a resolved net document")
        raw_capacity = item.get("capacityPerColorKey")
        if raw_capacity is None:
            continue
        if not isinstance(raw_capacity, Mapping):
            raise ValueError("not a resolved net document")
        capacity = cast(Mapping[str, Any], raw_capacity)
        key, maximum = capacity.get("key"), capacity.get("max")
        valid_key = _valid_capacity_key(key)
        if (
            set(capacity) != {"key", "max"}
            or not valid_key
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or maximum < 1
        ):
            raise ValueError("not a resolved net document")
        capacity_facts.append(f"({_name(place)}) capacityPerColorKey {_json(capacity)}")

    chains: list[str] = []
    data_facts: list[str] = []
    weight_facts: list[str] = []
    predicate_facts: list[str] = []
    correlate_facts: list[str] = []
    first_arc_transitions: list[str] = []
    index = 0
    while index < len(typed_arcs):
        arc = typed_arcs[index]
        try:
            if "consume" in arc:
                place = arc["from"]["place"]
                transition = arc["to"]["transition"]
                raw_consume = arc["consume"]
                if not isinstance(raw_consume, Mapping):
                    raise TypeError
                consume = cast(Mapping[str, Any], raw_consume)
                color = consume["type"]
                mode = consume.get("mode", "consume")
                operator = {
                    "consume": "->",
                    "read": "->?",
                    "inhibit": "->0",
                }.get(mode)
                if (
                    not all(
                        isinstance(item, str) for item in (place, transition, color)
                    )
                    or operator is None
                ):
                    raise TypeError
                predicate = consume.get("predicate")
                has_correlate = "correlate" in consume
                correlate = consume.get("correlate")
                if has_correlate and correlate is None:
                    raise TypeError
                weight = consume.get("weight", 1)
                if (
                    not isinstance(weight, int)
                    or isinstance(weight, bool)
                    or weight < 1
                    or mode == "inhibit"
                    and weight > 1
                ):
                    raise TypeError
                input_segment = (
                    "->"
                    if index in compact_arc_indexes
                    else f"-{_name(color)}{operator}"
                )
                chain = f"({_name(place)}) {input_segment} [{_name(transition)}]"
                first_arc_transitions.append(transition)
                produce = None
                produce_index = None
                if (
                    metadata is None
                    and mode == "consume"
                    and predicate is None
                    and not has_correlate
                    and weight == 1
                    and not _documented(arc)
                    and index + 1 < len(typed_arcs)
                ):
                    following = typed_arcs[index + 1]
                    if (
                        following.get("from", {}).get("transition") == transition
                        and "produce" in following
                        and not _documented(following)
                    ):
                        destination = following["to"]["place"]
                        produce = following["produce"]
                        output_color = produce["type"]
                        if not isinstance(destination, str) or not isinstance(
                            output_color, str
                        ):
                            raise TypeError
                        output_segment = (
                            "->"
                            if index + 1 in compact_arc_indexes
                            else f"-{_name(output_color)}->"
                        )
                        chain += f" {output_segment} ({_name(destination)})"
                        produce_index = index + 1
                needs_weight_handle = weight > 1
                handle_index = (
                    index
                    if index in metadata_handles
                    or _documented(arc)
                    or has_correlate
                    or needs_weight_handle
                    or predicate is not None
                    else produce_index
                    if produce is not None and ("data" in produce or "cel" in produce)
                    else None
                )
                if handle_index is not None:
                    handle = metadata_handles.get(handle_index, f"arc_{handle_index}")
                    chain = f"@{_name(handle)}: " + chain
                    if produce is not None and "data" in produce:
                        data_facts.append(f"@{handle} data {_json(produce['data'])}")
                    if produce is not None and "cel" in produce:
                        data_facts.append(f"@{handle} data cel {_json(produce['cel'])}")
                    if predicate is not None:
                        predicate_facts.append(
                            _predicate_fact(predicate, handle=handle)
                        )
                    if correlate is not None:
                        correlate_facts.append(
                            _correlate_fact(correlate, handle=handle)
                        )
                    if needs_weight_handle:
                        weight_facts.append(f"@{handle} weight {weight}")
                    if handle_index == index:
                        documentation_facts.extend(
                            _arc_documentation_facts(arc, handle)
                        )
                if produce_index is not None:
                    index = produce_index
            elif "produce" in arc:
                transition = arc["from"]["transition"]
                destination = arc["to"]["place"]
                produce = arc["produce"]
                color = produce["type"]
                if not all(
                    isinstance(item, str) for item in (transition, destination, color)
                ):
                    raise TypeError
                output_segment = (
                    "->" if index in compact_arc_indexes else f"-{_name(color)}->"
                )
                chain = f"[{_name(transition)}] {output_segment} ({_name(destination)})"
                if (
                    "data" in produce
                    or "cel" in produce
                    or index in metadata_handles
                    or _documented(arc)
                ):
                    handle = metadata_handles.get(index, f"arc_{index}")
                    chain = f"@{_name(handle)}: " + chain
                    documentation_facts.extend(_arc_documentation_facts(arc, handle))
                    if "data" in produce:
                        data_facts.append(
                            f"@{_name(handle)} data {_json(produce['data'])}"
                        )
                    if "cel" in produce:
                        data_facts.append(
                            f"@{_name(handle)} data cel {_json(produce['cel'])}"
                        )
            else:
                raise TypeError
        except (KeyError, TypeError) as error:
            raise ValueError("not a resolved net document") from error
        chains.append(chain)
        index += 1

    appearance_order = list(dict.fromkeys(first_arc_transitions))
    order_facts = (
        [
            f"[{_name(transition)}] order {rank}"
            for rank, transition in enumerate(transition_names, 1)
        ]
        if appearance_order != transition_names
        else []
    )

    place_names = [cast(str, item["name"]) for item in typed_places]
    if any(place not in place_names for place in typed_marking):
        raise ValueError("not a resolved net document")

    generic_token: dict[str, Any] = {"type": "token", "data": {}}
    token_templates: list[dict[str, Any]] = []
    marking_runs: list[tuple[str, str, int, int | None]] = []

    def add_marking(marking_name: str, raw_marking: Mapping[str, Any]) -> None:
        for place in place_names:
            if place not in raw_marking:
                continue
            raw_tokens = raw_marking[place]
            if not isinstance(raw_tokens, list):
                raise ValueError("not a resolved net document")
            tokens = cast(list[Any], raw_tokens)
            offset = 0
            while offset < len(tokens):
                raw_token = tokens[offset]
                if not isinstance(raw_token, Mapping):
                    raise ValueError("not a resolved net document")
                token = cast(dict[str, Any], raw_token)
                if set(token) != {"type", "data"} or not isinstance(
                    token.get("type"), str
                ):
                    raise ValueError("not a resolved net document")
                run_length = 1
                while offset + run_length < len(tokens) and json_values_equal(
                    tokens[offset + run_length], token
                ):
                    run_length += 1
                if json_values_equal(token, generic_token):
                    marking_runs.append((marking_name, place, run_length, None))
                    offset += run_length
                    continue
                template_index = next(
                    (
                        candidate_index
                        for candidate_index, candidate in enumerate(token_templates)
                        if json_values_equal(candidate, token)
                    ),
                    -1,
                )
                if template_index < 0:
                    token_templates.append(token)
                    template_index = len(token_templates) - 1
                marking_runs.append((marking_name, place, run_length, template_index))
                offset += run_length

    add_marking("initial", typed_marking)
    if metadata is not None:
        for marking_name, raw_marking in metadata["markings"].items():
            add_marking(cast(str, marking_name), cast(Mapping[str, Any], raw_marking))

    template_name = (
        "inserted_coin" if _is_authoritative_coin_deposit(document) else "token_0"
    )

    def emitted_template_name(index: int) -> str:
        return template_name if len(token_templates) == 1 else f"token_{index}"

    def marking_fact(
        marking_name: str,
        place: str,
        run_length: int,
        template_index: int | None,
    ) -> str:
        prefix = (
            f"marking {marking_name if marking_name == 'initial' else _name(marking_name)} "
            f"({_name(place)}) <- "
        )
        if template_index is None:
            return f"{prefix}{run_length}"
        repetition = f"{run_length} * " if run_length > 1 else ""
        return f"{prefix}{repetition}${emitted_template_name(template_index)}"

    marking_facts = [
        marking_fact(marking_name, place, run_length, template_index)
        for marking_name, place, run_length, template_index in marking_runs
    ]
    template_facts = [
        f"${emitted_template_name(index)}: "
        f"{_name(cast(str, token['type']))} {_json(token['data'])}"
        for index, token in enumerate(token_templates)
    ]

    documentation_facts.sort(
        key=lambda fact: (
            0
            if fact.startswith("net ")
            else 1
            if fact.startswith("(")
            else 2
            if fact.startswith("[")
            else 3
        )
    )
    view_facts: list[str] = []
    if metadata is not None:
        for view_name, view in sorted(metadata["views"].items()):
            for member in ("splines", "detail"):
                if member in view:
                    view_facts.append(
                        f"view {_name(cast(str, view_name))} {member} {view[member]}"
                    )
            ordered_relative: list[tuple[str, str, Mapping[str, Any]]] = []
            for subject, position in view["positions"].items():
                if "from" in position:
                    ordered_relative.append(
                        (cast(str, position["from"]), cast(str, subject), position)
                    )
            ordered_positions = sorted(
                (
                    (subject, position)
                    for subject, position in view["positions"].items()
                    if "from" not in position
                ),
                key=lambda item: (item[1]["x"], item[1]["y"], item[0]),
            )
            for subject, position in ordered_positions:
                subject_type, subject_name = cast(str, subject).split(":", 1)
                rendered_subject = (
                    f"({_name(subject_name)})"
                    if subject_type == "place"
                    else f"[{_name(subject_name)}]"
                )
                view_facts.append(
                    f"view {_name(cast(str, view_name))} position "
                    f"{rendered_subject} at {_json(position)}"
                )
            for base, subject, position in sorted(
                ordered_relative, key=lambda item: (item[0], item[1])
            ):
                subject_type, subject_name = subject.split(":", 1)
                base_type, base_name = base.split(":", 1)
                rendered_subject = (
                    f"({_name(subject_name)})"
                    if subject_type == "place"
                    else f"[{_name(subject_name)}]"
                )
                rendered_base = (
                    f"({_name(base_name)})"
                    if base_type == "place"
                    else f"[{_name(base_name)}]"
                )
                view_facts.append(
                    f"view {_name(cast(str, view_name))} position "
                    f"{rendered_subject} relative {rendered_base} "
                    f"+ {_json(position['delta'])}"
                )
            for handle, route in sorted(view["routes"].items()):
                view_facts.append(
                    f"view {_name(cast(str, view_name))} route @{_name(cast(str, handle))} "
                    f"orthogonal {_json(route['points'])}"
                )
        kind_order = {"place": 0, "transition": 1, "arc": 2, "color": 3}
        for subject, decoration in sorted(
            metadata.get("decorations", {}).items(),
            key=lambda item: (kind_order[item[0].split(":", 1)[0]], item[0]),
        ):
            subject_kind, subject_name = cast(str, subject).split(":", 1)
            if subject_kind == "color":
                if decoration.get("quiet") is True:
                    view_facts.append(f"decorate color {_name(subject_name)} quiet")
                if "show" in decoration:
                    view_facts.append(
                        f"decorate color {_name(subject_name)} show "
                        + " ".join(_json(path) for path in decoration["show"])
                    )
                continue
            rendered_subject = (
                f"({_name(subject_name)})"
                if subject_kind == "place"
                else f"[{_name(subject_name)}]"
                if subject_kind == "transition"
                else f"@{_name(subject_name)}"
            )
            if "highlight" in decoration:
                label = decoration["highlight"].get("label")
                view_facts.append(
                    f"decorate {rendered_subject} highlight"
                    + ("" if label is None else f" {_json(label)}")
                )
            for member in ("note", "summary"):
                if member in decoration:
                    view_facts.append(
                        f"decorate {rendered_subject} {member} {_json(decoration[member])}"
                    )
            if "beside" in decoration:
                side = decoration["beside"].get("side")
                view_facts.append(
                    f"decorate {rendered_subject} beside"
                    + ("" if side is None else f" {side}")
                )
        view_facts.append(f"extensions {_json(metadata['extensions'])}")

    proof_facts = _proof_facts(document)
    common_tail = [
        timer_facts,
        binding_name_facts,
        priority_facts,
        order_facts,
        capacity_facts,
        weight_facts,
        data_facts,
        predicate_facts,
        correlate_facts,
    ]
    sections = (
        [
            [header],
            place_accept_facts,
            chains,
            [*handlers, *guards],
            port_facts,
            *common_tail,
            [*marking_facts, *template_facts],
            proof_facts,
            documentation_facts,
            view_facts,
        ]
        if metadata is not None
        else [
            [header],
            place_accept_facts,
            chains,
            port_facts,
            [*handlers, *guards],
            *common_tail,
            [*marking_facts, *template_facts],
            proof_facts,
            documentation_facts,
        ]
    )
    lines: list[str] = []
    for section in sections:
        if not section:
            continue
        if lines:
            lines.append("")
        lines.extend(section)
    lines.append("")
    return "\n".join(lines)
