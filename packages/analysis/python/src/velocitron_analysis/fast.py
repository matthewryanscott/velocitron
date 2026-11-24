"""The fast path: the kernel explores a net and checks it from the tables
the reference fills, and the reference names what comes back.

:func:`explore_fast` fills the tables (``tables.fill``) and hands them to
the compiled kernel in the same process (D15). The kernel keeps the graph:
the soundness checks, what made the markings and a counterexample's steps
are read from it as numbers (P15), and :class:`KernelExplorer` names them in
the reference's words. :class:`KernelCases` asks the kernel which
transitions each case of a choice enables, over the tables of the cases'
tokens. An ordinary run explores on every core; the check against the
reference explores on one core, visiting markings in the reference's order
(D12), so a run stopped at the state cap holds the same markings and edges:
:func:`run_kernel` rebuilds the reference's states from the kernel's graph,
and :func:`first_difference` compares the two edge for edge. Both modes
give the same graph (I7).

A failure inside the kernel, while it explores or checks, fails the run
with the kernel's error and names ``--reference`` (D16, D17); nothing
switches path on its own.

References: the spec's P3, P14, P15, D12, D15, D16, D17.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from itertools import product
from typing import TYPE_CHECKING, Any

from velocitron_engine import Marking, Net

from .analysis import NetModel
from .choice import Dim, EngineCases, witness_marking
from .firing import Firing
from .progress import Progress
from .soundness import (
    ARRIVAL,
    NET,
    RECORD,
    UPDATE,
    Environment,
    Explorer,
    Verdict,
    _State,  # pyright: ignore[reportPrivateUsage]
)
from .tables import TOKEN_LIMIT, Rows, TooManyTokens, fill

if TYPE_CHECKING:
    from velocitron_kernel import Graph

REFERENCE_FLAG = "--reference"
_KINDS = (NET, ARRIVAL, UPDATE, RECORD)
_EMPTY = 0xFFFF
"""The kernel's token id for an empty context place."""


class FastPathError(Exception):
    """The kernel failed; the run fails with its error (D16)."""

    def __init__(self, error: str) -> None:
        super().__init__(
            f"the fast path failed: {error}. Run the same proof on the "
            f"reference explorer with {REFERENCE_FLAG}."
        )
        self.error = error


def _kernel() -> Any:
    try:
        import velocitron_kernel
    except ImportError as error:
        raise FastPathError(f"the kernel is not installed ({error})") from error
    return velocitron_kernel


def _explore(tables: Rows, progress: Progress | None, *, one_core: bool) -> Graph:
    """The kernel's graph of ``tables``' net, its rows filled on first use,
    explored on every core, or on one in the reference's order."""
    kernel = _kernel()
    try:
        return kernel.explore(
            tables.kernel,
            tables,
            tables.explorer.max_states,
            progress,
            one_core=one_core,
        )
    except kernel.KernelError as error:
        raise FastPathError(str(error)) from error


def explore_fast(
    net: Net,
    model: NetModel,
    *,
    environment: Environment,
    max_states: int,
    postpone: bool = True,
    wait_arrivals: bool = False,
    group_tokens: bool = True,
    saturate: bool = True,
    progress: Progress | None = None,
    one_core: bool = False,
) -> KernelExplorer:
    """Explore ``net`` on the fast path: an explorer that answers as
    :func:`soundness.explore`'s does, its graph held by the kernel.
    ``progress`` takes the kernel's progress lines (P12). The kernel uses
    every core, or one with ``one_core``; the graph is the same (I7)."""
    explorer = KernelExplorer(
        net,
        model,
        Firing(net, model),
        environment=environment,
        max_states=max_states,
        postpone=postpone,
        wait_arrivals=wait_arrivals,
        group_tokens=group_tokens,
        saturate=saturate,
        progress=progress,
    )
    explorer.one_core = one_core
    explorer.explore()
    return explorer


