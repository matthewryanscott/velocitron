"""The runtime composition merge engine.

Produces the combined :class:`Net` from a validated :class:`Composition`:
alias-qualifies every place/transition/arc endpoint, fuses wired port-places
into single shared places (place-fusion realization), rewrites arc endpoints
and produce destinations, and re-exposes unwired ports as the composition's
own boundary ports. The output is one :class:`Net`, verifiable as a single
Petri net and runnable by :class:`Engine`.

This module is the merge transform only — parsing and ``parse_composition``
validation live in :mod:`velocitron_petrinet`. The merge is a distinct,
file-free transform over already-parsed nets.

This module is the source of truth for the transform. It does not import
``velocitron``. ``velocitron_petrinet`` calls it, then validates the
merged net. ``merge_composition`` here requires ``parsed_nets``.

References: spec/composition.md; ADR 0004.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from .errors import NetValidationError
from .refine import validate_refinements
from .types import (
    Arc,
    Composition,
    DeclaredInvariant,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    ProofFacts,
    Refinement,
    Share,
    Timer,
    Token,
    Transition,
    Wire,
)


def _map_timer_places(
    timer: Timer | None, rename: Callable[[str], str]
) -> Timer | None:
    """Apply ``rename`` to a timer's place references (clock + bind values).

    The timer's CEL string is NEVER touched — it references only the reserved
    ``clock`` variable and the ``bind`` aliases, which is what makes a timed
    transition composition-safe (ADR 0018): the merge rewrites the place
    *values* exactly as it rewrites arc endpoints (alias-qualification here,
    fusion rewriting via the rewrite map), and the expression survives.
    """
    if timer is None:
        return None
    return Timer(
        clock=rename(timer.clock),
        cel=timer.cel,
        bind=(
            {var: rename(place) for var, place in timer.bind.items()}
            if timer.bind is not None
            else None
        ),
        maturity=timer.maturity,
    )


class _UnionFind:
    """Minimal union-find over port-place qualified names (N-ary fusion).

    Fan-out (one output wired to several inputs) and fan-in (several outputs
    wired to one input) both collapse to a single equivalence class, hence a
    single shared place.
    """

    def __init__(self, names: set[str]) -> None:
        self._parent: dict[str, str] = {n: n for n in names}

    def find(self, name: str) -> str:
        root = name
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression.
        while self._parent[name] != root:
            self._parent[name], name = root, self._parent[name]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def _member_precedence(
    members: list[str], qname_to_place: dict[str, Place]
) -> list[str]:
    """A fused class's members in the order they win conflicts
    (spec/composition.md "Fused-place annotations").

    Output (source) ports come before input ports — the fused place is
    named after its sources, and they take the same precedence — each
    group in sorted qualified-name order.
    """

    def _is_output(name: str) -> bool:
        port = qname_to_place[name].port
        return port is not None and port.direction == "output"

    ordered = sorted(m for m in members if _is_output(m))
    ordered += sorted(m for m in members if not _is_output(m))
    return ordered


def _fused_description(
    ordered: list[str], qname_to_place: dict[str, Place]
) -> str | None:
    """The first member's description, in precedence order."""
    return next((d for m in ordered if (d := qname_to_place[m].description)), None)


def _fused_annotations(
    ordered: list[str], qname_to_place: dict[str, Place]
) -> dict[str, Any]:
    """Annotations for a fused place: the members' annotations, the
    earliest member in precedence order winning conflicting keys. The
    ``fusion: true`` tag is set last, overriding any member value, so the
    viz renderer's fusion-place styling triggers on every fused place.
    """
    annotations: dict[str, Any] = {}
    for m in ordered:
        for key, value in (qname_to_place[m].annotations or {}).items():
            annotations.setdefault(key, value)
    annotations["fusion"] = True
    return annotations


