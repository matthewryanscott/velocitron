"""Opt-in static lint checks over a parsed :class:`Net`.

Lint findings are advisory, never errors: every shape flagged here is a
*legitimate* net that :func:`velocitron_petrinet.parse_net` accepts — the lint
exists because some legitimate shapes are far more often bugs than intent
(e.g. a net-generator dropping produce arcs leaves a transition that parses
clean but can never advance the net). Consumers opt in by calling
:func:`lint_net` and deciding what to do with the findings; parsing and
firing behavior are untouched by this module.

Intentional occurrences are acknowledged per-transition through the ADR 0011
documentation-fields carve-out: ``annotations: {"lint": {"suppress":
["<rule-id>"]}}`` on the transition silences that rule for that transition.
An arc-level rule also honors the same block on the flagged arc. A sink
transition can instead be marked as an intended end with ``annotations:
{"end": true}``, which silences ``consume-without-produce`` for it. The engine
continues to ignore ``annotations`` entirely; only this opt-in lint surface
reads the ``lint`` and ``end`` keys.

References: spec/net-schema.md (Lint rules, advisory, opt-in); ADR 0016;
ADR 0011; ADR 0030.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from velocitron_cel import load_celpy
from velocitron_engine import Net, Transition
from velocitron_viz import ViewApplicationError, fusion_layout, read_decorations

# Stable rule id: a transition with >=1 consume-mode arc and zero produce
# arcs. Read- and inhibit-mode arcs are not outputs and do not exempt a
# transition; a transition with ONLY read/inhibit inputs removes nothing and
# is a pure gate/observer, out of this rule's scope.
RULE_CONSUME_WITHOUT_PRODUCE = "consume-without-produce"

# Stable rule id: an inline ``predicate cel`` that selects a field of (or
# indexes) a name that is a color or a place of the net, such as
# ``switch.owner``. A predicate sees only its own token's fields as bare
# names, so such a name reads a field of the arc's token, almost never what
# the author meant (ADR 0030).
RULE_PREDICATE_NAMES_COLOR_OR_PLACE = "predicate-names-color-or-place"

# Stable rule id: a ``correlate cel`` that uses a name other than ``token``
# and ``binding``, such as ``attempt.destination``. A correlate sees only
# those two names, so any other name is an evaluation error, and an error
# rejects the binding without a message.
RULE_CORRELATE_FREE_NAME = "correlate-free-name"

# Stable rule id: a transition with >=1 produce arc and >=1 input arc, all of
# them read or inhibit arcs. Firing it removes nothing, so once enabled it
# stays enabled and adds a token on every firing, without end. A timer does
# not stop it: time only moves forward, so a matured timer stays matured. An
# inhibit arc from a place it produces into, for the color it produces there,
# makes it fire once, and exempts it. A source transition (no input arc) is a
# declared idiom, out of this rule's scope.
RULE_READ_ONLY_PRODUCER = "read-only-producer"

# Stable rule id: a whole-place ``position`` on a fusion place that the
# renderer draws as more than one copy. Every copy is pinned to that one
# point, so ``overlap=scale`` collapses the drawing and Graphviz can fail
# (ADR 0067).
RULE_FUSION_PLACE_POSITION = "fusion-place-position"

# CEL macros whose first argument binds a loop variable, not a free name.
_BINDING_MACROS = frozenset({"all", "exists", "exists_one", "map", "filter"})

# CEL type names: idents that are not free names (``type(x) == int``).
_CEL_TYPE_NAMES = frozenset(
    {"bool", "bytes", "double", "dyn", "int", "list", "map", "null_type"}
    | {"string", "type", "uint"}
)


@dataclass(frozen=True)
class LintFinding:
    """A single advisory lint finding: a stable rule id, the flagged
    transition's name, and a human-readable message.

    A place rule leaves ``transition`` empty and sets ``place`` and
    ``view`` instead.
    """

    rule: str
    transition: str
    message: str
    arc: int | None = None  # index in net.arcs of the flagged arc, if any
    inscription: Literal["predicate", "correlate"] | None = None  # flagged CEL
    place: str | None = None  # fusion place a view positions as one point
    view: str | None = None  # the view that carries that position


def suppressed_rules(annotations: Mapping[str, Any] | None) -> list[str]:
    """The rule ids an element's ``annotations.lint.suppress`` names.

    Anything other than the documented shape (a ``lint`` object carrying a
    ``suppress`` list) suppresses nothing — malformed suppression must fail
    open (the finding still fires) rather than silently silence a rule.
    """
    annotations = annotations or {}
    lint_block = annotations.get("lint")
    if not isinstance(lint_block, dict):
        return []
    suppress = cast("dict[str, Any]", lint_block).get("suppress")
    if not isinstance(suppress, list):
        return []
    return [rule for rule in cast("list[Any]", suppress) if isinstance(rule, str)]


_cel_parser: Any = None


def _parse_cel(expression: str) -> Any:
    """The celpy parse tree of ``expression``, or ``None`` if celpy cannot
    parse it.

    velocitron bundles celpy, whose parser is pure Python, so lint works
    whatever backend evaluates the net.
    """
    global _cel_parser
    if _cel_parser is None:
        _cel_parser = load_celpy().celparser.CELParser()
    try:
        return _cel_parser.parse(expression)
    except Exception:  # noqa: BLE001 - lint fails open on parser differences
        return None


def _macro_variables(tree: Any) -> set[str]:
    """Names a macro binds (``x`` in ``items.exists(x, x.ok)``)."""
    macro_variables: set[str] = set()
    for node in tree.iter_subtrees():
        if node.data == "member_dot_arg" and str(node.children[1]) in _BINDING_MACROS:
            first_argument = node.children[2].children[0]
            for ident in first_argument.find_data("ident"):
                macro_variables.add(str(ident.children[0]))
    return macro_variables


def _selected_names(expression: str) -> Iterator[tuple[str, str]]:
    """Free names that the CEL ``expression`` selects a field of or indexes.

    Yields ``(name, written)`` in source order, where ``written`` is the
    selection as the author wrote it (``switch.owner`` or ``switch[...]``).
    Names a macro binds are skipped. An expression celpy cannot parse yields
    nothing.
    """
    tree = _parse_cel(expression)
    if tree is None:
        return
    macro_variables = _macro_variables(tree)
    for node in tree.iter_subtrees_topdown():
        if node.data not in ("member_dot", "member_index"):
            continue
        operand = node.children[0]
        if operand.data != "member" or operand.children[0].data != "primary":
            continue
        primary = operand.children[0].children[0]
        if getattr(primary, "data", None) != "ident":
            continue
        name = str(primary.children[0])
        if name in macro_variables:
            continue
        if node.data == "member_dot":
            yield name, f"{name}.{node.children[1]}"
        else:
            yield name, f"{name}[...]"


def _predicate_findings(
    net: Net,
    transition: str,
    arc_index: int,
    colors: set[str],
    places: set[str],
) -> list[LintFinding]:
    arc = net.arcs[arc_index]
    consume = arc.consume
    assert consume is not None and arc.from_place is not None
    if consume.predicate is None or consume.predicate.cel is None:
        return []
    findings: list[LintFinding] = []
    reported: set[str] = set()
    for name, written in _selected_names(consume.predicate.cel):
        if name in reported or (name not in colors and name not in places):
            continue
        reported.add(name)
        rest = written[len(name) :]
        where = (
            f"predicate cel on the arc from {arc.from_place!r} to "
            f"{transition!r} uses {written!r}"
        )
        if name == consume.type:
            fix = (
                f"write {rest[1:]!r}"
                if rest.startswith(".")
                else f"drop the {name!r} prefix"
            )
            advice = (
                f"but a predicate sees its own {name!r} token's fields as bare "
                f"names; {fix}"
            )
        else:
            kind = (
                "a color and a place"
                if name in colors and name in places
                else "a color"
                if name in colors
                else "a place"
            )
            sources = [
                other.from_place
                for other in net.arcs
                if other.to_transition == transition
                and other.consume is not None
                and other.consume.mode != "inhibit"
                and other is not arc
                and (other.consume.type == name or other.from_place == name)
            ]
            example = f" (here binding.{sources[0]}[0]{rest})" if sources else ""
            advice = (
                f"but {name!r} is {kind}, and a predicate sees only its own "
                f"{consume.type!r} token's fields as bare names; for a condition "
                "between tokens use correlate cel over token and "
                f"binding{example}"
            )
        findings.append(
            LintFinding(
                rule=RULE_PREDICATE_NAMES_COLOR_OR_PLACE,
                transition=transition,
                message=f"{where}, {advice}",
                arc=arc_index,
                inscription="predicate",
            )
        )
    return findings


def binding_keys(net: Net, transition: Transition) -> dict[str, str]:
    """The keys of the ``binding`` the transition's CEL sees, each to its place."""
    if transition.binding_names is not None:
        return dict(transition.binding_names)
    return {
        arc.from_place: arc.from_place
        for arc in net.arcs
        if arc.to_transition == transition.name
        and arc.from_place is not None
        and arc.consume is not None
        and arc.consume.mode != "inhibit"
    }


