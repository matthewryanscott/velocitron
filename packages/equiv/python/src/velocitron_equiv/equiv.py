"""Structural equivalence of two nets up to renaming (``velocitron equiv``).

Both sides are merged first (a plain net stays as it is), so a single net,
a composition of sub-nets and a composition that uses another composition
can all be compared. A place or transition is known by its local name: its
merged name without the alias of the net that declares it (``gate.pending``
is ``pending``), and a fused place by the local names of its members. Two
sides are equivalent when this renaming maps every place, transition and arc
of one onto the other with the same behavior facts: colors, capacities,
environment supply, kept records, final places and markings, initial marking, guards,
priorities, handlers, timers, arc inscriptions, CEL binding names, domains
and declared invariants. Ports are the interface of a net, not its behavior: they are
reported apart and do not make two nets different.

References: ADR 0042; spec/composition.md.

``velocitron_equiv`` re-exports this module. The umbrella console entry
injects :func:`add_parser` and :func:`main`. This package does not import
``velocitron``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from velocitron_analysis import Composed, load
from velocitron_dsl import PetrinetDslError
from velocitron_engine import Arc, Marking, Net, Place, Timer
from velocitron_merge import port_fusion_map
from velocitron_petrinet import NetValidationError

MAX_DIFFERENCES = 20
_BINDING_KEY = re.compile(r"\bbinding\.([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class Equivalence:
    """The result of comparing two nets.

    ``renaming`` maps each node of the first net whose name differs to the
    node of the second (``(pending)`` to ``(start.pending)``).
    ``differences`` are behavior differences; ``interface`` are port
    differences, which do not count against equivalence.
    """

    renaming: tuple[tuple[str, str], ...]
    differences: tuple[str, ...]
    interface: tuple[str, ...]
    counts: tuple[int, int, int]

    @property
    def equivalent(self) -> bool:
        return not self.differences

    def text(self, first: str, second: str) -> str:
        places, transitions, arcs = self.counts
        lines: list[str] = []
        if self.equivalent:
            lines.append(f"equivalent up to renaming: {first} and {second}")
            lines.append(f"  {places} places, {transitions} transitions, {arcs} arcs")
        else:
            count = len(self.differences)
            lines.append(
                f"different: {first} and {second} "
                f"({count} difference{'s' if count != 1 else ''})"
            )
            for difference in self.differences[:MAX_DIFFERENCES]:
                lines.append(f"  - {difference}")
            if count > MAX_DIFFERENCES:
                lines.append(f"  ... and {count - MAX_DIFFERENCES} more")
        if self.renaming:
            lines.append("")
            lines.append(f"renaming ({first} -> {second}):")
            lines += [f"  {a} = {b}" for a, b in self.renaming]
        if self.interface:
            lines.append("")
            lines.append("interface differences (ports, not behavior):")
            lines += [f"  - {item}" for item in self.interface]
        return "\n".join(lines) + "\n"

    def as_json(self) -> dict[str, Any]:
        return {
            "equivalent": self.equivalent,
            "renaming": [{"first": a, "second": b} for a, b in self.renaming],
            "differences": list(self.differences),
            "interface": list(self.interface),
        }


@dataclass
class _Side:
    """One merged net with what is needed to name its nodes locally."""

    net: Net
    aliases: tuple[str, ...]
    members: dict[str, list[str]]
    closed: frozenset[str]

    @classmethod
    def of(cls, net: Net, composed: Composed | None) -> _Side:
        members: dict[str, list[str]] = {
            place.name: [place.name] for place in net.places
        }
        aliases: tuple[str, ...] = ()
        closed: frozenset[str] = frozenset()
        if composed is not None:
            aliases = tuple(composed.nets)
            fusion = port_fusion_map(composed.nets, composed.wires, composed.shares)
            grouped: dict[str, list[str]] = {}
            for member, fused in sorted(fusion.items()):
                grouped.setdefault(fused, []).append(member)
            members.update(grouped)
            closed = composed.fused()
        return cls(
            net=net,
            aliases=aliases,
            members=members,
            closed=closed,
        )

    def suffixes(self, qualified: str) -> list[set[str]]:
        """The names ``qualified`` answers to, by how many alias segments
        they keep: for ``lifecycle.gate.pending``, ``pending``, then
        ``lifecycle.pending`` and ``gate.pending``, then the full name."""
        alias = max(
            (a for a in self.aliases if qualified.startswith(f"{a}.")),
            key=len,
            default="",
        )
        if not alias:
            return [{qualified}]
        segments = alias.split(".")
        local = qualified[len(alias) + 1 :]
        return [
            {
                ".".join([*segments[:depth], local]),
                ".".join([*segments[len(segments) - depth :], local]),
            }
            if depth
            else {local}
            for depth in range(len(segments) + 1)
        ]


def _keys(side: _Side, names: Iterable[str], depth: int) -> set[str]:
    keys: set[str] = set()
    for name in names:
        suffixes = side.suffixes(name)
        keys |= suffixes[min(depth, len(suffixes) - 1)]
    return keys


def _match(
    first: _Side,
    second: _Side,
    nodes_a: Mapping[str, list[str]],
    nodes_b: Mapping[str, list[str]],
) -> dict[str, str]:
    """Pair nodes whose local names agree; deeper alias segments break ties."""
    mapping: dict[str, str] = {}
    left = dict(nodes_a)
    right = dict(nodes_b)
    depth = 0
    deepest = max(
        [
            len(side.suffixes(m))
            for side, nodes in ((first, left), (second, right))
            for members in nodes.values()
            for m in members
        ]
        or [1]
    )
    while left and right and depth < deepest:
        keys_a = {name: _keys(first, members, depth) for name, members in left.items()}
        keys_b = {
            name: _keys(second, members, depth) for name, members in right.items()
        }
        index_b: dict[str, set[str]] = {}
        for name, keys in keys_b.items():
            for key in keys:
                index_b.setdefault(key, set()).add(name)
        index_a: dict[str, set[str]] = {}
        for name, keys in keys_a.items():
            for key in keys:
                index_a.setdefault(key, set()).add(name)
        for name, keys in sorted(keys_a.items()):
            candidates = {b for key in keys for b in index_b.get(key, ())}
            if len(candidates) != 1:
                continue
            (candidate,) = candidates
            back = {a for key in keys_b[candidate] for a in index_a.get(key, ())}
            if back == {name}:
                mapping[name] = candidate
        for name, candidate in mapping.items():
            left.pop(name, None)
            right.pop(candidate, None)
        depth += 1
    return mapping


def compare(
    first: Net,
    second: Net,
    first_composition: Composed | None = None,
    second_composition: Composed | None = None,
) -> Equivalence:
    """Compare two merged nets up to the renaming of places and transitions."""
    side_a = _Side.of(first, first_composition)
    side_b = _Side.of(second, second_composition)
    places = _match(
        side_a,
        side_b,
        {p.name: side_a.members[p.name] for p in first.places},
        {p.name: side_b.members[p.name] for p in second.places},
    )
    transitions = _match(
        side_a,
        side_b,
        {t.name: [t.name] for t in first.transitions},
        {t.name: [t.name] for t in second.transitions},
    )
    # Canonical names are the first net's local names; an unmatched node of
    # the second net keeps its own name, marked so it never collides.
    canon_a = _Canon(
        _local_names(side_a, [p.name for p in first.places]),
        _local_names(side_a, [t.name for t in first.transitions]),
    )
    canon_b = _Canon(
        {b: canon_a.places[a] for a, b in places.items()},
        {b: canon_a.transitions[a] for a, b in transitions.items()},
    )
    for place in second.places:
        canon_b.places.setdefault(place.name, f"{place.name} (second only)")
    for transition in second.transitions:
        canon_b.transitions.setdefault(
            transition.name, f"{transition.name} (second only)"
        )

    differences: list[str] = []
    for place in first.places:
        if place.name not in places:
            differences.append(
                f"place ({canon_a.places[place.name]}) is only in the first net"
            )
    for place in second.places:
        if place.name not in places.values():
            differences.append(f"place ({place.name}) is only in the second net")
    for transition in first.transitions:
        if transition.name not in transitions:
            differences.append(
                f"transition [{canon_a.transitions[transition.name]}] is only in "
                "the first net"
            )
    for transition in second.transitions:
        if transition.name not in transitions.values():
            differences.append(
                f"transition [{transition.name}] is only in the second net"
            )

    facts_a = _facts(side_a, canon_a)
    facts_b = _facts(side_b, canon_b)
    for key in sorted(set(facts_a) | set(facts_b)):
        value_a, value_b = facts_a.get(key), facts_b.get(key)
        if value_a != value_b:
            differences.append(_describe(key, value_a, value_b))

    interface: list[str] = []
    ports_a = {canon_a.places[p.name]: _port(p) for p in first.places}
    ports_b = {canon_b.places[p.name]: _port(p) for p in second.places}
    for name in sorted(set(ports_a) | set(ports_b)):
        port_a, port_b = ports_a.get(name), ports_b.get(name)
        if port_a != port_b and (port_a or port_b):
            interface.append(
                f"({name}): {port_a or 'no port'} in the first net, "
                f"{port_b or 'no port'} in the second"
            )

    renaming = tuple(
        sorted(
            [(f"({a})", f"({b})") for a, b in places.items() if a != b]
            + [(f"[{a}]", f"[{b}]") for a, b in transitions.items() if a != b]
        )
    )
    return Equivalence(
        renaming=renaming,
        differences=tuple(differences),
        interface=tuple(interface),
        counts=(len(first.places), len(first.transitions), len(first.arcs)),
    )


@dataclass(frozen=True)
class _Canon:
    """The name each merged place and transition is compared under."""

    places: dict[str, str]
    transitions: dict[str, str]


def _local_names(side: _Side, names: Sequence[str]) -> dict[str, str]:
    """Each node's local name, or its merged name when the local name is
    not one name or is not unique among ``names``."""
    local: dict[str, str] = {}
    for name in names:
        keys = _keys(side, side.members.get(name, [name]), 0)
        local[name] = next(iter(keys)) if len(keys) == 1 else name
    counts: dict[str, int] = {}
    for value in local.values():
        counts[value] = counts.get(value, 0) + 1
    return {
        name: value if counts[value] == 1 else name for name, value in local.items()
    }


def _port(place: Place) -> str | None:
    if place.port is None:
        return None
    return f"{place.port.direction} port {place.port.type}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _arc_label(arc: Arc, canon: _Canon) -> tuple[str, str]:
    """``(place) -color-> [transition]`` and the arc's own facts."""
    if arc.consume is not None:
        operator = {"consume": "->", "read": "->?", "inhibit": "->0"}[arc.consume.mode]
        label = (
            f"({canon.places[arc.from_place or '']}) -{arc.consume.type}{operator} "
            f"[{canon.transitions[arc.to_transition or '']}]"
        )
        predicate = arc.consume.predicate
        facts = {
            "weight": arc.consume.weight,
            "predicate": None
            if predicate is None
            else {"cel": predicate.cel, "handler": predicate.handler},
            "correlate": arc.consume.correlate,
        }
        return label, _json(facts)
    produce = arc.produce
    assert produce is not None
    label = (
        f"[{canon.transitions[arc.from_transition or '']}] -{produce.type}-> "
        f"({canon.places[produce.destination]})"
    )
    return label, _json({"data": produce.data, "cel": produce.cel})


