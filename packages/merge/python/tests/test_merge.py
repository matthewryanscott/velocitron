"""Composition merge over already-parsed nets, without the umbrella package."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, cast

from velocitron_merge import (
    Arc,
    Composition,
    ConsumePattern,
    DeclaredInvariant,
    Marking,
    Net,
    NetValidationError,
    Place,
    Port,
    ProduceTemplate,
    ProofFacts,
    Refinement,
    Share,
    Timer,
    Token,
    Transition,
    Wire,
    merge_composition,
    merge_nets,
    port_fusion_map,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
_CASES = json.loads((_FIXTURES / "cases.json").read_text(encoding="utf-8"))


def _port(raw: dict[str, Any] | None) -> Port | None:
    if raw is None:
        return None
    direction = cast(Literal["input", "output"], raw["direction"])
    return Port(direction=direction, type=raw["type"])


def _net(doc: dict[str, Any]) -> Net:
    places = [
        Place(
            name=raw["name"],
            accepts=list(raw["accepts"]),
            port=_port(raw.get("port")),
            description=raw.get("description"),
            annotations=raw.get("annotations"),
        )
        for raw in doc["places"]
    ]
    transitions: list[Transition] = []
    for raw in doc["transitions"]:
        timer = None
        if "timer" in raw:
            spec = raw["timer"]
            timer = Timer(
                clock=spec["clock"],
                cel=spec["cel"],
                bind=spec.get("bind"),
                maturity=spec.get("maturity"),
            )
        transitions.append(
            Transition(
                name=raw["name"],
                handler=raw.get("handler"),
                guard=raw.get("guard"),
                priority=raw.get("priority"),
                timer=timer,
                description=raw.get("description"),
                annotations=raw.get("annotations"),
                binding_names=raw.get("bindingNames"),
            )
        )
    arcs: list[Arc] = []
    for raw in doc["arcs"]:
        if "consume" in raw:
            spec = raw["consume"]
            mode = cast(
                Literal["consume", "inhibit", "read"], spec.get("mode", "consume")
            )
            arcs.append(
                Arc(
                    from_place=raw["fromPlace"],
                    to_transition=raw["toTransition"],
                    consume=ConsumePattern(
                        type=spec["type"],
                        predicate=None,
                        mode=mode,
                        weight=spec.get("weight", 1),
                        correlate=spec.get("correlate"),
                    ),
                    description=raw.get("description"),
                    annotations=raw.get("annotations"),
                )
            )
        else:
            spec = raw["produce"]
            arcs.append(
                Arc(
                    from_transition=raw["fromTransition"],
                    to_place=raw["toPlace"],
                    produce=ProduceTemplate(
                        type=spec["type"],
                        destination=spec["destination"],
                        data=spec.get("data"),
                        cel=spec.get("cel"),
                    ),
                    description=raw.get("description"),
                    annotations=raw.get("annotations"),
                )
            )
    marking = None
    if "initialMarking" in doc:
        marking = Marking(
            {
                place: [Token(token["type"], dict(token["data"])) for token in tokens]
                for place, tokens in doc["initialMarking"].items()
            }
        )
    proofs = None
    if "proofs" in doc:
        raw_proofs = doc["proofs"]
        final = None
        if "final" in raw_proofs:
            final = [tuple(entry) for entry in raw_proofs["final"]]
        invariants = None
        if "invariants" in raw_proofs:
            invariants = [
                DeclaredInvariant(
                    weights=dict(item["weights"]),
                    constant=item.get("constant"),
                    name=item.get("name"),
                )
                for item in raw_proofs["invariants"]
            ]
        proofs = ProofFacts(final=final, invariants=invariants)
    domains = None
    if "domains" in doc:
        domains = {key: list(values) for key, values in doc["domains"].items()}
    return Net(
        name=doc["name"],
        places=places,
        transitions=transitions,
        arcs=arcs,
        initial_marking=marking,
        annotations=doc.get("annotations"),
        domains=domains,
        proofs=proofs,
    )


def _wires(case: dict[str, Any]) -> list[Wire]:
    return [
        Wire(
            raw["from"]["net"], raw["from"]["port"], raw["to"]["net"], raw["to"]["port"]
        )
        for raw in case["wires"]
    ]


def _shares(case: dict[str, Any]) -> tuple[Share, ...]:
    return tuple(
        Share(tuple((member["net"], member["place"]) for member in raw["places"]))
        for raw in case["shares"]
    )


def _refinements(case: dict[str, Any]) -> tuple[Refinement, ...]:
    return tuple(
        Refinement(raw["net"], raw["transition"], raw["by"])
        for raw in case["refinements"]
    )


def _final(case: dict[str, Any]) -> tuple[tuple[tuple[str, str], ...], ...] | None:
    if case["final"] is None:
        return None
    return tuple(
        tuple((member["net"], member["place"]) for member in marking)
        for marking in case["final"]
    )


def _project_place(place: Place) -> dict[str, Any]:
    projected: dict[str, Any] = {"name": place.name, "accepts": list(place.accepts)}
    if place.port is not None:
        projected["port"] = {"direction": place.port.direction, "type": place.port.type}
    if place.description:
        projected["description"] = place.description
    if place.annotations:
        projected["annotations"] = place.annotations
    return projected


def _project_transition(transition: Transition) -> dict[str, Any]:
    projected: dict[str, Any] = {"name": transition.name}
    if transition.handler is not None:
        projected["handler"] = transition.handler
    if transition.guard is not None:
        projected["guard"] = transition.guard
    if transition.priority is not None:
        projected["priority"] = transition.priority
    if transition.timer is not None:
        timer: dict[str, Any] = {
            "clock": transition.timer.clock,
            "cel": transition.timer.cel,
        }
        if transition.timer.bind:
            timer["bind"] = dict(transition.timer.bind)
        if transition.timer.maturity:
            timer["maturity"] = transition.timer.maturity
        projected["timer"] = timer
    if transition.description:
        projected["description"] = transition.description
    if transition.annotations:
        projected["annotations"] = transition.annotations
    if transition.binding_names:
        projected["bindingNames"] = dict(transition.binding_names)
    return projected


def _project_arc(arc: Arc) -> dict[str, Any]:
    if arc.consume is not None:
        consume: dict[str, Any] = {
            "type": arc.consume.type,
            "mode": arc.consume.mode,
            "weight": arc.consume.weight,
        }
        if arc.consume.correlate is not None:
            consume["correlate"] = arc.consume.correlate
        projected: dict[str, Any] = {
            "fromPlace": arc.from_place,
            "toTransition": arc.to_transition,
            "consume": consume,
        }
    else:
        assert arc.produce is not None
        produce: dict[str, Any] = {
            "type": arc.produce.type,
            "destination": arc.produce.destination,
        }
        if arc.produce.cel is not None:
            produce["cel"] = arc.produce.cel
        if arc.produce.data is not None:
            produce["data"] = arc.produce.data
        projected = {
            "fromTransition": arc.from_transition,
            "toPlace": arc.to_place,
            "produce": produce,
        }
    if arc.description:
        projected["description"] = arc.description
    if arc.annotations:
        projected["annotations"] = arc.annotations
    return projected


def _project_net(net: Net, fusion: dict[str, str]) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "name": net.name,
        "places": [_project_place(place) for place in net.places],
        "transitions": [
            _project_transition(transition) for transition in net.transitions
        ],
        "arcs": [_project_arc(arc) for arc in net.arcs],
        "fusion": [[member, fused] for member, fused in sorted(fusion.items())],
    }
    if net.initial_marking is not None:
        projected["initialMarking"] = {
            place: [{"type": token.type, "data": dict(token.data)} for token in tokens]
            for place, tokens in net.initial_marking.items()
        }
    if net.domains:
        projected["domains"] = {
            key: list(values) for key, values in net.domains.items()
        }
    if net.proofs is not None:
        proofs: dict[str, Any] = {}
        if net.proofs.final:
            proofs["final"] = [list(marking) for marking in net.proofs.final]
        if net.proofs.invariants:
            proofs["invariants"] = [
                {
                    "weights": dict(invariant.weights),
                    **(
                        {}
                        if invariant.constant is None
                        else {"constant": invariant.constant}
                    ),
                    **({} if not invariant.name else {"name": invariant.name}),
                }
                for invariant in net.proofs.invariants
            ]
        if proofs:
            projected["proofs"] = proofs
    if net.annotations:
        projected["annotations"] = net.annotations
    return projected


def project_cases() -> list[dict[str, Any]]:
    """Canonical projections of the shared fixtures. TypeScript asserts the same."""
    projected: list[dict[str, Any]] = []
    for case in _CASES["cases"]:
        nets = {alias: _net(doc) for alias, doc in case["nets"].items()}
        wires = _wires(case)
        shares = _shares(case)
        try:
            merged = merge_nets(
                nets,
                wires,
                _refinements(case),
                shares,
                name=case["mergeName"],
                final=_final(case),
            )
        except NetValidationError as exc:
            projected.append({"name": case["name"], "error": str(exc)})
            continue
        fusion = port_fusion_map(nets, wires, shares)
        body = _project_net(merged, fusion)
        body["name"] = case["name"]
        body["netName"] = merged.name
        projected.append(body)
    return projected


def test_single_wire_fuses_on_the_output_port() -> None:
    # given: a producer output wired to a consumer input
    case = next(item for item in project_cases() if item["name"] == "single-wire")
    # then: both ports are the output's qualified name, and the input's type is kept
    assert case["fusion"] == [["cons.inbox", "prod.out"], ["prod.out", "prod.out"]]
    fused = next(place for place in case["places"] if place["name"] == "prod.out")
    assert "port" not in fused
    assert fused["accepts"] == ["task", "note"]
    assert fused["description"] == "from prod"
    assert fused["annotations"]["fusion"] is True
    assert fused["annotations"]["lane"] == "prod"
    assert fused["annotations"]["extra"] == "sink"
    take = next(item for item in case["transitions"] if item["name"] == "cons.take")
    assert take["bindingNames"] == {"inbox": "prod.out"}


def test_fan_in_names_the_place_after_every_output() -> None:
    # given / when: two outputs wired to one input
    case = next(item for item in project_cases() if item["name"] == "fan-in")
    # then: the fused name sorts the output ports
    assert case["fusion"] == [
        ["left.out", "left.out__right.out"],
        ["right.out", "left.out__right.out"],
        ["sink.inbox", "left.out__right.out"],
    ]


def test_share_fuses_places_that_are_not_ports() -> None:
    # given / when: two buffers shared, with no wire
    case = next(item for item in project_cases() if item["name"] == "share")
    # then: the place is named after both members
    assert case["fusion"] == [
        ["alpha.buf", "alpha.buf__beta.buf"],
        ["beta.buf", "alpha.buf__beta.buf"],
    ]
    fused = next(
        place for place in case["places"] if place["name"] == "alpha.buf__beta.buf"
    )
    assert fused["description"] == "alpha"


def test_refinement_removes_the_replaced_transition() -> None:
    # given / when: courier refines shop.deliver
    case = next(item for item in project_cases() if item["name"] == "refinement")
    # then: deliver and its arcs are gone
    assert [item["name"] for item in case["transitions"]] == [
        "shop.send",
        "courier.pick",
        "courier.drop",
    ]
    assert all("shop.deliver" not in json.dumps(arc) for arc in case["arcs"])


def test_disagreements_are_the_shared_messages() -> None:
    # given / when: the fixture's rejected merges
    errors = {
        item["name"]: item["error"] for item in project_cases() if "error" in item
    }
    # then: Python and the fixture name the same conflicts
    assert errors["domain-conflict"] == "domain task.kind differs between a and b"
    assert (
        errors["actor-conflict"]
        == "actor clerk is a human in one net and a system in b"
    )
    assert (
        errors["refinement-unknown"]
        == "refine shop.[deliver] by ghost: unknown alias ghost"
    )


def test_merge_composition_requires_parsed_nets() -> None:
    # given: a composition with no parsed nets
    composition = Composition(nets=[], wires=[])
    # when / then: the package does not parse the references
    try:
        merge_composition(composition)
    except NetValidationError as exc:
        assert "parsed_nets" in str(exc)
    else:
        raise AssertionError("merge_composition parsed a document")


def test_merge_composition_uses_the_parsed_nets() -> None:
    # given: the single-wire nets already parsed
    case = next(item for item in _CASES["cases"] if item["name"] == "single-wire")
    nets = {alias: _net(doc) for alias, doc in case["nets"].items()}
    wires = _wires(case)
    direct = merge_nets(nets, wires, name="wired")
    # when: merge_composition reads parsed_nets
    merged = merge_composition(
        Composition(nets=[], wires=wires, parsed_nets=nets, name="wired")
    )
    # then: it matches merge_nets
    assert [place.name for place in merged.places] == [
        place.name for place in direct.places
    ]
    assert merged.name == "wired"


def test_projection_matches_the_shared_agreement() -> None:
    # given: the cross-language oracle written from this projection
    actual = project_cases()
    path = _FIXTURES / "agreement.json"
    if os.environ.get("MERGE_AGREEMENT_WRITE") == "1":
        path.write_text(
            json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    # when: the committed oracle is loaded
    expected = json.loads(path.read_text(encoding="utf-8"))
    # then: this package still produces it
    assert actual == expected
