"""Choice coverage: each token at a choice place enables exactly one way out.

A **choice** is a place with consume arcs of one color into two or more
transitions. For every token the data domains allow at that place, and every
context the other input places of those transitions can show (empty, or one
token about this key or another key, and each clock time), the prover asks
which of those transitions are enabled: the engine (:class:`EngineCases`),
or on the fast path the kernel over the reference's tables
(``fast.KernelCases``).

- A **gap** is a token and context where none is enabled. Gaps are looked
  for once the context is settled: every place a choice transition reads
  holds a token about this key, and the clock is at its last time slot, so a
  missing fact or a timer not yet due is a wait, not a gap.
- An **overlap** is a token and context where two or more are enabled. It
  is **resolved by priority** when one of them has the highest priority (the
  priority policy picks it), and **waived** when the place or one of the
  transitions carries ``annotations.lint.suppress: ["choice-overlap"]``
  (``choice-gap`` waives gaps the same way; ADR 0016).
- An **intended wait** is a gap case that a ``wait`` condition of one of the
  transitions holds for (ADR 0057). It is no defect, and unlike a waiver it
  covers only those cases.

Findings are reported as boxes of cases: each box lists, per field or
context place, the values for which the finding holds, with one concrete
witness.

References: spec/proofs.md; ADR 0036; ADR 0057.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from typing import Any, Protocol

from velocitron_engine import Marking, Net, Token, Transition
from velocitron_runtime import Wait, holds, intended_waits

from .lint import binding_keys, suppressed_rules
from .analysis import (
    ENVIRONMENT,
    INSTANCE,
    OTHER,
    OWN_KEY,
    FieldPath,
    NetModel,
    set_path,
)
from .firing import Firing
from .report import Finding, Proof

RULE_GAP = "choice-gap"
RULE_OVERLAP = "choice-overlap"

MAX_CASES = 200_000


@dataclass(frozen=True)
class Dim:
    """One dimension of a choice's cases: a field of the choice token
    (``path``) or what a context place holds (``place``)."""

    label: str
    values: tuple[Any, ...]  # field values, or tokens (None = empty) for a place
    place: str | None = None
    path: FieldPath | None = None
    bounds: tuple[float | int, ...] = ()  # the numbers a field's CEL compares with
    size: bool = False  # the values are lists and the bounds are their sizes


def _value_text(value: Any) -> str:
    if value is None:
        return "empty"
    if isinstance(value, Token):
        return (
            f"{value.type} {json.dumps(value.data, sort_keys=True, ensure_ascii=False)}"
        )
    if isinstance(value, str):
        return value if value == OTHER else json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


class Cases(Protocol):
    """Which transitions each case of a choice enables."""

    def unusual(
        self,
        place: str,
        color: str,
        base: Mapping[str, Any],
        dims: Sequence[Dim],
        names: Sequence[str],
    ) -> Iterator[tuple[tuple[int, ...], list[str]]]:
        """Each case of ``dims`` (the token's fields first, then the context
        places), in ``product`` order, that enables none or more than one
        of ``names``, with those it enables in the net's order."""
        ...


class EngineCases:
    """The reference: the engine asks each case's marking."""

    def __init__(self, firing: Firing) -> None:
        self.firing = firing

    def unusual(
        self,
        place: str,
        color: str,
        base: Mapping[str, Any],
        dims: Sequence[Dim],
        names: Sequence[str],
    ) -> Iterator[tuple[tuple[int, ...], list[str]]]:
        for point in product(*(range(len(dim.values)) for dim in dims)):
            marking = _marking(place, color, base, dims, point)
            on = [n for n in self.firing.enabled(marking) if n in names]
            if len(on) != 1:
                yield point, on


def choice_proofs(net: Net, model: NetModel, cases: Cases) -> list[Proof]:
    proofs: list[Proof] = []
    # Two transitions taking a shared resource (a lock), a fact or a kept
    # record compete for it or rewrite it; that is not a decision of this
    # instance. A place a token arrives at, the instance's start or an input
    # port, is open too, but the transitions that take it there decide what
    # this net does with it.
    arrivals = model.roles.start | {
        place.name
        for place in net.places
        if place.port is not None and place.port.direction == "input"
    }
    shared = (model.roles.open - arrivals) | model.roles.kept
    for place in net.places:
        if place.name in shared:
            continue
        for color in place.accepts:
            arcs = [
                arc
                for arc in net.arcs
                if arc.from_place == place.name
                and arc.consume is not None
                and arc.consume.mode == "consume"
                and arc.consume.type == color
            ]
            names: list[str] = []
            for arc in arcs:
                assert arc.to_transition is not None
                if arc.to_transition not in names:
                    names.append(arc.to_transition)
            if len(names) < 2:
                continue
            proofs.append(_choice(net, model, cases, place.name, color, names, arcs))
    return proofs


