"""What the prover knows about a net before it explores anything.

Two things are derived here, both from the net alone:

- **Roles of places.** Which places the environment writes (open places:
  no producing arc, an input port, a fusion place the net reads, or a timer's
  clock), which of those start the instance, which are shared resources the
  net takes and gives back, and which places are final.
- **Data domains.** For each token field the net's CEL tests, a small finite
  set of values that covers every way the CEL tells values apart: the
  literals a field is compared with (plus ``⟨other⟩``), ``true``/``false``
  for a field used as a boolean, values below, at and above numeric
  literals, ``own``/``other`` key values for fields a correlate joins, three
  ordered slots for fields compared with each other, and time slots for
  fields compared with a clock.

The prover evaluates the net's own CEL through the engine on tokens built
from these domains; nothing here evaluates CEL.

References: spec/proofs.md; ADR 0036.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable, cast

from . import kept as kept_module
from velocitron_engine import domain_violation
from velocitron_engine import Arc, Marking, Net, Token, Transition

from . import celscan
from .celscan import Call, Cmp, Lit, MapLit, Node, Opaque, Ref, Seq

OTHER = "⟨other⟩"
"""The value that stands for every string a field's literals do not name."""

LIST_ITEM = "⟨item⟩"

INSTANCE = frozenset({"key", "ordered", "free"})
"""Domain kinds an instance's own token fixes at its own value."""

ENVIRONMENT = frozenset({"free"})
"""Domain kinds an environment token fixes: it ranges over keys and slots."""

OWN_KEY = frozenset({"key", "free"})
"""An environment token about the instance's own key."""

FieldPath = tuple[str, ...]


@dataclass(frozen=True)
class ClockCopy:
    """A field a timer's maturity reads that was taken from a clock.

    ``offset`` is 0 when the field is the clock's own value (``since:
    binding.clock[0].now``). It is the added literal when the field is a
    deadline dated from the clock (``double(binding.clock[0].now) +
    120.0``). The latch, the field's value minus ``offset``, is the clock
    time that deadline was dated from. A latch has to be one of the
    clock's listed times: one taken at a maturity would date the next
    deadline later still, and time would never run out of new values.
    """

    place: str
    field: Field
    offset: int | float


@dataclass(frozen=True, order=True)
class Field:
    """One token field: a color and a path of keys into its data."""

    color: str
    path: FieldPath

    def text(self) -> str:
        return f"{self.color}.{'.'.join(self.path)}"


@dataclass(frozen=True)
class Domain:
    """The finite values the prover gives one field.

    ``values`` is the full domain, used by choice coverage. ``named`` leaves
    out ``⟨other⟩`` and, for a key, another key's value, unless a test passes
    them (``!=``, or a negated ``==`` or ``in``); soundness uses it.
    ``own`` is the value an instance's own token takes for a key, an ordered
    slot or a free field. ``bounds`` are the numbers the CEL compares a
    ``number`` or ``time`` field (or a ``list`` field's size) with; the
    values are points below, at and above them.
    """

    kind: str
    values: tuple[Any, ...]
    named: tuple[Any, ...]
    own: Any = None
    source: str = "derived"
    bounds: tuple[float | int, ...] = ()

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "values": list(self.values),
            "source": self.source,
        }
        if self.named != self.values:
            payload["soundnessValues"] = list(self.named)
        if self.own is not None:
            payload["own"] = self.own
        return payload


@dataclass
class _Facts:
    """What the CEL says about one field, or one class of joined fields."""

    literals: list[Any] = field(default_factory=list)
    numbers: list[float | int] = field(default_factory=list)
    sizes: list[int] = field(default_factory=list)
    boolean: bool = False
    ordered: bool = False
    clock: bool = False
    # Compared with ``!=`` (or a negated ``==``/``in``): a value that no
    # literal, or no joined field, names passes a test.
    differs: bool = False
    opaque: list[str] = field(default_factory=list)

    def merge(self, other: _Facts) -> None:
        self.literals += other.literals
        self.numbers += other.numbers
        self.sizes += other.sizes
        self.boolean |= other.boolean
        self.ordered |= other.ordered
        self.clock |= other.clock
        self.differs |= other.differs
        self.opaque += other.opaque


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[Field, Field] = {}

    def find(self, item: Field) -> Field:
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: Field, b: Field) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            low, high = sorted((ra, rb))
            self.parent[high] = low


@dataclass(frozen=True)
class PlaceRoles:
    """The part each place plays for one lifecycle instance."""

    instance_color: str
    open: frozenset[str]
    start: frozenset[str]
    resources: frozenset[str]
    facts: frozenset[str]
    read_only: frozenset[str]
    clocks: frozenset[str]
    final: frozenset[str]
    sinks: frozenset[str]
    instance: frozenset[str]
    records: frozenset[str] = frozenset()
    # Records this system keeps (ADR 0051): never open, never instance work.
    kept: frozenset[str] = frozenset()
    # Each final marking is a set of places that must all hold a token
    # (ADR 0049); ``final`` is their union.
    final_markings: tuple[frozenset[str], ...] = ()

    @property
    def side_outputs(self) -> frozenset[str]:
        """Sinks that are not final: no arc leaves them and no fact asks
        about them."""
        return self.sinks - self.final

    def finished(self, marking: Mapping[str, Any], times: int = 1) -> bool:
        """Whether ``marking`` covers ``times`` final markings at once, one
        per start of the instance (ADR 0052): repeats are allowed, and a
        place needs a token for each chosen final marking that names it."""
        markings = self.final_markings
        left = {place: len(marking.get(place) or ()) for place in self.final}

        def fits(need: int, first: int) -> bool:
            if need == 0:
                return True
            for i in range(first, len(markings)):
                final_marking = markings[i]
                if all(left[place] > 0 for place in final_marking):
                    for place in final_marking:
                        left[place] -= 1
                    found = fits(need - 1, i)
                    for place in final_marking:
                        left[place] += 1
                    if found:
                        return True
            return False

        return fits(times, 0)

    def as_json(self) -> dict[str, Any]:
        return {
            "instanceColor": self.instance_color,
            "start": sorted(self.start),
            "facts": sorted(self.facts),
            "updatable": sorted(self.read_only),
            "records": sorted(self.records),
            "kept": sorted(self.kept),
            "resources": sorted(self.resources),
            "clocks": sorted(self.clocks),
            "final": sorted(self.final),
            "sideOutputs": sorted(self.side_outputs),
        }


