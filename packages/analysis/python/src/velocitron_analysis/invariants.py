"""Place invariants: weighted token counts that no firing changes.

The prover computes the minimal P-semiflows of the net's skeleton: the
non-negative integer vectors ``y`` over places with ``y · C = 0``, where
``C`` is the incidence matrix (tokens a firing puts into a place, minus
tokens it takes out). A consume arc counts its weight; a produce arc counts
one token; read and inhibit arcs count nothing. Every semiflow ``y`` gives
an invariant: in every reachable marking, ``y · M`` equals ``y · M0`` plus
what the environment puts into open places in its support.

The algorithm is Farkas's, with Martinez and Silva's rule that drops every
row whose support is not minimal after each column.

These are counts of tokens, whatever their color or key. The report names a
key that the colors in a semiflow share (a "per destination" reading), but
it does not prove the per-key form.

References: spec/proofs.md; ADR 0036.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import gcd
from typing import Any

from velocitron_engine import Marking, Net

from .analysis import NetModel
from .report import Finding, Proof, Status
from .soundness import Environment


@dataclass(frozen=True)
class Invariant:
    """An author-declared place invariant: ``sum(weights[p] * |M(p)|) == constant``.

    ``constant`` ``None`` means "whatever the initial marking gives".
    """

    weights: Mapping[str, int]
    constant: int | None = None
    name: str | None = None


def incidence(net: Net) -> dict[str, dict[str, int]]:
    """``C[place][transition]``: tokens a firing adds to the place, minus those it takes."""
    matrix: dict[str, dict[str, int]] = {
        place.name: {tr.name: 0 for tr in net.transitions} for place in net.places
    }
    for arc in net.arcs:
        if arc.consume is not None and arc.from_place and arc.to_transition:
            if arc.consume.mode == "consume":
                matrix[arc.from_place][arc.to_transition] -= arc.consume.weight
        elif arc.produce is not None and arc.from_transition:
            matrix[arc.produce.destination][arc.from_transition] += 1
    return matrix


def semiflows(net: Net) -> list[dict[str, int]]:
    """The minimal P-semiflows of the skeleton, in a stable order."""
    places = [place.name for place in net.places]
    transitions = [tr.name for tr in net.transitions]
    matrix = incidence(net)
    n = len(places)
    rows: list[tuple[list[int], list[int]]] = [
        ([matrix[p][t] for t in transitions], [1 if i == j else 0 for j in range(n)])
        for i, p in enumerate(places)
    ]
    for column in range(len(transitions)):
        positive = [row for row in rows if row[0][column] > 0]
        negative = [row for row in rows if row[0][column] < 0]
        kept = [row for row in rows if row[0][column] == 0]
        for c1, y1 in positive:
            for c2, y2 in negative:
                a, b = -c2[column], c1[column]
                combined = (
                    [a * x + b * z for x, z in zip(c1, c2, strict=True)],
                    [a * x + b * z for x, z in zip(y1, y2, strict=True)],
                )
                kept.append(_normalize(combined))
        rows = _minimal(kept)
    result: list[dict[str, int]] = []
    for _, y in rows:
        result.append({places[i]: y[i] for i in range(n) if y[i]})
    result.sort(key=lambda flow: [places.index(p) for p in flow])
    return result


def _normalize(row: tuple[list[int], list[int]]) -> tuple[list[int], list[int]]:
    divisor = 0
    for value in row[0] + row[1]:
        divisor = gcd(divisor, value)
    if divisor > 1:
        return [v // divisor for v in row[0]], [v // divisor for v in row[1]]
    return row


def _minimal(
    rows: list[tuple[list[int], list[int]]],
) -> list[tuple[list[int], list[int]]]:
    supports = [frozenset(i for i, v in enumerate(y) if v) for _, y in rows]
    keep: list[tuple[list[int], list[int]]] = []
    seen: set[tuple[int, ...]] = set()
    for i, row in enumerate(rows):
        if not supports[i]:
            continue
        if any(supports[j] < supports[i] for j in range(len(rows))):
            continue
        key = tuple(row[1])
        if key in seen:
            continue
        seen.add(key)
        keep.append(row)
    return keep


def _weighted(weights: Mapping[str, int]) -> str:
    return " + ".join(name if k == 1 else f"{k}·{name}" for name, k in weights.items())


def _count(weights: Mapping[str, int], marking: Marking | None) -> int:
    if marking is None:
        return 0
    return sum(k * len(marking.get(p, ())) for p, k in weights.items())


def _shared_key(model: NetModel, places: Sequence[str]) -> str | None:
    """A key the colors of these places all carry, in fields a correlate
    names; a key that only a `data cel` copy joins is no per-key reading."""
    common: set[str] | None = None
    for place in places:
        for color in model.places[place].accepts:
            keys: set[str] = set()
            for path in model.known.get(color, set()):
                domain = model.domain(color, path)
                if (
                    domain is not None
                    and domain.kind == "key"
                    and domain.own
                    and model.canonical(color, path) in model.correlated
                ):
                    keys.add(str(domain.own))
            common = keys if common is None else common & keys
    if not common:
        return None
    return sorted(common)[0].removeprefix("own-")


def place_invariant_proofs(net: Net, model: NetModel) -> list[Proof]:
    proofs: list[Proof] = []
    initial = model.initial_marking()
    matrix = incidence(net)
    # A place no firing changes (a fact the net only reads) is its own
    # semiflow; it says nothing, so it is left out.
    flows = [
        flow
        for flow in semiflows(net)
        if any(matrix[place][tr] for place in flow for tr in matrix[place])
    ]
    for index, flow in enumerate(flows, start=1):
        constant = _count(flow, initial)
        opened = [p for p in flow if p in model.roles.open]
        statement = f"{_weighted(flow)} = {constant}"
        if opened:
            statement += (
                ", plus one for each token the environment puts into "
                + ", ".join(f"({p})" for p in opened)
            )
        colors: dict[str, list[str]] = {}
        for place in flow:
            for color in model.places[place].accepts:
                colors.setdefault(color, []).append(place)
        reading = "; ".join(
            f"{color} tokens in " + ", ".join(f"({p})" for p in places)
            for color, places in colors.items()
        )
        details: dict[str, Any] = {
            "weights": dict(flow),
            "initial": constant,
            "open": opened,
            "colors": colors,
        }
        key = _shared_key(model, list(flow))
        sentence = f"Counts {reading}."
        if key is not None:
            details["sharedKey"] = key
            sentence += (
                f" The colors share the key {key!r} through correlates, so it "
                f"likely holds per {key}; only the total count is proved."
            )
        proofs.append(
            Proof(
                "invariant",
                f"place invariant {index}",
                "proved",
                statement + ". " + sentence,
                details=details,
            )
        )
    return proofs


def _arrivals(
    weights: Mapping[str, int], model: NetModel, environment: Environment
) -> tuple[int, str | None]:
    """What the environment adds to a weighted sum, and why that is not one
    number when it is not.

    The environment model puts one token into each open place (or as many as
    ``injections`` allow), one start token per start (``starts``) into one of
    the start places, and a clock token into each empty clock place.
    """
    roles = model.roles
    initial = model.net.initial_marking
    added = 0
    for place, weight in weights.items():
        if place in roles.clocks:
            added += weight if not (initial and initial.get(place)) else 0
        elif place in roles.open and place not in roles.start:
            added += weight * environment.injections.get(place, 1)
    starts = {place: weights.get(place, 0) for place in roles.start}
    if not starts:
        return added, None
    arrivals = environment.starts
    if initial is not None and any(
        token.type == roles.instance_color
        for place in initial
        for token in initial[place]
    ):
        arrivals -= 1
    if arrivals == 0:
        return added, None
    if len(set(starts.values())) > 1:
        return added, (
            "the instance may start in "
            + " or ".join(f"({p})" for p in sorted(starts))
            + ", which the sum weighs differently"
        )
    return added + arrivals * next(iter(starts.values())), None


def declared_invariant_proofs(
    net: Net,
    model: NetModel,
    invariants: Sequence[Invariant],
    environment: Environment | None = None,
) -> list[Proof]:
    """Prove each declared invariant: no firing changes the weighted sum, and
    the sum equals the declared constant once the environment has made the
    arrivals its model allows."""
    environment = environment or Environment()
    matrix = incidence(net)
    proofs: list[Proof] = []
    for index, invariant in enumerate(invariants, start=1):
        name = invariant.name or f"declared invariant {index}"
        unknown = sorted(set(invariant.weights) - set(matrix))
        statement = f"{_weighted(invariant.weights)} = " + (
            str(invariant.constant)
            if invariant.constant is not None
            else "its initial value"
        )
        if unknown:
            proofs.append(
                Proof(
                    "invariant",
                    name,
                    "unknown",
                    statement,
                    reason=f"unknown place {unknown[0]!r}",
                )
            )
            continue
        findings: list[Finding] = []
        for tr in net.transitions:
            delta = sum(k * matrix[p][tr.name] for p, k in invariant.weights.items())
            if delta:
                findings.append(
                    Finding(
                        kind="changes",
                        summary=f"[{tr.name}] changes the sum by {delta:+d}.",
                        transition=tr.name,
                    )
                )
        initial = _count(invariant.weights, model.initial_marking())
        added, ambiguous = _arrivals(invariant.weights, model, environment)
        opened = [p for p in invariant.weights if p in model.roles.open]
        if (
            invariant.constant is not None
            and ambiguous is None
            and invariant.constant != initial + added
        ):
            summary = f"The initial marking gives {initial}, not {invariant.constant}."
            if added:
                summary = (
                    f"The initial marking gives {initial} and the environment's "
                    f"arrivals add {added}: {initial + added}, not {invariant.constant}."
                )
            findings.insert(0, Finding(kind="initial", summary=summary))
        details: dict[str, Any] = {
            "weights": dict(invariant.weights),
            "initial": initial,
        }
        if opened:
            details["open"] = opened
            details["arrivals"] = added
        status: Status = "refuted" if findings else "proved"
        reason = None
        if (
            status == "proved"
            and ambiguous is not None
            and invariant.constant is not None
        ):
            status, reason = "unknown", ambiguous
        if not findings and opened:
            statement += " once the environment has put its tokens into " + ", ".join(
                f"({p})" for p in opened
            )
        proofs.append(
            Proof(
                "invariant",
                name,
                status,
                statement,
                findings=tuple(findings),
                reason=reason,
                details=details,
            )
        )
    return proofs


__all__ = ["Invariant", "incidence", "semiflows"]