def _choice(
    net: Net,
    model: NetModel,
    cases: Cases,
    place: str,
    color: str,
    names: list[str],
    arcs: Sequence[Any],
) -> Proof:
    subject = f"choice at ({place}): " + " | ".join(f"[{n}]" for n in names)
    statement = (
        f"Every {color} token at ({place}) enables exactly one of "
        + ", ".join(f"[{n}]" for n in names)
        + "."
    )
    if any(arc.consume.weight != 1 for arc in arcs) or len(arcs) != len(names):
        return Proof(
            "choice",
            subject,
            "unknown",
            statement,
            reason="a transition takes more than one token from the place",
        )
    unsupported = [n for n in names if n in model.unsupported]
    if unsupported:
        reasons = "; ".join(
            f"[{n}]: " + ", ".join(model.unsupported[n]) for n in unsupported
        )
        return Proof("choice", subject, "unknown", statement, reason=reasons)

    token_dims, base = _token_dims(model, place, color)
    context: list[str] = []
    for name in names:
        for arc in model.inputs.get(name, ()):
            source = arc.from_place
            if source is not None and source != place and source not in context:
                context.append(source)
        timer = model.transitions[name].timer
        if timer is not None and timer.clock not in context:
            context.append(timer.clock)
    positive = {
        arc.from_place
        for name in names
        for arc in model.inputs.get(name, ())
        if arc.consume is not None and arc.consume.mode != "inhibit"
    }
    inhibited = {
        arc.from_place
        for name in names
        for arc in model.inputs.get(name, ())
        if arc.consume is not None and arc.consume.mode == "inhibit"
    }
    full_dims = list(token_dims)
    gap_dims = list(token_dims)
    for other in context:
        full_dims.append(_context_dim(model, other, settled=False))
        if other in model.roles.clocks:
            gap_dims.append(_context_dim(model, other, settled=True))
        elif other in positive and other not in inhibited:
            gap_dims.append(_context_dim(model, other, settled=True))
        else:
            gap_dims.append(_context_dim(model, other, settled=False))
    size = 1
    for dim in full_dims:
        size *= max(len(dim.values), 1)
    if size > MAX_CASES:
        return Proof(
            "choice",
            subject,
            "unknown",
            statement,
            reason=f"{size} cases to check, more than the limit of {MAX_CASES}",
        )

    suppressed_place = set(suppressed_rules(model.places[place].annotations))
    suppressed = {
        name: set(suppressed_rules(model.transitions[name].annotations))
        for name in names
    }

    waits = [
        (wait, _wait_keys(net, model.transitions[name]))
        for name in names
        for wait in intended_waits(model.transitions[name])
    ]

    def waiting(point: tuple[int, ...]) -> Wait | None:
        marking = _marking(place, color, base, gap_dims, point)
        return next((wait for wait, keys in waits if holds(wait, keys, marking)), None)

    gaps: list[tuple[int, ...]] = []
    waited: dict[Wait, list[tuple[int, ...]]] = {}
    for point, on in cases.unusual(place, color, base, gap_dims, names):
        if on:
            continue
        wait = waiting(point) if waits else None
        if wait is None:
            gaps.append(point)
        else:
            waited.setdefault(wait, []).append(point)
    overlaps: dict[tuple[str, tuple[str, ...]], list[tuple[int, ...]]] = {}
    priorities = {n: model.transitions[n].priority or 0 for n in names}
    priority_mode = any(tr.priority is not None for tr in net.transitions)
    for point, on in cases.unusual(place, color, base, full_dims, names):
        if len(on) < 2:
            continue
        top = max(priorities[n] for n in on)
        winners = [n for n in on if priorities[n] == top]
        if priority_mode and len(winners) == 1:
            kind = "resolved"
        elif RULE_OVERLAP in suppressed_place or any(
            RULE_OVERLAP in suppressed[n] for n in on
        ):
            kind = "waived"
        else:
            kind = "overlap"
        overlaps.setdefault((kind, tuple(on)), []).append(point)

    findings: list[Finding] = []
    gap_kind = (
        "waived-gap"
        if RULE_GAP in suppressed_place or any(RULE_GAP in suppressed[n] for n in names)
        else "gap"
    )
    for box in _cover(gaps, gap_dims):
        findings.append(
            _finding(gap_kind, box, gap_dims, place, color, base, (), len(gaps))
        )
    for wait, points in waited.items():
        for box in _cover(points, gap_dims):
            findings.append(
                _finding(
                    "wait", box, gap_dims, place, color, base, (), len(points), wait
                )
            )
    for (kind, on), points in sorted(
        overlaps.items(), key=lambda item: (_KIND_ORDER[item[0][0]], item[0][1])
    ):
        boxes = _cover(points, full_dims)
        for box in boxes:
            findings.append(
                _finding(kind, box, full_dims, place, color, base, on, len(points))
            )
    defects = [f for f in findings if f.kind in ("gap", "overlap")]
    opaque = sorted(
        {
            text
            for path in model.tested(place, color)
            for text in model.opaque.get(model.canonical(color, path), [])
        }
    )
    if defects:
        status = "refuted"
        reason = None
    elif opaque:
        status = "unknown"
        reason = (
            "the domains may miss values: " + "; ".join(opaque) + " is not analyzed"
        )
    else:
        status, reason = "proved", None
    details = {
        "place": place,
        "color": color,
        "transitions": names,
        "cases": size,
    }
    return Proof(
        "choice",
        subject,
        status,
        statement,
        findings=tuple(findings),
        reason=reason,
        details=details,
    )