def _timer(timer: Timer | None, canon: Mapping[str, str]) -> str | None:
    """A timer with its places renamed by ``canon`` (the place names)."""
    if timer is None:
        return None
    return _json(
        {
            "clock": canon[timer.clock],
            "cel": timer.cel,
            "bind": {k: canon[v] for k, v in (timer.bind or {}).items()},
            "maturity": timer.maturity,
        }
    )


def _facts(side: _Side, canon: _Canon) -> dict[tuple[str, ...], Any]:
    """Every behavior fact of a net, keyed by what it is about."""
    net = side.net
    places = canon.places
    facts: dict[tuple[str, ...], Any] = {}
    final_markings = (net.proofs.final or []) if net.proofs is not None else []
    final = {marking[0] for marking in final_markings if len(marking) == 1}
    taken = {
        arc.from_place
        for arc in net.arcs
        if arc.consume is not None and arc.consume.mode in ("consume", "read")
    }
    produced = {arc.produce.destination for arc in net.arcs if arc.produce is not None}
    marking = net.initial_marking if net.initial_marking is not None else Marking()
    for place in net.places:
        name = places[place.name]
        facts[("place", name, "colors")] = sorted(place.accepts)
        capacity = place.capacity_per_color_key
        facts[("place", name, "capacity")] = (
            None
            if capacity is None
            else {"keys": list(capacity.keys), "max": capacity.max}
        )
        # The prover lets the environment supply a place the net takes from
        # when nothing in the net produces into it, or when it is a fusion
        # place the composition did not close (ADR 0040).
        fusion = bool((place.annotations or {}).get("fusion"))
        # A kept record is the net's own from the start (ADR 0051).
        kept = (place.annotations or {}).get("kept")
        facts[("place", name, "kept")] = kept
        facts[("place", name, "supplied by the environment")] = (
            kept is None
            and place.name in taken
            and (
                place.name not in produced or (fusion and place.name not in side.closed)
            )
        )
        facts[("place", name, "final")] = place.name in final
        facts[("place", name, "marking")] = sorted(
            _json({"type": token.type, "data": token.data})
            for token in marking.get(place.name, [])
        )
    bound: dict[str, dict[str, str]] = {}
    for arc in net.arcs:
        if (
            arc.consume is not None
            and arc.consume.mode in ("consume", "read")
            and arc.from_place is not None
            and arc.to_transition is not None
        ):
            # A net that is not a merge names its places directly in CEL.
            key = next(iter(side.suffixes(arc.from_place)[0]))
            bound.setdefault(arc.to_transition, {})[key] = places[arc.from_place]
    cel_names: dict[str, set[str]] = {}
    for arc in net.arcs:
        texts: list[str | None] = []
        if arc.consume is not None:
            predicate = arc.consume.predicate
            texts += [arc.consume.correlate, predicate.cel if predicate else None]
        if arc.produce is not None:
            texts.append(arc.produce.cel)
            if arc.produce.data is not None:
                texts.append(_json(arc.produce.data))
        transition_name = arc.to_transition or arc.from_transition or ""
        for text in texts:
            if text:
                cel_names.setdefault(transition_name, set()).update(
                    _BINDING_KEY.findall(text)
                )
    for transition in net.transitions:
        name = canon.transitions[transition.name]
        facts[("transition", name, "guard")] = transition.guard
        facts[("transition", name, "priority")] = transition.priority
        facts[("transition", name, "handler")] = transition.handler
        facts[("transition", name, "timer")] = _timer(transition.timer, places)
        names = (
            {key: places[place] for key, place in transition.binding_names.items()}
            if transition.binding_names is not None
            else bound.get(transition.name, {})
        )
        # Only the names the transition's CEL reads change what it means.
        used = cel_names.get(transition.name, set())
        facts[("transition", name, "binding names")] = {
            key: place for key, place in sorted(names.items()) if key in used
        }
    arcs: dict[str, list[str]] = {}
    for arc in net.arcs:
        label, inscription = _arc_label(arc, canon)
        arcs.setdefault(label, []).append(inscription)
    for label, inscriptions in arcs.items():
        facts[("arc", label)] = sorted(inscriptions)
    for key, values in (net.domains or {}).items():
        facts[("domain", key)] = sorted(_json(value) for value in values)
    facts[("final markings",)] = sorted(
        sorted(places[place] for place in marking)
        for marking in final_markings
        if len(marking) > 1
    )
    invariants = (net.proofs.invariants or []) if net.proofs is not None else []
    facts[("invariants",)] = sorted(
        _json(
            {
                "weights": {places[p]: w for p, w in invariant.weights.items()},
                "constant": invariant.constant,
            }
        )
        for invariant in invariants
    )
    return facts


