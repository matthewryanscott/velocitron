"""Frozen dataclasses for the Petri net JSON schema.

Pure data: no behavior, no validation logic. Validation lives in
``velocitron_petrinet``. Field names are part of the public contract and are read
by attribute in the test suite — do not rename.
"""

from __future__ import annotations

from collections.abc import ItemsView, Iterable, Mapping, ValuesView
from dataclasses import dataclass
from typing import Any, Literal, TypeVar, overload
from pyrsistent import PVector, pvector

_T = TypeVar("_T")


@dataclass(frozen=True)
class Token:
    """A colored token: a type string plus a JSON-object payload."""

    type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class Port:
    """A place facet marking the place as a composition boundary."""

    direction: Literal["input", "output"]
    type: str


@dataclass(frozen=True)
class CapacityPerColorKey:
    """A place's non-behavioral verification bound (ADR 0019).

    At most ``max`` tokens per distinct value of the token-data key(s)
    ``keys`` (a single-field key parses to a 1-tuple). The engine never
    reads this — it does not gate enablement, binding, firing, or deposit;
    it is consumed only by the declarative property pass
    (:mod:`velocitron_properties`).
    """

    keys: tuple[str, ...]
    max: int


@dataclass(frozen=True)
class Place:
    """A place: name, accepted token types, and an optional port facet."""

    name: str
    accepts: list[str]
    port: Port | None = None
    description: str | None = None
    annotations: dict[str, Any] | None = None
    capacity_per_color_key: CapacityPerColorKey | None = None


@dataclass(frozen=True)
class Timer:
    """A transition's declarative temporal enablement condition (ADR 0018).

    ``clock`` names the clock place whose first token is the time reference
    (exposed to ``cel`` and optional ``maturity`` as the reserved variable
    ``clock``); ``cel`` is the authoritative temporal enablement condition,
    compiled at parse (D6); ``bind`` optionally maps CEL variable names to
    binding places, exposing the candidate binding's tokens to both
    expressions. ``maturity`` is the optional Runtime scheduling expression:
    it declares the next monotonic timestamp at which that candidate may
    mature. The deadline lives in token data — the engine holds no timer state.
    """

    clock: str
    cel: str
    bind: dict[str, str] | None = None
    maturity: str | None = None


@dataclass(frozen=True)
class Transition:
    """A transition: name, optional handler ref, optional guard ref, optional
    priority (honored by the built-in ``priority`` firing policy, ADR 0014),
    optional timer (ADR 0018), optional binding names (ADR 0032)."""

    name: str
    handler: str | None = None
    guard: str | None = None
    priority: int | None = None
    timer: Timer | None = None
    description: str | None = None
    annotations: dict[str, Any] | None = None
    binding_names: dict[str, str] | None = None
    """The key CEL's ``binding`` uses for each binding place: key → place.

    ``None`` keys ``binding`` by place name. The composition merge sets it to
    the constituent-local names, so the transition's CEL keeps its meaning
    after the merge renames places.
    """


@dataclass(frozen=True)
class Predicate:
    """A single-token arc filter: inline CEL OR a named pure predicate handler.

    Exactly one of ``cel`` / ``handler`` is set; the other is ``None``.
    """

    cel: str | None
    handler: str | None


@dataclass(frozen=True)
class ConsumePattern:
    """An arc's consume contract: token type, optional predicate, and mode.

    ``mode`` is one of:

    - ``"consume"`` (default) — remove ``weight`` matching tokens on fire.
    - ``"inhibit"`` — a zero-test requiring the absence of a matching token;
      consumes nothing and never contributes to the binding.
    - ``"read"`` — test-without-consume: gates enablement on the presence of
      ``weight`` matching tokens (like consume) and those tokens contribute to
      the binding (guard/handler/firing record see them), but they are NOT
      removed on fire.

    ``weight`` is the number of matching tokens the arc requires (default 1 =
    classical one-token-per-arc). It applies to ``consume`` (that many removed)
    and ``read`` (that many present and bound, none removed); it is ignored
    (and rejected by the parser) on inhibit arcs, which consume nothing by
    definition.

    ``correlate`` is the CEL source of a binding-correlated test over
    ``{token: <one token's data>, binding: <place-keyed bound-token data>}``.
    On an inhibit arc it is the anti-join (ADR 0017): the transition is
    enabled under a candidate binding only if NO matching token in the source
    place satisfies it. On a consume or read arc it is a join (ADR 0030):
    every token the arc binds must satisfy it. ``None`` (the default) adds no
    cross-token test.
    """

    type: str
    predicate: Predicate | None
    mode: Literal["consume", "inhibit", "read"]
    weight: int = 1
    correlate: str | None = None