def _correlate_findings(
    net: Net, transition: str, arc_index: int, binding_keys: Mapping[str, str]
) -> list[LintFinding]:
    arc = net.arcs[arc_index]
    consume = arc.consume
    assert consume is not None and arc.from_place is not None
    if consume.correlate is None:
        return []
    tree = _parse_cel(consume.correlate)
    if tree is None:
        return []
    allowed = {"token", "binding"} | _CEL_TYPE_NAMES | _macro_variables(tree)
    selections: dict[str, str] = {}
    for name, written in _selected_names(consume.correlate):
        selections.setdefault(name, written)
    key_of_place = {place: key for key, place in binding_keys.items()}
    findings: list[LintFinding] = []
    reported: set[str] = set()
    for node in tree.iter_subtrees_topdown():
        if node.data != "ident":
            continue
        name = str(node.children[0])
        if name in allowed or name in reported:
            continue
        reported.add(name)
        written = selections.get(name, name)
        rest = written[len(name) :]
        bound_places = [
            other.from_place
            for other in net.arcs
            if other.to_transition == transition
            and other.consume is not None
            and other.consume.mode != "inhibit"
            and other is not arc
            and other.consume.type == name
            and other.from_place in key_of_place
        ]
        if name in (consume.type, arc.from_place):
            fix = f"for this arc's token write 'token{rest}'"
        elif name in binding_keys:
            fix = f"write 'binding.{name}[0]{rest}'"
        elif bound_places:
            fix = f"write 'binding.{key_of_place[bound_places[0]]}[0]{rest}'"
        elif not rest:
            fix = f"for a field of this arc's token write 'token.{name}'"
        else:
            fix = (
                "read this arc's token as 'token' and another arc's token as "
                "'binding.<place>[0]'"
            )
        findings.append(
            LintFinding(
                rule=RULE_CORRELATE_FREE_NAME,
                transition=transition,
                message=(
                    f"correlate cel on the arc from {arc.from_place!r} to "
                    f"{transition!r} uses {written!r}, but a correlate sees only "
                    "'token' (this arc's token) and 'binding' (the bound tokens "
                    f"by place), so {name!r} is an evaluation error, which "
                    f"rejects the binding; {fix}"
                ),
                arc=arc_index,
                inscription="correlate",
            )
        )
    return findings


