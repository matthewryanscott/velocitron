"""Render a checked play path as a walkthrough, and as trace JSON.

A walkthrough draws the subnet the path touches once, with its starting
marking, and then one section per step that changes the marking: the
marking before and after as two Graphviz graphs with one layout, the
checks that follow the step, and the step's prose. A step's graphs draw the
step's scope (:data:`WalkScope`): by default only its transition and that
transition's places. Every graph goes through the ordinary rendering pass
(:func:`velocitron_viz.net_render_model`, :func:`velocitron_viz.net_twin_dots`),
so the net's views, decorations, fusion copies and ``beside`` carry over;
the walkthrough adds highlights and per-token row marks.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import asdict, is_dataclass, replace
from typing import Any, Literal, cast

from velocitron_engine import Arc, Marking, Net, Place, Token
from velocitron_play import (
    TRUNK,
    AssumeGuardBody,
    AssumePredicateBody,
    ExpectBody,
    FireBody,
    InjectBody,
    SequenceMode,
    Step,
    UpdateBody,
    WalkScope,
)
from velocitron_viz import (
    DEFAULT_VIEW,
    DETAIL_LEVELS,
    Decoration,
    Decorations,
    Detail,
    PairSide,
    RenderStyle,
    TokenChanges,
    TokenMark,
    apply_view,
    has_view,
    member_label,
    net_render_model,
    net_twin_dots,
    read_fusion_modes,
    view_setting,
)

from .check import CheckResult, PlayNet, PlayTrace, StepFailure, StepResult
from .sequence import render_plantuml, sequence_view

WalkthroughFormat = Literal["md", "json"]


# ── Trace JSON ───────────────────────────────────────────────────────────


def marking_json(marking: Marking) -> dict[str, list[dict[str, Any]]]:
    """A marking as JSON: places in name order, empty places left out."""
    return {
        place: [{"type": t.type, "data": t.data} for t in marking[place]]
        for place in sorted(marking)
        if marking[place]
    }


def _serialize_record_value(obj: Any) -> Any:
    """JSON for a token or dataclass on a firing record.

    The same vocabulary ``velocitron_journal.serialize_record_value`` uses
    for token payloads. Journal storage stays in the language implementation.
    """
    if isinstance(obj, Token):
        return {"type": obj.type, "data": obj.data}
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"cannot serialize {type(obj)!r} into a record payload")


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_serialize_record_value))


def _record_json(record: Mapping[str, Any]) -> dict[str, Any]:
    if "injectionId" in record:
        return {
            "kind": "injection",
            "place": record["place"],
            "injectionKind": record["kind"],
            "tokens": _plain(record["tokens"]),
            "replaced": _plain(record["replaced"]),
        }
    return {
        "kind": "firing",
        "transition": record["transition"],
        "status": record["status"],
        "inputTokens": _plain(record["inputTokens"]),
        "outputTokens": _plain(record["outputTokens"]),
    }


def trace_json(trace: PlayTrace) -> dict[str, Any]:
    """The trace as JSON for fixtures and tools: per step the statement, the
    marking after it, the engine records, the marking after each record and
    the checks. Timestamps, which the engine takes from the wall clock, are
    left out."""
    steps: list[dict[str, Any]] = []
    for result in trace.steps:
        steps.append(
            {
                "line": result.step.position.line,
                "kind": result.step.kind,
                "statement": result.step.statement,
                "records": [
                    _record_json(cast(Mapping[str, Any], r)) for r in result.records
                ],
                "afterEach": [marking_json(m) for m in result.markings],
                "checks": [check.as_json() for check in result.checks],
                "after": marking_json(result.after),
            }
        )
    failure = trace.failure
    return {
        "play": trace.play.name,
        "path": trace.path.name,
        "status": "passed" if failure is None else "failed",
        "inherited": trace.inherited,
        "initial": marking_json(trace.initial),
        "steps": steps,
        "failure": None
        if failure is None
        else {
            "line": failure.step.position.line,
            "statement": failure.step.statement,
            "code": failure.diagnostic.code,
            "message": failure.diagnostic.message,
            "details": list(failure.diagnostic.details),
        },
    }


# ── The touched subnet ───────────────────────────────────────────────────


def _touched(trace: PlayTrace) -> tuple[set[str], set[str]]:
    """Places and transitions the walkthrough draws.

    Every transition a step fires or names, with every place on its arcs
    (inhibit, read and its timer's clock included), and every place a step
    injects into, updates or checks.
    """
    net = trace.subject.net
    transitions: set[str] = set()
    places: set[str] = set()
    steps: list[Step] = [result.step for result in trace.steps]
    if trace.failure is not None:
        steps.append(trace.failure.step)
    names = trace.subject.place_names
    for step in steps:
        body = step.body
        if isinstance(body, FireBody):
            transitions.add(body.transition.name)
        elif isinstance(body, ExpectBody):
            for condition in body.conditions:
                transitions.update(t.name for t in condition.transitions)
                if condition.place is not None:
                    places.add(names[condition.place.name])
    for result in trace.steps:
        for place in (*result.produced, *result.replaced):
            places.add(place)
    if trace.failure is not None:
        body = trace.failure.step.body
        if isinstance(body, (InjectBody, UpdateBody)):
            places.add(names[body.place.name])
    for arc in net.arcs:
        if arc.to_transition in transitions and arc.from_place is not None:
            places.add(arc.from_place)
        if arc.from_transition in transitions and arc.to_place is not None:
            places.add(arc.to_place)
    for tr in net.transitions:
        if tr.name in transitions and tr.timer is not None:
            places.add(tr.timer.clock)
    return places, transitions


def _subnet(
    net: Net,
    places: set[str],
    transitions: set[str],
    faded: AbstractSet[str] = frozenset(),
) -> tuple[Net, dict[int, int]]:
    """``net`` cut down to the given nodes, with an old → new arc index map.

    A ``faded`` transition keeps no arc to a fusion place, which would draw
    one more copy of that place just for it."""
    fusion = {p.name for p in net.places if _is_fusion(p)}
    arc_map: dict[int, int] = {}
    arcs: list[Arc] = []
    for index, arc in enumerate(net.arcs):
        place = arc.from_place if arc.from_place is not None else arc.to_place
        transition = (
            arc.to_transition if arc.to_transition is not None else arc.from_transition
        )
        if transition in faded and place in fusion:
            continue
        if place in places and transition in transitions:
            arc_map[index] = len(arcs)
            arcs.append(arc)
    subnet = Net(
        name=net.name,
        places=[p for p in net.places if p.name in places],
        transitions=[t for t in net.transitions if t.name in transitions],
        arcs=arcs,
        initial_marking=None,
        description=net.description,
    )
    return subnet, arc_map


def _step_nodes(
    net: Net, step: Step, places_changed: Sequence[str], scope: WalkScope
) -> tuple[set[str], set[str], set[str]]:
    """Places, transitions and faded transitions one step's graph draws.

    ``step`` (and ``neighbors``) draw a firing's transition and every place
    on its arcs, its timer's clock included. An injection, update or advance
    draws its place alone. ``neighbors`` adds, faded, the other transitions
    on those places, except on a fusion place: the renderer draws a fusion
    place as a copy at each transition, so its other users are not
    neighbors in the picture.
    """
    places: set[str] = set(places_changed)
    transitions: set[str] = set()
    body = step.body
    if isinstance(body, FireBody):
        name = body.transition.name
        transitions.add(name)
        for arc in net.arcs:
            if arc.to_transition == name and arc.from_place is not None:
                places.add(arc.from_place)
            if arc.from_transition == name and arc.to_place is not None:
                places.add(arc.to_place)
        for transition in net.transitions:
            if transition.name == name and transition.timer is not None:
                places.add(transition.timer.clock)
    faded: set[str] = set()
    if scope == "neighbors":
        fusion = {p.name for p in net.places if _is_fusion(p)}
        hubs = places - fusion
        for arc in net.arcs:
            place = arc.from_place if arc.from_place is not None else arc.to_place
            other = (
                arc.to_transition
                if arc.to_transition is not None
                else arc.from_transition
            )
            if place in hubs and other is not None and other not in transitions:
                faded.add(other)
        for transition in net.transitions:
            timer = transition.timer
            if (
                timer is not None
                and timer.clock in hubs
                and transition.name not in transitions
            ):
                faded.add(transition.name)
    return places, transitions | faded, faded


def _is_fusion(place: Place) -> bool:
    return bool(place.annotations and place.annotations.get("fusion"))


def _unfuse_lone_places(net: Net) -> Net:
    """Drop the fusion tag of a place with no arc in ``net``.

    A fusion place is drawn as one copy per arc's transition, so a fusion
    place with no arc here would not be drawn at all.
    """
    linked = {arc.from_place for arc in net.arcs} | {arc.to_place for arc in net.arcs}
    places = [
        replace(
            place,
            annotations={
                k: v for k, v in (place.annotations or {}).items() if k != "fusion"
            },
        )
        if _is_fusion(place) and place.name not in linked
        else place
        for place in net.places
    ]
    return replace(net, places=places)


def _remap_decorations(
    decorations: Decorations, arc_map: Mapping[int, int]
) -> Decorations:
    return Decorations(
        nodes=dict(decorations.nodes),
        arcs={
            arc_map[index]: decoration
            for index, decoration in decorations.arcs.items()
            if index in arc_map
        },
        quiet_colors=decorations.quiet_colors,
        shown_fields=decorations.shown_fields,
    )


def _stage_view(
    document: Mapping[str, Any], subnet: Net, arc_map: Mapping[int, int]
) -> dict[str, Any]:
    """The default view, cut down to the subnet: positions of kept nodes,
    routes of kept arcs, and the view's style facts."""
    payload = cast(
        Mapping[str, Any],
        cast(Mapping[str, Any], document["annotations"])["petrinet.dsl/v1"],
    )
    view = cast(
        Mapping[str, Any], cast(Mapping[str, Any], payload["views"])[DEFAULT_VIEW]
    )
    kept = {f"place:{p.name}" for p in subnet.places} | {
        f"transition:{t.name}" for t in subnet.transitions
    }
    positions = {
        subject: entry
        for subject, entry in cast(Mapping[str, Any], view.get("positions", {})).items()
        if subject in kept
    }
    while True:
        orphans = [
            subject
            for subject, entry in positions.items()
            if isinstance(entry, dict)
            and "from" in entry
            and cast(dict[str, Any], entry)["from"] not in positions
        ]
        if not orphans:
            break
        for subject in orphans:
            del positions[subject]
    handles = cast(Mapping[str, Any], payload.get("arcHandles", {}))
    new_handles: dict[str, Any] = {}
    routes: dict[str, Any] = {}
    for handle, route in cast(Mapping[str, Any], view.get("routes", {})).items():
        entry = cast(Mapping[str, Any], handles.get(handle, {}))
        index = entry.get("index")
        if isinstance(index, int) and index in arc_map:
            new_handles[handle] = {**entry, "index": arc_map[index]}
            routes[handle] = route
    new_view = {**view, "positions": positions, "routes": routes}
    return {
        "annotations": {
            "petrinet.dsl/v1": {
                "views": {DEFAULT_VIEW: new_view},
                "arcHandles": new_handles,
            }
        }
    }


# ── Marks and decorations per step ───────────────────────────────────────


def _mark(
    marks: dict[str, list[TokenMark | None]],
    marking: Marking,
    tokens: Mapping[str, Sequence[Token]],
    mark: TokenMark,
) -> None:
    """Mark, in each place, the first unmarked token equal to each given one."""
    for place, wanted in tokens.items():
        present = list(marking.get(place, ()))
        row = marks.setdefault(place, [None] * len(present))
        for token in wanted:
            for position, candidate in enumerate(present):
                if row[position] is None and candidate == token:
                    row[position] = mark
                    break


def _highlight(
    decorations: Decorations, key: str, label: str | None, *, failure: bool = False
) -> Decorations:
    current = decorations.nodes.get(key, Decoration())
    nodes = dict(decorations.nodes)
    nodes[key] = replace(
        current, highlight=True, highlight_label=label, failure=failure
    )
    return replace(decorations, nodes=nodes)


def _changed_paths(old: Any, new: Any, prefix: str = "") -> set[str]:
    """Leaf field paths that ``new`` adds or changes over ``old``."""
    paths: set[str] = set()
    for key, value in cast(Mapping[str, Any], new).items():
        path = f"{prefix}{key}"
        if key not in old:
            paths.add(path)
        elif isinstance(old[key], dict) and isinstance(value, dict):
            paths |= _changed_paths(old[key], value, f"{path}.")
        elif old[key] != value:
            paths.add(path)
    return paths


def _leaves(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Every leaf field of ``data`` by its dotted path."""
    leaves: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            leaves |= _leaves(cast(Mapping[str, Any], value), f"{prefix}{key}.")
        else:
            leaves[f"{prefix}{key}"] = value
    return leaves


def _objects(data: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """``data`` and every object nested in it, each with its path prefix."""
    found: list[tuple[str, Any]] = [(prefix, data)]
    for key, value in data.items():
        if isinstance(value, dict):
            found += _objects(cast(Mapping[str, Any], value), f"{prefix}{key}.")
    return found


def _carried_from(
    new: Token, gone: Sequence[Token]
) -> tuple[Token, str, Mapping[str, Any]] | None:
    """The gone token (and the object in it) that ``new`` carries forward.

    The one gone token of the new token's color, when there is exactly one.
    Otherwise the gone token, or an object nested in it, most of whose
    fields ``new`` keeps unchanged, when exactly one keeps the most: a step
    that turns an ``attempt`` with an embedded ``delivery`` back into a
    ``delivery`` carries that embedded object forward.
    """
    same_color = [token for token in gone if token.type == new.type]
    if len(same_color) == 1:
        return same_color[0], "", same_color[0].data
    kept = _leaves(new.data)
    best: list[tuple[Token, str, Mapping[str, Any]]] = []
    best_count = 0
    for token in gone:
        for prefix, data in _objects(token.data):
            leaves = _leaves(data)
            count = sum(
                1 for path, value in leaves.items() if kept.get(path, ...) == value
            )
            if count * 2 <= len(leaves) or count < best_count:
                continue
            if count > best_count:
                best, best_count = [], count
            best.append((token, prefix, data))
    return best[0] if len(best) == 1 else None


def _step_changes(
    result: StepResult,
) -> list[tuple[Token, Token, frozenset[str], frozenset[str]]]:
    """(old token, new token, old paths, new paths) for each token a step changed.

    A new token's old one is the token it carries forward (see
    :func:`_carried_from`) among those the step consumed (a firing) or
    replaced (an update or a advance). With none, the token is new and nothing
    is marked changed. The new paths are the fields the new token adds or
    changes; the old paths are the same fields, inside the object the new
    token carries forward.
    """
    gone = [
        token
        for tokens in (
            result.consumed
            if isinstance(result.step.body, FireBody)
            else result.replaced
        ).values()
        for token in tokens
    ]
    changes: list[tuple[Token, Token, frozenset[str], frozenset[str]]] = []
    for tokens in result.produced.values():
        for token in tokens:
            carried = _carried_from(token, gone)
            if carried is None:
                continue
            old, prefix, data = carried
            paths = _changed_paths(data, token.data)
            if paths:
                changes.append(
                    (
                        old,
                        token,
                        frozenset(f"{prefix}{path}" for path in paths),
                        frozenset(paths),
                    )
                )
    return changes


def _token_changes(
    marking: Marking, changed: Sequence[tuple[Token, frozenset[str]]]
) -> TokenChanges:
    """Each changed token's paths, aligned with the marking's token order."""
    found: dict[str, list[frozenset[str]]] = {}
    for place, present in marking.items():
        row = [frozenset[str]() for _ in present]
        for token, paths in changed:
            for position, candidate in enumerate(present):
                if not row[position] and candidate == token:
                    row[position] = paths
                    break
        if any(row):
            found[place] = row
    return found


def _step_sides(
    result: StepResult, decorations: Decorations
) -> tuple[PairSide, PairSide]:
    step = result.step
    before_marks: dict[str, list[TokenMark | None]] = {}
    after_marks: dict[str, list[TokenMark | None]] = {}
    before_decorations = decorations
    after_decorations = decorations
    if isinstance(step.body, FireBody):
        _mark(before_marks, result.before, result.consumed, "consumed")
        _mark(before_marks, result.before, result.read, "read")
        _mark(after_marks, result.after, result.read, "read")
        _mark(after_marks, result.after, result.produced, "produced")
        key = f"transition:{step.body.transition.name}"
        before_decorations = _highlight(decorations, key, "fires")
        after_decorations = _highlight(decorations, key, "fired")
    else:
        _mark(before_marks, result.before, result.replaced, "replaced")
        _mark(after_marks, result.after, result.produced, "injected")
        verb = {"inject": "injected", "update": "updated", "advance": "clock moved"}[
            step.kind
        ]
        for place in result.produced:
            key = f"place:{place}"
            before_decorations = _highlight(before_decorations, key, None)
            after_decorations = _highlight(after_decorations, key, verb)
    changes = _step_changes(result)
    return (
        PairSide(
            "before",
            result.before,
            before_decorations,
            before_marks,
            _token_changes(
                result.before, [(old, paths) for old, _, paths, _ in changes]
            ),
        ),
        PairSide(
            "after",
            result.after,
            after_decorations,
            after_marks,
            _token_changes(
                result.after, [(new, paths) for _, new, _, paths in changes]
            ),
        ),
    )


def _caption(result: StepResult, net: Net) -> str:
    """One line on what moved, without token data (the graph shows it).

    Places are named as the graph labels them (:func:`member_label`)."""
    step = result.step
    transition = (
        next(t for t in net.transitions if t.name == step.body.transition.name)
        if isinstance(step.body, FireBody)
        else None
    )

    def counted(tokens: Mapping[str, Sequence[Token]]) -> str:
        return ", ".join(
            f"{len(toks)} in ({member_label(place, transition)})"
            for place, toks in tokens.items()
            if toks
        )

    if isinstance(step.body, FireBody):
        parts = [f"Fired [{step.body.transition.name}]"]
        if result.consumed:
            parts.append(f"consumed {counted(result.consumed)}")
        if result.read:
            parts.append(f"read {counted(result.read)}")
        rules = {
            "carry": "carried over",
            "play": "from the step",
            "merge": "carried over and merged",
            "net": "from the net",
            "nothing": "none, by the step",
        }
        produced = [
            f"({member_label(source.place, transition)}) {source.color}: "
            f"{rules[source.rule]}"
            for source in result.outputs
        ]
        if produced:
            parts.append("outputs " + "; ".join(produced))
        return " · ".join(parts) + "."
    verb = {"inject": "Injected", "update": "Updated", "advance": "Moved the clock:"}[
        step.kind
    ]
    tokens = "; ".join(
        f"({member_label(place)}) "
        + ", ".join(f"{t.type} {_json(t.data)}" for t in toks)
        for place, toks in result.produced.items()
    )
    replaced = sum(len(toks) for toks in result.replaced.values())
    suffix = f", replacing {replaced}" if replaced else ""
    return f"{verb} {tokens}{suffix}."


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# ── The document ─────────────────────────────────────────────────────────


class _Renderer:
    def __init__(self, trace: PlayTrace, rankdir: str, scope: WalkScope) -> None:
        self.trace = trace
        self.rankdir = rankdir
        self.scope: WalkScope = scope
        subject: PlayNet = trace.subject
        places, transitions = _touched(trace)
        self.subnet, self.arc_map = _subnet(subject.net, places, transitions)
        # The net's own highlights keep their labels but lose their fill and
        # pen, so the step's highlight is the one filled node in each graph.
        self.net_decorations = replace(
            subject.decorations,
            nodes={
                k: replace(d, highlight=False)
                for k, d in subject.decorations.nodes.items()
            },
            arcs={
                k: replace(d, highlight=False)
                for k, d in subject.decorations.arcs.items()
            },
        )
        self.decorations = _remap_decorations(self.net_decorations, self.arc_map)
        document = subject.document
        detail: Detail = "full"
        self.splines: str | None = None
        self.view: dict[str, Any] | None = None
        if document is not None and has_view(document, DEFAULT_VIEW):
            view_detail = view_setting(document, DEFAULT_VIEW, "detail")
            if view_detail in DETAIL_LEVELS:
                detail = view_detail
            self.splines = view_setting(document, DEFAULT_VIEW, "splines")
            self.view = _stage_view(document, self.subnet, self.arc_map)
        shown = {
            **subject.decorations.shown_fields,
            **{show.color: show.fields for show in trace.play.shows},
        }
        self.style = RenderStyle(
            detail=detail,
            quiet_colors=self.decorations.quiet_colors,
            shown_fields=shown,
        )

    def stage_dot(self, marking: Marking) -> str:
        model = net_render_model(
            self.subnet,
            rankdir=self.rankdir,
            marking=marking,
            style=self.style,
            decorations=self.decorations,
            fusion_modes=(
                read_fusion_modes(self.view, DEFAULT_VIEW)
                if self.view is not None
                else {}
            ),
        )
        if self.view is not None:
            return apply_view(model, self.view, DEFAULT_VIEW)
        return model.dot

    def step_net(
        self, step: Step, places_changed: Sequence[str]
    ) -> tuple[Net, Decorations]:
        """The net a step's graph draws, with its decorations, by scope."""
        if self.scope == "subnet":
            return self.subnet, self.decorations
        net = self.trace.subject.net
        places, transitions, faded = _step_nodes(net, step, places_changed, self.scope)
        subnet, arc_map = _subnet(net, places, transitions, faded)
        decorations = _remap_decorations(self.net_decorations, arc_map)
        nodes = dict(decorations.nodes)
        arcs = dict(decorations.arcs)
        for name in faded:
            key = f"transition:{name}"
            nodes[key] = replace(nodes.get(key, Decoration()), faded=True)
        for index, arc in enumerate(subnet.arcs):
            other = (
                arc.to_transition
                if arc.to_transition is not None
                else arc.from_transition
            )
            if other in faded:
                arcs[index] = replace(arcs.get(index, Decoration()), faded=True)
        return _unfuse_lone_places(subnet), replace(decorations, nodes=nodes, arcs=arcs)

    def twin_dots(self, result: StepResult) -> tuple[str, str]:
        net, decorations = self.step_net(
            result.step, [*result.produced, *result.replaced]
        )
        before, after = _step_sides(result, decorations)
        return net_twin_dots(
            net,
            before,
            after,
            rankdir=self.rankdir,
            style=self.style,
            splines=self.splines,
        )

    def failure_dot(self, failure: StepFailure) -> str:
        body = failure.step.body
        names = self.trace.subject.place_names
        changed = (
            [names[body.place.name]]
            if isinstance(body, (InjectBody, UpdateBody))
            else []
        )
        net, decorations = self.step_net(failure.step, changed)
        label = {
            "SC301": "not enabled",
            "SC302": "no binding matches",
            "SC303": "output not determined",
            "SC304": "deposit rejected",
        }.get(failure.diagnostic.code, "fails")
        if isinstance(body, FireBody):
            decorations = _highlight(
                decorations,
                f"transition:{body.transition.name}",
                f"✗ {label}",
                failure=True,
            )
        model = net_render_model(
            net,
            rankdir=self.rankdir,
            marking=failure.before,
            style=self.style,
            decorations=decorations,
        )
        return model.dot


def _heading(number: int, step: Step) -> str:
    return f"Step {number} — {step.title or f'`{step.statement}`'}"


def _assume_caption(step: Step) -> str:
    """One line for an `assume` step: what the checker will answer from here."""
    body = step.body
    assert isinstance(body, AssumeGuardBody | AssumePredicateBody)
    value = "true" if body.value else "false"
    if isinstance(body, AssumeGuardBody):
        return f"From here, guard {body.transition.name}'s answer is assumed {value}."
    return f"From here, predicate handler {body.predicate} is assumed {value}."


def _check_line(check: CheckResult) -> str:
    mark = "✓" if check.ok else "✗"
    show = not check.ok or check.kind == "next"
    return f"- {mark} `{check.text}`" + (f" — {check.detail}" if show else "")


def sequence_mode(
    trace: PlayTrace, override: SequenceMode | Literal["none"] | None = None
) -> SequenceMode | None:
    """The path's sequence view: the override, the path's, or the play's."""
    if override is not None:
        return None if override == "none" else override
    return trace.path.sequence or trace.play.sequence


def walkthrough_document(
    trace: PlayTrace,
    *,
    rankdir: str = "TB",
    scope: WalkScope | None = None,
    sequence: SequenceMode | Literal["none"] | None = None,
) -> dict[str, Any]:
    """The walkthrough as a JSON-ready document (the WalkthroughDocument).

    ``steps`` holds one entry per step that changes the marking; each
    ``expect`` adds its checks and prose to the entry before it, or to the
    stage when no step came before it. A branch's replayed prefix is listed
    in ``stage.inherited_steps`` — the same step fields without graphs,
    marked ``inherited`` — so a JSON consumer can retell the prefix; the
    Markdown walkthrough keeps its headings-only list. ``sequence`` holds the path's
    sequence diagram when the play (or ``sequence``) asks for one; with
    ``only``, the stage is ``None`` and ``steps`` is empty.
    """
    play = trace.play
    mode = sequence_mode(trace, sequence)
    sequence_json = (
        None
        if mode is None
        else {"mode": mode, "plantuml": render_plantuml(sequence_view(trace))}
    )
    resolved_scope = scope or play.scope or "step"
    if mode == "only":
        return {
            **_document_head(trace, resolved_scope, rankdir),
            "sequence": sequence_json,
            "stage": None,
            "steps": [],
            "failure": _failure_json(trace.failure),
        }
    renderer = _Renderer(trace, rankdir, resolved_scope)
    inherited = trace.steps[: trace.inherited]
    own = trace.steps[trace.inherited :]
    start = inherited[-1].after if inherited else trace.initial
    numbered = 0
    inherited_titles: list[str] = []
    inherited_steps: list[dict[str, Any]] = []
    for result in inherited:
        if result.step.kind not in ("expect", "assume"):
            numbered += 1
            inherited_titles.append(_heading(numbered, result.step))
            inherited_steps.append(
                {
                    "number": numbered,
                    "heading": _heading(numbered, result.step),
                    "title": result.step.title,
                    "statement": result.step.statement,
                    "line": result.step.position.line,
                    "caption": _caption(result, trace.subject.net),
                    "prose_md": result.step.prose,
                    "status": "inherited",
                }
            )
        elif result.step.kind == "assume":
            inherited_titles.append(f"`{result.step.statement}` (assumed)")
            inherited_steps.append(
                {
                    "number": None,
                    "heading": f"`{result.step.statement}` (assumed)",
                    "title": None,
                    "statement": result.step.statement,
                    "line": result.step.position.line,
                    "caption": _assume_caption(result.step),
                    "prose_md": result.step.prose,
                    "status": "inherited-assumed",
                }
            )
    stage: dict[str, Any] = {
        "dot": renderer.stage_dot(start),
        "checks": [],
        "prose_md": "",
        "inherited": inherited_titles,
        "inherited_steps": inherited_steps,
    }
    steps: list[dict[str, Any]] = []

    def add_checks(
        target: dict[str, Any], step: Step, checks: Sequence[CheckResult]
    ) -> None:
        if step.title:
            target["checks"].append({"title": step.title})
        target["checks"].extend(
            {"ok": c.ok, "text": c.text, "detail": c.detail, "kind": c.kind}
            for c in checks
        )
        if step.prose:
            target["prose_md"] = "\n\n".join(
                filter(None, [target["prose_md"], step.prose])
            )

    for result in own:
        if result.step.kind == "expect":
            add_checks(steps[-1] if steps else stage, result.step, result.checks)
            continue
        if result.step.kind == "assume":
            numbered += 1
            steps.append(
                {
                    "number": numbered,
                    "heading": _heading(numbered, result.step),
                    "title": result.step.title,
                    "statement": result.step.statement,
                    "line": result.step.position.line,
                    "caption": _assume_caption(result.step),
                    "checks": [],
                    "prose_md": result.step.prose,
                    "status": "assumed",
                }
            )
            continue
        numbered += 1
        before_dot, after_dot = renderer.twin_dots(result)
        steps.append(
            {
                "number": numbered,
                "heading": _heading(numbered, result.step),
                "title": result.step.title,
                "statement": result.step.statement,
                "line": result.step.position.line,
                "before_dot": before_dot,
                "after_dot": after_dot,
                "caption": _caption(result, trace.subject.net),
                "checks": [],
                "prose_md": result.step.prose,
                "status": "completed",
            }
        )
    failure = trace.failure
    if failure is not None:
        if failure.step.kind == "expect":
            target = steps[-1] if steps else stage
            add_checks(target, failure.step, failure.checks)
            target["status"] = "failed"
        else:
            numbered += 1
            steps.append(
                {
                    "number": numbered,
                    "heading": _heading(numbered, failure.step),
                    "title": failure.step.title,
                    "statement": failure.step.statement,
                    "line": failure.step.position.line,
                    "before_dot": renderer.failure_dot(failure),
                    "caption": "",
                    "checks": [],
                    "prose_md": failure.step.prose,
                    "status": "failed",
                }
            )
    return {
        **_document_head(trace, renderer.scope, rankdir),
        "sequence": sequence_json,
        "stage": stage,
        "steps": steps,
        "failure": _failure_json(failure),
    }


def _document_head(trace: PlayTrace, scope: str, rankdir: str) -> dict[str, Any]:
    play = trace.play
    path = trace.path
    return {
        "play": play.name,
        "title": play.title or play.name,
        "path": path.name,
        "path_title": path.title,
        "branch_from": path.from_label.name if path.from_label else None,
        "net": trace.subject.label,
        "status": "passed" if trace.failure is None else "failed",
        "scope": scope,
        "direction": rankdir.lower(),
        "prose_md": "\n\n".join(filter(None, [play.prose, path.prose])),
    }


def _failure_json(failure: StepFailure | None) -> dict[str, Any] | None:
    if failure is None:
        return None
    return {
        "code": failure.diagnostic.code,
        "message": failure.diagnostic.message,
        "text": failure.diagnostic.render(),
        "line": failure.step.position.line,
    }


def render_walkthrough(
    trace: PlayTrace,
    *,
    format: WalkthroughFormat = "md",
    rankdir: str = "TB",
    scope: WalkScope | None = None,
    sequence: SequenceMode | Literal["none"] | None = None,
) -> str:
    """Render one checked path as Markdown, or as WalkthroughDocument JSON.

    A failed path renders up to its failing step and ends with the failure.
    """
    document = walkthrough_document(
        trace, rankdir=rankdir, scope=scope, sequence=sequence
    )
    if format == "json":
        return json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    return _markdown(document)


def _fence(dot: str) -> str:
    return f"```dot\n{dot}```"


def _checks_md(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for check in checks:
        if "title" in check:
            lines.append(f"**{check['title']}**")
            continue
        lines.append(
            _check_line(
                CheckResult(
                    text=check["text"],
                    ok=check["ok"],
                    detail=check["detail"],
                    kind=check["kind"],
                )
            )
        )
    return lines


def _markdown(document: Mapping[str, Any]) -> str:
    title = document["title"]
    if document["path"] != TRUNK:
        title += f" — {document['path_title'] or document['path']}"
    blocks: list[str] = [f"# {title}"]
    facts = [f"Net: `{document['net']}`", f"Path: `{document['path']}`"]
    if document["branch_from"]:
        facts.append(f"branches from `@{document['branch_from']}`")
    facts.append(
        "Status: " + ("passed" if document["status"] == "passed" else "failed")
    )
    blocks.append(" · ".join(facts))
    if document["prose_md"]:
        blocks.append(document["prose_md"])
    sequence = document["sequence"]
    if sequence is not None:
        if sequence["mode"] == "beside":
            blocks.append("## Sequence")
        blocks.append(f"```plantuml\n{sequence['plantuml']}```")
    stage = document["stage"]
    if stage is None:
        return "\n\n".join([*blocks, *_failure_md(document)]) + "\n"
    blocks.append("## Starting marking")
    if stage["inherited"]:
        blocks.append(
            "This path first replays these steps:\n\n"
            + "\n".join(f"- {heading}" for heading in stage["inherited"])
        )
    blocks.append(_fence(stage["dot"]))
    checks = _checks_md(stage["checks"])
    if checks:
        blocks.append("\n".join(checks))
    if stage["prose_md"]:
        blocks.append(stage["prose_md"])
    for step in document["steps"]:
        mark = (
            " · assumed"
            if step["status"] == "assumed"
            else (" ✗" if step["status"] == "failed" else "")
        )
        blocks.append(f"## {step['heading']}{mark}")
        if "before_dot" in step:
            blocks.append(_fence(step["before_dot"]))
        if "after_dot" in step:
            blocks.append(_fence(step["after_dot"]))
        if step["caption"]:
            blocks.append(f"*{step['caption']}*")
        checks = _checks_md(step["checks"])
        if checks:
            blocks.append("\n".join(checks))
        if step["prose_md"]:
            blocks.append(step["prose_md"])
    return "\n\n".join([*blocks, *_failure_md(document)]) + "\n"


def _failure_md(document: Mapping[str, Any]) -> list[str]:
    failure = document["failure"]
    if failure is None:
        return []
    return ["## The check stops here\n\n```text\n" + failure["text"] + "\n```"]
