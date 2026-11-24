"""The net's canonical document and the sha256 registration checks.

Generated modules stamp :func:`net_sha256`. ``velocitron_netbase`` re-exports
these functions and checks the same digest when a generated class registers,
so the two cannot drift. ``velocitron_netbase`` re-exports that package.
:data:`SYNTH_HANDLER` is the prefix a host uses for
a synthesized handler ref. A declared ref that uses it fails generation.

``render_canonical_json`` is the viz package's RFC 8785 renderer. This
module does not import ``velocitron``.
"""

from __future__ import annotations

import hashlib
from typing import Any

from velocitron_engine import Arc, Marking, Net, Place, Transition
from velocitron_viz import render_canonical_json

__all__ = [
    "SYNTH_HANDLER",
    "canonical_net_json",
    "net_document",
    "net_sha256",
]

# A synthesized ref's spelling. The Engine rejects a transition name not
# declared in the net, so no user handler ref — which is always keyed by a
# DECLARED transition's name — can collide with the `velocitron:synth:`
# prefix. Colons do not appear in declared names. ``velocitron_netbase``
# re-exports this same string, and ``velocitron_netbase`` re-exports it.
SYNTH_HANDLER = "velocitron:synth:"


def net_document(net: Net) -> dict[str, Any]:
    """Turn ``net`` back into the canonical JSON document ``parse_net`` reads.

    ``parse_net(net_document(net)) == net`` for every net the language can
    express (the round-trip is the acceptance contract), including merge
    output and synthesized-ref copies built in code.
    """
    document: dict[str, Any] = {"name": net.name}
    if net.description is not None:
        document["description"] = net.description
    if net.annotations is not None:
        document["annotations"] = net.annotations
    if net.domains is not None:
        document["domains"] = {key: list(values) for key, values in net.domains.items()}
    if net.proofs is not None:
        proofs_document: dict[str, Any] = {}
        if net.proofs.final is not None:
            proofs_document["final"] = [
                entry[0] if len(entry) == 1 else [*entry] for entry in net.proofs.final
            ]
        if net.proofs.invariants is not None:
            facts_document: list[dict[str, Any]] = []
            for invariant in net.proofs.invariants:
                fact: dict[str, Any] = {"weights": dict(invariant.weights)}
                if invariant.constant is not None:
                    fact["constant"] = invariant.constant
                if invariant.name is not None:
                    fact["name"] = invariant.name
                facts_document.append(fact)
            proofs_document["invariants"] = facts_document
        document["proofs"] = proofs_document
    if net.initial_marking is not None:
        document["initialMarking"] = _marking_document(net.initial_marking)

    document["places"] = [_place_document(place) for place in net.places]
    document["transitions"] = [
        _transition_document(transition) for transition in net.transitions
    ]
    document["arcs"] = [_arc_document(arc) for arc in net.arcs]
    return document


def _place_document(place: Place) -> dict[str, Any]:
    document: dict[str, Any] = {"name": place.name, "accepts": list(place.accepts)}
    if place.port is not None:
        document["port"] = {
            "direction": place.port.direction,
            "type": place.port.type,
        }
    if place.description is not None:
        document["description"] = place.description
    if place.annotations is not None:
        document["annotations"] = place.annotations
    if place.capacity_per_color_key is not None:
        keys: tuple[str, ...] = place.capacity_per_color_key.keys
        document["capacityPerColorKey"] = {
            "key": keys[0] if len(keys) == 1 else list(keys),
            "max": place.capacity_per_color_key.max,
        }
    return document


def _transition_document(transition: Transition) -> dict[str, Any]:
    document: dict[str, Any] = {"name": transition.name}
    if transition.handler is not None:
        document["handler"] = transition.handler
    if transition.guard is not None:
        document["guard"] = transition.guard
    if transition.priority is not None:
        document["priority"] = transition.priority
    if transition.description is not None:
        document["description"] = transition.description
    if transition.annotations is not None:
        document["annotations"] = transition.annotations
    if transition.binding_names is not None:
        document["bindingNames"] = dict(transition.binding_names)
    if transition.timer is not None:
        timer: dict[str, Any] = {
            "clock": transition.timer.clock,
            "cel": transition.timer.cel,
        }
        if transition.timer.bind is not None:
            timer["bind"] = dict(transition.timer.bind)
        if transition.timer.maturity is not None:
            timer["maturity"] = transition.timer.maturity
        document["timer"] = timer
    return document


def _arc_document(arc: Arc) -> dict[str, Any]:
    document: dict[str, Any] = {}
    if arc.consume is not None:
        consume = arc.consume
        document["from"] = (
            {"place": arc.from_place}
            if arc.from_place is not None
            else {"transition": arc.from_transition}
        )
        document["to"] = {"transition": arc.to_transition}
        pattern: dict[str, Any] = {}
        if consume.mode != "consume":
            pattern["mode"] = consume.mode
        if consume.weight != 1:
            pattern["weight"] = consume.weight
        pattern["type"] = consume.type
        if consume.predicate is not None:
            predicate = consume.predicate
            if predicate.cel is not None:
                pattern["predicate"] = {"cel": predicate.cel}
            else:
                pattern["predicate"] = {"handler": predicate.handler}
        if consume.correlate is not None:
            pattern["correlate"] = {"cel": consume.correlate}
        document["consume"] = pattern
    elif arc.produce is not None:
        produce = arc.produce
        document["from"] = {"transition": arc.from_transition}
        document["to"] = {"place": arc.to_place}
        produced: dict[str, Any] = {"type": produce.type}
        if produce.data is not None:
            produced["data"] = produce.data
        if produce.cel is not None:
            produced["cel"] = produce.cel
        produced["destination"] = produce.destination
        document["produce"] = produced
    else:
        raise ValueError(f"arc with no inscription: {arc}")
    if arc.description is not None:
        document["description"] = arc.description
    if arc.annotations is not None:
        document["annotations"] = arc.annotations
    return document


def _marking_document(marking: Marking) -> dict[str, Any]:
    return {
        place: [{"type": token.type, "data": dict(token.data)} for token in tokens]
        for place, tokens in marking.items()
    }


def canonical_net_json(net: Net) -> str:
    """The net as the pretty canonical-JSON profile bytes.

    UTF-8, LF, a final LF, two-space indentation, object members sorted by
    UTF-16 code units (RFC 8785's sort) and rendered by its primitive
    spellings; arrays keep semantic order (``spec/petrinet-language.md``).
    """
    return render_canonical_json(net_document(net), indent=2) + "\n"


def net_sha256(net: Net) -> str:
    """The sha256 hex digest of :func:`canonical_net_json`."""
    return hashlib.sha256(canonical_net_json(net).encode("utf-8")).hexdigest()