def _describe(key: tuple[str, ...], first: Any, second: Any) -> str:
    """One difference in the words of the net."""
    if key[0] == "arc":
        if first is None:
            return f"arc {key[1]} is only in the second net"
        if second is None:
            return f"arc {key[1]} is only in the first net"
        if len(first) != len(second):
            return f"arc {key[1]}: {len(first)} in the first net, {len(second)} in the second"
        return f"arc {key[1]}: {_inscription_change(first, second)}"
    if key[0] == "place":
        subject = f"place ({key[1]}) {key[2]}"
    elif key[0] == "transition":
        subject = f"transition [{key[1]}] {key[2]}"
    elif key[0] == "domain":
        subject = f"domain {key[1]}"
    elif key[0] == "final markings":
        subject = "final markings of more than one place"
    else:
        subject = "declared invariants"
    if first is None or second is None:
        missing = "first" if first is None else "second"
        return f"{subject}: missing in the {missing} net"
    return f"{subject}: {_show(first)} in the first net, {_show(second)} in the second"


def _inscription_change(first: Sequence[str], second: Sequence[str]) -> str:
    changes: list[str] = []
    for a, b in zip(first, second, strict=True):
        facts_a, facts_b = json.loads(a), json.loads(b)
        for name in sorted(set(facts_a) | set(facts_b)):
            if facts_a.get(name) != facts_b.get(name):
                changes.append(
                    f"{name} {_show(facts_a.get(name))} in the first net, "
                    f"{_show(facts_b.get(name))} in the second"
                )
    return "; ".join(changes)