Resolver = Callable[[Ref], "tuple[Field, str | None] | None"]


class NetModel:
    """Roles, field references and data domains of one net."""

    def __init__(
        self,
        net: Net,
        *,
        overrides: Mapping[str, Sequence[Any]] | None = None,
        instance_color: str | None = None,
        final: Iterable[str | Sequence[str]] | None = None,
        other_keys: bool = False,
        start: Iterable[str] | None = None,
        closed: Iterable[str] = (),
        block: bool = False,
    ) -> None:
        """``overrides`` (a domains file) win over the net's own ``domains``.

        ``start`` names the start places instead of deriving them. A place in
        ``closed`` is never open because of its ``fusion`` annotation: a
        composition fuses wired ports into such places, and their producers
        are inside the merged net. In a ``block`` (a refining net), a sink
        that is neither final nor a port is an instance place, not a side
        output: no composed net can take a token from it.
        """
        self.net = net
        self.places = {place.name: place for place in net.places}
        self.transitions = {tr.name: tr for tr in net.transitions}
        self.colors = sorted({c for place in net.places for c in place.accepts})
        self.inputs: dict[str, list[Arc]] = {}
        self.outputs: dict[str, list[Arc]] = {}
        for arc in net.arcs:
            if arc.consume is not None and arc.to_transition is not None:
                self.inputs.setdefault(arc.to_transition, []).append(arc)
            elif arc.produce is not None and arc.from_transition is not None:
                self.outputs.setdefault(arc.from_transition, []).append(arc)
        self.clock_colors = {
            color
            for tr in net.transitions
            if tr.timer is not None and tr.timer.clock in self.places
            for color in self.places[tr.timer.clock].accepts
        }
        self.other_keys = other_keys
        # Raw findings, keyed by the field as the CEL wrote it.
        self._raw: dict[Field, _Facts] = {}
        self._joins: list[tuple[Field, Field, str]] = []
        self._known_raw: set[Field] = set()
        # Fields some `correlate` names: the only joins that key a reading.
        self._correlated_raw: set[Field] = set()
        self._tested_raw: dict[str, set[Field]] = {}
        self.embeds: dict[tuple[str, str], str] = {}
        self.unsupported: dict[str, list[str]] = {}
        # Per timed transition, each comparison of the clock with arithmetic
        # in its timer, the fields the comparison reads, and, for a sum
        # (`clock.now >= since + wait`), the clock it compares.
        self._arithmetic_timers: dict[
            str, list[tuple[str, set[Field], Field | None]]
        ] = {}
        # Per color, one entry per producing arc: the fields it sets to a literal.
        self._literal_outputs: dict[str, list[dict[str, Any]]] = {}
        self._read_cel()
        self.kept = kept_module.kept_records(net)
        self._closed = frozenset(closed)
        self.roles = self._roles(instance_color, final, start, block)
        self._read_kept()
        self._kept_marking: dict[str, Token] | None = None
        declared = dict(net.domains or {})
        overrides = dict(overrides or {})
        # A closed field the CEL never reads still has to be on every token
        # the prover builds, or the engine rejects the token.
        for text in [*declared, *overrides]:
            color, _, rest = text.partition(".")
            if rest:
                self._known_raw.add(Field(color, tuple(rest.split("."))))
        self.known: dict[str, set[FieldPath]] = {}
        for item in self._known_raw:
            self.known.setdefault(item.color, set()).add(item.path)
            # A field read through an embedded token is a field of that
            # token's own color too: a fresh delivery needs `destination`
            # when the net reads `attempt.delivery.destination`.
            inner = self.canonical(item.color, item.path)
            self.known.setdefault(inner.color, set()).add(inner.path)
        self.correlated = frozenset(
            self.canonical(item.color, item.path) for item in self._correlated_raw
        )
        self.domains, self.opaque = self._domains(declared, overrides)
        self.unplaced_timers = self._unplaced_timers()

    # ── Reading the CEL ────────────────────────────────────────────────

    def _binding_place(self, transition: Transition, key: str) -> str | None:
        names = transition.binding_names
        return names.get(key) if names is not None else key

    def _binding_color(self, transition: str, place: str) -> str | None:
        for arc in self.inputs.get(transition, ()):
            assert arc.consume is not None
            if arc.from_place == place and arc.consume.mode != "inhibit":
                return arc.consume.type
        return None

    def _read_cel(self) -> None:
        embeds: list[tuple[str, str, str]] = []
        copies: list[tuple[Field, Field]] = []
        deadlines: list[tuple[Field, Field, int | float]] = []
        for tr in self.net.transitions:
            if tr.guard is not None:
                self.unsupported.setdefault(tr.name, []).append(
                    f"the named guard {tr.guard!r} has no handler here"
                )
            for arc in self.inputs.get(tr.name, ()):
                consume = arc.consume
                assert consume is not None and arc.from_place is not None
                predicate = consume.predicate
                if predicate is not None and predicate.handler:
                    self.unsupported.setdefault(tr.name, []).append(
                        f"the named predicate {predicate.handler!r} on the arc "
                        f"from ({arc.from_place}) has no handler here"
                    )
                if predicate is not None and predicate.cel:
                    self._scan(
                        celscan.parse(predicate.cel),
                        predicate.cel,
                        lambda ref, arc=arc: self._predicate_ref(arc, ref),
                    )
                if consume.correlate:
                    self._scan(
                        celscan.parse(consume.correlate),
                        consume.correlate,
                        lambda ref, arc=arc, tr=tr: self._correlated(
                            self._correlate_ref(tr, arc, ref)
                        ),
                    )
            if tr.timer is not None:
                self._scan(
                    celscan.parse(tr.timer.cel),
                    tr.timer.cel,
                    lambda ref, tr=tr: self._timer_ref(tr, ref),
                    timer=tr.name,
                )
            for arc in self.outputs.get(tr.name, ()):
                produce = arc.produce
                assert produce is not None
                set_literals: dict[str, Any] = {}
                self._literal_outputs.setdefault(produce.type, []).append(set_literals)
                if isinstance(produce.data, dict):
                    literal = cast(dict[str, Any], produce.data)
                    for key, value in literal.items():
                        target = Field(produce.type, (key,))
                        self._known_raw.add(target)
                        if isinstance(value, (str, bool, int, float)) or value is None:
                            self._fact(target).literals.append(value)
                            set_literals[key] = value
                    continue
                if produce.cel is None:
                    continue
                tree = celscan.parse(produce.cel)
                for ref in celscan.refs(tree):
                    self._binding_ref(tr, ref)
                if isinstance(tree, MapLit):
                    for key_node, value in tree.entries:
                        if not isinstance(key_node, Lit) or not isinstance(
                            key_node.value, str
                        ):
                            continue
                        target = Field(produce.type, (key_node.value,))
                        self._known_raw.add(target)
                        if isinstance(value, Lit):
                            self._fact(target).literals.append(value.value)
                            set_literals[key_node.value] = value.value
                        elif isinstance(value, Ref):
                            whole = self._whole_token(tr, value)
                            source = self._binding_ref(tr, value)
                            if whole is not None:
                                embeds.append((produce.type, key_node.value, whole))
                            elif source is not None:
                                copies.append((target, source[0]))
                        elif isinstance(value, Opaque):
                            dated = self._dated_from_clock(tr, value)
                            if dated is not None:
                                deadlines.append((target, dated[0], dated[1]))
                elif isinstance(tree, Ref):
                    source = self._binding_ref(tr, tree)
                    if source is not None and len(source[0].path) == 1:
                        embeds.append(
                            (source[0].color, source[0].path[0], produce.type)
                        )
        for color, key, inner in embeds:
            self.embeds[(color, key)] = inner
        # A field named after a color holds a token of that color when its
        # subfields are read: `attempt.delivery.destination`.
        colors = set(self.colors)
        for item in self._known_raw:
            if len(item.path) >= 2 and item.path[0] in colors:
                self.embeds.setdefault((item.color, item.path[0]), item.path[0])
        for target, source in copies:
            self._joins.append((target, source, "=="))
        self.maturity_copies = self._maturity_copies(copies, deadlines)

    def _dated_from_clock(
        self, tr: Transition, node: Opaque
    ) -> tuple[Field, int | float] | None:
        """``(clock field, offset)`` when ``node`` is that field plus
        number literals, as ``double(binding.clock[0].now) + 120.0`` is.

        ``double`` is already unwrapped by the scanner, so the sum is the
        clock reference and the literals. A difference (``now - 120``) is
        the same shape with a negative literal."""
        if not node.terms:
            return None
        ref: Ref | None = None
        offset = 0
        for sign, term in node.terms:
            if isinstance(term, Ref):
                if ref is not None or sign != 1:
                    return None
                ref = term
                continue
            if not isinstance(term.value, (int, float)) or isinstance(
                term.value, bool
            ):
                return None
            offset += sign * term.value
        if ref is None:
            return None
        source = self._binding_ref(tr, ref)
        if source is None or source[0].color not in self.clock_colors:
            return None
        return source[0], offset

    def _maturity_copies(
        self,
        copies: list[tuple[Field, Field]],
        deadlines: list[tuple[Field, Field, int | float]],
    ) -> dict[str, tuple[ClockCopy, ...]]:
        """Per timed transition, the fields its ``timer maturity`` reads that
        were taken from a clock, each with the place its timer binds it from
        and the offset that turns the field back into the latched time.

        A straight copy (``'since': binding.clock[0].now``) has offset 0 and
        holds the clock's own values. A deadline dated from the clock
        (``double(binding.clock[0].now) + 120.0``) holds that time plus the
        offset. Either way the latch has to be a listed clock time, or the
        next deadline would be dated from a maturity."""
        offsets: dict[Field, int | float] = {}
        ambiguous: set[Field] = set()

        def put(target: Field, source: Field, offset: int | float) -> None:
            if source.color not in self.clock_colors:
                return
            key = self.canonical(target.color, target.path)
            if key in ambiguous:
                return
            previous = offsets.get(key)
            if previous is not None and previous != offset:
                ambiguous.add(key)
                del offsets[key]
                return
            offsets[key] = offset

        for target, source in copies:
            put(target, source, 0)
        for target, source, offset in deadlines:
            put(target, source, offset)
        found: dict[str, tuple[ClockCopy, ...]] = {}
        for tr in self.net.transitions:
            if tr.timer is None or tr.timer.maturity is None:
                continue
            reads: list[ClockCopy] = []
            for ref in celscan.refs(celscan.parse(tr.timer.maturity)):
                use = self._timer_ref(tr, ref)
                if use is None or use[1] is None:
                    continue
                item, place = use
                if place is None:
                    continue
                offset = offsets.get(self.canonical(item.color, item.path))
                if offset is None:
                    continue
                reads.append(ClockCopy(place, item, offset))
            if reads:
                found[tr.name] = tuple(reads)
        return found

    def _read_kept(self) -> None:
        """A kept record's start sets its fields as a produce ``data cel``
        does; a field it copies from the instance joins the instance's."""
        for record in self.kept.values():
            tree = celscan.parse(record.start)
            if not isinstance(tree, MapLit):
                continue
            set_literals: dict[str, Any] = {}
            self._literal_outputs.setdefault(record.color, []).append(set_literals)
            for key_node, value in tree.entries:
                if not isinstance(key_node, Lit) or not isinstance(key_node.value, str):
                    continue
                target = Field(record.color, (key_node.value,))
                self._known_raw.add(target)
                if isinstance(value, Lit):
                    self._fact(target).literals.append(value.value)
                    set_literals[key_node.value] = value.value
                elif isinstance(value, Ref) and value.root == kept_module.INSTANCE:
                    path = _names(value.path)
                    if path is not None:
                        source = Field(self.roles.instance_color, path)
                        self._known_raw.add(source)
                        self._joins.append((target, source, "=="))

    def _predicate_ref(self, arc: Arc, ref: Ref) -> tuple[Field, str | None] | None:
        consume = arc.consume
        assert consume is not None
        path = _names((ref.root, *ref.path))
        return (Field(consume.type, path), arc.from_place) if path else None

    def _correlate_ref(
        self, tr: Transition, arc: Arc, ref: Ref
    ) -> tuple[Field, str | None] | None:
        consume = arc.consume
        assert consume is not None
        if ref.root == "token":
            path = _names(ref.path)
            return (Field(consume.type, path), arc.from_place) if path else None
        if ref.root == "binding":
            return self._binding_ref(tr, ref)
        return None

    def _correlated(
        self, use: tuple[Field, str | None] | None
    ) -> tuple[Field, str | None] | None:
        """Note a field a correlate names, and pass its use through."""
        if use is not None:
            self._correlated_raw.add(use[0])
        return use

    def _timer_ref(self, tr: Transition, ref: Ref) -> tuple[Field, str | None] | None:
        timer = tr.timer
        assert timer is not None
        path = _names(ref.path)
        if path is None:
            return None
        if ref.root == "clock":
            accepts = (
                self.places[timer.clock].accepts if timer.clock in self.places else []
            )
            return (Field(accepts[0], path), timer.clock) if len(accepts) == 1 else None
        place = (timer.bind or {}).get(ref.root)
        color = self._binding_color(tr.name, place) if place is not None else None
        return (Field(color, path), place) if color is not None else None

    def _whole_token(self, tr: Transition, ref: Ref) -> str | None:
        """The color of ``binding.p[0]`` when a CEL names a whole bound token."""
        if ref.root != "binding" or len(ref.path) != 2:
            return None
        key, index = ref.path
        if not isinstance(key, str) or not isinstance(index, int):
            return None
        place = self._binding_place(tr, key)
        return self._binding_color(tr.name, place) if place is not None else None

    def _binding_ref(self, tr: Transition, ref: Ref) -> tuple[Field, str | None] | None:
        if ref.root != "binding" or len(ref.path) < 3:
            return None
        key, index, *rest = ref.path
        if not isinstance(key, str) or not isinstance(index, int):
            return None
        place = self._binding_place(tr, key)
        color = self._binding_color(tr.name, place) if place is not None else None
        path = _names(tuple(rest))
        if color is None or path is None or place is None:
            return None
        item = Field(color, path)
        self._known_raw.add(item)
        self._tested_raw.setdefault(place, set()).add(item)
        return item, place

    def _scan(
        self, tree: Node, text: str, resolve: Resolver, *, timer: str | None = None
    ) -> None:
        """Read what ``text`` tests; ``timer`` names the transition whose
        timer it is."""

        def use_of(node: Node) -> Field | None:
            if not isinstance(node, Ref):
                return None
            use = resolve(node)
            if use is None:
                return None
            item, place = use
            self._known_raw.add(item)
            if place is not None:
                self._tested_raw.setdefault(place, set()).add(item)
            return item

        for ref in celscan.refs(tree):
            use_of(ref)
        for ref in celscan.boolean_refs(tree):
            item = use_of(ref)
            if item is not None:
                self._fact(item).boolean = True
        negated = {id(node) for node in celscan.negated(tree)}
        read: set[int] = set()
        for node in celscan.walk(tree):
            if id(node) in read:
                continue
            if isinstance(node, Cmp):
                if self._compare(
                    node, use_of, text, timer, negated=id(node) in negated
                ):
                    read.update((id(node.left), id(node.right)))
            elif isinstance(node, Call) and node.name != "size":
                for arg in node.args:
                    item = use_of(arg)
                    if item is not None:
                        self._fact(item).opaque.append(text)
            elif isinstance(node, Opaque):
                for ref in node.refs:
                    item = use_of(ref)
                    if item is not None:
                        self._fact(item).opaque.append(text)

    def _compare(
        self,
        node: Cmp,
        use_of: Callable[[Node], Field | None],
        text: str,
        timer: str | None,
        *,
        negated: bool = False,
    ) -> bool:
        """Read one comparison. True when it read its sides whole: a timer's
        clock compared with a sum, whose terms are not opaque."""
        op, left, right = node.op, node.left, node.right
        if op == "in":
            item = use_of(left)
            if item is not None and isinstance(right, Seq) and right.kind == "list":
                if negated:
                    self._fact(item).differs = True
                for value in right.items:
                    if isinstance(value, Lit):
                        self._fact(item).literals.append(value.value)
                    else:
                        self._fact(item).opaque.append(text)
            elif item is not None:
                self._fact(item).opaque.append(text)
            return False
        if isinstance(left, Lit) and not isinstance(right, Lit):
            left, right, op = right, left, _FLIP[op]
        if isinstance(left, Call) and left.name == "size" and len(left.args) == 1:
            item = use_of(left.args[0])
            if item is not None and isinstance(right, Lit) and _is_number(right.value):
                self._fact(item).sizes.append(int(right.value))
            elif item is not None:
                self._fact(item).opaque.append(text)
            return False
        if timer and self._clock_sum(node, use_of, text, timer):
            return True
        left_item, right_item = use_of(left), use_of(right)
        if left_item is not None and isinstance(right, Lit):
            facts = self._fact(left_item)
            if _is_number(right.value):
                facts.numbers.append(right.value)
            else:
                facts.literals.append(right.value)
                # A value no literal names passes this test.
                if negated != (op == "!="):
                    facts.differs = True
            if timer and left_item.color in self.clock_colors:
                facts.clock = True
            return False
        if left_item is not None and right_item is not None:
            if negated and op in ("==", "!="):
                op = "==" if op == "!=" else "!="
            self._joins.append((left_item, right_item, op))
            if timer:
                for item in (left_item, right_item):
                    if item.color in self.clock_colors:
                        self._fact(item).clock = True
            return False
        clocked = False
        fields = {item for ref in celscan.refs(node) if (item := use_of(ref))}
        for item in (left_item, right_item):
            if item is not None:
                self._fact(item).opaque.append(text)
        # A clock compared in a timer holds time, whatever it is compared
        # with: arithmetic on a field is read only as far as the domains go,
        # but the clock still gets time slots.
        for item in fields:
            if timer and item.color in self.clock_colors:
                self._fact(item).clock = True
                clocked = True
        if timer and clocked:
            self._arithmetic_timers.setdefault(timer, []).append((text, fields, None))
        return False

    def _clock_sum(
        self,
        node: Cmp,
        use_of: Callable[[Node], Field | None],
        text: str,
        timer: str,
    ) -> bool:
        """Read a timer comparison of the clock with a sum, such as
        ``clock.now >= idle.since + idle.wait`` or ``clock.now - idle.since >=
        idle.wait``: the clock once, and references and numbers elsewhere.
        The clock gets time slots; whether the terms place the deadline is
        settled with the domains (:meth:`_unplaced_timers`)."""
        if node.op not in ("<", "<=", ">", ">="):
            return False
        sides = (node.left, node.right)
        if not any(isinstance(side, Opaque) and side.terms for side in sides):
            return False
        terms: list[Node] = []
        for side in sides:
            if isinstance(side, Opaque) and side.terms:
                terms.extend(term for _, term in side.terms)
            elif isinstance(side, (Ref, Lit)):
                terms.append(side)
            else:
                return False
        fields: set[Field] = set()
        clocks: list[Field] = []
        for term in terms:
            if isinstance(term, Lit):
                if not _is_number(term.value):
                    return False
                continue
            item = use_of(term)
            if item is None:
                return False
            fields.add(item)
            if item.color in self.clock_colors:
                clocks.append(item)
        if len(clocks) != 1:
            return False
        self._fact(clocks[0]).clock = True
        self._arithmetic_timers.setdefault(timer, []).append((text, fields, clocks[0]))
        return True

    def _fact(self, item: Field) -> _Facts:
        return self._raw.setdefault(item, _Facts())

    # ── Normal form of a field: embedded tokens ────────────────────────

    def canonical(self, color: str, path: FieldPath) -> Field:
        """The field a path names, looking through embedded tokens:
        ``attempt.delivery.destination`` is ``delivery.destination``."""
        while len(path) > 1 and (color, path[0]) in self.embeds:
            color, path = self.embeds[(color, path[0])], path[1:]
        return Field(color, path)

    def embedded(self, color: str, path: FieldPath) -> str | None:
        """The color of the token a path holds, when it holds a whole token."""
        item = self.canonical(color, path)
        if len(item.path) == 1:
            return self.embeds.get((item.color, item.path[0]))
        return None

    # ── Domains ────────────────────────────────────────────────────────

    def _domains(
        self,
        declared: Mapping[str, Sequence[Any]],
        overrides: Mapping[str, Sequence[Any]],
    ) -> tuple[dict[Field, Domain], dict[Field, list[str]]]:
        classes = _UnionFind()
        facts: dict[Field, _Facts] = {}
        for raw, raw_facts in self._raw.items():
            item = self.canonical(raw.color, raw.path)
            classes.find(item)
            facts.setdefault(item, _Facts()).merge(raw_facts)
        for a, b, op in self._joins:
            ca, cb = self.canonical(a.color, a.path), self.canonical(b.color, b.path)
            facts.setdefault(ca, _Facts())
            facts.setdefault(cb, _Facts())
            classes.union(ca, cb)
            if op in ("<", "<=", ">", ">="):
                facts[ca].ordered = True
            if op == "!=":
                facts[ca].differs = True
        members: dict[Field, list[Field]] = {}
        for item in sorted(facts):
            members.setdefault(classes.find(item), []).append(item)
        domains: dict[Field, Domain] = {}
        opaque: dict[Field, list[str]] = {}
        for root, group in members.items():
            merged = _Facts()
            for item in group:
                merged.merge(facts[item])
            if merged.opaque:
                for item in group:
                    opaque[item] = sorted(set(merged.opaque))
            clock_fields = [c for c in group if c.color in self.clock_colors]
            data_fields = [c for c in group if c.color not in self.clock_colors]
            name = root.path[-1]
            for item in group:
                if merged.clock:
                    domains[item] = _time_domain(
                        merged, len(data_fields), clock=item in clock_fields
                    )
                elif len(group) > 1 and merged.ordered and not merged.literals:
                    domains[item] = Domain("ordered", (1, 2, 3), (1, 2, 3), own=2)
                elif len(group) > 1 and not merged.literals and not merged.numbers:
                    own, other = f"own-{name}", f"other-{name}"
                    named = (
                        (own, other) if merged.differs or self.other_keys else (own,)
                    )
                    domains[item] = Domain("key", (own, other), named, own=own)
                else:
                    domains[item] = _value_domain(merged, name)
            # A field the net only ever sets from literals holds no other value.
            produced = [self._literal_values(item) for item in group]
            if all(domains[item].kind == "literal" for item in group) and all(
                values is not None for values in produced
            ):
                values = tuple(
                    _unique_values(v for values in produced for v in values or ())
                )
                for item in group:
                    domains[item] = Domain("literal", values, values)
        for color, paths in sorted(self._paths_by_color().items()):
            for path in sorted(paths):
                item = self.canonical(color, path)
                if item in domains or self.embedded(color, path) is not None:
                    continue
                value = f"own-{item.path[-1]}"
                domains[item] = Domain("free", (value,), (value,), own=value)
        # The net's own domain facts replace the derived domains, and a
        # domains file replaces both: derive, then override.
        for source, given in (("declared", declared), ("override", overrides)):
            for text, values in given.items():
                color, _, rest = text.partition(".")
                if not rest:
                    raise ValueError(
                        f"a domain override names color.field, got {text!r}"
                    )
                listed = tuple(values)
                if not listed:
                    raise ValueError(
                        f"the domain override for {text!r} lists no values"
                    )
                item = self.canonical(color, tuple(rest.split(".")))
                old = domains.get(item)
                own = old.own if old is not None and old.own in listed else None
                domains[item] = Domain(source, listed, listed, own=own, source=source)
                opaque.pop(item, None)
        return dict(sorted(domains.items())), opaque

    def _literal_values(self, item: Field) -> list[Any] | None:
        """The values ``item`` can hold when every arc that makes its color
        sets it to a literal and the environment writes no place of that
        color; else ``None``. The initial marking's values count too."""
        outputs = self._literal_outputs.get(item.color, [])
        if len(item.path) != 1 or not outputs:
            return None
        key = item.path[0]
        if any(key not in output for output in outputs):
            return None
        if any(item.color in self.places[name].accepts for name in self.roles.open):
            return None
        values = [output[key] for output in outputs]
        for tokens in (self.net.initial_marking or Marking()).values():
            for token in tokens:
                if token.type == item.color and key in token.data:
                    values.append(token.data[key])
        return _unique_values(values)

    def _paths_by_color(self) -> dict[str, set[FieldPath]]:
        result: dict[str, set[FieldPath]] = {}
        for item in self._known_raw:
            result.setdefault(item.color, set()).add(item.path)
        return result

    def domain(self, color: str, path: FieldPath) -> Domain | None:
        return self.domains.get(self.canonical(color, path))

    def _unplaced_timers(self) -> dict[str, list[str]]:
        """Timers that compare the clock with arithmetic on fields some of
        which hold derived values: time slots or placeholders say nothing
        about when a sum is due, so the exploration cannot tell when such a
        timer fires. A domains file that gives those fields values, or a
        field only literals set, places it. In a sum whose clock holds real
        times (given, or bounded by the net's own numbers), a field that
        holds time (one the net compares with or copies from the clock) is
        placed as a deadline field is. A sum's loose fields are opaque to
        choice coverage too."""
        found: dict[str, list[str]] = {}
        for name, uses in sorted(self._arithmetic_timers.items()):
            for text, fields, clock in uses:
                timed = clock is not None and self._real_times(clock)
                loose: list[Field] = []
                for item in sorted(fields):
                    domain = self.domain(item.color, item.path)
                    if domain is None or (
                        domain.source == "derived"
                        and domain.kind != "literal"
                        and not (timed and domain.kind in ("time", "clock"))
                    ):
                        loose.append(item)
                if not loose:
                    continue
                found.setdefault(name, []).append(
                    "its timer compares the clock with arithmetic "
                    f"({text}), and the derived values of "
                    f"{', '.join(item.text() for item in loose)} cannot say "
                    "when that is due; give them values in a domains file"
                )
                if clock is not None:
                    for item in loose:
                        canonical = self.canonical(item.color, item.path)
                        texts = self.opaque.setdefault(canonical, [])
                        if text not in texts:
                            texts.append(text)
        return found

    def _real_times(self, clock: Field) -> bool:
        """Whether the clock's values are times rather than ordered slots: a
        domains file gives them, or the net's own numbers bound them."""
        domain = self.domain(clock.color, clock.path)
        return domain is not None and (
            domain.source != "derived" or bool(domain.bounds)
        )

    # ── Roles ──────────────────────────────────────────────────────────

    def _roles(
        self,
        instance_color: str | None,
        final: Iterable[str | Sequence[str]] | None,
        start_places: Iterable[str] | None,
        block: bool = False,
    ) -> PlaceRoles:
        produced: set[str] = set()
        consumed: set[str] = set()
        read: set[str] = set()
        for arc in self.net.arcs:
            if arc.produce is not None:
                produced.add(arc.produce.destination)
            elif arc.consume is not None and arc.from_place is not None:
                (consumed if arc.consume.mode == "consume" else read).add(
                    arc.from_place
                )
        clocks = {tr.timer.clock for tr in self.net.transitions if tr.timer is not None}
        used = consumed | read
        kept = set(self.kept)
        records = self._records() - kept
        open_places: set[str] = set(clocks) | records
        for place in self.net.places:
            if place.name in kept:
                continue
            fusion = bool(place.annotations and place.annotations.get("fusion"))
            fusion = fusion and place.name not in self._closed
            if place.name in used and (place.name not in produced or fusion):
                open_places.add(place.name)
        if instance_color is None:
            counts: dict[str, int] = {}
            for place in self.net.places:
                if place.name not in open_places and place.name not in kept:
                    for color in place.accepts:
                        counts[color] = counts.get(color, 0) + 1
            order = {color: i for i, color in enumerate(self._declared_colors())}
            instance_color = (
                min(counts, key=lambda c: (-counts[c], order.get(c, 0)))
                if counts
                else (self.colors[0] if self.colors else "token")
            )
        # An input port where the instance arrives is open even when the net
        # also feeds it (a polling loop back into its own input). Another
        # input port the net feeds stays closed: inside this net its own
        # producer fills it, as a composed partner would.
        for place in self.net.places:
            if (
                place.port is not None
                and place.port.direction == "input"
                and instance_color in place.accepts
                and place.name not in kept
            ):
                open_places.add(place.name)
        if start_places is not None:
            start = set(start_places)
            unknown = sorted(start - set(self.places))
            if unknown:
                raise ValueError(f"unknown start place {unknown[0]!r}")
            open_places |= start
        else:
            start = self._derived_start(
                open_places - clocks - records, produced, instance_color
            )
        resources = {
            name for name in open_places - clocks - start - records if name in consumed
        }
        facts = open_places - clocks - start - resources
        read_only = {name for name in facts if name not in produced} | records
        sinks = {
            place.name
            for place in self.net.places
            if place.name not in used
            and place.name not in records
            and place.name not in kept
        }
        if final is not None:
            final_markings = tuple(
                frozenset([entry] if isinstance(entry, str) else entry)
                for entry in final
            )
            final_places: set[str] = set[str]().union(*final_markings)
            unknown = sorted(final_places - set(self.places))
            if unknown:
                raise ValueError(f"unknown final place {unknown[0]!r}")
            if final_places & kept:
                raise ValueError(
                    f"({sorted(final_places & kept)[0]}) is a kept record, "
                    "never a final place: what it holds is not the instance's"
                )
        else:
            final_places = set[str]()
            for name in sinks:
                place = self.places[name]
                output_port = (
                    place.port is not None and place.port.direction == "output"
                )
                if instance_color in place.accepts or output_port:
                    final_places.add(name)
            final_markings = tuple(frozenset([name]) for name in sorted(final_places))
        if block:
            sinks = {
                name
                for name in sinks
                if name in final_places or self.places[name].port is not None
            }
        instance = {
            place.name
            for place in self.net.places
            if place.name not in open_places
            and place.name not in sinks
            and place.name not in final_places
            and place.name not in kept
        }
        return PlaceRoles(
            instance_color=instance_color,
            open=frozenset(open_places),
            start=frozenset(start),
            resources=frozenset(resources),
            facts=frozenset(facts),
            read_only=frozenset(read_only),
            clocks=frozenset(clocks),
            final=frozenset(final_places),
            sinks=frozenset(sinks),
            instance=frozenset(instance),
            records=frozenset(records),
            kept=frozenset(kept),
            final_markings=final_markings,
        )

    def _records(self) -> set[str]:
        """Places that live in a ``record`` lifeline (ADR 0039): records the
        outside world keeps, open whatever produces into, wires or shares them."""
        actors = (self.net.annotations or {}).get("actors")
        kinds: dict[Any, Any] = {}
        for entry in cast(list[Any], actors if isinstance(actors, list) else []):
            if isinstance(entry, dict):
                fields = cast(dict[str, Any], entry)
                kinds[fields.get("name")] = fields.get("kind")
        records: set[str] = set()
        for place in self.net.places:
            lives = (place.annotations or {}).get("lives")
            if isinstance(lives, str) and kinds.get(lives) == "record":
                records.add(place.name)
        return records

    def _derived_start(
        self, candidates: set[str], produced: set[str], instance_color: str
    ) -> set[str]:
        start: set[str] = set()
        for name in sorted(candidates):
            if instance_color in self.places[name].accepts:
                start.add(name)
                continue
            if name in produced:
                continue
            for tr, arcs in self.inputs.items():
                takes = any(
                    a.from_place == name
                    and a.consume is not None
                    and a.consume.mode == "consume"
                    for a in arcs
                )
                takes_instance = any(
                    a.consume is not None
                    and a.consume.mode == "consume"
                    and a.consume.type == instance_color
                    for a in arcs
                )
                makes = any(
                    a.produce is not None and a.produce.type == instance_color
                    for a in self.outputs.get(tr, ())
                )
                if takes and makes and not takes_instance:
                    start.add(name)
        return start

    def _declared_colors(self) -> list[str]:
        seen: list[str] = []
        for place in self.net.places:
            for color in place.accepts:
                if color not in seen:
                    seen.append(color)
        return seen

    # ── Kept records ───────────────────────────────────────────────────

    def instance_data(self) -> dict[str, Any]:
        """The check's instance token: its own value for every key, ordered
        slot and free field, and the first value of a declared field."""
        variants = self.token_variants(
            self.roles.instance_color, vary=(), own=INSTANCE, full=False
        )
        return variants[0] if variants else {}

    def kept_marking(self) -> dict[str, Token]:
        """Each kept record's start, built against the check's instance.

        Raises ``ValueError`` when a start cannot be built, or breaks a
        declared domain.
        """
        if self._kept_marking is None:
            instance = self.instance_data()
            built: dict[str, Token] = {}
            for name, record in sorted(self.kept.items()):
                token = Token(record.color, kept_module.build_start(record, instance))
                violation = domain_violation(self.net, name, token)
                if violation is not None:
                    raise ValueError(
                        f"the start of ({name}) breaks a domain: {violation}"
                    )
                built[name] = token
            self._kept_marking = built
        return self._kept_marking

    def initial_marking(self) -> Marking:
        """The net's initial marking with every kept record at its start."""
        marking = self.net.initial_marking or Marking()
        for name, token in self.kept_marking().items():
            marking = marking.set(name, [token])
        return marking

    # ── Building tokens ────────────────────────────────────────────────

    def tested(self, place: str, color: str) -> set[FieldPath]:
        """The paths of ``color`` that some CEL reads from ``place``'s tokens."""
        return {
            item.path
            for item in self._tested_raw.get(place, set())
            if item.color == color
        }

    def token_variants(
        self,
        color: str,
        *,
        vary: Iterable[FieldPath] | None,
        own: frozenset[str],
        full: bool,
        base: Mapping[str, Any] | None = None,
        bound: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        """Every token data of ``color`` that the domains allow.

        ``vary`` names the paths that take every value of their domain;
        ``None`` varies every known path (an environment token). A field
        whose domain kind is in ``own`` takes its own value instead
        (:data:`INSTANCE` for the instance's tokens). ``base`` is the data an
        output starts from (the carry rule): its values stay unless a varied
        path changes them. A path holding a whole token of another color
        copies the one bound token of that color (``bound``, keyed by color),
        or else is built the same way.
        """
        paths = sorted(self.known.get(color, set()))
        varied = set(paths) if vary is None else set(vary)
        choices: list[tuple[FieldPath, tuple[Any, ...]]] = []
        embedded: dict[str, str] = {}
        for path in paths:
            inner = self.embeds.get((color, path[0]))
            if inner is not None:
                embedded[path[0]] = inner
                continue
            in_base = base is not None and _has_path(base, path)
            domain = self.domain(color, path)
            if domain is None:
                continue
            if path not in varied:
                fixed = domain.own
                # The engine rejects a token without a declared field.
                if fixed is None and domain.source != "derived":
                    fixed = domain.values[0]
                if in_base or fixed is None:
                    continue
                choices.append((path, (fixed,)))
                continue
            if domain.own is not None and domain.kind in own:
                values: tuple[Any, ...] = (domain.own,)
            else:
                values = domain.values if full else domain.named
            choices.append((path, values))
        nested: dict[str, list[dict[str, Any]]] = {}
        for top, inner in sorted(embedded.items()):
            if base is not None and isinstance(base.get(top), dict):
                nested[top] = [_deep_copy(base[top])]
                continue
            tokens = list((bound or {}).get(inner, ()))
            if len(tokens) == 1:
                nested[top] = [_deep_copy(tokens[0])]
                continue
            sub_vary = {path[1:] for path in varied if path[0] == top and len(path) > 1}
            nested[top] = self.token_variants(
                inner, vary=sub_vary, own=own, full=full, bound=bound
            )
        nested_keys = sorted(nested)
        result: list[dict[str, Any]] = []
        for values in product(*(values for _, values in choices)):
            for parts in product(*(nested[key] for key in nested_keys)):
                data: dict[str, Any] = _deep_copy(dict(base)) if base else {}
                for (path, _), value in zip(choices, values, strict=True):
                    set_path(data, path, value)
                for key, part in zip(nested_keys, parts, strict=True):
                    data[key] = _deep_copy(part)
                result.append(data)
        return _unique(result)


_FLIP = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}