@dataclass(frozen=True)
class ProduceTemplate:
    """An arc's produce contract: a routing declaration, not the tokens.

    Declares the output ``type`` and ``destination`` place; the handler
    supplies the actual tokens. Optional literal ``data`` lets a passthrough
    or routing transition emit a fixed token without a registered handler.
    Optional ``cel`` (ADR 0023, mutually exclusive with ``data``) is the
    computed variant: evaluated at deposit over the ADR 0017 ``binding``
    map for a pair the handler left uncovered.
    """

    type: str
    destination: str
    data: object | None = None
    cel: str | None = None


@dataclass(frozen=True)
class Arc:
    """An arc-centric edge.

    A consume arc sets ``from_place`` + ``to_transition`` and ``consume``
    (``produce`` is ``None``). A produce arc sets ``from_transition`` +
    ``to_place`` and ``produce`` (``consume`` is ``None``).
    """

    from_place: str | None = None
    from_transition: str | None = None
    to_place: str | None = None
    to_transition: str | None = None
    consume: ConsumePattern | None = None
    produce: ProduceTemplate | None = None
    description: str | None = None
    annotations: dict[str, Any] | None = None


class Marking(Mapping[str, PVector[Token]]):
    """Immutable, persistent, structurally-shared mapping over places.

    A thin wrapper over a ``dict[str, PVector[Token]]`` that is never
    changed after it is built: the outer map is keyed by place, and each
    per-place collection is a persistent vector (``PVector``, pyrsistent)
    rather than a persistent set. The ``PVector`` choice is deliberate, for
    two reasons:

    - ``Token`` is unhashable (a frozen dataclass carrying a ``dict``
      payload), so a hash-keyed ``PSet`` cannot hold tokens at all.

    - Per-place insertion order is load-bearing: deterministic binding
      selection walks each place's tokens lexicographically by insertion
      order so firings replay identically.

    The read API is the full ``collections.abc.Mapping`` surface (``[]``,
    ``.get``, ``in``, ``.items()``, ``.values()``, ``len``, iteration).
    ``Marking`` is unhashable (because ``Token`` is), matching the
    equality-based multiset contract.

    Mutation goes through ``.set(key, iterable)``, which returns a NEW
    ``Marking`` that shares the token vectors of untouched places; in-place
    writes raise (``Marking`` has no ``__setitem__``; ``PVector`` is
    immutable). The outer map is copied on ``set`` rather than kept as a
    persistent map: a net has tens of places, and copying a dict that size
    costs less than a persistent-map update, while every read is a plain
    dict lookup. The inherited ``Mapping.__eq__`` compares content, so a
    ``Marking`` equals a plain ``dict`` of lists when their contents match
    (``PVector`` compares equal to a ``list``).

    References: spec/firing-semantics.md (D2); AGENTS.md.
    """

    __slots__ = ("_places",)

    def __init__(
        self, data: Mapping[str, Iterable[Token]] | "Marking" | None = None
    ) -> None:
        if data is None:
            self._places: dict[str, PVector[Token]] = {}
        elif isinstance(data, Marking):
            # Re-wrapping a Marking shares its map, which nobody changes.
            self._places = data._places
        else:
            self._places = {
                k: v if isinstance(v, PVector) else pvector(v) for k, v in data.items()
            }

    @classmethod
    def _from_places(cls, places: dict[str, PVector[Token]]) -> "Marking":
        """Internal reconstruction seam: wrap an already-built map.

        Wraps the map without re-coercing its values or copying it; the
        caller hands it over and never changes it again. Used by ``set`` so
        updates route through here rather than the public constructor
        (which takes the dict-of-lists shape).

        References: spec/firing-semantics.md (D4).
        """
        m = cls.__new__(cls)
        m._places = places
        return m

    def __getitem__(self, key: str) -> PVector[Token]:
        return self._places[key]

    # The prover reads markings millions of times; these skip the
    # Mapping mixins, which look every key up again through __getitem__.
    @overload
    def get(self, key: str, /) -> PVector[Token] | None: ...
    @overload
    def get(self, key: str, default: PVector[Token] | _T, /) -> PVector[Token] | _T: ...
    def get(self, key: str, default: Any = None) -> Any:
        return self._places.get(key, default)

    def items(self) -> ItemsView[str, PVector[Token]]:
        return self._places.items()

    def values(self) -> ValuesView[PVector[Token]]:
        return self._places.values()

    def __contains__(self, key: object) -> bool:
        return key in self._places

    def __iter__(self):
        return iter(self._places)

    def __len__(self) -> int:
        return len(self._places)

    def set(self, key: str, value: Iterable[Token] | PVector[Token]) -> "Marking":
        """Return a new ``Marking`` with ``key`` set to ``value`` (coerced to
        a ``PVector``); untouched places are shared structurally."""
        pv = value if isinstance(value, PVector) else pvector(value)
        places = dict(self._places)
        places[key] = pv
        return type(self)._from_places(places)

    def __repr__(self) -> str:
        return f"Marking({self._places!r})"