def _fusion_classes(
    qname_to_place: Mapping[str, Place],
    wires: Sequence[Wire],
    shares: Sequence[Share] = (),
) -> dict[str, list[str]]:
    """Each fused place's name → its member port qualified names, sorted.

    A wire joins an output port (from) to an input port (to); fusion is the
    equivalence relation induced by all wires. Only wired port names
    participate — an unwired port stays a boundary (no class, no fusion).
    The fused name is the sorted `__`-concatenation of the class's OUTPUT
    (source) port qualified names — the place is named after what deposits
    into it. Input ports are class members but never appear in the name.
    Deterministic regardless of wire ordering; handles fan-in (multiple
    sources) without a tiebreaker.

    A share (ADR 0040) joins its member places into the same relation,
    with no direction. A class with no output port among its members is
    named after all of them.
    """
    wire_endpoints = [
        (f"{w.from_net}.{w.from_port}", f"{w.to_net}.{w.to_port}") for w in wires
    ]
    share_members = [[f"{net}.{place}" for net, place in s.members] for s in shares]
    wired = {ep for pair in wire_endpoints for ep in pair}
    wired |= {member for members in share_members for member in members}

    uf = _UnionFind(wired)
    for src, dst in wire_endpoints:
        uf.union(src, dst)
    for members in share_members:
        for member in members[1:]:
            uf.union(members[0], member)

    classes: dict[str, list[str]] = {}
    for name in sorted(wired):
        classes.setdefault(uf.find(name), []).append(name)

    named: dict[str, list[str]] = {}
    for members in classes.values():
        source_ports = sorted(
            m
            for m in members
            if (port := qname_to_place[m].port) is not None
            and port.direction == "output"
        )
        named["__".join(source_ports or members)] = members
    return named


def port_fusion_map(
    alias_to_net: Mapping[str, Net],
    wires: Sequence[Wire],
    shares: Sequence[Share] = (),
) -> dict[str, str]:
    """Every wired port's qualified name (``alias.place``) → the name of the
    fused place :func:`merge_nets` makes for it.

    A consumer that names places of the constituent nets (a play
    addressing ``attempt.sending``) resolves a fused port through this map,
    so the ``__`` fused name stays an implementation detail of the merge.
    """
    qname_to_place = {
        f"{alias}.{place.name}": place
        for alias, net in alias_to_net.items()
        for place in net.places
    }
    return {
        member: fused_name
        for fused_name, members in _fusion_classes(
            qname_to_place, wires, shares
        ).items()
        for member in members
    }