class KernelExplorer(Explorer):
    """An explorer whose graph the kernel holds. It keeps no state of its
    own: the soundness checks, what made the markings and the steps of a
    counterexample come from the kernel as numbers (P15), and only the
    markings a finding shows are named."""

    _graph: Graph | None = None
    _tables: Rows | None = None
    one_core: bool = False
    """Explore on one core, in the reference's order, not on every core."""

    def explore(self) -> None:
        tables = fill(self)
        graph = _explore(tables, self.progress, one_core=self.one_core)
        _name(self, tables, graph)
        self._graph, self._tables = graph, tables

    @property
    def graph(self) -> Graph:
        assert self._graph is not None, "the kernel has not explored yet"
        return self._graph

    def size(self) -> tuple[int, int]:
        return self.graph.states, self.graph.edges

    def marking(self, index: int) -> Marking:
        assert self._tables is not None
        places, tokens = self.place_names, self._tables.tokens
        runs = self._checked(lambda: self.graph.marking(index))
        return Marking(
            {places[place]: [tokens[t] for t in toks] for place, toks in runs}
        )

    def _parent_moves(self, index: int) -> list[int]:
        return list(self._checked(lambda: self.graph.path(index)))

    def _verdict(self) -> Verdict:
        pid = {p: i for i, p in enumerate(self.place_names)}
        instance = 0
        for place in self.roles.instance:
            instance |= 1 << pid[place]
        (
            all_good,
            bad,
            improper,
            fired,
            stop,
            end,
            tail,
            cycle,
            rescues,
        ) = self._checked(lambda: self.graph.check(instance))
        return Verdict(
            all_good=all_good,
            bad=bad,
            improper=improper,
            fired=frozenset(fired),
            stop=stop,
            end=end,
            tail=tuple(tail),
            cycle=tuple(cycle),
            rescues=frozenset((move, _KINDS[kind]) for move, kind in rescues),
        )

    def _first_steps(self) -> list[tuple[str, int, int]]:
        return [
            (_KINDS[kind], move, count)
            for kind, move, count in self._checked(self.graph.first_steps)
        ]

    def _place_counts(self) -> tuple[int, list[tuple[str, int]]]:
        names = self.place_names
        return self.graph.states, [
            (names[place], without)
            for place, without in self._checked(self.graph.place_counts)
        ]

    @staticmethod
    def _checked[T](read: Callable[[], T]) -> T:
        """What the kernel reads off its graph; its failure fails the run
        (D16, while the soundness checks run)."""
        kernel = _kernel()
        try:
            return read()
        except kernel.KernelError as error:
            raise FastPathError(str(error)) from error


class KernelCases:
    """Which transitions each case of a choice enables, on the fast path:
    the reference numbers the cases' tokens and fills their rows, and the
    kernel walks each case's bindings over those rows (D8), as it walks a
    marking's. A choice whose cases meet more than ``limit`` tokens is
    asked of the engine, and ``on_reference`` hears it once (D14, D16: never
    in silence).

    Raises :class:`tables.Untabled` for a net the tables cannot carry."""

    def __init__(
        self,
        net: Net,
        model: NetModel,
        firing: Firing,
        environment: Environment,
        on_reference: Callable[[str], None] | None,
        *,
        limit: int = TOKEN_LIMIT,
    ) -> None:
        self.explorer = Explorer(
            net, model, firing, environment=environment, max_states=0
        )
        fill(self.explorer)  # the check: raises Untabled
        self.engine = EngineCases(firing)
        self.on_reference = on_reference
        self.limit = limit
        self.tr_id = {tr.name: i for i, tr in enumerate(net.transitions)}
        self.noted: set[str] = set()

    def unusual(
        self,
        place: str,
        color: str,
        base: Mapping[str, Any],
        dims: Sequence[Dim],
        names: Sequence[str],
    ) -> Iterator[tuple[tuple[int, ...], list[str]]]:
        fields = [dim for dim in dims if dim.path is not None]
        context = dims[len(fields) :]
        assert all(dim.place is not None for dim in context), (
            "a choice's dims are the token's fields, then the context places"
        )
        try:
            # Fresh tables: the kernel takes their rows from the first
            # token on.
            rows = fill(self.explorer, limit=self.limit)
            tokens = [
                rows.token(witness_marking(place, color, base, fields, point)[place][0])
                for point in product(*(range(len(dim.values)) for dim in fields))
            ]
            places = [
                (
                    rows.pid[dim.place or ""],
                    [_EMPTY if v is None else rows.token(v) for v in dim.values],
                )
                for dim in context
            ]
        except TooManyTokens:
            if self.on_reference is not None and place not in self.noted:
                self.noted.add(place)
                self.on_reference(
                    f"the choice at ({place}), with more than {self.limit} tokens"
                )
            yield from self.engine.unusual(place, color, base, dims, names)
            return
        order = sorted(names, key=self.tr_id.__getitem__)
        kernel = _kernel()
        try:
            found = kernel.cases(
                rows.kernel,
                rows,
                rows.update(),
                [self.tr_id[name] for name in order],
                rows.pid[place],
                tokens,
                places,
            )
        except kernel.KernelError as error:
            raise FastPathError(str(error)) from error
        sizes = [len(dim.values) for dim in dims]
        for number, mask in found:
            point: list[int] = []
            for size in reversed(sizes):
                number, at = divmod(number, size)
                point.append(at)
            yield (
                tuple(reversed(point)),
                [name for k, name in enumerate(order) if mask >> k & 1],
            )


def run_kernel(tables: Rows) -> Explorer:
    """Hand ``tables`` to the kernel, which explores on one core in the
    reference's order and asks them for each row on first use, and rebuild
    their explorer's states from the graph it gives back, for
    :func:`first_difference` (D12)."""
    explorer = tables.explorer
    graph = _explore(tables, explorer.progress, one_core=True)
    _name(explorer, tables, graph)
    _rebuild(explorer, tables, graph)
    return explorer


