"""Resolve contribution IR into canonical net or composition JSON.

ANTLR lowering lives in ``velocitron_dsl``. This module compiles CEL,
resolves contributions, and closes the document through :func:`parse_net`
or :func:`parse_composition`. It does not emit ``.petrinet`` text.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Final, NoReturn, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from velocitron_cel import get_default_adapter
from velocitron_dsl import (
    Diagnostic,
    PetrinetDslError,
    RelatedDiagnostic,
    SourcePosition,
    SourceSpan,
    contains_isolated_surrogate,
    json_values_equal,
    untag_json_value,
    valid_capacity_key,
    valid_field_path,
)
from velocitron_ir import (
    CONTRIBUTION_IR_FORMAT,
    CONTRIBUTION_IR_VERSION,
    contribution_ir_schema,
)

from .parse import NetValidationError, parse_composition, parse_net

__all__ = [
    "SourceInput",
    "resolve_contribution_ir",
]

_RELATIVE_SOURCE_ID = re.compile(
    r"^(?!/)(?![A-Za-z]:[\\/])(?![A-Za-z][A-Za-z0-9+.-]*:).+$"
)
_TIMER_BIND_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DECORATION_SUBJECT_KINDS: Final[Mapping[str, str]] = {
    "place": "place",
    "transition": "transition",
    "arcHandle": "arc",
    "color": "color",
}

# The packaged wire schema is consulted once, at import time, by every
# resolve_contribution_ir call. Resolution itself is the only consumer — the
# engine runtime never touches this module — so a single shared validator
# keeps schema-consult cost off the hot path entirely. See ADR 0026.
_IR_VALIDATOR: Final = Draft202012Validator(contribution_ir_schema())  # pyright: ignore[reportUnknownMemberType]


@dataclass(frozen=True)
class SourceInput:
    """Text and explicit portable identity for one DSL source."""

    source_id: str
    text: str


def _exact_point(value: Any) -> bool:
    """True for an exact v1 coordinate point: exactly the x and y members,
    each a plain (non-boolean) number without a finite/lexeme requirement
    beyond what the tagged-number lexer already enforces."""
    if not isinstance(value, Mapping):
        return False
    point = cast(Mapping[str, Any], value)
    return set(point) == {"x", "y"} and all(
        isinstance(point[axis], (int, float)) and not isinstance(point[axis], bool)
        for axis in ("x", "y")
    )


def _resolution_error(
    code: str,
    message: str,
    span: Mapping[str, Any] | None = None,
    help: str | None = None,
    related: tuple[tuple[str, Mapping[str, Any]], ...] = (),
) -> PetrinetDslError:
    try:
        if span is not None:
            source = str(span["source"])
            start = span["start"]
            end = span["end"]
            resolved_span = SourceSpan(
                source,
                SourcePosition(start["byteOffset"], start["line"], start["column"]),
                SourcePosition(end["byteOffset"], end["line"], end["column"]),
            )
        else:
            raise KeyError
    except (KeyError, TypeError):
        position = SourcePosition(0, 1, 1)
        resolved_span = SourceSpan("<ir>", position, position)
    related_diagnostics = tuple(
        RelatedDiagnostic(
            related_message,
            SourceSpan(
                str(related_span["source"]),
                SourcePosition(
                    related_span["start"]["byteOffset"],
                    related_span["start"]["line"],
                    related_span["start"]["column"],
                ),
                SourcePosition(
                    related_span["end"]["byteOffset"],
                    related_span["end"]["line"],
                    related_span["end"]["column"],
                ),
            ),
        )
        for related_message, related_span in related
    )
    return PetrinetDslError(
        Diagnostic(code, message, resolved_span, help, related_diagnostics)
    )


def _position_subject(
    raw: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    """``(kind, name, copy_transition)`` for a view position subject or base.

    ``kind`` is ``place``, ``transition``, or ``placeCopy``. ``name`` is the
    place for a copy. ``copy_transition`` is empty unless ``kind`` is
    ``placeCopy``.
    """
    kind = raw.get("type")
    if kind == "placeCopy":
        place, transition = raw.get("place"), raw.get("transition")
        if (
            set(raw) != {"type", "place", "transition"}
            or not isinstance(place, str)
            or not place
            or not isinstance(transition, str)
            or not transition
        ):
            return None
        return "placeCopy", place, transition
    name = raw.get("name")
    if (
        kind not in {"place", "transition"}
        or set(raw) != {"type", "name"}
        or not isinstance(name, str)
        or not name
    ):
        return None
    return cast(str, kind), name, ""


def _position_key(kind: str, name: str, copy_transition: str) -> str:
    """The positions-map key for one subject or relative base."""
    if kind == "placeCopy":
        return f"place:{name}@transition:{copy_transition}"
    return f"{kind}:{name}"


def _rendered_position_target(kind: str, name: str, copy_transition: str) -> str:
    if kind == "placeCopy":
        return f"({name})@[{copy_transition}]"
    if kind == "place":
        return f"({name})"
    return f"[{name}]"


def _arc_place_transition(arc: Mapping[str, Any]) -> tuple[str, str] | None:
    """The ``(place, transition)`` pair an arc joins, in either direction."""
    source, destination = arc.get("from"), arc.get("to")
    if not isinstance(source, Mapping) or not isinstance(destination, Mapping):
        return None
    if "place" in source and "transition" in destination:
        place, transition = source["place"], destination["transition"]
    elif "transition" in source and "place" in destination:
        place, transition = destination["place"], source["transition"]
    else:
        return None
    if not isinstance(place, str) or not isinstance(transition, str):
        return None
    return place, transition


def _sibling_groups(
    arcs: Sequence[Mapping[str, Any]], fusion: set[str]
) -> list[tuple[str, ...]]:
    """Transitions whose one drawn input place is the same place (ADR 0035).

    Fusion places do not count as inputs. A group is in the order of each
    transition's first arc from that place. Only groups of two or more are
    returned. Keep this in step with ``sibling_groups`` in the renderer.
    """
    inputs: dict[str, set[str]] = {}
    first_arcs: list[tuple[str, str]] = []
    for arc in arcs:
        source, destination = arc.get("from"), arc.get("to")
        if not isinstance(source, Mapping) or not isinstance(destination, Mapping):
            continue
        place, transition = source.get("place"), destination.get("transition")
        if (
            not isinstance(place, str)
            or not isinstance(transition, str)
            or place in fusion
        ):
            continue
        seen = inputs.setdefault(transition, set())
        if place not in seen:
            seen.add(place)
            first_arcs.append((place, transition))
    groups: dict[str, list[str]] = {}
    for place, transition in first_arcs:
        if inputs[transition] == {place}:
            groups.setdefault(place, []).append(transition)
    return [tuple(group) for group in groups.values() if len(group) > 1]


def _shared_copy_owners(
    arcs: Sequence[Mapping[str, Any]],
    fusion: set[str],
    beside_open: set[str],
) -> dict[tuple[str, str], frozenset[str]]:
    """``(place, transition)`` → the two transitions that share that copy.

    ADR 0035 draws one copy between neighbor transitions when the place has
    ``beside`` and no side. A run pairs from the left. A place with a side,
    or without ``beside``, has no shared copy, so it is absent here.
    """
    users: dict[str, set[str]] = {}
    for arc in arcs:
        pair = _arc_place_transition(arc)
        if pair is None or pair[0] not in beside_open:
            continue
        users.setdefault(pair[0], set()).add(pair[1])
    shared: dict[tuple[str, str], frozenset[str]] = {}
    for group in _sibling_groups(arcs, fusion):
        for place in beside_open:
            if not any(transition in users.get(place, ()) for transition in group):
                continue
            start = 0
            while start < len(group):
                end = start
                while end < len(group) and group[end] in users.get(place, ()):
                    end += 1
                run = group[start:end]
                for index in range(0, len(run) - 1, 2):
                    owners = frozenset((run[index], run[index + 1]))
                    shared[(place, run[index])] = owners
                    shared[(place, run[index + 1])] = owners
                start = end + 1 if end == start else end
    return shared


def _relative_span(span: Mapping[str, Any], prefix: str, target: str) -> dict[str, Any]:
    start = cast(Mapping[str, Any], span["start"])
    line = cast(int, start["line"])
    column = cast(int, start["column"]) + len(prefix)
    byte_offset = cast(int, start["byteOffset"]) + len(prefix.encode("utf-8"))
    return {
        "source": span["source"],
        "start": {"byteOffset": byte_offset, "line": line, "column": column},
        "end": {
            "byteOffset": byte_offset + len(target.encode("utf-8")),
            "line": line,
            "column": column + len(target),
        },
    }


def _parse_marking_token(
    raw_token: object,
    *,
    message: str,
    span: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(raw_token, Mapping):
        raise _resolution_error("PN200", message, span)
    token = cast(Mapping[str, Any], raw_token)
    if set(token) == {"template"}:
        raw_template = token["template"]
        if not isinstance(raw_template, Mapping):
            raise _resolution_error("PN200", message, span)
        template = cast(Mapping[str, Any], raw_template)
        name = template.get("name")
        if (
            set(template) != {"type", "name"}
            or template.get("type") != "template"
            or not isinstance(name, str)
            or not name
        ):
            raise _resolution_error("PN200", message, span)
        return {"template": name}
    if set(token) != {"color", "data"}:
        raise _resolution_error("PN200", message, span)
    color = token.get("color")
    raw_data = token.get("data")
    if not isinstance(color, str) or not color or not isinstance(raw_data, Mapping):
        raise _resolution_error("PN200", message, span)
    try:
        data = untag_json_value(cast(Mapping[str, Any], raw_data))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise _resolution_error("PN200", message, span) from error
    if not isinstance(data, dict):
        raise _resolution_error("PN200", message, span)
    return {"color": color, "data": data}


def _materialize_marking_token(
    *,
    place: str,
    token: Mapping[str, Any],
    count: int,
    accepted_colors: Sequence[str],
    templates: Mapping[str, Any],
    span: Mapping[str, Any],
    marking_name: str | None = None,
) -> list[dict[str, Any]]:
    template = token.get("template")
    if isinstance(template, str):
        if template not in templates:
            raise _resolution_error("PN202", f"undefined template ${template}", span)
        if len(accepted_colors) != 1:
            raise _resolution_error(
                "PN202", f"template ${template} color is ambiguous at ({place})", span
            )
        color = accepted_colors[0]
        template_data = templates[template]
        if not isinstance(template_data, dict):
            raise _resolution_error(
                "PN202",
                f"template ${template} data must be a JSON object",
                span,
            )
        data = cast(dict[str, Any], template_data)
    else:
        color = cast(str, token["color"])
        if color not in accepted_colors:
            subject = (
                "marking" if marking_name is None else f"named marking {marking_name!r}"
            )
            raise _resolution_error(
                "PN202",
                f"{subject} token color {color!r} is not accepted by place ({place})",
                span,
            )
        data = cast(dict[str, Any], token["data"])
    return [{"type": color, "data": deepcopy(data)} for _ in range(count)]


def _is_source_span(value: object, expected_source: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    span = cast(dict[str, Any], value)
    if (
        set(span) != {"source", "start", "end"}
        or span["source"] != expected_source
        or _RELATIVE_SOURCE_ID.fullmatch(expected_source) is None
    ):
        return False
    positions: list[tuple[int, int, int]] = []
    for raw_position in (span["start"], span["end"]):
        if not isinstance(raw_position, Mapping):
            return False
        position = cast(dict[str, Any], raw_position)
        if set(position) != {"byteOffset", "line", "column"}:
            return False
        byte_offset = position["byteOffset"]
        line = position["line"]
        column = position["column"]
        if (
            not isinstance(byte_offset, int)
            or isinstance(byte_offset, bool)
            or byte_offset < 0
            or not isinstance(line, int)
            or isinstance(line, bool)
            or line < 1
            or not isinstance(column, int)
            or isinstance(column, bool)
            or column < 1
        ):
            return False
        positions.append((byte_offset, line, column))
    start, end = positions
    return start[0] <= end[0] and start[1:] <= end[1:]


def _source_identity(value: object, source_member: str) -> tuple[str, int, int] | None:
    if not isinstance(value, Mapping):
        return None
    identity = cast(Mapping[str, Any], value)
    if set(identity) != {source_member, "statement", "part"}:
        return None
    source = identity.get(source_member)
    statement = identity.get("statement")
    part = identity.get("part")
    if (
        not isinstance(source, str)
        or _RELATIVE_SOURCE_ID.fullmatch(source) is None
        or not isinstance(statement, int)
        or isinstance(statement, bool)
        or statement < 0
        or not isinstance(part, int)
        or isinstance(part, bool)
        or part < 0
    ):
        return None
    return source, statement, part


def _contribution_identity(value: object) -> tuple[str, int, int] | None:
    return _source_identity(value, "source")


def _arc_identity(value: object) -> tuple[str, int, int] | None:
    return _source_identity(value, "document")


# Per-kind shape diagnostics; the strings mirror the resolver's own per-kind
# contributions-loop checks so a wire-schema failure reports the same message
# the handwritten check would have raised (ADR 0026).
_INVALID_CONTRIBUTION_MESSAGES: Final[Mapping[str, str]] = {
    "document.net-header": "invalid net header contribution",
    "document.composition-header": "invalid composition header contribution",
    "place.declare": "invalid place declaration contribution",
    "transition.declare": "invalid transition declaration contribution",
    "place.accepts": "invalid place accepted-colors contribution",
    "place.port": "invalid place port contribution",
    "arc.handle": "invalid arc handle contribution",
    "order.transition": "invalid transition order contribution",
    "order.arc-run": "invalid arc-run order contribution",
    "place.capacity-per-color-key": "invalid place capacity contribution",
    "arc.weight": "invalid arc weight contribution",
    "arc.produce-data": "invalid arc produce-data contribution",
    "arc.produce-cel": "invalid arc produce-cel contribution",
    "arc.predicate": "invalid arc predicate contribution",
    "arc.correlate": "invalid arc correlate contribution",
    "arc.declare": "invalid arc declaration",
    "transition.timer": "invalid transition timer contribution",
    "transition.timer-maturity": "invalid transition timer maturity contribution",
    "transition.timer-bind": "invalid transition timer bind contribution",
    "transition.binding-name": "invalid transition binding name contribution",
    "transition.priority": "invalid transition priority contribution",
    "transition.handler": "invalid transition handler contribution",
    "transition.guard": "invalid transition guard contribution",
    "marking.append": "invalid initial marking contribution",
    "template.define": "invalid template definition contribution",
    "documentation.description": "invalid documentation description contribution",
    "documentation.annotation": "invalid documentation annotation contribution",
    "metadata.named-marking": "invalid named marking contribution",
    "view.position": "invalid view position contribution",
    "view.route": "invalid view route contribution",
    "view.splines": "invalid view splines contribution",
    "view.detail": "invalid view detail contribution",
    "decoration.highlight": "invalid highlight decoration contribution",
    "decoration.note": "invalid note decoration contribution",
    "decoration.summary": "invalid summary decoration contribution",
    "decoration.quiet": "invalid quiet decoration contribution",
    "decoration.beside": "invalid beside decoration contribution",
    "decoration.show": "invalid show decoration contribution",
    "document.extensions": "invalid document extensions contribution",
    "domain.values": "invalid domain contribution",
    "proof.final": "invalid final place contribution",
    "proof.invariant": "invalid invariant contribution",
    "actor.declare": "invalid actor declaration contribution",
    "composition.use": "invalid composition use",
    "composition.wire": "invalid composition wire",
    "composition.share": "invalid composition share",
    "composition.refine": "invalid composition refine",
    "composition.final": "invalid composition final",
}

# Document-targeted description and annotation facts predate the typed net
# document target and remain accepted by resolution; the wire schema rejects
# their legacy target, so the schema gate tolerates exactly that shape (ADR 0026).
_LEGACY_DOCUMENT_METADATA_KINDS: Final[frozenset[str]] = frozenset(
    {"documentation.description", "documentation.annotation"}
)


def _schema_error_contribution_index(error: ValidationError) -> int | None:
    path = error.absolute_path
    if (
        len(path) >= 2
        and path[0] == "contributions"
        and isinstance(path[1], int)
        and not isinstance(path[1], bool)
    ):
        return int(path[1])
    return None


def _invalid_contribution_message(kind: object) -> str:
    if isinstance(kind, str):
        message = _INVALID_CONTRIBUTION_MESSAGES.get(kind)
        if message is not None:
            return message
    return f"unsupported contribution kind {kind!r}"


def _only_legacy_document_metadata_failed_schema(
    document_ir: Mapping[str, Any],
    errors: Sequence[ValidationError],
) -> bool:
    """True when every schema failure is a tolerated pre-v1 metadata target.

    Resolution still accepts descriptions and annotations that target the
    document with the legacy ``{"type": "document"}`` shape, which the wire
    schema's closed element target cannot express. Tolerance requires the
    affected contributions to be otherwise complete so the envelope's
    remaining handwritten checks can safely read them.
    """
    raw_contributions = document_ir.get("contributions")
    if not isinstance(raw_contributions, list):
        return False
    contributions = cast("list[Any]", raw_contributions)
    invalid_indexes: set[int] = set()
    for error in errors:
        index = _schema_error_contribution_index(error)
        if index is None:
            return False
        invalid_indexes.add(index)
    if not invalid_indexes:
        return False
    for index in invalid_indexes:
        if index >= len(contributions):
            return False
        raw_contribution = contributions[index]
        if not isinstance(raw_contribution, Mapping):
            return False
        contribution = cast(Mapping[str, Any], raw_contribution)
        if frozenset(contribution) != _CONTRIBUTION_MEMBER_KEYS:
            return False
        if contribution["kind"] not in _LEGACY_DOCUMENT_METADATA_KINDS:
            return False
        raw_target = contribution["target"]
        if (
            not isinstance(raw_target, Mapping)
            or set(cast(Mapping[str, Any], raw_target)) != {"type"}
            or raw_target["type"] != "document"
        ):
            return False
    return True


_CONTRIBUTION_MEMBER_KEYS: Final[frozenset[str]] = frozenset(
    {"id", "kind", "ordinal", "span", "target", "value"}
)


def _reject_schema_invalid_ir(
    document_ir: Mapping[str, Any],
    errors: Sequence[ValidationError],
) -> NoReturn:
    """Translate wire-schema failures into the resolution diagnostics.

    The order mirrors the replaced handwritten preflight so every pinned
    PN-coded diagnostic keeps its code, message, and span (ADR 0026).
    """
    if (
        document_ir.get("format") != CONTRIBUTION_IR_FORMAT
        or document_ir.get("version") != CONTRIBUTION_IR_VERSION
    ):
        raise _resolution_error(
            "PN200", "unsupported Contribution IR format or version"
        )
    if set(document_ir) != {
        "format",
        "version",
        "documentKind",
        "document",
        "contributions",
    }:
        raise _resolution_error("PN200", "invalid Contribution IR document shape")
    raw_document = document_ir["document"]
    if not isinstance(raw_document, Mapping):
        raise _resolution_error("PN200", "invalid Contribution IR document")
    document = cast(Mapping[str, Any], raw_document)
    document_id = document.get("id")
    if (
        document_ir["documentKind"] not in {"net", "composition"}
        or set(document) != {"id"}
        or not isinstance(document_id, str)
        or _RELATIVE_SOURCE_ID.fullmatch(document_id) is None
    ):
        raise _resolution_error("PN200", "invalid Contribution IR document")
    if not isinstance(document_ir["contributions"], list):
        raise _resolution_error("PN200", "contributions must be an array")
    invalid_index: int | None = None
    for error in errors:
        index = _schema_error_contribution_index(error)
        if index is not None and (invalid_index is None or index < invalid_index):
            invalid_index = index
    if invalid_index is None:
        raise _resolution_error("PN200", "invalid Contribution IR document shape")
    raw_contribution = cast("list[Any]", document_ir["contributions"])[invalid_index]
    if not isinstance(raw_contribution, Mapping):
        raise _resolution_error("PN200", "invalid Contribution IR contribution shape")
    if (
        frozenset(cast(Mapping[str, Any], raw_contribution))
        != _CONTRIBUTION_MEMBER_KEYS
    ):
        raise _resolution_error("PN200", "invalid Contribution IR contribution shape")
    contribution = cast(Mapping[str, Any], raw_contribution)
    kind = contribution["kind"]
    raw_target = contribution["target"]
    raw_value = contribution["value"]
    target = cast(Mapping[str, Any], raw_target)
    value = cast(Mapping[str, Any], raw_value)
    raw_span = contribution["span"]
    span = cast(Mapping[str, Any], raw_span) if isinstance(raw_span, Mapping) else None
    identity = _contribution_identity(contribution["id"])
    # Span provenance is a resolver-owned cross-fact: the schema cannot bind
    # a span's source to the contribution id's source, so a schema-reported
    # span failure still carries the pinned provenance message.
    if identity is not None and not _is_source_span(contribution["span"], identity[0]):
        raise _resolution_error("PN200", "invalid contribution span")
    if kind == "arc.declare" and isinstance(raw_value, Mapping):
        mode = value.get("mode")
        transition_name_span = value.get("transitionNameSpan")
        if identity is not None and mode == "consume":
            if transition_name_span is None:
                raise _resolution_error(
                    "PN200", "invalid consumed arc declaration", span
                )
            if not _is_source_span(transition_name_span, identity[0]):
                raise _resolution_error(
                    "PN200", "consumed arc has invalid transitionNameSpan", span
                )
        elif (
            identity is not None
            and mode != "consume"
            and transition_name_span is not None
        ):
            raise _resolution_error("PN200", "invalid consumed arc declaration", span)
    if (
        kind == "arc.weight"
        and isinstance(raw_value, Mapping)
        and isinstance(raw_target, Mapping)
    ):
        weight = value.get("weight")
        if isinstance(weight, int) and not isinstance(weight, bool) and weight < 1:
            raise _resolution_error(
                "PN202",
                "arc weight must be an integer greater than or equal to 1; "
                f"got {weight!r} for @{target.get('name')}",
                span,
            )
    if (
        kind == "place.capacity-per-color-key"
        and isinstance(raw_value, Mapping)
        and isinstance(raw_target, Mapping)
    ):
        name = target.get("name")
        if set(value) != {"key", "max"}:
            raise _resolution_error(
                "PN202",
                f"capacityPerColorKey for ({name}) must contain exactly key and max",
                span,
            )
        if not valid_capacity_key(value["key"]):
            raise _resolution_error(
                "PN202",
                "capacityPerColorKey key must be a non-empty string or non-empty "
                f"array of non-empty strings for ({name})",
                span,
            )
        maximum = value["max"]
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
            raise _resolution_error(
                "PN202",
                "capacityPerColorKey max must be an integer greater than or "
                f"equal to 1; got {maximum!r} for ({name})",
                span,
            )
    if (
        kind == "view.route"
        and isinstance(raw_value, Mapping)
        and isinstance(raw_target, Mapping)
    ):
        raw_view = value.get("view")
        if (
            isinstance(raw_view, Mapping)
            and isinstance(cast(Mapping[str, Any], raw_view).get("name"), str)
            and value.get("points") == []
        ):
            raise _resolution_error(
                "PN202",
                f"view {cast(Mapping[str, Any], raw_view)['name']!r} route "
                f"@{target.get('name')} requires at least one point",
                span,
                'add at least one {"x": Number, "y": Number} point',
            )
    raise _resolution_error("PN200", _invalid_contribution_message(kind), span)


def _resolve_composition_contributions(
    contribution_items: list[Any],
    *,
    aggregate_sources: bool = False,
    net_loader: Callable[[str], Mapping[str, Any] | Path | str] | None = None,
    origin: Path | None = None,
) -> dict[str, Any]:
    header: tuple[str, Mapping[str, Any]] | None = None
    uses: dict[str, tuple[str, Mapping[str, Any]]] = {}
    ordered_uses: list[dict[str, str]] = []
    wires: list[dict[str, dict[str, str]]] = []
    wire_spans: dict[tuple[tuple[str, str], tuple[str, str]], Mapping[str, Any]] = {}
    wire_endpoint_spans: dict[
        tuple[tuple[str, str], tuple[str, str]],
        tuple[Mapping[str, Any], Mapping[str, Any]],
    ] = {}
    refinements: list[dict[str, str]] = []
    refine_facts: dict[
        tuple[str, str], tuple[str, Mapping[str, Any], Mapping[str, Any]]
    ] = {}
    shares: list[dict[str, list[dict[str, str]]]] = []
    share_spans: dict[str, Mapping[str, Any]] = {}
    final: list[list[dict[str, str]]] = []
    final_markings: set[frozenset[tuple[str, str]]] = set()
    final_spans: dict[str, Mapping[str, Any]] = {}

    for raw_contribution in contribution_items:
        contribution = cast(dict[str, Any], raw_contribution)
        kind = contribution["kind"]
        target = contribution["target"]
        value = contribution["value"]
        span = contribution["span"]
        identity = _contribution_identity(contribution["id"])
        if (
            not isinstance(target, Mapping)
            or not isinstance(value, Mapping)
            or not isinstance(span, Mapping)
            or identity is None
            or identity[2] != 0
        ):
            raise _resolution_error(
                "PN200",
                "invalid composition contribution",
                cast(Mapping[str, Any], span) if isinstance(span, Mapping) else None,
            )
        target = cast(dict[str, Any], target)
        value = cast(dict[str, Any], value)
        span = cast(dict[str, Any], span)
        if not aggregate_sources and identity[1] != contribution["ordinal"]:
            raise _resolution_error(
                "PN200", "invalid composition statement order", span
            )
        if header is None and kind != "document.composition-header":
            raise _resolution_error("PN200", "composition header must be first", span)
        if target != {"type": "document"}:
            raise _resolution_error("PN200", "invalid composition target", span)

        if kind == "document.composition-header":
            namespace = value.get("namespace")
            if (
                (
                    header is not None
                    and (not aggregate_sources or namespace != header[0])
                )
                or set(value) != {"namespace"}
                or not isinstance(namespace, str)
                or not namespace
                or contains_isolated_surrogate(namespace)
            ):
                raise _resolution_error(
                    "PN200", "invalid composition header contribution", span
                )
            if header is None:
                header = (namespace, span)
        elif kind == "composition.use":
            ref, alias = value.get("ref"), value.get("alias")
            if (
                set(value) != {"ref", "alias"}
                or not isinstance(ref, str)
                or not ref
                or not isinstance(alias, str)
                or not alias
                or _TIMER_BIND_IDENTIFIER.fullmatch(alias) is None
                or contains_isolated_surrogate(ref)
            ):
                raise _resolution_error("PN200", "invalid composition use", span)
            existing = uses.get(alias)
            if existing is not None:
                first_ref, first_span = existing
                if first_ref != ref:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting use facts for alias {alias}",
                        span,
                        "use each alias for exactly one referenced net",
                        (
                            (
                                f"first use of alias {alias} was declared here",
                                first_span,
                            ),
                        ),
                    )
                continue
            uses[alias] = (ref, span)
            ordered_uses.append({"ref": ref, "alias": alias})
        elif kind == "composition.wire":
            raw_from, raw_to = value.get("from"), value.get("to")
            if (
                set(value) != {"from", "to"}
                or not isinstance(raw_from, Mapping)
                or not isinstance(raw_to, Mapping)
            ):
                raise _resolution_error("PN200", "invalid composition wire", span)
            typed_from = cast(Mapping[str, Any], raw_from)
            typed_to = cast(Mapping[str, Any], raw_to)
            endpoint_values: list[tuple[str, str]] = []
            endpoint_spans: list[Mapping[str, Any]] = []
            for endpoint in (typed_from, typed_to):
                alias, place, endpoint_span = (
                    endpoint.get("alias"),
                    endpoint.get("place"),
                    endpoint.get("span"),
                )
                if (
                    set(endpoint) != {"alias", "place", "span"}
                    or not isinstance(alias, str)
                    or not alias
                    or not isinstance(place, str)
                    or not place
                    or not _is_source_span(endpoint_span, identity[0])
                ):
                    raise _resolution_error("PN200", "invalid composition wire", span)
                typed_endpoint_span = cast(Mapping[str, Any], endpoint_span)
                if alias not in uses:
                    raise _resolution_error(
                        "PN202",
                        f"wire references unknown alias {alias}",
                        typed_endpoint_span,
                        "declare the alias with use before wiring it",
                    )
                endpoint_values.append((alias, place))
                endpoint_spans.append(typed_endpoint_span)
            source, destination = endpoint_values
            key = (source, destination)
            if key in wire_spans:
                continue
            reverse = (destination, source)
            if reverse in wire_spans:
                raise _resolution_error(
                    "PN202",
                    "conflicting wire facts reverse the same endpoints",
                    span,
                    "remove the reversed wire; wires run output to input",
                    (
                        (
                            "first wire between these endpoints was declared here",
                            wire_spans[reverse],
                        ),
                    ),
                )
            wire_spans[key] = span
            wire_endpoint_spans[key] = (endpoint_spans[0], endpoint_spans[1])
            wires.append(
                {
                    "from": {"net": source[0], "port": source[1]},
                    "to": {"net": destination[0], "port": destination[1]},
                }
            )
        elif kind == "composition.share":
            raw_places = value.get("places")
            if (
                set(value) != {"places"}
                or not isinstance(raw_places, list)
                or len(cast(list[Any], raw_places)) < 2
            ):
                raise _resolution_error("PN200", "invalid composition share", span)
            members: list[tuple[str, str]] = []
            for raw_member in cast(list[Any], raw_places):
                if not isinstance(raw_member, Mapping):
                    raise _resolution_error("PN200", "invalid composition share", span)
                member = cast(Mapping[str, Any], raw_member)
                alias, place = member.get("alias"), member.get("place")
                member_span = member.get("span")
                if (
                    set(member) != {"alias", "place", "span"}
                    or not isinstance(alias, str)
                    or not alias
                    or not isinstance(place, str)
                    or not place
                    or not _is_source_span(member_span, identity[0])
                ):
                    raise _resolution_error("PN200", "invalid composition share", span)
                if alias not in uses:
                    raise _resolution_error(
                        "PN202",
                        f"share references unknown alias {alias}",
                        cast(Mapping[str, Any], member_span),
                        "declare the alias with use before sharing its place",
                    )
                members.append((alias, place))
            label = "share " + " ~ ".join(
                f"{alias}.({place})" for alias, place in members
            )
            if label in share_spans:
                continue
            share_spans[label] = span
            shares.append(
                {"places": [{"net": alias, "place": place} for alias, place in members]}
            )
        elif kind == "composition.refine":
            raw_transition, raw_by = value.get("transition"), value.get("by")
            if (
                set(value) != {"transition", "by"}
                or not isinstance(raw_transition, Mapping)
                or not isinstance(raw_by, Mapping)
            ):
                raise _resolution_error("PN200", "invalid composition refine", span)
            refined = cast(Mapping[str, Any], raw_transition)
            refining = cast(Mapping[str, Any], raw_by)
            alias, name = refined.get("alias"), refined.get("name")
            by, transition_span = refining.get("alias"), refined.get("span")
            by_span = refining.get("span")
            if (
                set(refined) != {"alias", "name", "span"}
                or set(refining) != {"alias", "span"}
                or not isinstance(alias, str)
                or not alias
                or not isinstance(name, str)
                or not name
                or not isinstance(by, str)
                or not by
                or not _is_source_span(transition_span, identity[0])
                or not _is_source_span(by_span, identity[0])
            ):
                raise _resolution_error("PN200", "invalid composition refine", span)
            typed_transition_span = cast(Mapping[str, Any], transition_span)
            typed_by_span = cast(Mapping[str, Any], by_span)
            for refine_alias, alias_span in (
                (alias, typed_transition_span),
                (by, typed_by_span),
            ):
                if refine_alias not in uses:
                    raise _resolution_error(
                        "PN202",
                        f"refine references unknown alias {refine_alias}",
                        alias_span,
                        "declare the alias with use before refining with it",
                    )
            if by == alias:
                raise _resolution_error(
                    "PN202",
                    f"refine {alias}.[{name}] by {by}: a net cannot refine its "
                    "own transition",
                    typed_by_span,
                    "refine with the alias of another net",
                )
            existing_refine = refine_facts.get((alias, name))
            if existing_refine is not None:
                if existing_refine[0] == by:
                    continue
                raise _resolution_error(
                    "PN202",
                    f"conflicting refine facts for {alias}.[{name}]",
                    span,
                    "refine each transition by exactly one net",
                    (
                        (
                            f"first refine of {alias}.[{name}] was declared here",
                            existing_refine[1],
                        ),
                    ),
                )
            refine_facts[(alias, name)] = (by, span, typed_transition_span)
            refinements.append({"net": alias, "transition": name, "by": by})
        elif kind == "composition.final":
            raw_markings = value.get("markings")
            if (
                set(value) != {"markings"}
                or not isinstance(raw_markings, list)
                or not raw_markings
            ):
                raise _resolution_error("PN200", "invalid composition final", span)
            for raw_marking in cast(list[Any], raw_markings):
                if not isinstance(raw_marking, list) or not raw_marking:
                    raise _resolution_error("PN200", "invalid composition final", span)
                marking_members: list[tuple[str, str]] = []
                for raw_member in cast(list[Any], raw_marking):
                    if not isinstance(raw_member, Mapping):
                        raise _resolution_error(
                            "PN200", "invalid composition final", span
                        )
                    member = cast(Mapping[str, Any], raw_member)
                    alias, place = member.get("alias"), member.get("place")
                    member_span = member.get("span")
                    if (
                        set(member) != {"alias", "place", "span"}
                        or not isinstance(alias, str)
                        or not alias
                        or not isinstance(place, str)
                        or not place
                        or not _is_source_span(member_span, identity[0])
                    ):
                        raise _resolution_error(
                            "PN200", "invalid composition final", span
                        )
                    if alias not in uses:
                        raise _resolution_error(
                            "PN202",
                            f"final references unknown alias {alias}",
                            cast(Mapping[str, Any], member_span),
                            "declare the alias with use before naming its place",
                        )
                    marking_members.append((alias, place))
                label = "final " + " + ".join(
                    f"{alias}.({place})" for alias, place in marking_members
                )
                if len(set(marking_members)) != len(marking_members):
                    raise _resolution_error(
                        "PN202",
                        f"{label}: names a place more than once",
                        span,
                        "name each place of a final marking once",
                    )
                if frozenset(marking_members) in final_markings:
                    continue
                final_markings.add(frozenset(marking_members))
                final_spans[label] = span
                final.append(
                    [{"net": alias, "place": place} for alias, place in marking_members]
                )
        else:
            raise _resolution_error(
                "PN200", f"unsupported contribution kind {kind!r}", span
            )

    if header is None:
        raise _resolution_error("PN200", "missing composition header")
    if not ordered_uses:
        raise _resolution_error(
            "PN202",
            "composition requires at least one use fact",
            header[1],
            'add `use "path" as alias` after the composition header',
        )
    result: dict[str, Any] = {
        "name": header[0],
        "nets": ordered_uses,
        "wires": wires,
    }
    if shares:
        result["shares"] = shares
    if refinements:
        result["refinements"] = refinements
    if final:
        result["final"] = final
    if net_loader is None and origin is None:
        return result
    try:
        parse_composition(result, net_loader=net_loader, origin=origin)
    except NetValidationError as error:
        message = str(error)
        default_span = header[1]

        def same(written: tuple[str, str], alias: str, name: str) -> bool:
            # A path into a nested composition is reported under the
            # flattened alias: (lifecycle, gate.x) is (lifecycle.gate, x).
            return f"{written[0]}.{written[1]}" == f"{alias}.{name}"

        missing_port = re.fullmatch(
            r"net '([^']+)' has no port named '([^']+)'", message
        )
        if missing_port is not None:
            alias, port = missing_port.groups()
            wire_span, (alias, port) = next(
                (
                    (endpoint_spans[index], endpoints[index])
                    for endpoints, endpoint_spans in wire_endpoint_spans.items()
                    for index in range(2)
                    if same(endpoints[index], alias, port)
                ),
                (default_span, (alias, port)),
            )
            raise _resolution_error(
                "PN202",
                f"wire references unknown port {alias}.({port})",
                wire_span,
                "wire only declared port places",
            ) from None
        bad_direction = re.fullmatch(
            r"wire (source|target) port '([^']+)'\.'([^']+)' "
            r"is not an (output|input) port",
            message,
        )
        if bad_direction is not None:
            role, alias, port, direction = bad_direction.groups()
            endpoint_index = 0 if role == "source" else 1
            wire_span, (alias, port) = next(
                (
                    (endpoint_spans[endpoint_index], endpoints[endpoint_index])
                    for endpoints, endpoint_spans in wire_endpoint_spans.items()
                    if same(endpoints[endpoint_index], alias, port)
                ),
                (default_span, (alias, port)),
            )
            help_text = (
                "reverse the wire so it runs from output to input"
                if role == "source"
                else "wire into an input port"
            )
            message = (
                f"wire source endpoint {alias}.({port}) is an input port; "
                "a wire must run from an output port to an input port"
                if role == "source"
                else f"wire {role} {alias}.({port}) must be an {direction} port"
            )
            raise _resolution_error(
                "PN202",
                message,
                wire_span,
                help_text,
            ) from None
        type_mismatch = re.fullmatch(
            r"wire type mismatch: '([^']+)'\.'([^']+)' type '([^']+)' "
            r"!= '([^']+)'\.'([^']+)' type '([^']+)'",
            message,
        )
        if type_mismatch is not None:
            from_alias, from_port, from_type, to_alias, to_port, to_type = (
                type_mismatch.groups()
            )
            wire_span, ((from_alias, from_port), (to_alias, to_port)) = next(
                (
                    (endpoint_spans[1], endpoints)
                    for endpoints, endpoint_spans in wire_endpoint_spans.items()
                    if same(endpoints[0], from_alias, from_port)
                    and same(endpoints[1], to_alias, to_port)
                ),
                (default_span, ((from_alias, from_port), (to_alias, to_port))),
            )
            raise _resolution_error(
                "PN202",
                f"wire port colors differ: {from_alias}.({from_port}) carries "
                f"{from_type!r} but {to_alias}.({to_port}) carries {to_type!r}",
                wire_span,
                "connect ports that declare the same color",
            ) from None
        share_failure = re.match(r"(share .*?): ", message)
        if share_failure is not None and share_failure[1] in share_spans:
            raise _resolution_error(
                "PN202",
                message,
                share_spans[share_failure[1]],
                "share places that exist and accept the same colors",
            ) from None
        final_failure = re.match(r"(final .*?): ", message)
        if final_failure is not None and final_failure[1] in final_spans:
            raise _resolution_error(
                "PN202",
                message,
                final_spans[final_failure[1]],
                "name places that the composed nets declare",
            ) from None
        refine_failure = re.match(
            r"refine ([A-Za-z_][A-Za-z0-9_.]*)\.\[(.*?)\] by [A-Za-z_][A-Za-z0-9_]*: ",
            message,
        )
        if refine_failure is not None:
            fact = next(
                (
                    fact
                    for written, fact in refine_facts.items()
                    if same(written, refine_failure[1], refine_failure[2])
                ),
                None,
            )
            reason = message[refine_failure.end() :]
            help_text = next(
                (help_text for phrase, help_text in _REFINE_HELP if phrase in reason),
                None,
            )
            raise _resolution_error(
                "PN202",
                message,
                fact[2] if fact is not None else default_span,
                help_text,
            ) from None
        raise _resolution_error(
            "PN500", f"composition reference loading failed: {message}", header[1]
        ) from None
    return result


_REFINE_HELP: Final[tuple[tuple[str, str], ...]] = (
    ("has no transition", "refine a transition the net declares"),
    (
        "may only consume, read and produce",
        "refine a transition without inhibit arcs or a timer",
    ),
    ("is not wired", "wire the place to a port of the refining net"),
    ("wired to it carry", "wire the place to a port that carries the arc's color"),
    ("is a composition", "refine by the alias of a net, not of a composition"),
)


def resolve_contribution_ir(
    ir: Any,
    *,
    source_ids: Sequence[str] | None = None,
    net_loader: Callable[[str], Mapping[str, Any] | Path | str] | None = None,
    origin: Path | None = None,
    validate_ir: bool = True,
) -> dict[str, Any]:
    """Strictly decode v1 Contributions into canonical core JSON.

    Shape-only loading of the same document lives in ``velocitron_ir``
    (``packages/ir/python``). That package validates the wire schema and
    leaves CEL source as text. This function remains the resolver: it
    compiles CEL and, for a composition, loads referenced nets.

    ``validate_ir=False`` skips the pre-resolution Contribution IR schema
    check (the ~90% of compile time on large nets; a consumer that already
    trusts its sources, such as a primer app recompiling known text, opts
    out). Resolution's own structural checks still run: an IR the schema
    would have rejected fails loudly later, at the same ``PN200``-shaped
    resolution errors or at net validation — the check is an early,
    better-located diagnostic, not a gate.
    """
    if not isinstance(ir, Mapping):
        raise _resolution_error("PN200", "invalid Contribution IR document shape")
    document_ir = cast(Mapping[str, Any], ir)
    if validate_ir:
        schema_errors = list(_IR_VALIDATOR.iter_errors(document_ir))  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if schema_errors and not _only_legacy_document_metadata_failed_schema(
            document_ir, schema_errors
        ):
            _reject_schema_invalid_ir(document_ir, schema_errors)
    document_id = document_ir["document"]["id"]
    if source_ids is None:
        allowed_source_ids = frozenset((document_id,))
    elif (
        not source_ids
        or source_ids[0] != document_id
        or len(set(source_ids)) != len(source_ids)
        or any(
            _RELATIVE_SOURCE_ID.fullmatch(source_id) is None for source_id in source_ids
        )
    ):
        raise _resolution_error("PN200", "invalid aggregate source identities")
    else:
        allowed_source_ids = frozenset(source_ids)
    document_kind = document_ir["documentKind"]
    contribution_items = cast(list[Any], document_ir["contributions"])
    ids: set[tuple[str, int, int]] = set()
    for ordinal, raw_contribution in enumerate(contribution_items):
        contribution = cast(dict[str, Any], raw_contribution)
        ordinal_value = contribution["ordinal"]
        if (
            not isinstance(ordinal_value, int)
            or isinstance(ordinal_value, bool)
            or ordinal_value != ordinal
        ):
            raise _resolution_error(
                "PN200", "contribution ordinals must be contiguous zero-based integers"
            )
        unique_id = _contribution_identity(contribution["id"])
        if unique_id is None:
            raise _resolution_error("PN200", "invalid contribution identity")
        if unique_id[0] not in allowed_source_ids:
            message = (
                "contribution identity source must match document id"
                if source_ids is None
                else "contribution identity source is not in document sources"
            )
            raise _resolution_error("PN200", message)
        if not _is_source_span(contribution["span"], unique_id[0]):
            raise _resolution_error("PN200", "invalid contribution span")
        if unique_id in ids:
            raise _resolution_error("PN200", "duplicate contribution identity")
        ids.add(unique_id)
    if document_kind == "composition":
        return _resolve_composition_contributions(
            contribution_items,
            aggregate_sources=source_ids is not None,
            net_loader=net_loader,
            origin=origin,
        )

    header: Mapping[str, Any] | None = None
    places: list[str] = []
    accepts: dict[str, list[str]] = {}
    declared_accepts: dict[str, tuple[list[str], Mapping[str, Any]]] = {}
    place_appearances: list[str] = []
    declared_places: set[str] = set()
    transitions: list[str] = []
    ports: dict[str, tuple[dict[str, str], Mapping[str, Any]]] = {}
    handlers: dict[str, tuple[str, Mapping[str, Any]]] = {}
    guards: dict[str, tuple[str, Mapping[str, Any]]] = {}
    transition_spans: dict[str, Mapping[str, Any]] = {}
    arcs: list[dict[str, Any]] = []
    arc_declarations: list[dict[str, Any]] = []
    arc_indexes: dict[tuple[str, int, int], int] = {}
    arc_objects: dict[tuple[str, int, int], dict[str, Any]] = {}
    arc_handles: dict[str, list[tuple[str, int, int]]] = {}
    arc_handle_spans: dict[str, Mapping[str, Any]] = {}
    arc_handle_ids: dict[str, tuple[str, int, int]] = {}
    claimed_handle_arc_ids: set[tuple[str, int, int]] = set()
    arc_data: dict[str, tuple[Any, Mapping[str, Any]]] = {}
    arc_cels: dict[str, tuple[str, Mapping[str, Any]]] = {}
    arc_predicates: dict[str, tuple[dict[str, str], Mapping[str, Any]]] = {}
    arc_correlates: dict[str, tuple[str, Mapping[str, Any]]] = {}
    capacities: dict[str, tuple[dict[str, Any], Mapping[str, Any]]] = {}
    timers: dict[str, tuple[str, str, Mapping[str, Any]]] = {}
    timer_binds: dict[str, dict[str, tuple[str, Mapping[str, Any]]]] = {}
    timer_maturities: dict[str, tuple[str, Mapping[str, Any]]] = {}
    binding_names: dict[str, dict[str, tuple[str, Mapping[str, Any]]]] = {}
    priorities: dict[str, tuple[int, Mapping[str, Any]]] = {}
    arc_weights: dict[str, tuple[int, Mapping[str, Any]]] = {}
    transition_orders: dict[str, int] = {}
    transition_order_ranks: dict[int, tuple[str, Mapping[str, Any]]] = {}
    handle_orders: dict[str, int] = {}
    templates: dict[str, Any] = {}
    template_spans: dict[str, Mapping[str, Any]] = {}
    markings: list[tuple[str, dict[str, Any], int, Mapping[str, Any]]] = []
    descriptions: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
    annotations: dict[tuple[str, str], dict[str, tuple[Any, Mapping[str, Any]]]] = {}
    named_markings: dict[
        str, list[tuple[str, dict[str, Any], int, Mapping[str, Any]]]
    ] = {}
    positions: dict[tuple[str, str], dict[str, tuple[Any, ...]]] = {}
    relative_bases: list[tuple[str, str, str, str, Mapping[str, Any]]] = []
    routes: dict[tuple[str, str], tuple[list[dict[str, Any]], Mapping[str, Any]]] = {}
    view_styles: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
    decorations: dict[str, dict[str, tuple[Any, Mapping[str, Any]]]] = {}
    extensions: tuple[dict[str, Any], Mapping[str, Any]] | None = None
    domains: dict[str, tuple[list[Any], Mapping[str, Any]]] = {}
    final_markings: dict[frozenset[str], tuple[tuple[str, ...], Mapping[str, Any]]] = {}
    invariants: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
    actors: dict[str, tuple[str, Mapping[str, Any]]] = {}

    for raw_contribution in contribution_items:
        contribution = cast(dict[str, Any], raw_contribution)
        kind = contribution["kind"]
        target = contribution["target"]
        value = contribution["value"]
        span = contribution["span"]
        if (
            not isinstance(target, Mapping)
            or not isinstance(value, Mapping)
            or not isinstance(span, Mapping)
        ):
            raise _resolution_error("PN200", "invalid Contribution IR member")
        target = cast(dict[str, Any], target)
        value = cast(dict[str, Any], value)
        span = cast(dict[str, Any], span)
        if kind == "document.net-header":
            if (
                (
                    header is not None
                    and (source_ids is None or value.get("name") != header.get("name"))
                )
                or target != {"type": "document"}
                or set(value) - {"name", "description"}
                or not isinstance(value.get("name"), str)
            ):
                raise _resolution_error(
                    "PN200", "invalid net header contribution", span
                )
            if header is None:
                header = value
        elif kind == "place.declare":
            name = target.get("name")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "place"
                or not isinstance(name, str)
                or not name
                or value
            ):
                raise _resolution_error(
                    "PN200", "invalid place declaration contribution", span
                )
            declared_places.add(name)
            if name not in place_appearances:
                place_appearances.append(name)
        elif kind == "transition.declare":
            name = target.get("name")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or value
            ):
                raise _resolution_error(
                    "PN200", "invalid transition declaration contribution", span
                )
            if name not in transitions:
                transitions.append(name)
                transition_spans[name] = span
        elif kind == "place.accepts":
            name, raw_colors = target.get("name"), value.get("colors")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "place"
                or not isinstance(name, str)
                or not name
                or set(value) != {"colors"}
                or not isinstance(raw_colors, list)
                or not raw_colors
                or any(
                    not isinstance(color, str) or not color
                    for color in cast(list[object], raw_colors)
                )
                or len(cast(list[object], raw_colors))
                != len(set(cast(list[object], raw_colors)))
            ):
                raise _resolution_error(
                    "PN200", "invalid place accepted-colors contribution", span
                )
            colors = cast(list[str], raw_colors)
            if name not in place_appearances:
                place_appearances.append(name)
            existing = declared_accepts.get(name)
            if existing is not None:
                first_colors, first_span = existing
                if first_colors != colors:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting accepted-color facts for place ({name})",
                        span,
                        "remove one declaration or make both accepted-color lists identical",
                        (("first accepted-color declaration was here", first_span),),
                    )
                continue
            declared_accepts[name] = (colors, span)
        elif kind == "place.port":
            name, direction, color = (
                target.get("name"),
                value.get("direction"),
                value.get("color"),
            )
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "place"
                or not isinstance(name, str)
                or not name
                or set(value) != {"direction", "color"}
                or direction not in {"input", "output"}
                or not isinstance(color, str)
                or not color
            ):
                raise _resolution_error(
                    "PN200", "invalid place port contribution", span
                )
            port = {"direction": cast(str, direction), "type": color}
            existing = ports.get(name)
            if existing is not None:
                first_port, first_span = existing
                if first_port != port:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting port facts for place ({name})",
                        span,
                        "remove one declaration or make both port values identical",
                        (("first port was declared here", first_span),),
                    )
                continue
            ports[name] = (port, span)
        elif kind == "arc.handle":
            name = target.get("name")
            raw_arc_ids = value.get("arcIds")
            contribution_id = _contribution_identity(contribution["id"])
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or set(value) != {"arcIds"}
                or not isinstance(raw_arc_ids, list)
                or len(cast(list[Any], raw_arc_ids)) < 1
                or contribution_id is None
                or contribution_id[2] != 0
            ):
                raise _resolution_error(
                    "PN200", "invalid arc handle contribution", span
                )
            resolved_ids: list[tuple[str, int, int]] = []
            for raw_arc_id in cast(list[Any], raw_arc_ids):
                arc_id = _arc_identity(raw_arc_id)
                if (
                    arc_id is None
                    or arc_id[0] != contribution_id[0]
                    or arc_id in claimed_handle_arc_ids
                ):
                    raise _resolution_error(
                        "PN200", "invalid arc handle contribution", span
                    )
                resolved_ids.append(arc_id)
            claimed_handle_arc_ids.update(resolved_ids)
            if name in arc_handles:
                if arc_handles[name] != resolved_ids:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting declarations for arc handle @{name}",
                        span,
                        related=(
                            ("first declaration was here", arc_handle_spans[name]),
                        ),
                    )
                continue
            arc_handles[name] = resolved_ids
            arc_handle_ids[name] = contribution_id
            arc_handle_spans[name] = span
        elif kind == "order.transition":
            name, rank = target.get("name"), value.get("rank")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not isinstance(rank, int)
                or rank < 1
                or name in transition_orders
            ):
                raise _resolution_error(
                    "PN200", "invalid transition order contribution", span
                )
            if rank in transition_order_ranks:
                first_name, first_span = transition_order_ranks[rank]
                raise _resolution_error(
                    "PN202",
                    f"transition order position {rank} is assigned more than once",
                    span,
                    "assign each explicitly ordered transition a unique positive position",
                    ((f"[{first_name}] first assigned position {rank}", first_span),),
                )
            transition_orders[name] = rank
            transition_order_ranks[rank] = (name, span)
        elif kind == "order.arc-run":
            name, rank = target.get("name"), value.get("rank")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or not isinstance(rank, int)
                or rank < 1
                or name in handle_orders
            ):
                raise _resolution_error(
                    "PN200", "invalid arc-run order contribution", span
                )
            handle_orders[name] = rank
        elif kind == "place.capacity-per-color-key":
            name = target.get("name")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "place"
                or not isinstance(name, str)
            ):
                raise _resolution_error(
                    "PN200", "invalid place capacity contribution", span
                )
            if set(value) != {"key", "max"}:
                raise _resolution_error(
                    "PN202",
                    f"capacityPerColorKey for ({name}) must contain exactly key and max",
                    span,
                )
            key, maximum = value["key"], value["max"]
            valid_key = valid_capacity_key(key)
            if not valid_key:
                raise _resolution_error(
                    "PN202",
                    f"capacityPerColorKey key must be a non-empty string or non-empty array of non-empty strings for ({name})",
                    span,
                )
            if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
                raise _resolution_error(
                    "PN202",
                    "capacityPerColorKey max must be an integer greater than or "
                    f"equal to 1; got {maximum!r} for ({name})",
                    span,
                )
            capacity: dict[str, Any] = {"key": key, "max": maximum}
            if name in capacities:
                first, first_span = capacities[name]
                if first != capacity:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting capacityPerColorKey facts for ({name})",
                        span,
                        related=(("first declaration was here", first_span),),
                    )
                continue
            capacities[name] = (capacity, span)
        elif kind == "arc.weight":
            name, weight = target.get("name"), value.get("weight")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or set(value) != {"weight"}
            ):
                raise _resolution_error(
                    "PN200", "invalid arc weight contribution", span
                )
            if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
                raise _resolution_error(
                    "PN202",
                    "arc weight must be an integer greater than or equal to 1; "
                    f"got {weight!r} for @{name}",
                    span,
                )
            if name in arc_weights:
                first, first_span = arc_weights[name]
                if first != weight:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting weight facts for arc @{name}",
                        span,
                        related=(("first declaration was here", first_span),),
                    )
                continue
            arc_weights[name] = (weight, span)
        elif kind == "arc.produce-data":
            name, raw_data = target.get("name"), value.get("data")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or set(value) != {"data"}
                or not isinstance(raw_data, Mapping)
            ):
                raise _resolution_error(
                    "PN200", "invalid arc produce-data contribution", span
                )
            try:
                data = untag_json_value(cast(Mapping[str, Any], raw_data))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise _resolution_error(
                    "PN200", "invalid tagged JSON arc data value", span
                ) from error
            if name in arc_data:
                first_data, first_span = arc_data[name]
                if not json_values_equal(first_data, data):
                    rendered = json.dumps(
                        first_data,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    raise _resolution_error(
                        "PN202",
                        f"conflicting data facts for arc @{name}",
                        span,
                        "remove one declaration or make both arc data values identical",
                        related=(
                            (f"first value {rendered} was declared here", first_span),
                        ),
                    )
                continue
            arc_data[name] = (data, span)
        elif kind == "arc.produce-cel":
            name, cel = target.get("name"), value.get("cel")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or set(value) != {"cel"}
                or not isinstance(cel, str)
                or not cel
            ):
                raise _resolution_error(
                    "PN200", "invalid arc produce-cel contribution", span
                )
            if name in arc_cels:
                first_cel, first_span = arc_cels[name]
                if first_cel != cel:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting data cel facts for arc @{name}",
                        span,
                        related=(("first declaration was here", first_span),),
                    )
                continue
            arc_cels[name] = (cel, span)
        elif kind == "arc.predicate":
            name = target.get("name")
            predicate_kind = value.get("kind")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or not isinstance(predicate_kind, str)
                or predicate_kind not in {"cel", "handler"}
                or set(value) != {"kind", predicate_kind}
                or not isinstance(value.get(predicate_kind), str)
                or not value[predicate_kind]
            ):
                raise _resolution_error(
                    "PN200", "invalid arc predicate contribution", span
                )
            predicate = {predicate_kind: cast(str, value[predicate_kind])}
            if name in arc_predicates:
                first_predicate, first_span = arc_predicates[name]
                if first_predicate != predicate:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting predicate facts for arc @{name}",
                        span,
                        "remove one declaration or make both predicate values identical",
                        (("first predicate was declared here", first_span),),
                    )
                continue
            arc_predicates[name] = (predicate, span)
        elif kind == "arc.correlate":
            name, cel = target.get("name"), value.get("cel")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(name, str)
                or set(value) != {"cel"}
                or not isinstance(cel, str)
                or not cel
            ):
                raise _resolution_error(
                    "PN200", "invalid arc correlate contribution", span
                )
            if name in arc_correlates:
                first_cel, first_span = arc_correlates[name]
                if first_cel != cel:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting correlate facts for arc @{name}",
                        span,
                        "remove one declaration or make both CEL expressions identical",
                        (("first correlate was declared here", first_span),),
                    )
                continue
            arc_correlates[name] = (cel, span)
        elif kind == "arc.declare":
            raw_color = value.get("color")
            raw_source = value.get("from")
            raw_destination = value.get("to")
            mode = value.get("mode")
            arc_id = _arc_identity(target.get("id"))
            contribution_id = _contribution_identity(contribution["id"])
            if (
                set(target) != {"type", "id"}
                or target.get("type") != "arc"
                or arc_id is None
                or contribution_id is None
                or arc_id != contribution_id
                or not isinstance(raw_color, Mapping)
                or not isinstance(raw_source, Mapping)
                or not isinstance(raw_destination, Mapping)
                or mode not in {"consume", "read", "inhibit", "produce"}
            ):
                raise _resolution_error("PN200", "invalid arc declaration", span)
            color = cast(dict[str, Any], raw_color)
            source = cast(dict[str, Any], raw_source)
            destination = cast(dict[str, Any], raw_destination)
            if not (
                set(color) == {"kind", "value"}
                and color.get("kind") == "explicit"
                and isinstance(color.get("value"), str)
                and color.get("value")
            ):
                raise _resolution_error("PN200", "invalid arc declaration", span)
            is_input: bool = (
                source.get("type") == "place"
                and destination.get("type") == "transition"
                and mode in {"consume", "read", "inhibit"}
            )
            if is_input:
                expected_keys = {"from", "to", "color", "mode"}
                if mode == "consume":
                    expected_keys.add("transitionNameSpan")
                if set(value) != expected_keys:
                    raise _resolution_error(
                        "PN200", "invalid consumed arc declaration", span
                    )
                place, transition = source.get("name"), destination.get("name")
                transition_name_span = value.get("transitionNameSpan", span)
                if mode == "consume" and not _is_source_span(
                    transition_name_span, contribution_id[0]
                ):
                    raise _resolution_error(
                        "PN200", "consumed arc has invalid transitionNameSpan", span
                    )
            elif (
                source.get("type") == "transition"
                and destination.get("type") == "place"
                and mode == "produce"
            ):
                if set(value) != {"from", "to", "color", "mode"}:
                    raise _resolution_error(
                        "PN200", "invalid produced arc declaration", span
                    )
                place, transition = destination.get("name"), source.get("name")
                transition_name_span = span
            else:
                raise _resolution_error(
                    "PN200", "invalid Coin Deposit arc direction", span
                )
            if not isinstance(place, str) or not isinstance(transition, str):
                raise _resolution_error(
                    "PN200", "arc endpoint names must be strings", span
                )
            if place not in place_appearances:
                place_appearances.append(place)
            if transition not in transitions:
                transitions.append(transition)
                transition_spans[transition] = transition_name_span
            arc_declarations.append(
                {
                    "id": arc_id,
                    "place": place,
                    "transition": transition,
                    "isInput": is_input,
                    "mode": mode,
                    "color": color,
                    "span": span,
                    "transitionNameSpan": transition_name_span,
                }
            )
        elif kind == "transition.timer":
            name = target.get("name")
            raw_clock = value.get("clock")
            if not isinstance(raw_clock, Mapping):
                raise _resolution_error(
                    "PN200", "invalid transition timer contribution", span
                )
            clock = cast(Mapping[str, Any], raw_clock)
            cel = value.get("cel")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"clock", "cel"}
                or set(clock) != {"type", "name"}
                or clock.get("type") != "place"
                or not isinstance(clock.get("name"), str)
                or not clock.get("name")
                or not isinstance(cel, str)
                or not cel
            ):
                raise _resolution_error(
                    "PN200", "invalid transition timer contribution", span
                )
            timer_fact = (cast(str, clock["name"]), cel)
            if name in timers:
                first_clock, first_cel, first_span = timers[name]
                if timer_fact[0] != first_clock:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting timer clock facts for transition [{name}]",
                        span,
                        "remove one declaration or make both timer clock values identical",
                        (("first timer clock was declared here", first_span),),
                    )
                if timer_fact[1] != first_cel:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting timer CEL facts for transition [{name}]",
                        span,
                        "remove one declaration or make both timer CEL values identical",
                        (("first timer CEL was declared here", first_span),),
                    )
                continue
            timers[name] = (*timer_fact, span)
        elif kind == "transition.timer-maturity":
            name = target.get("name")
            maturity = value.get("maturity")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"maturity"}
                or not isinstance(maturity, str)
                or not maturity
            ):
                raise _resolution_error(
                    "PN200", "invalid transition timer maturity contribution", span
                )
            existing = timer_maturities.get(name)
            if existing is not None and maturity != existing[0]:
                raise _resolution_error(
                    "PN202",
                    f"conflicting timer maturity CEL facts for transition [{name}]",
                    span,
                    "remove one declaration or make both timer maturity CEL values identical",
                    (("first timer maturity CEL was declared here", existing[1]),),
                )
            timer_maturities.setdefault(name, (maturity, span))
        elif kind == "transition.timer-bind":
            name = target.get("name")
            bind_name = value.get("name")
            raw_place = value.get("place")
            if not isinstance(raw_place, Mapping):
                raise _resolution_error(
                    "PN200", "invalid transition timer bind contribution", span
                )
            place = cast(Mapping[str, Any], raw_place)
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"name", "place"}
                or not isinstance(bind_name, str)
                or _TIMER_BIND_IDENTIFIER.fullmatch(bind_name) is None
                or set(place) != {"type", "name"}
                or place.get("type") != "place"
                or not isinstance(place.get("name"), str)
                or not place.get("name")
            ):
                raise _resolution_error(
                    "PN200", "invalid transition timer bind contribution", span
                )
            binds = timer_binds.setdefault(name, {})
            place_name = cast(str, place["name"])
            if bind_name in binds:
                first_place, first_span = binds[bind_name]
                if place_name != first_place:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting timer bind facts for {bind_name!r} "
                        f"on transition [{name}]",
                        span,
                        "remove one declaration or make both timer bind values identical",
                        (("first timer bind was declared here", first_span),),
                    )
                continue
            binds[bind_name] = (place_name, span)
        elif kind == "transition.binding-name":
            name = target.get("name")
            key = value.get("name")
            raw_place = value.get("place")
            if not isinstance(raw_place, Mapping):
                raise _resolution_error(
                    "PN200", "invalid transition binding name contribution", span
                )
            place = cast(Mapping[str, Any], raw_place)
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"name", "place"}
                or not isinstance(key, str)
                or not key
                or set(place) != {"type", "name"}
                or place.get("type") != "place"
                or not isinstance(place.get("name"), str)
                or not place.get("name")
            ):
                raise _resolution_error(
                    "PN200", "invalid transition binding name contribution", span
                )
            keys = binding_names.setdefault(name, {})
            place_name = cast(str, place["name"])
            if key in keys:
                first_place, first_span = keys[key]
                if place_name != first_place:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting binding name facts for {key!r} "
                        f"on transition [{name}]",
                        span,
                        "remove one declaration or make both binding name values identical",
                        (("first binding name was declared here", first_span),),
                    )
                continue
            keys[key] = (place_name, span)
        elif kind == "transition.priority":
            name = target.get("name")
            priority = value.get("priority")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"priority"}
                or not isinstance(priority, int)
                or isinstance(priority, bool)
                or priority < 0
            ):
                raise _resolution_error(
                    "PN200", "invalid transition priority contribution", span
                )
            if name in priorities:
                first_priority, first_span = priorities[name]
                if priority != first_priority:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting priority facts for transition [{name}]",
                        span,
                        "remove one declaration or make both priority values identical",
                        (("first priority was declared here", first_span),),
                    )
                continue
            priorities[name] = (priority, span)
        elif kind == "transition.handler":
            name, handler = target.get("name"), value.get("handler")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"handler"}
                or not isinstance(handler, str)
            ):
                raise _resolution_error(
                    "PN200", "invalid transition handler contribution", span
                )
            existing = handlers.get(name)
            if existing is not None:
                if existing[0] != handler:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting handler facts for transition [{name}]",
                        span,
                        "remove one declaration or make both handler values identical",
                        (("first handler was declared here", existing[1]),),
                    )
                continue
            handlers[name] = (handler, span)
        elif kind == "transition.guard":
            name, guard = target.get("name"), value.get("guard")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "transition"
                or not isinstance(name, str)
                or not name
                or set(value) != {"guard"}
                or not isinstance(guard, str)
                or not guard
            ):
                raise _resolution_error(
                    "PN200", "invalid transition guard contribution", span
                )
            if name in guards:
                first_guard, first_span = guards[name]
                if first_guard != guard:
                    raise _resolution_error(
                        "PN204",
                        f"conflicting guard facts for transition [{name}]",
                        span,
                        "remove one declaration or make both guard values identical",
                        (("first guard was declared here", first_span),),
                    )
                continue
            guards[name] = (guard, span)
        elif kind == "marking.append":
            place = target.get("name")
            count = value.get("count")
            message = "invalid initial marking contribution"
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "place"
                or not isinstance(place, str)
                or not place
                or set(value) != {"count", "token"}
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 1
            ):
                raise _resolution_error("PN200", message, span)
            token = _parse_marking_token(value.get("token"), message=message, span=span)
            markings.append((place, token, count, span))
        elif kind == "template.define":
            name, raw_tagged_value = target.get("name"), value.get("value")
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "template"
                or not isinstance(name, str)
                or not isinstance(raw_tagged_value, Mapping)
            ):
                raise _resolution_error(
                    "PN200", "invalid template definition contribution", span
                )
            tagged_value = cast(dict[str, Any], raw_tagged_value)
            try:
                resolved_template = untag_json_value(tagged_value)
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise _resolution_error(
                    "PN200", "invalid tagged JSON template value", span
                ) from error
            if name in templates:
                if not json_values_equal(templates[name], resolved_template):
                    raise _resolution_error(
                        "PN202",
                        f"conflicting definitions for template ${name}",
                        span,
                        related=(("first definition was here", template_spans[name]),),
                    )
                continue
            templates[name] = resolved_template
            template_spans[name] = span
        elif kind == "documentation.description":
            target_type, target_name, text = (
                target.get("type"),
                target.get("name", ""),
                value.get("text"),
            )
            if (
                set(target) not in ({"type"}, {"type", "name"})
                or target_type not in {"document", "place", "transition", "arcHandle"}
                or target_type == "document"
                and set(target) != {"type"}
                or target_type != "document"
                and (
                    set(target) != {"type", "name"} or not isinstance(target_name, str)
                )
                or set(value) != {"text"}
                or not isinstance(text, str)
            ):
                raise _resolution_error(
                    "PN200", "invalid documentation description contribution", span
                )
            key = (cast(str, target_type), cast(str, target_name))
            existing = descriptions.get(key)
            if existing is not None and existing[0] != text:
                raise _resolution_error(
                    "PN202",
                    f"conflicting description facts for {target_type} "
                    + (
                        f"({target_name})"
                        if target_type == "place"
                        else f"[{target_name}]"
                        if target_type == "transition"
                        else f"@{target_name}"
                        if target_type == "arcHandle"
                        else "net"
                    ),
                    span,
                    related=(("first description was declared here", existing[1]),),
                )
            descriptions.setdefault(key, (text, span))
        elif kind == "documentation.annotation":
            target_type, target_name, annotation_key = (
                target.get("type"),
                target.get("name", ""),
                value.get("key"),
            )
            raw_annotation = value.get("value")
            if (
                set(target) not in ({"type"}, {"type", "name"})
                or target_type not in {"document", "place", "transition", "arcHandle"}
                or target_type == "document"
                and set(target) != {"type"}
                or target_type != "document"
                and (
                    set(target) != {"type", "name"} or not isinstance(target_name, str)
                )
                or set(value) != {"key", "value"}
                or not isinstance(annotation_key, str)
                or not annotation_key
                or not isinstance(raw_annotation, Mapping)
            ):
                raise _resolution_error(
                    "PN200", "invalid documentation annotation contribution", span
                )
            if annotation_key == "petrinet.dsl/v1":
                raise _resolution_error(
                    "PN202",
                    "annotation key 'petrinet.dsl/v1' is reserved for compiler-owned metadata",
                    span,
                    "use extensions for opaque full-document data",
                )
            try:
                annotation_value = untag_json_value(
                    cast(Mapping[str, Any], raw_annotation)
                )
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise _resolution_error(
                    "PN200", "invalid documentation annotation contribution", span
                ) from error
            identity = (cast(str, target_type), cast(str, target_name))
            facts = annotations.setdefault(identity, {})
            existing = facts.get(annotation_key)
            if existing is not None and not json_values_equal(
                existing[0], annotation_value
            ):
                rendered_target = (
                    f"place ({target_name})"
                    if target_type == "place"
                    else f"transition [{target_name}]"
                    if target_type == "transition"
                    else f"arc @{target_name}"
                    if target_type == "arcHandle"
                    else "net"
                )
                raise _resolution_error(
                    "PN202",
                    f"conflicting annotation {annotation_key} facts for {rendered_target}",
                    span,
                    "remove one declaration or make both annotation values identical",
                    (("first annotation value was declared here", existing[1]),),
                )
            facts.setdefault(annotation_key, (annotation_value, span))
        elif kind == "metadata.named-marking":
            name = value.get("name")
            raw_entries = value.get("entries")
            if (
                target != {"type": "document"}
                or set(value) != {"name", "entries"}
                or not isinstance(name, str)
                or not name
                or not isinstance(raw_entries, list)
            ):
                raise _resolution_error(
                    "PN200", "invalid named marking contribution", span
                )
            if name == "initial":
                raise _resolution_error(
                    "PN202",
                    "'initial' is reserved and cannot name a non-initial marking",
                    span,
                    "use the unquoted initial marking keyword or choose another name",
                )
            parsed_entries: list[
                tuple[str, dict[str, Any], int, Mapping[str, Any]]
            ] = []
            for raw_entry in cast(list[Any], raw_entries):
                if not isinstance(raw_entry, Mapping):
                    raise _resolution_error(
                        "PN200", "invalid named marking contribution", span
                    )
                entry = cast(Mapping[str, Any], raw_entry)
                raw_place, count = entry.get("place"), entry.get("count")
                if not isinstance(raw_place, Mapping):
                    raise _resolution_error(
                        "PN200", "invalid named marking contribution", span
                    )
                place_value = cast(Mapping[str, Any], raw_place)
                place = place_value.get("name")
                if (
                    set(entry) != {"place", "count", "token"}
                    or place_value.get("type") != "place"
                    or set(place_value) != {"type", "name"}
                    or not isinstance(place, str)
                    or not place
                    or not isinstance(count, int)
                    or isinstance(count, bool)
                    or count < 1
                ):
                    raise _resolution_error(
                        "PN200", "invalid named marking contribution", span
                    )
                token = _parse_marking_token(
                    entry.get("token"),
                    message="invalid named marking contribution",
                    span=span,
                )
                parsed_entries.append((place, token, count, span))
            named_markings.setdefault(name, []).extend(parsed_entries)
        elif kind == "view.position":
            view_name, raw_subject, raw_position = (
                target.get("name"),
                value.get("subject"),
                value.get("position"),
            )
            parsed_subject = (
                _position_subject(cast(Mapping[str, Any], raw_subject))
                if isinstance(raw_subject, Mapping)
                else None
            )
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "view"
                or not isinstance(view_name, str)
                or not view_name
                or set(value) != {"subject", "position"}
                or parsed_subject is None
                or not isinstance(raw_position, Mapping)
            ):
                raise _resolution_error(
                    "PN200", "invalid view position contribution", span
                )
            subject_kind, subject_name, subject_transition = parsed_subject
            raw_position_mapping = cast(Mapping[str, Any], raw_position)
            position: dict[str, Any]
            if set(raw_position_mapping) == {"from", "delta"}:
                raw_base = raw_position_mapping["from"]
                parsed_base = (
                    _position_subject(cast(Mapping[str, Any], raw_base))
                    if isinstance(raw_base, Mapping)
                    else None
                )
                if parsed_base is None:
                    raise _resolution_error(
                        "PN200", "invalid view position contribution", span
                    )
                base_kind, base_name, base_transition = parsed_base
                try:
                    decoded_delta = untag_json_value(raw_position_mapping["delta"])
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise _resolution_error(
                        "PN200", "invalid view position contribution", span
                    ) from error
                if not _exact_point(decoded_delta):
                    raise _resolution_error(
                        "PN200", "invalid view position contribution", span
                    )
                position = {
                    "from": _position_key(base_kind, base_name, base_transition),
                    "delta": decoded_delta,
                }
                relative_bases.append(
                    (view_name, base_kind, base_name, base_transition, span)
                )
            else:
                try:
                    decoded_position = untag_json_value(raw_position_mapping)
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise _resolution_error(
                        "PN200", "invalid view position contribution", span
                    ) from error
                if not isinstance(decoded_position, dict):
                    raise _resolution_error(
                        "PN200", "invalid view position contribution", span
                    )
                position = cast(dict[str, Any], decoded_position)
                if not _exact_point(position):
                    raise _resolution_error(
                        "PN200", "invalid view position contribution", span
                    )
            subject_key = _position_key(subject_kind, subject_name, subject_transition)
            view_positions = positions.setdefault((view_name, subject_kind), {})
            existing = view_positions.get(subject_key)
            if existing is not None and not json_values_equal(existing[0], position):
                noun = "copy " if subject_kind == "placeCopy" else f"{subject_kind} "
                raise _resolution_error(
                    "PN202",
                    "conflicting position facts for "
                    + noun
                    + _rendered_position_target(
                        subject_kind, subject_name, subject_transition
                    )
                    + f" in view {view_name!r}",
                    span,
                    "remove one declaration or make both positions identical",
                    (("first position was declared here", existing[1]),),
                )
            view_positions.setdefault(
                subject_key,
                (position, span, subject_kind, subject_name, subject_transition),
            )
        elif kind == "view.route":
            handle, raw_view, raw_points = (
                target.get("name"),
                value.get("view"),
                value.get("points"),
            )
            view_value = (
                cast(Mapping[str, Any], raw_view)
                if isinstance(raw_view, Mapping)
                else None
            )
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "arcHandle"
                or not isinstance(handle, str)
                or set(value) != {"view", "points"}
                or view_value is None
                or view_value.get("type") != "view"
                or set(view_value) != {"type", "name"}
                or not isinstance(view_value.get("name"), str)
                or not isinstance(raw_points, list)
                or not raw_points
            ):
                raise _resolution_error(
                    "PN200", "invalid view route contribution", span
                )
            points: list[dict[str, Any]] = []
            try:
                for raw_point in cast(list[Any], raw_points):
                    if not isinstance(raw_point, Mapping):
                        raise ValueError
                    decoded_point = untag_json_value(cast(Mapping[str, Any], raw_point))
                    point = (
                        cast(dict[str, Any], decoded_point)
                        if isinstance(decoded_point, dict)
                        else None
                    )
                    if (
                        point is None
                        or set(point) != {"x", "y"}
                        or any(
                            not isinstance(point[axis], (int, float))
                            or isinstance(point[axis], bool)
                            for axis in ("x", "y")
                        )
                    ):
                        raise ValueError
                    points.append(point)
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise _resolution_error(
                    "PN200", "invalid view route contribution", span
                ) from error
            route_key = (cast(str, view_value["name"]), handle)
            existing = routes.get(route_key)
            if existing is not None and not json_values_equal(existing[0], points):
                raise _resolution_error(
                    "PN202",
                    f"conflicting route facts for arc @{handle} in view {view_value['name']!r}",
                    span,
                    related=(("first route was declared here", existing[1]),),
                )
            routes.setdefault(route_key, (points, span))
        elif kind in ("view.splines", "view.detail"):
            member = kind.removeprefix("view.")
            view_name, style_value = target.get("name"), value.get(member)
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "view"
                or not isinstance(view_name, str)
                or not view_name
                or set(value) != {member}
                or not isinstance(style_value, str)
            ):
                raise _resolution_error(
                    "PN200", f"invalid view {member} contribution", span
                )
            existing_style = view_styles.get((view_name, member))
            if existing_style is not None and existing_style[0] != style_value:
                raise _resolution_error(
                    "PN202",
                    f"conflicting {member} facts for view {view_name!r}",
                    span,
                    "remove one declaration or make both values identical",
                    ((f"first {member} value was declared here", existing_style[1]),),
                )
            view_styles.setdefault((view_name, member), (style_value, span))
        elif kind in (
            "decoration.highlight",
            "decoration.note",
            "decoration.summary",
            "decoration.quiet",
            "decoration.beside",
            "decoration.show",
        ):
            member = kind.removeprefix("decoration.")
            target_type, target_name = target.get("type"), target.get("name")
            allowed_types = (
                {"color"}
                if member in ("quiet", "show")
                else {"place"}
                if member == "beside"
                else {"transition", "arcHandle"}
                if member == "summary"
                else {"place", "transition", "arcHandle"}
            )
            if member == "highlight":
                valid_value = set(value) <= {"label"} and isinstance(
                    value.get("label", ""), str
                )
                decoration_value: Any = dict(value)
            elif member == "beside":
                side = value.get("side", "left")
                valid_value = set(value) <= {"side"} and side in ("left", "right")
                decoration_value = dict(value)
            elif member == "quiet":
                valid_value = not value
                decoration_value = True
            elif member == "show":
                raw_fields = value.get("fields")
                fields = (
                    cast(list[object], raw_fields)
                    if isinstance(raw_fields, list)
                    else []
                )
                valid_value = (
                    set(value) == {"fields"}
                    and bool(fields)
                    and all(valid_field_path(path) for path in fields)
                    and len(set(fields)) == len(fields)
                )
                decoration_value = list(fields)
            else:
                valid_value = set(value) == {"text"} and isinstance(value["text"], str)
                decoration_value = value.get("text")
            if (
                set(target) != {"type", "name"}
                or target_type not in allowed_types
                or not isinstance(target_name, str)
                or not target_name
                or not valid_value
            ):
                raise _resolution_error(
                    "PN200", _invalid_contribution_message(kind), span
                )
            subject_kind = _DECORATION_SUBJECT_KINDS[cast(str, target_type)]
            subject_facts = decorations.setdefault(f"{subject_kind}:{target_name}", {})
            existing_decoration = subject_facts.get(member)
            if existing_decoration is not None and not json_values_equal(
                existing_decoration[0], decoration_value
            ):
                rendered_target = (
                    f"({target_name})"
                    if subject_kind == "place"
                    else f"[{target_name}]"
                    if subject_kind == "transition"
                    else f"@{target_name}"
                    if subject_kind == "arc"
                    else f"color {target_name}"
                )
                raise _resolution_error(
                    "PN202",
                    f"conflicting {member} decorations for {rendered_target}",
                    span,
                    "remove one declaration or make both decorations identical",
                    (
                        (
                            f"first {member} decoration was declared here",
                            existing_decoration[1],
                        ),
                    ),
                )
            subject_facts.setdefault(member, (decoration_value, span))
        elif kind == "document.extensions":
            raw_extensions = value.get("extensions")
            if (
                target != {"type": "document"}
                or set(value) != {"extensions"}
                or not isinstance(raw_extensions, Mapping)
            ):
                raise _resolution_error(
                    "PN200", "invalid document extensions contribution", span
                )
            try:
                decoded_extensions = untag_json_value(
                    cast(Mapping[str, Any], raw_extensions)
                )
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise _resolution_error(
                    "PN200", "invalid document extensions contribution", span
                ) from error
            if not isinstance(decoded_extensions, dict):
                raise _resolution_error(
                    "PN200", "invalid document extensions contribution", span
                )
            extension_value = cast(dict[str, Any], decoded_extensions)
            if extensions is not None and not json_values_equal(
                extensions[0], extension_value
            ):
                raise _resolution_error(
                    "PN202",
                    "conflicting document extensions facts",
                    span,
                    related=(("first extensions were declared here", extensions[1]),),
                )
            if extensions is None:
                extensions = (extension_value, span)
        elif kind == "domain.values":
            color, path, raw_values = (
                target.get("name"),
                value.get("path"),
                value.get("values"),
            )
            try:
                domain_values = (
                    [untag_json_value(item) for item in cast(list[Any], raw_values)]
                    if isinstance(raw_values, list)
                    else []
                )
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise _resolution_error(
                    "PN200", "invalid domain contribution", span
                ) from error
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "color"
                or not isinstance(color, str)
                or not color
                or set(value) != {"path", "values"}
                or not valid_field_path(path)
                or not domain_values
                or any(
                    item is None or isinstance(item, (dict, list))
                    for item in domain_values
                )
                or any(
                    json_values_equal(item, other)
                    for index, item in enumerate(domain_values)
                    for other in domain_values[:index]
                )
            ):
                raise _resolution_error("PN200", "invalid domain contribution", span)
            key = f"{color}.{path}"
            existing_domain = domains.get(key)
            if existing_domain is not None:
                if not json_values_equal(existing_domain[0], domain_values):
                    raise _resolution_error(
                        "PN202",
                        f"conflicting domain facts for {key}",
                        span,
                        "remove one declaration or make both value lists identical",
                        (("first domain was declared here", existing_domain[1]),),
                    )
                continue
            domains[key] = (domain_values, span)
        elif kind == "proof.final":
            name = target.get("name")
            others = value.get("with", [])
            if (
                set(target) != {"type", "name"}
                or target.get("type") != "place"
                or not isinstance(name, str)
                or not name
                or set(value) - {"with"}
                or not isinstance(others, list)
                or ("with" in value and not others)
                or not all(
                    isinstance(other, str) and other
                    for other in cast(list[Any], others)
                )
            ):
                raise _resolution_error(
                    "PN200", "invalid final place contribution", span
                )
            marking = (name, *cast(list[str], others))
            if len(set(marking)) != len(marking):
                raise _resolution_error(
                    "PN200", "invalid final place contribution", span
                )
            final_markings.setdefault(frozenset(marking), (marking, span))
        elif kind == "proof.invariant":
            raw_terms = value.get("terms")
            terms = cast(list[Any], raw_terms) if isinstance(raw_terms, list) else []
            constant = value.get("constant")
            invariant_name = value.get("name")
            if (
                target != {"type": "document", "kind": "net"}
                or set(value) - {"terms", "name", "constant"}
                or not terms
                or not all(
                    isinstance(term, Mapping)
                    and set(cast(Mapping[str, Any], term)) == {"place", "weight"}
                    and isinstance(cast(Mapping[str, Any], term)["place"], str)
                    and cast(Mapping[str, Any], term)["place"]
                    and isinstance(cast(Mapping[str, Any], term)["weight"], int)
                    and not isinstance(cast(Mapping[str, Any], term)["weight"], bool)
                    and cast(Mapping[str, Any], term)["weight"] >= 1
                    for term in terms
                )
                or len({term["place"] for term in terms}) != len(terms)
                or (
                    constant is not None
                    and (
                        not isinstance(constant, int)
                        or isinstance(constant, bool)
                        or constant < 0
                    )
                )
                or (
                    invariant_name is not None
                    and (not isinstance(invariant_name, str) or not invariant_name)
                )
            ):
                raise _resolution_error("PN200", "invalid invariant contribution", span)
            invariant: dict[str, Any] = {
                "weights": {term["place"]: term["weight"] for term in terms}
            }
            if constant is not None:
                invariant["constant"] = constant
            if invariant_name is not None:
                for first, first_span in invariants:
                    if first.get("name") == invariant_name:
                        raise _resolution_error(
                            "PN202",
                            f"two invariants are named {invariant_name!r}",
                            span,
                            "give each invariant its own name",
                            (("first invariant was declared here", first_span),),
                        )
                invariant["name"] = invariant_name
            invariants.append((invariant, span))
        elif kind == "actor.declare":
            actor_name, actor_kind = value.get("name"), value.get("kind")
            if (
                target != {"type": "document", "kind": "net"}
                or set(value) != {"name", "kind"}
                or not isinstance(actor_name, str)
                or not actor_name
                or actor_kind not in ("person", "system", "record")
            ):
                raise _resolution_error(
                    "PN200", "invalid actor declaration contribution", span
                )
            existing_actor = actors.get(actor_name)
            if existing_actor is not None:
                if existing_actor[0] != actor_kind:
                    raise _resolution_error(
                        "PN202",
                        f"conflicting actor declarations for {actor_name!r}",
                        span,
                        "declare each actor once, as a person or as a system",
                        (("first declaration was here", existing_actor[1]),),
                    )
                continue
            actors[actor_name] = (actor_kind, span)
        else:
            raise _resolution_error(
                "PN200", f"unsupported contribution kind {kind!r}", span
            )

    places.extend(place_appearances)
    accepts.update(
        (place, list(declared_accepts[place][0]))
        for place in place_appearances
        if place in declared_accepts
    )

    for declaration in arc_declarations:
        arc_id = declaration["id"]
        place = declaration["place"]
        transition = declaration["transition"]
        is_input = declaration["isInput"]
        mode = declaration["mode"]
        span = declaration["span"]
        color = declaration["color"]
        resolved_color = color["value"]
        if place not in accepts:
            accepts[place] = []
        declared = declared_accepts.get(place)
        if declared is not None and resolved_color not in declared[0]:
            raise _resolution_error(
                "PN202",
                f"arc color {resolved_color!r} conflicts with accepted colors declared for ({place})",
                span,
                "add the arc color to the place declaration or change the arc color",
                (("accepted colors were declared here", declared[1]),),
            )
        if resolved_color not in accepts[place]:
            accepts[place].append(resolved_color)
        arc: dict[str, Any] = {
            "from": {"place": place} if is_input else {"transition": transition},
            "to": {"transition": transition} if is_input else {"place": place},
        }
        if is_input:
            consume: dict[str, Any] = {"type": resolved_color}
            if mode != "consume":
                consume["mode"] = mode
            arc["consume"] = consume
        else:
            arc["produce"] = {"destination": place, "type": resolved_color}
        if arc_id in arc_indexes:
            raise _resolution_error("PN200", "duplicate arc identity", span)
        arc_indexes[arc_id] = len(arcs)
        arcs.append(arc)
        arc_objects[arc_id] = arc

    for place in declared_places:
        if place not in accepts:
            accepts[place] = ["token"]

    for handle, resolved_ids in arc_handles.items():
        handle_id = arc_handle_ids[handle]
        declaration_count = sum(arc_id[:2] == handle_id[:2] for arc_id in arc_indexes)
        expected_ids = [
            (handle_id[0], handle_id[1], part)
            for part in range(1, declaration_count + 1)
        ]
        if resolved_ids != expected_ids:
            raise _resolution_error(
                "PN200",
                "invalid arc handle contribution",
                arc_handle_spans[handle],
            )
        if any(arc_id not in arc_indexes for arc_id in resolved_ids):
            raise _resolution_error(
                "PN202",
                f"handle @{handle} refers to an unknown arc",
                arc_handle_spans[handle],
            )

    for place, (_, span) in capacities.items():
        if place not in accepts:
            raise _resolution_error(
                "PN202", f"capacity refers to unknown place ({place})", span
            )

    for place, (port, span) in ports.items():
        if place not in accepts:
            raise _resolution_error(
                "PN202", f"port refers to unknown place ({place})", span
            )
        if port["type"] not in accepts[place]:
            raise _resolution_error(
                "PN202",
                f"port color {port['type']!r} is not accepted by place ({place})",
                span,
                "declare a port color already accepted by the place",
            )

    for handle, (weight, span) in arc_weights.items():
        if handle not in arc_handles:
            raise _resolution_error(
                "PN202", f"weight refers to unknown arc handle @{handle}", span
            )
        input_indexes = [
            arc_indexes[arc_id]
            for arc_id in arc_handles[handle]
            if "consume" in arcs[arc_indexes[arc_id]]
        ]
        if not input_indexes:
            raise _resolution_error(
                "PN202", f"arc weight is not allowed on produce arc @{handle}", span
            )
        if len(input_indexes) != 1:
            raise _resolution_error(
                "PN202",
                f"arc handle @{handle} must identify exactly one input arc for weight",
                span,
            )
        consume = arcs[input_indexes[0]]["consume"]
        if consume.get("mode") == "inhibit" and weight > 1:
            raise _resolution_error(
                "PN202",
                f"arc weight greater than 1 is not allowed on inhibit arc @{handle}",
                span,
            )
        if weight > 1:
            consume["weight"] = weight
    for handle, (data, span) in arc_data.items():
        if handle not in arc_handles:
            raise _resolution_error(
                "PN202", f"data refers to unknown arc handle @{handle}", span
            )
        produce_indexes = [
            arc_indexes[arc_id]
            for arc_id in arc_handles[handle]
            if "produce" in arcs[arc_indexes[arc_id]]
        ]
        if len(produce_indexes) != 1:
            raise _resolution_error(
                "PN202",
                f"arc handle @{handle} must identify exactly one produce arc",
                span,
            )
        arcs[produce_indexes[0]]["produce"]["data"] = data
    for handle, (cel, span) in arc_cels.items():
        if handle in arc_data:
            raise _resolution_error(
                "PN202",
                f"arc @{handle} declares both data and data cel; "
                "they are mutually exclusive",
                span,
                related=(("literal data was declared here", arc_data[handle][1]),),
            )
        if handle not in arc_handles:
            raise _resolution_error(
                "PN202", f"data cel refers to unknown arc handle @{handle}", span
            )
        produce_indexes = [
            arc_indexes[arc_id]
            for arc_id in arc_handles[handle]
            if "produce" in arcs[arc_indexes[arc_id]]
        ]
        if len(produce_indexes) != 1:
            raise _resolution_error(
                "PN202",
                f"arc handle @{handle} must identify exactly one produce arc",
                span,
            )
        try:
            get_default_adapter().compile(cel)
        except Exception:  # noqa: BLE001 - backend-specific errors
            raise _resolution_error(
                "PN203",
                f"invalid CEL data expression for arc @{handle}",
                span,
                "fix the CEL expression syntax",
            ) from None
        arcs[produce_indexes[0]]["produce"]["cel"] = cel
    for handle, (predicate, span) in arc_predicates.items():
        if handle not in arc_handles:
            raise _resolution_error(
                "PN202", f"predicate refers to unknown arc handle @{handle}", span
            )
        consume_indexes = [
            arc_indexes[arc_id]
            for arc_id in arc_handles[handle]
            if "consume" in arcs[arc_indexes[arc_id]]
        ]
        if len(consume_indexes) != 1:
            raise _resolution_error(
                "PN202",
                f"arc handle @{handle} must identify exactly one consume arc",
                span,
            )
        cel = predicate.get("cel")
        if cel is not None:
            try:
                get_default_adapter().compile(cel)
            except Exception:  # noqa: BLE001 - backend-specific errors
                raise _resolution_error(
                    "PN203",
                    f"invalid CEL predicate for arc @{handle}",
                    span,
                    "fix the CEL expression syntax",
                ) from None
        arcs[consume_indexes[0]]["consume"]["predicate"] = predicate
    for handle, (cel, span) in arc_correlates.items():
        if handle not in arc_handles:
            raise _resolution_error(
                "PN202", f"correlate refers to unknown arc handle @{handle}", span
            )
        input_indexes = [
            arc_indexes[arc_id]
            for arc_id in arc_handles[handle]
            if "consume" in arcs[arc_indexes[arc_id]]
        ]
        if len(input_indexes) != 1:
            target = "no input arc" if not input_indexes else "several input arcs"
            raise _resolution_error(
                "PN202",
                "correlate must target exactly one input arc (->, ->?, ->0); "
                f"@{handle} names {target}",
                span,
                "move correlate to a named input arc",
                ((f"arc @{handle} was declared here", arc_handle_spans[handle]),),
            )
        try:
            get_default_adapter().compile(cel)
        except Exception:  # noqa: BLE001 - backend-specific errors
            raise _resolution_error(
                "PN203",
                f"invalid CEL correlate for arc @{handle}",
                span,
                "fix the CEL expression syntax",
            ) from None
        arcs[input_indexes[0]]["consume"]["correlate"] = {"cel": cel}
    for transition, (_, span) in guards.items():
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"guard refers to unknown transition [{transition}]",
                span,
            )
    for transition, (_, _, span) in timers.items():
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"timer refers to unknown transition [{transition}]",
                span,
            )
    for transition, (_, span) in timer_maturities.items():
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"timer maturity refers to unknown transition [{transition}]",
                span,
            )
        if transition not in timers:
            raise _resolution_error(
                "PN201",
                f"transition [{transition}] has timer maturity but no timer fact",
                span,
                f'add `[{transition}] timer clock (...) cel "..."`',
            )
    for transition, binds in timer_binds.items():
        first_bind_span = next(iter(binds.values()))[1]
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"timer bind refers to unknown transition [{transition}]",
                first_bind_span,
            )
        if transition not in timers:
            raise _resolution_error(
                "PN201",
                f"transition [{transition}] has timer binds but no timer fact",
                first_bind_span,
                f'add `[{transition}] timer clock (...) cel "..."`',
            )
    for transition, keys in binding_names.items():
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"binding name refers to unknown transition [{transition}]",
                next(iter(keys.values()))[1],
            )
    for transition, (_, span) in handlers.items():
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"handler refers to unknown transition [{transition}]",
                span,
            )
    for transition, (_, span) in priorities.items():
        if transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"priority refers to unknown transition [{transition}]",
                span,
            )

    def check_metadata_target(
        target_type: str, target_name: str, fact_span: Mapping[str, Any], noun: str
    ) -> None:
        verb = "describing" if noun == "description" else "annotating"
        if target_type == "place" and target_name not in accepts:
            raise _resolution_error(
                "PN202",
                f"{noun} references unknown place {target_name!r}; metadata facts cannot declare semantic objects",
                fact_span,
                f"declare the place in topology before {verb} it",
            )
        if target_type == "transition" and target_name not in transitions:
            raise _resolution_error(
                "PN202",
                f"{noun} references unknown transition {target_name!r}; metadata facts cannot declare semantic objects",
                fact_span,
                f"declare the transition in topology before {verb} it",
            )
        if target_type == "arcHandle" and target_name not in arc_handles:
            raise _resolution_error(
                "PN202",
                f"{noun} references unknown arc handle @{target_name}",
                fact_span,
                f"declare and name the arc before {verb} it",
            )

    for (target_type, target_name), (_, fact_span) in descriptions.items():
        check_metadata_target(target_type, target_name, fact_span, "description")
    for (target_type, target_name), facts in annotations.items():
        check_metadata_target(
            target_type, target_name, next(iter(facts.values()))[1], "annotation"
        )
    incident = {
        pair for arc in arcs if (pair := _arc_place_transition(arc)) is not None
    }

    def quoted_name(name: str) -> str:
        if _TIMER_BIND_IDENTIFIER.fullmatch(name):
            return name
        return json.dumps(name, ensure_ascii=False)

    def copy_span(
        fact_span: Mapping[str, Any],
        view_name: str,
        place: str,
        transition: str,
        *,
        subject: bool,
    ) -> Mapping[str, Any]:
        if not subject:
            return fact_span
        return _relative_span(
            fact_span,
            f"view {quoted_name(view_name)} position ",
            f"({quoted_name(place)})@[{quoted_name(transition)}]",
        )

    def require_copy(
        place: str,
        transition: str,
        fact_span: Mapping[str, Any],
        view_name: str,
        *,
        subject: bool,
    ) -> None:
        error_span = copy_span(fact_span, view_name, place, transition, subject=subject)
        if place not in accepts or transition not in transitions:
            raise _resolution_error(
                "PN202",
                f"view {view_name!r} references unknown copy "
                f"({place})@[{transition}]; presentation facts cannot declare "
                "semantic objects",
                error_span,
                "declare the place and the transition in topology before "
                "positioning the copy",
            )
        fusion = annotations.get(("place", place), {}).get("fusion")
        if fusion is None or fusion[0] is not True:
            raise _resolution_error(
                "PN202",
                f"copy target ({place})@[{transition}] needs a fusion place; "
                f"({place}) is drawn once, so it has no copies",
                error_span,
                f"annotate it with `({place}) annotation fusion true`, "
                "or position the place",
            )
        if (place, transition) not in incident:
            raise _resolution_error(
                "PN202",
                f"transition [{transition}] has no arc to place ({place}), so "
                f"({place})@[{transition}] is not a copy",
                error_span,
                f"draw an arc between [{transition}] and ({place}), "
                "or remove the copy target",
            )

    for (view_name, subject_type), view_positions in positions.items():
        known = (
            accepts if subject_type == "place" else {name: None for name in transitions}
        )
        for _subject_key, stored in view_positions.items():
            _position, fact_span, kind, subject_name, copy_transition = stored
            if kind == "placeCopy":
                require_copy(
                    subject_name,
                    copy_transition,
                    fact_span,
                    view_name,
                    subject=True,
                )
                continue
            if subject_name not in known:
                rendered_view_name = quoted_name(view_name)
                rendered_subject_name = quoted_name(subject_name)
                target_span = _relative_span(
                    fact_span,
                    f"view {rendered_view_name} position ",
                    f"({rendered_subject_name})"
                    if subject_type == "place"
                    else f"[{rendered_subject_name}]",
                )
                raise _resolution_error(
                    "PN202",
                    f"view {view_name!r} references unknown {subject_type} {subject_name!r}; presentation facts cannot declare semantic objects",
                    target_span,
                    f"declare the {subject_type} in topology before positioning it",
                )
    for view_name, base_kind, base_name, base_transition, fact_span in relative_bases:
        if base_kind == "placeCopy":
            require_copy(
                base_name, base_transition, fact_span, view_name, subject=False
            )
            continue
        base_known = (
            accepts if base_kind == "place" else {name: None for name in transitions}
        )
        if base_name not in base_known:
            rendered_base_name = quoted_name(base_name)
            raise _resolution_error(
                "PN202",
                f"view {view_name!r} relative base references unknown "
                + f"{base_kind} {rendered_base_name!r}; presentation facts "
                + "cannot declare semantic objects",
                fact_span,
                "declare the "
                + f"{base_kind} in topology before using it as a relative base",
            )
    for view_name, base_kind, base_name, _base_transition, fact_span in relative_bases:
        if base_kind != "place":
            continue
        if f"place:{base_name}" not in positions.get((view_name, "place"), {}):
            raise _resolution_error(
                "PN202",
                f"view {view_name!r} relative base ({base_name}) is the place "
                f"entry's point, but view {view_name!r} has no position for "
                f"({base_name})",
                fact_span,
                f"position ({base_name}) in this view before offsetting from it",
            )
    for (view_name, handle), (_, fact_span) in routes.items():
        if handle not in arc_handles:
            raise _resolution_error(
                "PN202",
                f"view {view_name!r} route references unknown arc handle @{handle}",
                fact_span,
                "declare and name the routed arc before routing it",
            )
    known_colors = {color for colors in accepts.values() for color in colors}
    for subject, facts in decorations.items():
        subject_kind, subject_name = subject.split(":", 1)
        known = (
            subject_name in accepts
            if subject_kind == "place"
            else subject_name in transitions
            if subject_kind == "transition"
            else subject_name in arc_handles
            if subject_kind == "arc"
            else subject_name in known_colors
        )
        if not known:
            noun = "arc handle" if subject_kind == "arc" else subject_kind
            raise _resolution_error(
                "PN202",
                f"decoration references unknown {noun} {subject_name!r}; "
                "presentation facts cannot declare semantic objects",
                next(iter(facts.values()))[1],
                f"declare the {noun} before decorating it",
            )
        fusion = annotations.get(("place", subject_name), {}).get("fusion")
        if "beside" in facts and (fusion is None or fusion[0] is not True):
            raise _resolution_error(
                "PN202",
                f"beside decoration needs a fusion place; ({subject_name}) is "
                "drawn once, so it has no local copies to place",
                facts["beside"][1],
                f"annotate it with `({subject_name}) annotation fusion true`, "
                "or remove the beside decoration",
            )
    fusion_places = {
        name
        for (target_type, name), facts in annotations.items()
        if target_type == "place"
        and (fusion_fact := facts.get("fusion")) is not None
        and fusion_fact[0] is True
    }
    beside_open = {
        subject.split(":", 1)[1]
        for subject, facts in decorations.items()
        if subject.startswith("place:")
        and (beside := facts.get("beside")) is not None
        and isinstance(beside[0], Mapping)
        and "side" not in beside[0]
    }
    shared_owners = _shared_copy_owners(arcs, fusion_places, beside_open)
    shared_groups: dict[
        tuple[str, str, frozenset[str]],
        list[tuple[dict[str, Any], Mapping[str, Any], str]],
    ] = {}
    for (view_name, subject_type), view_positions in positions.items():
        if subject_type != "placeCopy":
            continue
        for stored in view_positions.values():
            stored_position, fact_span, _kind, place, transition = stored
            owners = shared_owners.get((place, transition))
            if owners is None:
                continue
            shared_groups.setdefault((view_name, place, owners), []).append(
                (stored_position, fact_span, transition)
            )
    for (view_name, place, _owners), entries in shared_groups.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda item: cast(int, item[1]["start"]["byteOffset"]))
        first_position, first_span, first_transition = entries[0]
        for stored_position, fact_span, transition in entries[1:]:
            if json_values_equal(stored_position, first_position):
                continue
            raise _resolution_error(
                "PN202",
                f"conflicting position facts for shared copy ({place})@"
                f"[{first_transition}] and ({place})@[{transition}] in view "
                f"{view_name!r}",
                fact_span,
                "remove one declaration or make both positions identical",
                (("first position was declared here", first_span),),
            )
    for key, (_, fact_span) in domains.items():
        color = key.split(".", 1)[0]
        if color not in known_colors:
            raise _resolution_error(
                "PN202",
                f"domain refers to unknown color {color!r}; no place accepts it",
                fact_span,
                "name a color that a place accepts",
            )
    for marking, fact_span in final_markings.values():
        for place in marking:
            if place not in accepts:
                raise _resolution_error(
                    "PN202", f"final refers to unknown place ({place})", fact_span
                )
    for invariant, fact_span in invariants:
        for place in invariant["weights"]:
            if place not in accepts:
                raise _resolution_error(
                    "PN202", f"invariant refers to unknown place ({place})", fact_span
                )
    if header is None:
        header = {"name": "unnamed"}
    if transition_orders:
        if set(transition_orders) != set(transitions) or set(
            transition_orders.values()
        ) != set(range(1, len(transitions) + 1)):
            raise _resolution_error(
                "PN202", "transition order must rank every transition exactly once"
            )
        transitions.sort(key=transition_orders.__getitem__)
    if handle_orders:
        if set(handle_orders) != set(arc_handles) or set(handle_orders.values()) != set(
            range(1, len(arc_handles) + 1)
        ):
            raise _resolution_error(
                "PN202", "arc-run order must rank every handle exactly once"
            )
        covered = {arc_id for ids in arc_handles.values() for arc_id in ids}
        if set(arc_indexes) != covered:
            raise _resolution_error(
                "PN202",
                "arc-run order cannot omit arcs from an unhandled chain",
            )
        ordered_arcs: list[dict[str, Any]] = []
        for handle in sorted(handle_orders, key=handle_orders.__getitem__):
            for arc_id in arc_handles[handle]:
                if arc_id not in arc_indexes:
                    raise _resolution_error(
                        "PN202", f"handle @{handle} refers to an unknown arc"
                    )
                ordered_arcs.append(arcs[arc_indexes[arc_id]])
        arcs = ordered_arcs
    initial_marking: dict[str, list[dict[str, Any]]] = {}
    for place, token, count, span in markings:
        if place not in accepts:
            raise _resolution_error(
                "PN202", f"marking refers to unknown place ({place})", span
            )
        initial_marking.setdefault(place, []).extend(
            _materialize_marking_token(
                place=place,
                token=token,
                count=count,
                accepted_colors=accepts[place],
                templates=templates,
                span=span,
            )
        )
    resolved_named_markings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for marking_name, entries in named_markings.items():
        resolved_marking: dict[str, list[dict[str, Any]]] = {}
        for place, token, count, fact_span in entries:
            if place not in accepts:
                raise _resolution_error(
                    "PN202",
                    f"named marking {marking_name!r} references unknown place {place!r}; marking facts cannot declare semantic objects",
                    fact_span,
                    "declare the place in topology before marking it",
                )
            resolved_marking.setdefault(place, []).extend(
                _materialize_marking_token(
                    place=place,
                    token=token,
                    count=count,
                    accepted_colors=accepts[place],
                    templates=templates,
                    span=fact_span,
                    marking_name=marking_name,
                )
            )
        resolved_named_markings[marking_name] = resolved_marking
    resolved_places: list[dict[str, Any]] = []
    for place in places:
        resolved_place: dict[str, Any] = {"name": place, "accepts": accepts[place]}
        if place in capacities:
            resolved_place["capacityPerColorKey"] = capacities[place][0]
        if place in ports:
            resolved_place["port"] = ports[place][0]
        description_fact = descriptions.get(("place", place))
        if description_fact is not None:
            resolved_place["description"] = description_fact[0]
        annotation_facts = annotations.get(("place", place))
        if annotation_facts:
            resolved_place["annotations"] = {
                key: annotation_facts[key][0] for key in annotation_facts
            }
        resolved_places.append(resolved_place)
    resolved_transitions: list[dict[str, Any]] = []
    for transition in transitions:
        resolved_transition: dict[str, Any] = {"name": transition}
        handler = handlers.get(transition)
        if handler is not None:
            resolved_transition["handler"] = handler[0]
        if transition in guards:
            resolved_transition["guard"] = guards[transition][0]
        if transition in timers:
            clock, cel, _ = timers[transition]
            timer: dict[str, Any] = {"clock": clock, "cel": cel}
            binds = timer_binds.get(transition)
            if binds:
                timer["bind"] = {name: binds[name][0] for name in sorted(binds)}
            resolved_transition["timer"] = timer
            maturity = timer_maturities.get(transition)
            if maturity is not None:
                timer["maturity"] = maturity[0]
        keys = binding_names.get(transition)
        if keys:
            resolved_transition["bindingNames"] = {
                key: keys[key][0] for key in sorted(keys)
            }
        priority = priorities.get(transition)
        if priority is not None and priority[0] != 0:
            resolved_transition["priority"] = priority[0]
        description_fact = descriptions.get(("transition", transition))
        if description_fact is not None:
            resolved_transition["description"] = description_fact[0]
        annotation_facts = annotations.get(("transition", transition))
        if annotation_facts:
            resolved_transition["annotations"] = {
                key: annotation_facts[key][0] for key in annotation_facts
            }
        resolved_transitions.append(resolved_transition)
    current_arc_indexes = {id(arc): index for index, arc in enumerate(arcs)}
    for handle, resolved_ids in arc_handles.items():
        description_fact = descriptions.get(("arcHandle", handle))
        annotation_facts = annotations.get(("arcHandle", handle))
        if description_fact is None and not annotation_facts:
            continue
        for arc_id in resolved_ids:
            arc_position = current_arc_indexes[id(arc_objects[arc_id])]
            if description_fact is not None:
                arcs[arc_position]["description"] = description_fact[0]
            if annotation_facts:
                arcs[arc_position]["annotations"] = {
                    key: annotation_facts[key][0] for key in annotation_facts
                }

    result: dict[str, Any] = {
        "name": header["name"],
        "places": resolved_places,
        "transitions": resolved_transitions,
        "arcs": arcs,
    }
    if markings or not (
        named_markings
        or positions
        or routes
        or view_styles
        or decorations
        or extensions is not None
    ):
        result["initialMarking"] = initial_marking
    header_description = header.get("description")
    metadata_description = descriptions.get(("document", ""))
    if metadata_description is not None:
        if (
            header_description is not None
            and header_description != metadata_description[0]
        ):
            raise _resolution_error(
                "PN202",
                "conflicting description facts for net",
                metadata_description[1],
            )
        result["description"] = metadata_description[0]
    elif header_description is not None:
        result["description"] = header_description
    document_annotations = annotations.get(("document", ""))
    if document_annotations:
        result["annotations"] = {
            key: document_annotations[key][0] for key in document_annotations
        }
    if actors:
        if document_annotations and "actors" in document_annotations:
            raise _resolution_error(
                "PN202",
                "conflicting annotation actors facts for net",
                document_annotations["actors"][1],
                "declare actors with `person` and `system` lines only",
                (("first actor was declared here", next(iter(actors.values()))[1]),),
            )
        result.setdefault("annotations", {})["actors"] = [
            {"name": name, "kind": kind} for name, (kind, _) in actors.items()
        ]
    if domains:
        result["domains"] = {key: values for key, (values, _) in domains.items()}
    if final_markings or invariants:
        proofs: dict[str, Any] = {}
        if final_markings:
            proofs["final"] = [
                marking[0] if len(marking) == 1 else list(marking)
                for marking, _ in final_markings.values()
            ]
        if invariants:
            proofs["invariants"] = [invariant for invariant, _ in invariants]
        result["proofs"] = proofs
    metadata_handles = (
        {
            target_name
            for target_type, target_name in {*descriptions, *annotations}
            if target_type == "arcHandle"
        }
        | {handle for _, handle in routes}
        | {
            subject.split(":", 1)[1]
            for subject in decorations
            if subject.startswith("arc:")
        }
    )
    views: dict[str, dict[str, Any]] = {}
    for (view_name, _), view_positions in positions.items():
        view = views.setdefault(view_name, {"positions": {}, "routes": {}})
        view["positions"].update(
            {subject: position[0] for subject, position in view_positions.items()}
        )
    for (view_name, handle), (points, _) in routes.items():
        view = views.setdefault(view_name, {"positions": {}, "routes": {}})
        view["routes"][handle] = {"style": "orthogonal", "points": points}
    for (view_name, member), (style_value, _) in view_styles.items():
        view = views.setdefault(view_name, {"positions": {}, "routes": {}})
        view[member] = style_value
    if (
        resolved_named_markings
        or views
        or decorations
        or extensions is not None
        or metadata_handles
    ):
        payload_handles: dict[str, Any] = {}
        for handle in sorted(metadata_handles):
            resolved_ids = arc_handles[handle]
            if len(resolved_ids) != 1:
                raise _resolution_error(
                    "PN202",
                    f"metadata arc handle '@{handle}' must identify exactly one arc",
                    arc_handle_spans[handle],
                )
            arc_object = arc_objects[resolved_ids[0]]
            current_index = current_arc_indexes[id(arc_object)]
            resolved_arc = arcs[current_index]
            if "consume" in resolved_arc:
                fingerprint = {
                    "from": deepcopy(resolved_arc["from"]),
                    "to": deepcopy(resolved_arc["to"]),
                    "type": resolved_arc["consume"]["type"],
                    "mode": resolved_arc["consume"].get("mode", "consume"),
                }
            else:
                fingerprint = {
                    "from": deepcopy(resolved_arc["from"]),
                    "to": deepcopy(resolved_arc["to"]),
                    "type": resolved_arc["produce"]["type"],
                    "mode": "produce",
                }
            payload_handles[handle] = {
                "index": current_index,
                "fingerprint": fingerprint,
            }
        payload: dict[str, Any] = {
            "arcHandles": payload_handles,
            "markings": resolved_named_markings,
            "views": views,
            "extensions": extensions[0] if extensions is not None else {},
        }
        if decorations:
            payload["decorations"] = {
                subject: {member: fact[0] for member, fact in facts.items()}
                for subject, facts in decorations.items()
            }
        result.setdefault("annotations", {})["petrinet.dsl/v1"] = payload

    try:
        parse_net(result)
    except NetValidationError as error:
        parser_message = str(error)
        for transition, keys in binding_names.items():
            if f"bindingNames on transition {transition!r}" in parser_message:
                raise _resolution_error(
                    "PN202",
                    f"binding names on transition [{transition}] must name "
                    "exactly the places it consumes or reads",
                    next(iter(keys.values()))[1],
                    "give each consume or read input place one bind fact",
                ) from None
        for transition, (clock, _, timer_span) in timers.items():
            if f"transition {transition!r}" not in parser_message:
                continue
            if "references undeclared" in parser_message:
                raise _resolution_error(
                    "PN201",
                    f"timer clock place ({clock}) for transition "
                    f"[{transition}] is not declared",
                    timer_span,
                    "declare the clock place in topology before using it in a timer",
                ) from None
            for bind_name, (place, bind_span) in timer_binds.get(
                transition, {}
            ).items():
                if f"bind variable {bind_name!r}" not in parser_message:
                    continue
                if bind_name == "clock":
                    raise _resolution_error(
                        "PN202",
                        f"timer bind name 'clock' is reserved on transition "
                        f"[{transition}]",
                        bind_span,
                        "choose a bind name other than 'clock'",
                    ) from None
                raise _resolution_error(
                    "PN202",
                    f"timer bind {bind_name!r} on transition [{transition}] "
                    f"names place ({place}), but that place does not feed "
                    f"[{transition}] through a consume or read arc",
                    bind_span,
                    "bind the variable to a consume or read input place",
                ) from None
            if "invalid CEL expression" in parser_message:
                raise _resolution_error(
                    "PN203",
                    f"invalid CEL timer for transition [{transition}]",
                    timer_span,
                    "fix the CEL expression syntax",
                ) from None
        raise
    return result