def _read_only_producer_finding(net: Net, transition: str) -> LintFinding | None:
    inputs = [arc for arc in net.arcs if arc.to_transition == transition]
    outputs = [arc for arc in net.arcs if arc.from_transition == transition]
    if (
        not inputs
        or not outputs
        or any(
            arc.consume is not None and arc.consume.mode == "consume" for arc in inputs
        )
    ):
        return None
    produced = {(arc.to_place, arc.produce.type) for arc in outputs if arc.produce}
    if any(
        arc.consume is not None
        and arc.consume.mode == "inhibit"
        and (arc.from_place, arc.consume.type) in produced
        for arc in inputs
    ):
        return None
    places = ", ".join(dict.fromkeys(f"({arc.to_place})" for arc in outputs))
    return LintFinding(
        rule=RULE_READ_ONLY_PRODUCER,
        transition=transition,
        message=(
            f"[{transition}] reads but consumes nothing, so it can fire again "
            f"and again, adding a token to {places} each time; consume a "
            "token, or inhibit it on its own output so it fires once"
        ),
    )


def _is_fusion_place(annotations: Mapping[str, Any] | None) -> bool:
    return bool(annotations and annotations.get("fusion"))


def _fusion_position_findings(net: Net) -> list[LintFinding]:
    """Whole-place positions that pin every copy of a fusion place at once."""
    annotations = net.annotations or {}
    payload_raw = annotations.get("petrinet.dsl/v1")
    if not isinstance(payload_raw, Mapping):
        return []
    payload = cast("Mapping[str, Any]", payload_raw)
    views_raw = payload.get("views")
    if not isinstance(views_raw, Mapping):
        return []
    views = cast("Mapping[str, Any]", views_raw)
    fusion = {
        place.name: place for place in net.places if _is_fusion_place(place.annotations)
    }
    if not fusion:
        return []
    candidates: list[tuple[str, str]] = []
    for view_name, view_raw in views.items():
        if not isinstance(view_raw, Mapping):
            continue
        view = cast("Mapping[str, Any]", view_raw)
        positions_raw = view.get("positions")
        if not isinstance(positions_raw, Mapping):
            continue
        positions = cast("Mapping[str, Any]", positions_raw)
        for subject in positions:
            if not subject.startswith("place:"):
                continue
            name = subject.removeprefix("place:")
            if name in fusion:
                candidates.append((view_name, name))
    if not candidates:
        return []
    try:
        decorations = read_decorations({"annotations": annotations})
    except ViewApplicationError:
        return []
    layout = fusion_layout(net, set(fusion), decorations)
    drawn: dict[str, set[str]] = {}
    for (name, _transition), copy in layout.copies.items():
        drawn.setdefault(name, set()).add(copy)
    findings: list[LintFinding] = []
    reported: set[tuple[str, str]] = set()
    for view_name, name in candidates:
        if (view_name, name) in reported:
            continue
        reported.add((view_name, name))
        if RULE_FUSION_PLACE_POSITION in suppressed_rules(fusion[name].annotations):
            continue
        count = len(drawn.get(name, ()))
        if count <= 1:
            continue
        findings.append(
            LintFinding(
                rule=RULE_FUSION_PLACE_POSITION,
                transition="",
                place=name,
                view=view_name,
                message=(
                    f"view {view_name!r} positions fusion place {name!r}, which "
                    f"draws {count} copies; a whole-place position stacks every "
                    "copy on one point"
                ),
            )
        )
    return findings


