"""The prover's fast path: explore a net from the tables the reference fills."""

from typing import Any, Protocol, final

class KernelError(Exception):
    """A failure inside the kernel: a row the reference could not fill, or a
    panic."""

Update = tuple[
    list[tuple[list[bool], list[int], list[list[bool]], int | None]], list[float]
]
Effect = tuple[list[tuple[int, int]], list[tuple[int, int]]]

class Rows(Protocol):
    """The reference's side of the tables: fills a row on first use."""

    def fire(
        self, t: int, combo: list[int], clock: int | None, /
    ) -> tuple[int, list[Effect | None], Update]: ...
    def corr(
        self, c: int, tid: int, anchor_tid: int | None, /
    ) -> tuple[bool, Update]: ...
    def timer(
        self, t: int, c: int, bind: list[int], /
    ) -> tuple[bool, int | None, Update]: ...
    def tick(self, clock: int, c: int, v: int, /) -> tuple[int, Update]: ...

@final
class Graph:
    """What an exploration found: the graph, with every state's marking."""

    @property
    def capped(self) -> bool: ...
    @property
    def states(self) -> int: ...
    @property
    def markings(self) -> list[int]:
        """Per state, (place, count, tokens...) runs."""
    @property
    def marking_offsets(self) -> list[int]: ...
    @property
    def used_of(self) -> list[int]: ...
    @property
    def used(self) -> list[list[tuple[int, int]]]: ...
    @property
    def flags(self) -> list[int]:
        """Per state: 1 final, 2 expanded, 4 cut."""
    @property
    def parent(self) -> list[tuple[int, int]]: ...
    @property
    def edge_offsets(self) -> list[int]: ...
    @property
    def edge_moves(self) -> list[int]: ...
    @property
    def edge_targets(self) -> list[int]: ...
    @property
    def edge_kinds(self) -> list[int]:
        """0 net, 1 arrival, 2 update, 3 record."""
    @property
    def moves(self) -> list[tuple[int, int, int]]: ...
    @property
    def stopped(self) -> list[int]: ...
    @property
    def withheld(self) -> list[tuple[int, int, int]]: ...
    @property
    def deposit_errors(self) -> list[tuple[int, int]]: ...
    @property
    def held_moves(self) -> list[int]: ...
    def place_counts(self) -> list[tuple[int, int]]:
        """For each place some marking's key holds: how many distinct keys
        are left when it is ignored."""
    @property
    def edges(self) -> int:
        """How many edges the graph holds."""
    def check(
        self, instance: int, /
    ) -> tuple[
        bool,
        int | None,
        int | None,
        list[int],
        bool,
        int,
        list[int],
        list[int],
        list[tuple[int, int]],
    ]:
        """The soundness checks: (all_good, bad, improper, fired, stop, end,
        tail, cycle, rescues); ``instance`` masks the instance's places."""
    def first_steps(self) -> list[tuple[int, int, int]]:
        """(edge kind, move, count) for each step that first reached a
        marking."""
    def marking(self, index: int, /) -> list[tuple[int, list[int]]]:
        """State ``index``'s marking: (place, tokens) for each marked place."""
    def path(self, index: int, /) -> list[int]:
        """The moves that first reached state ``index``."""

class Progress(Protocol):
    """The progress line of one exploration (``velocitron_analysis.progress``)."""

    def tick(self, markings: int, waiting: int, /) -> None: ...

def explore(
    tables: dict[str, Any],
    rows: Rows,
    max_states: int,
    progress: Progress | None = None,
    *,
    one_core: bool = False,
) -> Graph:
    """Explore on every core, or with ``one_core`` on one, visiting markings
    in the reference's order; both give the same graph, ids and all. Asks
    ``rows`` for each row on first use, in that order; ``progress`` hears
    how far the run is."""

def cases(
    tables: dict[str, Any],
    rows: Rows,
    update: Update,
    transitions: list[int],
    place: int,
    tokens: list[int],
    context: list[tuple[int, list[int]]],
) -> list[tuple[int, int]]:
    """Each case of a choice, in ``product`` order, that enables none or
    more than one of ``transitions``: its number and a mask of those it
    enables. A case is one of ``tokens`` in ``place`` and one entry for
    each ``context`` place, a token or ``0xFFFF`` for the place empty."""