def _name(explorer: Explorer, tables: Rows, graph: Graph) -> None:
    """Name what the kernel found beside its markings: the moves, the
    caps that stopped it, the maturities left out, failed deposits."""
    names = [tr.name for tr in explorer.net.transitions]
    for kind, a, b in graph.moves:
        move = tables.move(kind, a, b)
        index = explorer._move(move)  # pyright: ignore[reportPrivateUsage]
        if index != len(explorer.moves) - 1:
            raise FastPathError(f"the kernel's move {move} repeats move {index}")
    explorer.capped = graph.capped
    explorer.stopped = {names[t]: n for t, n in enumerate(graph.stopped) if n}
    for state, t, value in graph.withheld:
        explorer._withheld_states.add(state)  # pyright: ignore[reportPrivateUsage]
        explorer.withheld.setdefault(names[t], set()).add(tables.values[value])
    explorer.deposit_errors = [
        message
        for row, alt in graph.deposit_errors
        if (message := tables.fires[row].errors[alt]) is not None
    ]
    explorer.held_moves = {names[t] for t in graph.held_moves}


def _rebuild(explorer: Explorer, tables: Rows, graph: Graph) -> None:
    """The reference's states and parents, from the kernel's graph."""
    places = explorer.place_names
    tokens = tables.tokens
    used = [
        tuple((tables.used_names[k], n) for k, n in vector) for vector in graph.used
    ]
    marks, offsets = graph.markings, graph.marking_offsets
    flags, used_of = graph.flags, graph.used_of
    edge_offsets = graph.edge_offsets
    moves, targets, kinds = graph.edge_moves, graph.edge_targets, graph.edge_kinds
    states: list[_State] = []
    for i in range(graph.states):
        lists: dict[str, list[Any]] = {}
        j, end = offsets[i], offsets[i + 1]
        while j < end:
            place, count = marks[j], marks[j + 1]
            lists[places[place]] = [tokens[t] for t in marks[j + 2 : j + 2 + count]]
            j += 2 + count
        flag = flags[i]
        state = _State(
            Marking(lists),
            used[used_of[i]],
            edges=[
                (moves[e], targets[e], _KINDS[kinds[e]])
                for e in range(edge_offsets[i], edge_offsets[i + 1])
            ],
            expanded=bool(flag & 2),
            final=bool(flag & 1),
            cut=bool(flag & 4),
        )
        states.append(state)
    explorer.states = states
    explorer.parent = {
        i: (state, move)
        for i, (state, move) in enumerate(graph.parent)
        if state != 0xFFFFFFFF
    }


def first_difference(reference: Explorer, fast: Explorer) -> str | None:
    """Where two explorations of one net part, edge for edge: each state's
    marking (token lists in order), counts, flags and edges (move, target,
    kind), each move, each parent, and what the run stopped on. None when
    they are the same."""
    text = reference._token_text  # pyright: ignore[reportPrivateUsage]
    if len(reference.states) != len(fast.states):
        return f"markings: reference {len(reference.states)}, fast {len(fast.states)}"
    for i, (a, b) in enumerate(zip(reference.states, fast.states, strict=True)):
        ma = {p: [text(t) for t in ts] for p, ts in a.marking.items() if ts}
        mb = {p: [text(t) for t in ts] for p, ts in b.marking.items() if ts}
        if ma != mb:
            return f"marking {i}: reference {ma}, fast {mb}"
        if a.used != b.used:
            return f"marking {i}'s counts: reference {a.used}, fast {b.used}"
        for flag in ("expanded", "final", "cut"):
            if getattr(a, flag) != getattr(b, flag):
                return f"marking {i} {flag}: reference {getattr(a, flag)}, fast {getattr(b, flag)}"
        if a.edges != b.edges:
            return f"marking {i}'s edges: reference {a.edges}, fast {b.edges}"
    ka = [m.key(text) for m in reference.moves]
    kb = [m.key(text) for m in fast.moves]
    if ka != kb:
        at = next(
            (i for i, (x, y) in enumerate(zip(ka, kb, strict=False)) if x != y),
            min(len(ka), len(kb)),
        )
        return f"move {at}: reference {ka[at] if at < len(ka) else None}, fast {kb[at] if at < len(kb) else None}"
    for name in ("parent", "capped", "stopped", "withheld", "held_moves"):
        if getattr(reference, name) != getattr(fast, name):
            return f"{name}: reference {getattr(reference, name)}, fast {getattr(fast, name)}"
    if reference._withheld_states != fast._withheld_states:  # pyright: ignore[reportPrivateUsage]
        return "the markings that withheld a maturity differ"
    if set(reference.deposit_errors) != set(fast.deposit_errors):
        return f"deposit errors: reference {sorted(set(reference.deposit_errors))}, fast {sorted(set(fast.deposit_errors))}"
    return None


__all__ = [
    "REFERENCE_FLAG",
    "FastPathError",
    "KernelCases",
    "KernelExplorer",
    "explore_fast",
    "first_difference",
    "run_kernel",
]