def merge_nets(
    alias_to_net: dict[str, Net],
    wires: list[Wire],
    refinements: Sequence[Refinement] = (),
    shares: Sequence[Share] = (),
    name: str = "composition",
    final: Sequence[Sequence[tuple[str, str]]] | None = None,
) -> Net:
    """Merge nets under aliases, fusing wired ports into shared places.

    A pure, file-free transform over already-parsed nets. The language
    implementation validates the returned net before the caller sees it.
    The ``packages/merge`` copy returns that net without the closing
    validation and does not compile CEL.

    Each refinement removes its transition and every arc of that transition;
    the refining net, wired to the same places, takes its part.

    Steps:

    0. Check that each refining net fits the transition it replaces.

    1. Qualify every Place and Transition name with its net alias, and index
       Port facets by qualified name. Refined transitions are left out. A
       transition without an ``actor`` annotation takes its net's default
       actor (the net's own ``actor`` annotation), so actors survive.

    2. Build port-fusion equivalence classes from the Wires and Shares via
       union-find. A Wire joins an output Port to an input Port; a Share
       joins places with no direction (ADR 0040). Only wired Ports and
       shared places participate, so an unwired Port stays a boundary.

    3. Realize each equivalence class as one fused Place, named after its
       sorted output-Port qualified names, and build a rewrite map from every
       member to the fused name. The fused Place is tagged
       ``annotations.fusion = true`` and carries the member Ports'
       description and annotations, output (source) Ports merging before
       input Ports, each group in sorted qualified-name order (earliest
       member wins the description and conflicting keys; the fusion tag is
       set last and always wins).

    4. Rewrite Arc endpoints and ProduceTemplate destinations to the
       qualified or fused names, preserving the Arc-centric representation,
       and record each Transition's ``binding_names`` (local place name →
       merged place) so its CEL keeps its meaning (ADR 0032).

    5. Compose initial markings: qualify keys and merge tokens that land on
       the same fused Place.

    6. Carry every constituent's domains (one value set per color field)
       and proof facts, under the merged place names (ADR 0037), and its
       declared actors, as the merged net's ``actors`` annotation (ADR 0038).

    7. The language implementation validates the composed net. The package
       copy stops before that check.
    """
    # ── 0. Check refinements; collect the refined transitions' qualified names.
    validate_refinements(refinements, wires, alias_to_net, shares)
    refined = {f"{r.net}.{r.transition}" for r in refinements}

    # ── 1. Qualify places and transitions; index port places by qualified name.
    qualified_places: list[Place] = []
    qname_to_place: dict[str, Place] = {}
    qualified_transitions: list[Transition] = []
    for alias, net in alias_to_net.items():
        default_actor = (net.annotations or {}).get("actor")
        for place in net.places:
            qname = f"{alias}.{place.name}"
            # description/annotations carry through qualification — they are
            # doc-only (ADR 0011) but consumers (e.g. the viz renderer's
            # fusion-place styling) read them off the merged net. Fused
            # places (step 3 below) get their members' description and
            # annotations merged, plus the `fusion: true` tag.
            qp = Place(
                name=qname,
                accepts=list(place.accepts),
                port=place.port,
                description=place.description,
                annotations=place.annotations,
            )
            qualified_places.append(qp)
            qname_to_place[qname] = qp
        for t in net.transitions:
            if f"{alias}.{t.name}" in refined:
                continue
            qualified_transitions.append(
                Transition(
                    name=f"{alias}.{t.name}",
                    handler=t.handler,
                    guard=t.guard,
                    priority=t.priority,
                    # Timer place references qualify like arc endpoints; the
                    # fusion rewrite is applied in step 4, once the rewrite
                    # map exists. The CEL string is never touched (ADR 0018).
                    timer=_map_timer_places(t.timer, lambda n, a=alias: f"{a}.{n}"),
                    description=t.description,
                    annotations=_with_actor(t.annotations, default_actor),
                )
            )

    def _q(alias: str, name: str | None) -> str | None:
        return f"{alias}.{name}" if name is not None else None

    # ── 2. Build port-fusion equivalence classes via union-find.
    # rewrite_map: every member of a fused class → the fused place name.
    rewrite_map: dict[str, str] = {}
    fused_places: list[Place] = []
    for fused_name, members in _fusion_classes(qname_to_place, wires, shares).items():
        accepts = list(
            dict.fromkeys(a for m in members for a in qname_to_place[m].accepts)
        )
        ordered = _member_precedence(members, qname_to_place)
        fused_places.append(
            Place(
                name=fused_name,
                accepts=accepts,
                port=None,
                description=_fused_description(ordered, qname_to_place),
                annotations=_fused_annotations(ordered, qname_to_place),
            )
        )
        for m in members:
            rewrite_map[m] = fused_name

    # ── 3. Assemble places: unwired/non-port qualified places + fused places.
    places: list[Place] = [qp for qp in qualified_places if qp.name not in rewrite_map]
    places.extend(fused_places)

    # ── 4. Rewrite arc endpoints and produce destinations to qualified/fused.
    def _rw(name: str | None) -> str | None:
        if name is None:
            return None
        return rewrite_map.get(name, name)

    # Timer place references follow the same fusion rewrite as arc endpoints
    # (a wired clock port fuses into the shared place the timer must read).
    qualified_transitions = [
        t
        if t.timer is None
        else replace(
            t, timer=_map_timer_places(t.timer, lambda n: rewrite_map.get(n, n))
        )
        for t in qualified_transitions
    ]

    # Binding names (ADR 0032): each transition's CEL keeps reading `binding`
    # under its constituent's names. A constituent that already declares them
    # (itself a merge) keeps its keys; otherwise the keys are its local place
    # names. Either way only the place values are rewritten.
    binding_names: dict[str, dict[str, str]] = {}
    for alias, net in alias_to_net.items():
        for t in net.transitions:
            if f"{alias}.{t.name}" in refined:
                continue
            local = dict(t.binding_names or {})
            if t.binding_names is None:
                for arc in net.arcs:
                    if (
                        arc.to_transition == t.name
                        and arc.from_place is not None
                        and arc.consume is not None
                        and arc.consume.mode in ("consume", "read")
                    ):
                        local.setdefault(arc.from_place, arc.from_place)
            if local:
                binding_names[f"{alias}.{t.name}"] = {
                    key: rewrite_map.get(f"{alias}.{place}", f"{alias}.{place}")
                    for key, place in local.items()
                }
    qualified_transitions = [
        replace(t, binding_names=binding_names[t.name])
        if t.name in binding_names
        else t
        for t in qualified_transitions
    ]

    arcs: list[Arc] = []
    for alias, net in alias_to_net.items():
        for arc in net.arcs:
            if _q(alias, arc.to_transition or arc.from_transition) in refined:
                continue
            produce = None
            if arc.produce is not None:
                produce = ProduceTemplate(
                    type=arc.produce.type,
                    destination=rewrite_map.get(
                        f"{alias}.{arc.produce.destination}",
                        f"{alias}.{arc.produce.destination}",
                    ),
                    data=arc.produce.data,
                    cel=arc.produce.cel,
                )
            arcs.append(
                Arc(
                    from_place=_rw(_q(alias, arc.from_place)),
                    from_transition=_q(alias, arc.from_transition),
                    to_place=_rw(_q(alias, arc.to_place)),
                    to_transition=_q(alias, arc.to_transition),
                    consume=arc.consume,
                    produce=produce,
                    description=arc.description,
                    annotations=arc.annotations,
                )
            )

    # ── 5. Compose initial markings: qualify keys, merge fused-place keys.
    composed: dict[str, list[Token]] = {}
    has_marking = False
    for alias, net in alias_to_net.items():
        if net.initial_marking is None:
            continue
        has_marking = True
        for key, tokens in net.initial_marking.items():
            qkey = f"{alias}.{key}"
            target = rewrite_map.get(qkey, qkey)
            composed.setdefault(target, []).extend(tokens)
    initial_marking = Marking(composed) if has_marking else None

    # ── 6. Domains and proof facts (ADR 0037); declared actors (ADR 0038).
    domains = _merged_domains(alias_to_net)
    proofs = _merged_proofs(alias_to_net, rewrite_map, arcs, final)
    actors = _merged_actors(alias_to_net)

    result = Net(
        name=name,
        places=places,
        transitions=qualified_transitions,
        arcs=arcs,
        initial_marking=initial_marking,
        domains=domains or None,
        proofs=proofs,
        annotations={"actors": actors} if actors else None,
    )

    return result


