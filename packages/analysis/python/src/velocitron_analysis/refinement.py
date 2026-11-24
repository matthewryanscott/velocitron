"""Check that a refining net is a sound block for the transition it replaces.

``refine lifecycle.[attempt] by attempt`` replaces one transition by a whole
net, wired to the transition's places through ports (ADR 0034). The check
looks at the refining net alone, as a workflow net from the input port that
takes the transition's token to the output ports wired into the
transition's output place:

- every token that enters through the input port leads to exactly one token
  leaving through one of those output ports, on every path (option to
  complete, and no second token);
- nothing of the instance stays behind in the refining net when it leaves
  (proper completion);
- every transition of the refining net can fire (no dead transitions).

Van der Aalst (2000) and van Hee, Sidorova and Voorhoeve (2003) show that
replacing a transition of a sound net by such a block keeps the net sound,
when the transition is never enabled twice at once; spec/proofs.md and
ADR 0037 state the conditions.

References: spec/proofs.md; ADR 0034; ADR 0037.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from velocitron_merge import port_fusion_map
from velocitron_engine import Net, Refinement, Share, Wire

from .analysis import NetModel
from .report import Finding, Proof, Status
from .soundness import Environment, Explorer, soundness_proofs


@dataclass(frozen=True)
class Composed:
    """The composition a net was merged from: constituents by alias, their
    files, the wires, the refinements and the shares."""

    nets: Mapping[str, Net]
    files: Mapping[str, Path]
    wires: Sequence[Wire]
    refinements: Sequence[Refinement]
    shares: Sequence[Share] = ()

    def fused(self) -> frozenset[str]:
        """The merged places that are closed because the composition fused them.

        A wired place's producers are inside the merged net. A place that a
        share fuses keeps the role its members had (ADR 0040): when a member
        is annotated ``fusion``, the environment still supplies it.
        """
        fusion = port_fusion_map(self.nets, self.wires, self.shares)
        supplied = {
            fusion.get(f"{net}.{place}", "")
            for share in self.shares
            for net, place in share.members
            if _annotated_fusion(self.nets[net], place)
        }
        return frozenset(set(fusion.values()) - supplied)


def _annotated_fusion(net: Net, place_name: str) -> bool:
    place = next((p for p in net.places if p.name == place_name), None)
    return bool(place is not None and (place.annotations or {}).get("fusion"))


@dataclass(frozen=True)
class RefinementCheck:
    """One refinement's proof, with what is needed to write its plays."""

    proof: Proof
    net: Net
    model: NetModel | None
    file: Path


def _wired_ports(
    composed: Composed, refinement: Refinement, place: str, direction: str
) -> list[str]:
    """Ports of the refining net in ``direction`` that the wires fuse with
    ``place`` of the refined net."""
    fused = port_fusion_map(composed.nets, composed.wires, composed.shares)
    target = fused.get(f"{refinement.net}.{place}")
    if target is None:
        return []
    by = composed.nets[refinement.by]
    return [
        candidate.name
        for candidate in by.places
        if candidate.port is not None
        and candidate.port.direction == direction
        and fused.get(f"{refinement.by}.{candidate.name}") == target
    ]


def _statement(color: str, by: str, inputs: list[str], outputs: list[str]) -> str:
    entry = " or ".join(f"({p})" for p in inputs) or "its input port"
    exits = " or ".join(f"({p})" for p in outputs) or "its output ports"
    return (
        f"Each {color} token that enters {by} through {entry} leaves as exactly "
        f"one token through {exits}, on every path; every transition of {by} "
        f"can fire; nothing of the instance stays in {by}."
    )


def _unknown(
    subject: str, statement: str, reason: str, details: dict[str, Any]
) -> Proof:
    return Proof(
        "refinement", subject, "unknown", statement, reason=reason, details=details
    )