def _names(path: Sequence[str | int]) -> FieldPath | None:
    names = tuple(part for part in path if isinstance(part, str))
    return names or None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _boundaries(numbers: Iterable[float | int]) -> tuple[float | int, ...]:
    """A value below, at and above each literal, so that every comparison
    with a literal sees each of its outcomes."""
    literals = sorted(set(numbers))
    if not literals:
        return ()
    integral = all(isinstance(n, int) for n in literals)
    values: set[float | int] = set()
    for i, n in enumerate(literals):
        values.add(n)
        if integral:
            values.update((n - 1, n + 1))
            continue
        lower = literals[i - 1] if i > 0 else None
        upper = literals[i + 1] if i + 1 < len(literals) else None
        values.add(
            (n + lower) / 2 if lower is not None else (n / 2 if n > 0 else n - 1)
        )
        values.add(
            (n + upper) / 2 if upper is not None else (n * 2 if n > 0 else n + 1)
        )
    return tuple(sorted(values))


def _value_domain(facts: _Facts, name: str) -> Domain:
    literals = _unique_values(facts.literals)
    if facts.sizes:
        sizes = [int(n) for n in _boundaries(facts.sizes) if n >= 0]
        lists = tuple([LIST_ITEM] * n for n in sizes)
        bounds = tuple(sorted(set(facts.sizes)))
        return Domain("list", lists, lists, bounds=bounds)
    if (
        facts.boolean
        and all(isinstance(v, bool) for v in literals)
        and not facts.numbers
    ):
        return Domain("bool", (True, False), (True, False))
    if not literals and facts.numbers:
        values = _boundaries(facts.numbers)
        bounds = tuple(sorted(set(facts.numbers)))
        return Domain("number", values, values, bounds=bounds)
    if literals or facts.numbers:
        values = tuple(literals) + _boundaries(facts.numbers)
        if all(isinstance(v, bool) for v in values):
            return Domain("bool", (True, False), (True, False))
        named = values + (OTHER,) if facts.differs else values
        return Domain("literal", values + (OTHER,), named)
    value = f"own-{name}"
    return Domain("free", (value,), (value,), own=value)