_KIND_ORDER = {"overlap": 0, "waived": 1, "resolved": 2}


def _wait_keys(net: Net, transition: Transition) -> dict[str, str]:
    """The keys a ``wait`` condition's ``binding`` holds: the transition's
    own binding keys, and each place it inhibits, keyed by the name the net
    that declares it uses (the local name inside a composition), since a gap
    an inhibitor causes is about the tokens there."""
    keys = binding_keys(net, transition)
    alias = transition.name.rpartition(".")[0] if transition.binding_names else ""
    for arc in net.arcs:
        if (
            arc.to_transition != transition.name
            or arc.from_place is None
            or arc.consume is None
            or arc.consume.mode != "inhibit"
        ):
            continue
        place = arc.from_place
        key = place.removeprefix(f"{alias}.") if alias else place
        keys.setdefault(key, place)
    return keys


def _token_dims(
    model: NetModel, place: str, color: str
) -> tuple[list[Dim], dict[str, Any]]:
    """One dimension per tested field of the choice token; the rest is fixed."""
    bases = model.token_variants(color, vary=(), own=INSTANCE, full=True)
    base = bases[0] if bases else {}
    dims: list[Dim] = []
    for path in sorted(model.tested(place, color)):
        if model.embedded(color, path) is not None:
            continue
        domain = model.domain(color, path)
        if domain is None or (domain.own is not None and domain.kind in INSTANCE):
            continue
        if len(domain.values) > 1:
            dims.append(
                Dim(
                    ".".join(path),
                    tuple(domain.values),
                    path=path,
                    bounds=domain.bounds,
                    size=domain.kind == "list",
                )
            )
        elif domain.values:
            set_path(base, path, domain.values[0])
    return dims, base


def _context_dim(model: NetModel, place: str, *, settled: bool) -> Dim:
    if place in model.roles.clocks:
        color = model.places[place].accepts[0]
        field_name = next(
            (p[0] for p in sorted(model.known.get(color, set())) if len(p) == 1), "now"
        )
        domain = model.domain(color, (field_name,))
        values = tuple(domain.values) if domain else (0,)
        if settled:
            values = values[-1:]
        return Dim(
            f"({place})",
            tuple(Token(color, {field_name: v}) for v in values),
            place=place,
        )
    tokens: list[Token | None] = [] if settled else [None]
    for color in model.places[place].accepts:
        own = OWN_KEY if settled else ENVIRONMENT
        for data in model.token_variants(color, vary=None, own=own, full=True):
            tokens.append(Token(color, data))
    return Dim(f"({place})", tuple(tokens), place=place)


def _marking(
    place: str,
    color: str,
    base: Mapping[str, Any],
    dims: Sequence[Dim],
    point: Sequence[int],
) -> Marking:
    data = json.loads(json.dumps(base))
    places: dict[str, list[Token]] = {}
    for dim, index in zip(dims, point, strict=True):
        value = dim.values[index]
        if dim.path is not None:
            set_path(data, dim.path, value)
        elif value is not None:
            assert dim.place is not None
            places.setdefault(dim.place, []).append(value)
    places[place] = [Token(color, data)]
    return Marking(places)