def check_refinement(
    composed: Composed,
    refinement: Refinement,
    *,
    domains: Mapping[str, Sequence[Any]],
    environment: Environment,
    other_keys: bool,
    max_states: int,
    wait_arrivals: bool = False,
    progress: Callable[[str], object] | None = None,
) -> RefinementCheck:
    """Prove that ``refinement.by`` is a sound block for the refined transition."""
    outer = composed.nets[refinement.net]
    by = composed.nets[refinement.by]
    file = composed.files[refinement.by]
    subject = (
        f"refinement {refinement.net}.[{refinement.transition}] by {refinement.by}"
    )
    consumes = [
        arc
        for arc in outer.arcs
        if arc.to_transition == refinement.transition
        and arc.consume is not None
        and arc.consume.mode == "consume"
    ]
    produces = sorted(
        {
            arc.produce.destination
            for arc in outer.arcs
            if arc.from_transition == refinement.transition and arc.produce is not None
        }
    )
    color = (
        consumes[0].consume.type
        if len(consumes) == 1 and consumes[0].consume
        else "token"
    )
    inputs = (
        _wired_ports(composed, refinement, consumes[0].from_place or "", "input")
        if len(consumes) == 1
        else []
    )
    outputs = [
        port
        for place in produces
        for port in _wired_ports(composed, refinement, place, "output")
    ]
    side_outputs = sorted(
        place.name
        for place in by.places
        if place.port is not None
        and place.port.direction == "output"
        and place.name not in outputs
    )
    details: dict[str, Any] = {
        "net": refinement.net,
        "transition": refinement.transition,
        "by": refinement.by,
        "file": str(file),
        "inputs": inputs,
        "outputs": outputs,
        "sideOutputs": side_outputs,
    }
    statement = _statement(color, refinement.by, inputs, outputs)
    if len(consumes) != 1:
        return RefinementCheck(
            _unknown(
                subject,
                statement,
                f"[{refinement.transition}] takes {len(consumes)} tokens; the check "
                "follows a transition that takes one",
                details,
            ),
            by,
            None,
            file,
        )
    if len(produces) != 1:
        return RefinementCheck(
            _unknown(
                subject,
                statement,
                f"[{refinement.transition}] produces into {len(produces)} places; the "
                "check follows a transition with one output place",
                details,
            ),
            by,
            None,
            file,
        )
    if not inputs or not outputs:
        return RefinementCheck(
            _unknown(
                subject,
                statement,
                "no port of the refining net is wired to the transition's places",
                details,
            ),
            by,
            None,
            file,
        )
    model = NetModel(
        by,
        overrides=domains,
        instance_color=color,
        final=outputs,
        other_keys=other_keys,
        start=inputs,
        block=True,
    )
    found, explorer = soundness_proofs(
        by,
        model,
        environment=environment,
        max_states=max_states,
        wait_arrivals=wait_arrivals,
        progress=progress,
    )
    findings: list[Finding] = [f for proof in found for f in proof.findings]
    findings += _second_tokens(explorer, outputs)
    statuses: list[Status] = [proof.status for proof in found]
    if any(f.kind == "improper" for f in findings):
        statuses.append("refuted")
    status: Status = (
        "refuted"
        if "refuted" in statuses
        else "unknown"
        if "unknown" in statuses
        else "proved"
    )
    reasons = sorted({proof.reason for proof in found if proof.reason})
    markings, edges = explorer.size()
    details["exploration"] = {
        "states": markings,
        "edges": edges,
        "capped": explorer.capped,
        "maxStates": max_states,
    }
    proof = Proof(
        "refinement",
        subject,
        status,
        statement,
        findings=tuple(findings),
        reason="; ".join(reasons) if status == "unknown" and reasons else None,
        details=details,
        assumptions=environment.assumptions() if status != "refuted" else (),
    )
    return RefinementCheck(proof, by, model, file)


def _second_tokens(explorer: Explorer, outputs: Sequence[str]) -> list[Finding]:
    """A finding when one move puts more than one token into the outputs."""
    for index, state in enumerate(explorer.states):
        if not state.final:
            continue
        count = sum(len(state.marking.get(place, ())) for place in outputs)
        if count > 1:
            return [
                Finding(
                    kind="improper",
                    summary=(
                        f"{count} tokens leave through "
                        + ", ".join(f"({p})" for p in outputs)
                        + " for one token that entered."
                    ),
                    path=tuple(explorer.moves[m] for m in explorer.path_to(index)),
                    marking={
                        place: [
                            {"type": t.type, "data": t.data}
                            for t in state.marking.get(place, ())
                        ]
                        for place in outputs
                        if state.marking.get(place)
                    },
                )
            ]
    return []


def refinement_environment(alias: str, environment: Environment) -> Environment:
    """The environment bounds that name places or transitions of one
    constituent, by the constituent's own names (``loan.form`` -> ``form``).
    The refining net's instance is the one token the refined transition
    takes, so it starts once whatever ``starts`` says (ADR 0052)."""
    prefix = f"{alias}."

    def local(bounds: Mapping[str, int]) -> dict[str, int]:
        return {
            key.removeprefix(prefix): value
            for key, value in bounds.items()
            if key.startswith(prefix)
        }

    return replace(
        environment,
        injections=local(environment.injections),
        updates=local(environment.updates),
        firings=local(environment.firings),
        starts=1,
    )