def _time_domain(facts: _Facts, data_fields: int, *, clock: bool) -> Domain:
    if facts.numbers:
        values = _boundaries(facts.numbers)
        low = values[0]
        if clock:
            values = (low - 1 if isinstance(low, int) else low / 2, *values)
        bounds = tuple(sorted(set(facts.numbers)))
        return Domain("clock" if clock else "time", values, values, bounds=bounds)
    slots = tuple(range(1, max(data_fields, 1) + 1))
    if clock:
        return Domain("clock", (0, *slots), (0, *slots))
    return Domain("time", slots, slots)


def _unique_values(values: Iterable[Any]) -> list[Any]:
    seen: list[Any] = []
    for value in values:
        if not any(type(value) is type(old) and value == old for old in seen):
            seen.append(value)
    return seen


def _unique(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _has_path(data: Mapping[str, Any], path: FieldPath) -> bool:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping):
            return False
        level = cast(Mapping[str, Any], current)
        if key not in level:
            return False
        current = level[key]
    return True


def set_path(data: dict[str, Any], path: FieldPath, value: Any) -> None:
    current = data
    for key in path[:-1]:
        nxt: Any = current.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            current[key] = nxt
        current = cast(dict[str, Any], nxt)
    current[path[-1]] = _deep_copy(value)


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in cast(dict[str, Any], value).items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in cast(list[Any], value)]
    return value