def witness_marking(
    place: str,
    color: str,
    base: Mapping[str, Any],
    dims: Sequence[Dim],
    point: Sequence[int],
) -> Marking:
    return _marking(place, color, base, dims, point)


def _cover(
    points: Sequence[tuple[int, ...]], dims: Sequence[Dim]
) -> list[list[set[int]]]:
    """Disjoint boxes of cases (a set of values per dimension) that together
    hold exactly ``points``, so no case is reported twice."""
    left = set(points)
    boxes: list[list[set[int]]] = []
    for point in sorted(left):
        if point not in left:
            continue
        box = [{value} for value in point]
        for d, dim in enumerate(dims):
            for value in range(len(dim.values)):
                if value in box[d]:
                    continue
                trial = [set(values) for values in box]
                trial[d].add(value)
                if all(candidate in left for candidate in product(*trial)):
                    box[d].add(value)
        left -= set(product(*box))
        boxes.append(box)
    return boxes


def _range_text(dim: Dim, values: set[int]) -> str | None:
    """``values`` as one range around the numbers the CEL compares with, as
    in ``wearShare ≥ 0.01``; ``None`` when they are not one range."""
    low, high = min(values), max(values)
    if not dim.bounds or high - low + 1 != len(values):
        return None
    numbers = [len(v) if dim.size else v for v in dim.values]
    if low == high and numbers[low] in dim.bounds:
        return None
    label = f"size({dim.label})" if dim.size else dim.label
    lower = upper = None
    if low > 0:
        if numbers[low] in dim.bounds:
            lower = (numbers[low], "≤")
        else:
            lower = (max(b for b in dim.bounds if b < numbers[low]), "<")
    if high < len(numbers) - 1:
        if numbers[high] in dim.bounds:
            upper = ("≤", numbers[high])
        else:
            upper = ("<", min(b for b in dim.bounds if b > numbers[high]))
    if lower is not None and upper is not None:
        start, end = json.dumps(lower[0]), json.dumps(upper[1])
        return f"{start} {lower[1]} {label} {upper[0]} {end}"
    if lower is not None:
        flipped = "≥" if lower[1] == "≤" else ">"
        return f"{label} {flipped} {json.dumps(lower[0])}"
    assert upper is not None
    return f"{label} {upper[0]} {json.dumps(upper[1])}"


def _finding(
    kind: str,
    box: list[set[int]],
    dims: Sequence[Dim],
    place: str,
    color: str,
    base: Mapping[str, Any],
    on: Sequence[str],
    count: int,
    wait: Wait | None = None,
) -> Finding:
    cases: dict[str, Any] = {}
    parts: list[str] = []
    for dim, values in zip(dims, box, strict=True):
        if len(values) == len(dim.values):
            continue
        listed = [_value_text(dim.values[v]) for v in sorted(values)]
        cases[dim.label] = listed if len(listed) > 1 else listed[0]
        left_out = [_value_text(v) for i, v in enumerate(dim.values) if i not in values]
        ranged = _range_text(dim, values)
        if ranged is not None:
            parts.append(ranged)
        elif len(listed) == 1:
            parts.append(f"{dim.label} is {listed[0]}")
        elif len(left_out) < len(listed):
            parts.append(f"{dim.label} is not " + " or ".join(left_out))
        else:
            parts.append(f"{dim.label} is one of " + ", ".join(listed))
    when = " and ".join(parts) if parts else "always"
    point = tuple(min(values) for values in box)
    marking = _marking(place, color, base, dims, point)
    witness = {
        p: [{"type": t.type, "data": t.data} for t in tokens]
        for p, tokens in marking.items()
    }
    names = " and ".join(f"[{n}]" for n in on)
    both = "both" if len(on) == 2 else "all"
    if wait is not None:
        summary = (
            f"the {color} token waits for {wait.reason} when {when}; "
            f"[{wait.transition}] declares this wait"
        )
    elif kind in ("gap", "waived-gap"):
        summary = f"no transition takes the {color} token when {when}"
    elif kind == "resolved":
        summary = f"{names} are {both} enabled when {when}; priority picks one"
    else:
        summary = f"{names} are {both} enabled when {when}"
    if kind.startswith("waived"):
        summary += " (waived)"
    return Finding(
        kind=kind,
        summary=summary,
        witness=witness,
        cases=cases or {"all": "any"},
        enabled=tuple(on),
        count=count,
    )