def _show(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    predicate = cast(Mapping[str, Any], value) if isinstance(value, Mapping) else None
    if predicate is not None and set(predicate) == {"cel", "handler"}:
        cel, handler = predicate.get("cel"), predicate.get("handler")
        return f"`{cel}`" if cel is not None else f"handler {handler}"
    if isinstance(value, str):
        return f"`{value}`"
    return _json(value)


# ── CLI ──────────────────────────────────────────────────────────────────


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser = commands.add_parser(
        "equiv",
        help="check that two nets are the same net up to renaming",
        description=(
            "Merge both nets (a net, a composition, or a composition that uses "
            "other compositions) and compare them up to the renaming of places "
            "and transitions: a node is known by its name without its net's "
            "alias, and a fused place by its members' names. Compares colors, "
            "capacities, environment supply, kept records, final places and "
            "markings, initial marking, guards, priorities, handlers, timers, arc inscriptions, CEL "
            "binding names, domains and declared invariants. Port differences are "
            "printed apart as interface differences. Exits 0 when the nets are "
            "equivalent, 1 when they differ, 2 when a net cannot be loaded."
        ),
    )
    parser.add_argument(
        "first", metavar="FIRST", help="a .petrinet or .json net or composition"
    )
    parser.add_argument(
        "second", metavar="SECOND", help="a .petrinet or .json net or composition"
    )
    parser.add_argument("--json", action="store_true", help="print the result as JSON")


def main(args: argparse.Namespace) -> int:
    loaded: list[tuple[Net, Composed | None]] = []
    for path in (args.first, args.second):
        try:
            loaded.append(load(Path(path)))
        except PetrinetDslError as error:
            sys.stderr.write(error.diagnostic.render() + "\n")
            return 2
        except (OSError, UnicodeError, ValueError, NetValidationError) as error:
            sys.stderr.write(f"{path}:1:1: error[PN200]: {error}\n")
            return 2
    (first, first_composition), (second, second_composition) = loaded
    result = compare(first, second, first_composition, second_composition)
    if args.json:
        sys.stdout.write(json.dumps(result.as_json(), indent=2) + "\n")
    else:
        sys.stdout.write(result.text(args.first, args.second))
    return 0 if result.equivalent else 1


__all__ = ["Equivalence", "add_parser", "compare", "main"]