@dataclass(frozen=True)
class DeclaredInvariant:
    """A place invariant the author claims: ``sum(weights[p] * |M(p)|) == constant``.

    ``constant`` ``None`` means whatever the initial marking and the
    environment give. The engine never reads it; ``velocitron prove`` does.
    """

    weights: dict[str, int]
    constant: int | None = None
    name: str | None = None


@dataclass(frozen=True)
class ProofFacts:
    """Claims about the net that only ``velocitron prove`` checks (ADR 0037).

    Each ``final`` entry is a final marking: the places that must all hold a
    token before the instance is finished (ADR 0049).
    """

    final: list[tuple[str, ...]] | None = None
    invariants: list[DeclaredInvariant] | None = None


@dataclass(frozen=True)
class Net:
    """A complete Petri net: places, transitions, arc-centric arcs, marking.

    ``domains`` maps ``color.field.path`` to the closed list of values that
    field holds; the engine rejects a deposit or an injection outside it
    (ADR 0037).
    """

    name: str
    places: list[Place]
    transitions: list[Transition]
    arcs: list[Arc]
    initial_marking: Marking | None = None
    description: str | None = None
    annotations: dict[str, Any] | None = None
    domains: dict[str, list[Any]] | None = None
    proofs: ProofFacts | None = None


@dataclass(frozen=True)
class Wire:
    """A composition wire: an output port of one net to an input port of another."""

    from_net: str
    from_port: str
    to_net: str
    to_port: str


@dataclass(frozen=True)
class Refinement:
    """A composition refinement: the ``by`` net replaces ``net``'s ``transition``."""

    net: str
    transition: str
    by: str


@dataclass(frozen=True)
class Share:
    """A composition share: places of several nets that are one place.

    Each member is a ``(net alias, place name)`` pair. A share has no
    direction, and its members need not be ports (ADR 0040).
    """

    members: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class NetRef:
    """A reference to a net document within a composition, with an optional alias."""

    ref: str
    alias: str | None = None


@dataclass(frozen=True)
class Composition:
    """A composition document: net references, the wires connecting their
    ports, the places the nets share, and the transitions other nets refine.

    ``nets`` are the references as written. A referenced composition is
    flattened (ADR 0041): ``parsed_nets``, ``wires``, ``shares`` and
    ``refinements`` name its nets ``<alias>.<inner alias>``, and ``sources``
    gives each parsed net's reference, rebased onto this composition.
    ``final`` holds the final markings the composition declares, each a
    tuple of ``(net alias, place name)`` pairs (ADR 0049); a referenced
    composition's own ``final`` does not carry over.
    """

    nets: list[NetRef]
    wires: list[Wire]
    parsed_nets: dict[str, Net] | None = None
    refinements: tuple[Refinement, ...] = ()
    shares: tuple[Share, ...] = ()
    sources: dict[str, str] | None = None
    name: str | None = None
    final: tuple[tuple[tuple[str, str], ...], ...] | None = None