def _merged_domains(alias_to_net: Mapping[str, Net]) -> dict[str, list[Any]]:
    """Every constituent's domains; a color field keeps one value set."""
    merged: dict[str, list[Any]] = {}
    owner: dict[str, str] = {}
    for alias, net in alias_to_net.items():
        for key, values in (net.domains or {}).items():
            if key not in merged:
                merged[key] = list(values)
                owner[key] = alias
                continue
            if _value_set(merged[key]) != _value_set(values):
                raise NetValidationError(
                    f"domain {key} differs between {owner[key]} and {alias}"
                )
    return merged


def _with_actor(
    annotations: dict[str, Any] | None, default_actor: Any
) -> dict[str, Any] | None:
    """A transition's annotations with its net's default actor filled in."""
    if not isinstance(default_actor, str) or "actor" in (annotations or {}):
        return annotations
    return {**(annotations or {}), "actor": default_actor}


def _merged_actors(alias_to_net: Mapping[str, Net]) -> list[dict[str, str]]:
    """Every constituent's declared actors, first declaration first."""
    merged: dict[str, str] = {}
    for alias, net in alias_to_net.items():
        declared = (net.annotations or {}).get("actors")
        if not isinstance(declared, list):
            continue
        for entry in cast(list[Any], declared):
            if not isinstance(entry, Mapping):
                continue
            name = cast(Mapping[str, Any], entry).get("name")
            kind = cast(Mapping[str, Any], entry).get("kind", "system")
            if not isinstance(name, str):
                continue
            if name in merged and merged[name] != kind:
                raise NetValidationError(
                    f"actor {name} is a {merged[name]} in one net "
                    f"and a {kind} in {alias}"
                )
            merged.setdefault(name, kind)
    return [{"name": name, "kind": kind} for name, kind in merged.items()]