def lint_net(net: Net) -> list[LintFinding]:
    """Run all lint rules over a parsed net; return advisory findings.

    Findings follow transition declaration order; within a transition the
    transition-level rules come first, then arc findings in arc declaration
    order. Place findings follow, in view order and then position order.
    An empty list means the net is clean under every (non-suppressed) rule.
    """
    consuming_transitions: set[str] = set()
    producing_transitions: set[str] = set()
    colors: set[str] = set()
    for arc in net.arcs:
        if arc.consume is not None and arc.consume.mode == "consume":
            assert arc.to_transition is not None  # parser-enforced direction
            consuming_transitions.add(arc.to_transition)
        if arc.produce is not None:
            assert arc.from_transition is not None  # parser-enforced direction
            producing_transitions.add(arc.from_transition)
    for place in net.places:
        colors.update(place.accepts)
    places = {place.name for place in net.places}
    findings: list[LintFinding] = []
    for transition in net.transitions:
        suppressed = suppressed_rules(transition.annotations)
        if (
            transition.name in consuming_transitions
            and transition.name not in producing_transitions
            and RULE_CONSUME_WITHOUT_PRODUCE not in suppressed
            and (transition.annotations or {}).get("end") is not True
        ):
            findings.append(
                LintFinding(
                    rule=RULE_CONSUME_WITHOUT_PRODUCE,
                    transition=transition.name,
                    message=(
                        f"transition {transition.name!r} consumes but never "
                        f"produces — likely missing produce arc; if this is an "
                        f'intended end, mark it with annotations {{"end": true}} '
                        f"([{transition.name}] annotation end true)"
                    ),
                )
            )
        if RULE_READ_ONLY_PRODUCER not in suppressed:
            finding = _read_only_producer_finding(net, transition.name)
            if finding is not None:
                findings.append(finding)
        keys = binding_keys(net, transition)
        for arc_index, arc in enumerate(net.arcs):
            if arc.to_transition != transition.name or arc.consume is None:
                continue
            arc_suppressed = suppressed + suppressed_rules(arc.annotations)
            if RULE_PREDICATE_NAMES_COLOR_OR_PLACE not in arc_suppressed:
                findings.extend(
                    _predicate_findings(net, transition.name, arc_index, colors, places)
                )
            if RULE_CORRELATE_FREE_NAME not in arc_suppressed:
                findings.extend(
                    _correlate_findings(net, transition.name, arc_index, keys)
                )
    findings.extend(_fusion_position_findings(net))
    return findings


__all__ = [
    "RULE_CONSUME_WITHOUT_PRODUCE",
    "RULE_CORRELATE_FREE_NAME",
    "RULE_FUSION_PLACE_POSITION",
    "RULE_PREDICATE_NAMES_COLOR_OR_PLACE",
    "RULE_READ_ONLY_PRODUCER",
    "LintFinding",
    "binding_keys",
    "lint_net",
    "suppressed_rules",
]