def _value_set(values: Sequence[Any]) -> set[str]:
    return {json.dumps(value) for value in values}


def _merged_proofs(
    alias_to_net: Mapping[str, Net],
    rewrite_map: Mapping[str, str],
    arcs: Sequence[Arc],
    composition_final: Sequence[Sequence[tuple[str, str]]] | None = None,
) -> ProofFacts | None:
    """Constituents' proof facts under merged place names.

    A declared invariant keeps its weights (a fused place sums the weights
    of its members). The composition's own final markings replace its nets'
    final places (ADR 0049). Without them, a net's final marking stays final
    only while no arc of the composition reads or takes from its places.
    """
    read = {arc.from_place for arc in arcs if arc.from_place is not None}
    final: list[tuple[str, ...]] = []

    def add(marking: Sequence[str]) -> None:
        places = tuple(dict.fromkeys(marking))
        if all(set(places) != set(known) for known in final):
            final.append(places)

    for marking in composition_final or []:
        add(
            [
                rewrite_map.get(f"{alias}.{place}", f"{alias}.{place}")
                for alias, place in marking
            ]
        )
    invariants: list[DeclaredInvariant] = []
    declared = composition_final is not None
    for alias, net in alias_to_net.items():
        if net.proofs is None:
            continue
        declared = True
        if composition_final is None:
            for marking in net.proofs.final or []:
                places = [
                    rewrite_map.get(f"{alias}.{place}", f"{alias}.{place}")
                    for place in marking
                ]
                if not any(place in read for place in places):
                    add(places)
        for invariant in net.proofs.invariants or []:
            weights: dict[str, int] = {}
            for place, weight in invariant.weights.items():
                name = rewrite_map.get(f"{alias}.{place}", f"{alias}.{place}")
                weights[name] = weights.get(name, 0) + weight
            invariants.append(
                DeclaredInvariant(
                    weights=weights,
                    constant=invariant.constant,
                    name=f"{alias}.{invariant.name}" if invariant.name else None,
                )
            )
    if not declared:
        return None
    return ProofFacts(final=final or None, invariants=invariants or None)


def merge_composition(composition: Composition) -> Net:
    """Merge a validated :class:`Composition` into a single :class:`Net`.

    Uses ``composition.parsed_nets`` when present, closing the
    validate-to-merge gap at no extra parsing cost. The language
    implementation re-parses each net reference when that map is missing.
    The ``packages/merge`` copy requires ``parsed_nets`` and does not read
    files. Both key by the resolved alias and delegate to :func:`merge_nets`.
    """
    if composition.parsed_nets is None:
        raise NetValidationError(
            "merge_composition requires composition.parsed_nets; "
            "this package does not parse net documents"
        )
    alias_to_net: dict[str, Net] = composition.parsed_nets
    return merge_nets(
        alias_to_net,
        composition.wires,
        composition.refinements,
        composition.shares,
        name=composition.name or "composition",
        final=composition.final,
    )
