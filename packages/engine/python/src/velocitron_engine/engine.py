"""The reference firing engine for velocitron nets.

Drives the full firing phase pipeline for a loaded :class:`Net`:

- **Enablement** — detect which transitions have a satisfiable binding in
  the current :class:`Marking`.
- **Binding** — deterministic first-enabled binding selection across the
  consume arcs' lexicographic token combinations, driven by ONE lazy
  enumeration shared with `timer_maturities` (ADR 0027).
- **Firing** — consume → invoke handler → deposit per the produce contract
  → record, with atomic rollback of the tentative consume on any failure.
- **Selection loop** — repeat enable → pick via firing policy → fire until
  quiescence or ``max_steps``.
- **CEL predicate evaluation** — exact string equalities recognized once; all
  other arc filters compiled once per expression and evaluated per token.
- **Timed transitions** — declarative ``timer`` enablement over a clock
  place's token (ADR 0018), with ``advance``'s ``time=`` mode as the
  engine-owned advance-and-re-evaluate seam.
- **Deposit-violation handling** — configurable ``raise`` /
  ``record_then_raise`` / ``record_then_drop`` modes.

The journal is decoupled via hooks: the engine emits :class:`FiringRecord`
 objects with NO ``sequence`` — the journal implementation owns numbering.

References: spec/firing-semantics.md (D2, D3, D4, D6).
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from itertools import combinations, product
from types import MappingProxyType
from typing import Any, Literal, NamedTuple, Protocol, cast, overload
from weakref import ReferenceType, ref

from pyrsistent import pvector

from .adapter import CelAdapter
from .contract import (
    FiringContext,
    FiringPolicyInput,
    FiringTimestamps,
    GuardHandler,
    GuardHandlerInput,
    HandlerError,
    PredicateHandlerInput,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from .journal import (
    FiringRecord,
    FiringStatus,
    InjectionKind,
    InjectionRecord,
    Journal,
    TraceEvent,
    TraceRecord,
)
from .registry import (
    DEFAULT_FIRING_POLICY,
    PRIORITY_FIRING_POLICY,
    HandlerNotFound,
    HandlerRegistry,
)
from .schema import (
    Arc,
    ConsumePattern,
    Marking,
    Net,
    Place,
    Predicate,
    ProduceTemplate,
    Timer,
    Token,
    Transition,
)

# The three legal deposit-violation modes.
_DEPOSIT_VIOLATION_MODES = ("raise", "record_then_raise", "record_then_drop")

# Deliberately narrower than CEL's full string grammar.  Only an unqualified
# identifier, equality, and a quoted string whose escapes are unambiguously
# quote/backslash escapes can bypass the adapter.  Every other valid CEL form
# stays on the backend path.
_STRING_EQUALITY = re.compile(
    r"""[ \t\r\n]*([A-Za-z_][A-Za-z0-9_]*)[ \t\r\n]*==[ \t\r\n]*"""
    r"""(?:"((?:[^\x00-\x1f"\\]|\\["\\])*)"|'((?:[^\x00-\x1f'\\]|\\['\\])*)')"""
    r"""[ \t\r\n]*"""
)
# CEL's lexical grammar excludes KEYWORD from SELECTOR and RESERVED from IDENT.
_CEL_RESERVED_WORDS = frozenset(
    ["false", "in", "null", "true", "as", "break", "const", "continue", "else", "for", "function", "if", "import", "let", "loop", "package", "namespace", "return", "var", "void", "while"]
)

_CEL_FAST_PATH_UNCACHED = object()
_LOGGER = logging.getLogger(__name__)


def _trace_error(exc: Exception) -> HandlerError:
    """Build a :class:`HandlerError` from an exception a traced call raised.

    The Engine reads a raising guard as not-enabled and a raising predicate as
    false (unchanged behavior); the trace record still carries the failure.
    """
    return HandlerError(type=type(exc).__name__, message=str(exc))


def _string_equality(expr: str) -> tuple[str, str] | None:
    """Extract the one CEL equality shape whose Python semantics are exact."""
    match = _STRING_EQUALITY.fullmatch(expr)
    if match is None:
        return None
    identifier = match.group(1)
    if identifier in _CEL_RESERVED_WORDS:
        return None
    encoded = match.group(2)
    if encoded is None:
        encoded = match.group(3)
    if "\\" not in encoded:
        return identifier, encoded

    decoded: list[str] = []
    index = 0
    while index < len(encoded):
        char = encoded[index]
        if char == "\\":
            index += 1
            char = encoded[index]
        decoded.append(char)
        index += 1
    return identifier, "".join(decoded)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _token_text(token: Token) -> str:
    return f"{token.type} {_json_text(token.data)}"


def _binding_text(binding: Mapping[str, Sequence[Token]]) -> str:
    return "; ".join(
        f"({place}) {', '.join(_token_text(tok) for tok in toks)}"
        for place, toks in binding.items()
    )


def _arc_text(arc: Arc) -> str:
    """An input arc in `.petrinet` chain notation: ``(p) -color->? [t]``."""
    consume = arc.consume
    assert consume is not None
    head = {"consume": "->", "read": "->?", "inhibit": "->0"}[consume.mode]
    return f"({arc.from_place}) -{consume.type}{head} [{arc.to_transition}]"


def _cel_value_text(value: Any) -> str:
    if value is True or value is False or value is None:
        return json.dumps(value)
    try:
        return _json_text(value)
    except TypeError:
        return repr(value)


_SELECTION = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)((?:\.[A-Za-z_][A-Za-z0-9_]*|\[[0-9]+\])+)"
)
_SELECTION_STEP = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[([0-9]+)\]")
_MISSING = object()


def _selected_values(expr: str, env: Mapping[str, Any]) -> str:
    """``name.field = value`` for each selection ``expr`` makes from ``env``.

    A diagnostic aid only: a regular expression finds selection paths such as
    ``clock.now`` or ``binding.waiting[0].isbn`` and walks them in Python, so
    a selection inside a string literal may be listed too.
    """
    parts: list[str] = []
    seen: set[str] = set()
    for match in _SELECTION.finditer(expr):
        root, path = match.group(1), match.group(2)
        if root not in env or match.group(0) in seen:
            continue
        seen.add(match.group(0))
        value: Any = env[root]
        for step in _SELECTION_STEP.finditer(path):
            field, index = step.group(1), step.group(2)
            if field is not None and isinstance(value, dict):
                value = cast(dict[str, Any], value).get(field, _MISSING)
            elif index is not None and isinstance(value, list):
                items = cast(list[Any], value)
                value = items[int(index)] if int(index) < len(items) else _MISSING
            else:
                value = _MISSING
            if value is _MISSING:
                break
        rendered = "missing" if value is _MISSING else _cel_value_text(value)
        parts.append(f"{root}{path} = {rendered}")
    return ", ".join(parts)


def _arc_slices(
    binding_arcs: Sequence[Arc], tokens: Mapping[str, Sequence[Token]]
) -> list[tuple[Arc, list[Token]]]:
    """Split a place-keyed binding back into each arc's bound tokens.

    ``_binding_from_combo`` concatenates the tokens of arcs that share a
    source place in arc order, so taking ``weight`` tokens per arc in the
    same order recovers each arc's share exactly.
    """
    cursor: dict[str, int] = {}
    slices: list[tuple[Arc, list[Token]]] = []
    for arc in binding_arcs:
        place = arc.from_place
        assert place is not None and arc.consume is not None
        start = cursor.get(place, 0)
        end = start + arc.consume.weight
        slices.append((arc, list(tokens[place][start:end])))
        cursor[place] = end
    return slices


class _Binding(NamedTuple):
    """A selected binding: the tokens the fire sees vs the tokens it removes.

    ``tokens`` is the FULL binding — consume- and read-mode arc tokens keyed by
    source place — which the guard, handler (``inputTokens``), and firing record
    all see. ``consumed`` is the consume-only subset the engine removes on fire;
    read-mode arcs are test-without-consume, so their tokens are in ``tokens``
    but never in ``consumed``. With no read arcs the two are equal, so the
    classical case is unchanged.

    References: spec/firing-semantics.md (a, b, D1); ADR 0012.
    """

    tokens: dict[str, list[Token]]
    consumed: dict[str, list[Token]]


class _BindingRejection(Enum):
    """Why the binding enumeration rejected a candidate (or the whole walk).

    The enumeration's ONE vocabulary of rejections (ADR 0027). Candidate-level
    members annotate a yielded binding that failed one of the pure, structural
    per-binding tests; walk-level members close a walk that produced no
    candidate binding at all (``tokens``/``consumed`` are ``None`` there).

    The guard is deliberately NOT a rejection reason: it is possibly impure
    (ADR 0002), so it is evaluated by the first-success consumer
    (:meth:`Engine._select_binding`), which may stop the enumeration early —
    never inside it.
    """

    # Walk-level: a pre-binding gate failed the whole transition before any
    # candidate binding existed — the uncorrelated inhibit zero-test matched, a
    # binding arc had fewer matching tokens than its ``weight``, or a timer's
    # clock place was empty (no time reference ⇒ not enabled, ADR 0018).
    PER_ARC_MISS = "per-arc-miss"
    # Walk-level: the cartesian product was walked to its end without one
    # surviving binding (sub-multiset, correlate-miss, correlated-inhibit,
    # timer, and — consumer-side — guard failures exhaust it).
    PRODUCT_MISS = "product-miss"
    # Candidate-level: the combined bound multiset would bind one token to two
    # arcs — not a valid sub-multiset of the source place (D1; shared-place
    # binding, ADR 0012).
    SUBMULTISET = "sub-multiset"
    # Candidate-level: a token bound on a correlated consume or read arc did
    # not satisfy its ``correlate`` against the binding (eval error or
    # non-boolean fails closed, ADR 0030).
    CORRELATE_MISS = "correlate-miss"
    # Candidate-level: a correlated inhibit arc's per-binding anti-join
    # blocked the binding (eval error or non-boolean fails closed, ADR 0017).
    CORRELATED_INHIBIT = "correlated-inhibit"
    # Candidate-level: the timer-hold gate failed — ``timer.cel`` did not
    # evaluate to exact ``true`` for this binding, so it is unmatured
    # (ADR 0018). This is the wake-candidate consumer's success signal:
    # :meth:`Engine.timer_maturities` consumes the FIRST such yield.
    TIMER_HOLD = "timer-hold"


@dataclass(frozen=True)
class _CandidateBinding:
    """One candidate binding yielded by the enumeration, plus why rejected.

    ``rejected`` is ``None`` for a Viable binding — one that passed every
    pure, structural gate (uncorrelated inhibits, per-arc candidates,
    sub-multiset validity, consume/read correlates, correlated inhibits, and,
    for a timed transition,
    the timer-hold gate). The consumers own the remaining, possibly-impure
    tests: the guard (first-success) and the ``timer.maturity`` scheduling
    expression (first-wake).

    Walk-level rejections carry ``None`` ``tokens``/``consumed``; they are the
    FINAL yield of an exhausted walk.
    """

    tokens: dict[str, list[Token]] | None
    consumed: dict[str, list[Token]] | None
    rejected: _BindingRejection | None


class TimerMaturity(NamedTuple):
    """A future clock advance candidate declared by one timer binding."""

    transition: str
    clock: str
    at: float


BindingChoice = Callable[[Mapping[str, Sequence[Token]]], bool]
"""A caller's filter over full candidate bindings (consume- and read-mode
tokens keyed by source place); see :meth:`Engine.reserve`."""


EnablementGate = Literal[
    "clock-empty",
    "inhibit-hit",
    "arc-short",
    "sub-multiset",
    "correlate-miss",
    "correlated-inhibit",
    "timer-hold",
    "guard-unresolved",
    "guard-rejected",
    "guard-error",
]


@dataclass(frozen=True)
class EnablementReason:
    """One gate that turned a transition's binding (or every binding) away.

    ``gate`` names the gate in the enumeration's vocabulary (ADR 0027), split
    finer where the walk folds several causes into one rejection: a
    ``per-arc-miss`` becomes ``clock-empty``, ``inhibit-hit`` or
    ``arc-short``. ``message`` is one line with the values that decided it;
    ``details`` holds further lines (for ``arc-short``, why each token in the
    place was turned away). ``arc`` is the arc's index in ``net.arcs``.
    """

    gate: EnablementGate
    message: str
    place: str | None = None
    arc: int | None = None
    tokens: tuple[Token, ...] = ()
    binding: Mapping[str, Sequence[Token]] | None = None
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnablementExplanation:
    """Why a transition is or is not enabled in one marking.

    ``enabled`` and ``binding`` are exactly what :meth:`Engine.select_binding`
    decides. ``viable`` lists the candidate bindings that passed every pure
    gate, in enumeration order (at most :attr:`Engine.EXPLAIN_LIMIT`).
    ``reasons`` lists the gates that rejected candidates, at most
    :attr:`Engine.EXPLAIN_LIMIT` distinct messages per gate, in the order the
    walk met them.
    """

    transition: str
    enabled: bool
    binding: Mapping[str, Sequence[Token]] | None
    viable: tuple[Mapping[str, Sequence[Token]], ...]
    reasons: tuple[EnablementReason, ...]


class FiringReservation(NamedTuple):
    """A binding whose consume-mode tokens have been reserved for async work.

    ``Engine.fire`` remains the synchronous one-shot primitive.  Long-lived
    runtimes use this explicit two-phase seam instead: :meth:`Engine.reserve`
    selects a binding and removes only its consume-mode tokens, then
    :meth:`Engine.settle` either deposits a completed handler result or restores
    the reserved input on failure.  A runtime must admit only independent
    reservations, so no other in-flight operation can mutate the reservation's
    consumed places before it settles.
    """

    net: Net
    original_marking: Marking
    reserved_marking: Marking
    transition: str
    attempt: int
    context: FiringContext
    input_tokens: dict[str, list[Token]]
    consumed_tokens: dict[str, list[Token]]


class OutputProvider(Protocol):
    """Fills a symbolic firing's outputs, or ``None`` to skip the transition.

    Given the net and one live reservation (its binding already selected,
    consume-mode tokens reserved), return the :class:`TransitionHandlerOutput`
    to settle with, or ``None`` — the caller excludes the transition for the
    remainder of the advance: no record, the transition stays enabled.

    Must be a pure function of ``(net, reservation)``: the engine may probe
    more candidates than it settles, one reservation at a time, and calls
    the provider again at settle time rather than caching.
    """

    def __call__(
        self, net: Net, reservation: FiringReservation
    ) -> TransitionHandlerOutput | None: ...


class AdvanceOutcome(NamedTuple):
    """What ``advance`` returns in provider mode: the marking after every
    settled firing, and per firing the record with the marking that firing
    alone produced (``firings[i]``'s marking is ``firings[i+1]``'s start,
    and the last is ``marking``)."""

    marking: Marking
    firings: tuple[tuple[FiringRecord, Marking], ...]


class _TopologyIndex(NamedTuple):
    """Immutable, declaration-ordered lookup tables for one :class:`Net`."""

    transitions: tuple[Transition, ...]
    transition_by_name: Mapping[str, Transition]
    place_by_name: Mapping[str, Place]
    input_arcs: Mapping[tuple[str, str], tuple[Arc, ...]]
    binding_arcs: Mapping[str, tuple[Arc, ...]]
    produce_arcs: Mapping[str, tuple[Arc, ...]]
    candidate_mask_by_place: Mapping[str, int]
    always_candidate_mask: int


class DepositViolation(Exception):
    """Raised on a deposit-contract violation when configured to raise.

    A deposit violation is a programmer-bug signal: the transition handler
    returned tokens to a place with no matching produce template, or with the
    wrong token type. Carry a human-readable message.

    References: spec/firing-semantics.md (D3).
    """


def _same_json_value(left: Any, right: Any) -> bool:
    """JSON equality: one number type, and a boolean is never a number."""
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def domain_violation(net: Net, place: str, token: Token) -> str | None:
    """Why ``token`` breaks one of the net's declared domains, or ``None``.

    A domain (ADR 0037) names ``color.field.path`` and its closed values; a
    token of that color must hold one of them at that path.
    """
    for key, values in (net.domains or {}).items():
        color, *path = key.split(".")
        if color != token.type:
            continue
        current: Any = token.data
        for name in path:
            if not isinstance(current, dict) or name not in current:
                return (
                    f"token {token.type} into ({place}) has no "
                    f"{'.'.join(path)}, which domain {key} requires"
                )
            current = cast(dict[str, Any], current)[name]
        if not any(_same_json_value(current, value) for value in values):
            listed = ", ".join(json.dumps(v, ensure_ascii=False) for v in values)
            return (
                f"token {token.type} into ({place}) holds {'.'.join(path)} = "
                f"{json.dumps(current, ensure_ascii=False)}, outside domain "
                f"{key}: {listed}"
            )
    return None


# Each adapter's compiled produce programs, by expression. Keyed by the
# adapter's identity with a weak reference, like ``Engine._topology``: the
# programs never keep an adapter alive, an entry leaves with its adapter,
# and checking the referent makes id reuse harmless.
_PRODUCE_PROGRAMS: dict[int, tuple[ReferenceType[CelAdapter], dict[str, Any]]] = {}


def _produce_program(cel: str, cel_adapter: CelAdapter) -> Any:
    """The compiled program of ``cel`` for ``cel_adapter``, compiled once."""
    key = id(cel_adapter)
    cached = _PRODUCE_PROGRAMS.get(key)
    if cached is None or cached[0]() is not cel_adapter:
        try:
            weak = ref(cel_adapter, lambda _gone: _PRODUCE_PROGRAMS.pop(key, None))
        except TypeError:
            # An adapter without weak references (``__slots__``) compiles
            # on every call, as before.
            return cel_adapter.compile(cel)  # pyright: ignore[reportUnknownMemberType]
        cached = _PRODUCE_PROGRAMS[key] = (weak, {})
    programs = cached[1]
    program = programs.get(cel)
    if program is None:
        program = programs[cel] = cel_adapter.compile(cel)  # pyright: ignore[reportUnknownMemberType]
    return program


def evaluate_produce_cel(
    cel: str,
    binding: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    cel_adapter: CelAdapter,
) -> Any:
    """Evaluate one produce template's ``data cel`` the Engine's own way.

    ``binding`` is the ADR 0017 map the Engine's ``_cel_binding`` builds:
    bound-token *data* per key (place name, or ``binding_names`` key). The
    scope is exactly the fallback's: ``{"binding": <that map>}`` — no
    firing context. A generated handler must fill its outputs through this
    function, so the values it deposits are the values the Engine's
    fallback would compute; ``Engine._deposit`` calls it too, making this
    the one evaluator (ADR 0058, Decision 2). Domain checks stay at
    deposit.

    Each adapter compiles an expression once; later calls reuse the
    program, since every deposit of a template evaluates the same text.

    Returns the raw Python result; raises on an evaluation error, so a
    caller decides its own failure handling (the Engine routes one through
    :class:`_DepositError`). When the fields the expression names hold both
    ints and doubles, which CEL never mixes in arithmetic, the error gets a
    note naming each with its type (:func:`error_text` renders it).
    """
    try:
        return cel_adapter.eval(
            _produce_program(cel, cel_adapter), {"binding": binding}
        )
    except Exception as exc:
        note = _number_mix_note(cel, {"binding": binding})
        if note is not None:
            exc.add_note(note)
        raise


def error_text(exc: BaseException) -> str:
    """``exc``'s message followed by its notes, for a record's error text."""
    return "; ".join([str(exc), *getattr(exc, "__notes__", ())])


def _number_mix_note(cel: str, scope: Mapping[str, Any]) -> str | None:
    """Name the int and double fields ``cel`` reads, when it reads both.

    CEL has no implicit int/double promotion, so ``0 + 600.0`` fails on
    every backend. A token's numbers keep the type the caller gave them
    (``0`` from a test, ``time.time()`` from a clock), so the same net can
    pass with one caller and fail with another."""
    ints: list[str] = []
    doubles: list[str] = []
    for path, value in _number_leaves(scope, ""):
        if re.search(rf"(?<![\w.]){re.escape(path)}(?![\w\[])", cel) is None:
            continue
        if isinstance(value, int):
            ints.append(f"{path} is int {value!r}")
        else:
            doubles.append(f"{path} is double {value!r}")
    if not ints or not doubles:
        return None
    return (
        "CEL does not mix int and double in arithmetic: "
        + ", ".join(ints + doubles)
        + "; give them one type (a double in the token, or double(...))"
    )


def _number_leaves(value: Any, path: str) -> Iterator[tuple[str, int | float]]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield path, value
    elif isinstance(value, Mapping):
        for key, item in cast(Mapping[str, Any], value).items():
            yield from _number_leaves(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        for index, item in enumerate(cast(Sequence[Any], value)):
            yield from _number_leaves(item, f"{path}[{index}]")


class _DepositError(Exception):
    """Internal: a deposit broke the produce contract after the handler ran.

    A produce template's ``cel`` failed (an evaluation error or a non-object
    result, ADR 0023), or a deposited token holds a value outside a declared
    domain (ADR 0037). Never escapes ``fire``/``settle`` — both catch it and
    route the failure through the ordinary deposit-contract-violation
    handling (D3), carrying this exception's message as the violation detail.
    """


class UnknownTransitionError(Exception):
    """Raised when a transition name does not resolve to a declared transition.

    A public engine entry point that takes a transition name (``fire``,
    ``select_binding``) rejects a name absent from the net's declared
    transitions: an unknown name (a typo) is a **programmer bug**, surfaced as a
    raise rather than silently firing with an empty binding — the empty binding
    is the legitimate path for a *declared* source transition (no input arcs),
    and an undeclared name is indistinguishable from it inside
    ``_binding_candidates`` (both have no binding arcs), so the check must live at
    the name-taking public boundary.

    Distinct from :class:`HandlerNotFound` (a net-referenced handler ref missing
    from the registry, which the engine degrades to a *transition failure* — a
    ``failed`` record): here the transition itself is not in the net, so there
    is no transition to fail — the call is malformed. Mirrors
    ``inject_token``'s ``ValueError`` for an unknown place (a programmer bug the
    seam raises on, not a firing outcome).

    Carries the offending :attr:`transition` name and the :attr:`net` name.

    References: spec/firing-semantics.md (D10).
    """

    transition: str
    net: str

    def __init__(self, net: str, transition: str) -> None:
        super().__init__(f"net {net!r} has no transition named {transition!r}")
        self.net = net
        self.transition = transition


class Conflict(Exception):
    """Raised by a strict ``advance`` when two or more transitions are
    enabled at once and the firing policy would pick one.

    A net whose choices are proved (choice coverage) never shows a conflict;
    a strict advance makes a changed net that does an error, not a silent
    pick. Under the priority policy only the transitions that share the top
    declared priority conflict. Nothing fired at the marking it raised on.

    Carries the :attr:`net` name, the conflicting :attr:`transitions`, in
    declaration order, and the :attr:`marking` they are enabled in, the one
    the advance stopped at.

    References: spec/firing-semantics.md (e).
    """

    net: str
    transitions: tuple[str, ...]
    marking: Marking

    def __init__(
        self, net: str, transitions: Sequence[str], *, marking: Marking
    ) -> None:
        names = ", ".join(f"[{name}]" for name in transitions)
        super().__init__(f"{net}: {names} are enabled at once")
        self.net = net
        self.transitions = tuple(transitions)
        self.marking = marking


class FailedAttempt(Exception):
    """Raised by a strict ``advance`` or ``fire`` when a firing attempt fails.

    The failed :attr:`record` went to the journal as usual, and the marking
    is unchanged by it (atomic rollback). A strict advance stops there rather
    than retrying the transition. :attr:`marking` is where it stopped: what
    the firings before the failed attempt left, so a caller that keeps a
    marking between runs goes on from there.

    References: spec/firing-semantics.md (e).
    """

    net: str
    record: FiringRecord
    marking: Marking

    def __init__(self, net: str, record: FiringRecord, *, marking: Marking) -> None:
        error = record["error"]
        detail = f"{error['type']}: {error['message']}" if error else "no error given"
        super().__init__(f"{net}: [{record['transition']}] failed: {detail}")
        self.net = net
        self.record = record
        self.marking = marking


class _FailureLedger:
    """The one implementation of ADR 0015's failure-budget invariant.

    Counts each transition's consecutive ``failed`` firings and clears every
    count on any ``completed`` firing. Selection consults the ledger twice per
    round: :meth:`admissible` decides whether a transition may still compete
    (a count that has reached the budget makes it **exhausted** — excluded from
    selection until a completed firing resets the counts), and :meth:`counts`
    builds the ``consecutiveFailures`` policy input, which is threaded to every
    policy whether or not a budget is configured.

    Owned by the Engine: ``Engine.advance`` creates a fresh ledger per ``advance``
    call (counts scoped to the call, so replay determinism holds), and the Runtime's
    admission loop holds one long-lived ledger obtained from
    :meth:`Engine.selection_ledger`. The Runtime contributes only its own
    distinct seam rule (failed transitions are parked until an input place
    changes); it never re-implements this invariant.

    The counts are a pure function of the firing sequence — never wall-clock —
    and exhaustion is not separately journaled: it is derivable from the
    recorded sequence.

    References: ADR 0015; spec/firing-semantics.md (D5, D9, e).
    """

    def __init__(self, budget: int | None) -> None:
        # ``None`` = no budget (default): exhaustion is never applied, but the
        # consecutive-failure history is still counted and threaded to
        # policies. Budget >= 1 is validated at Engine construction.
        self._budget = budget
        self._failures: dict[str, int] = {}

    def admissible(self, transition: str) -> bool:
        """Whether ``transition`` has not exhausted its failure budget."""
        if self._budget is None:
            return True
        return self._failures.get(transition, 0) < self._budget

    def filtered(self, enabled: list[str]) -> list[str]:
        """The still-admissible subset of ``enabled``, in input order."""
        return [name for name in enabled if self.admissible(name)]

    def counts(self, enabled: list[str]) -> dict[str, int]:
        """``FiringPolicyInput.consecutiveFailures``: keyed by exactly
        ``enabled`` (no failure history = 0)."""
        return {name: self._failures.get(name, 0) for name in enabled}

    def record(self, transition: str, status: str) -> None:
        """Fold one firing outcome into the ledger: a ``failed`` firing
        increments the transition's count; any completed firing clears every
        count (the marking changed, so an exhausted transition's inputs may
        differ and it earns fresh retries)."""
        if status == "failed":
            self._failures[transition] = self._failures.get(transition, 0) + 1
        else:
            self._failures.clear()


class Engine:
    """The reference firing engine for velocitron nets.

    Owns the firing phase pipeline end to end:

    - **Enablement** — which transitions have a satisfiable binding.
    - **Binding** — deterministic first-enabled binding selection.
    - **Firing** — consume → invoke → deposit → record, with atomic rollback
      of the tentative consume on any failure.
    - **Selection loop** — repeat until quiescence or ``max_steps``.
    - **CEL predicate evaluation** — cached exact-string fast path, otherwise
      compile-once and eval-per-token arc filters.
    - **Timed transitions** — declarative ``timer`` enablement + ``advance``
      with ``time=`` (ADR 0018, ADR 0060).
    - **Deposit-violation handling** — configurable raise / record / drop modes.

    The engine never assigns ``sequence`` to a record — that is the journal's
    concern.

    References: spec/firing-semantics.md (D4).
    """

    def __init__(
        self,
        registry: HandlerRegistry,
        *,
        policy: str = DEFAULT_FIRING_POLICY,
        journal: Journal | None = None,
        deposit_violation: str = "raise",
        cel_adapter: CelAdapter | None = None,
        max_consecutive_failures: int | None = None,
    ) -> None:
        if deposit_violation not in _DEPOSIT_VIOLATION_MODES:
            raise ValueError(
                f"deposit_violation must be one of {_DEPOSIT_VIOLATION_MODES}, "
                f"got {deposit_violation!r}"
            )
        # The opt-in failure budget (ADR 0015): None (default) = unlimited —
        # today's behavior, a persistently failing transition stays selectable
        # forever. An int >= 1 caps consecutive failed firings per transition
        # within an advance; 0 would exhaust every transition before its first
        # fire, so it is a configuration error like a bad deposit_violation.
        if max_consecutive_failures is not None and max_consecutive_failures < 1:
            raise ValueError(
                "max_consecutive_failures must be >= 1 (or None for no "
                f"budget), got {max_consecutive_failures!r}"
            )
        # "raise" is the only legal mode when no journal is attached: the
        # record_then_* modes need somewhere to record the violation.
        if deposit_violation != "raise" and journal is None:
            raise ValueError(
                "deposit_violation='record_then_raise'/'record_then_drop' "
                "requires a journal"
            )
        # Validate the firing-policy ref at construction: it is engine
        # config (not net-referenced), known at __init__ with no transition
        # context to fail within. An unresolvable policy is a configuration
        # error raised here -- not a HandlerNotFound crashing out of `advance`
        # on the first step. The resolve-miss-as-transition-failure rule
        # scopes to net-referenced handlers within fire/enablement.
        # References: spec/firing-semantics.md (e).
        registry.resolve_firing_policy(policy)
        self.registry = registry
        self.policy = policy
        self.journal = journal
        self.deposit_violation = deposit_violation
        self.max_consecutive_failures = max_consecutive_failures
        # CEL: one adapter, a compile-once-per-expression backend cache, and a
        # cached recognizer for the exact identifier == string-literal shape.
        # The caller injects the adapter. This package does not select a
        # backend. Eval errors are caught in _eval_predicate. D6.
        if cel_adapter is None:
            raise ValueError(
                "cel_adapter is required; velocitron-engine does not bundle a "
                "CEL backend"
            )
        self._cel_adapter: CelAdapter = cel_adapter
        self._cel_cache: dict[str, Any] = {}
        self._cel_string_equalities: dict[str, tuple[str, str] | None] = {}
        # Key by identity because Net's frozen dataclass contains unhashable
        # list fields. A weak reference avoids retaining every Net shown to a
        # long-lived Engine; checking its referent makes id reuse harmless.
        self._topology_cache: dict[int, tuple[ReferenceType[Net], _TopologyIndex]] = {}

    def _topology(self, net: Net) -> _TopologyIndex:
        """Return the immutable topology index belonging to ``net``."""
        key = id(net)
        cached = self._topology_cache.get(key)
        if cached is not None and cached[0]() is net:
            return cached[1]

        transitions = tuple(net.transitions)
        transition_by_name = {tr.name: tr for tr in transitions}
        place_by_name = {place.name: place for place in net.places}
        input_lists: dict[tuple[str, str], list[Arc]] = {}
        binding_lists: dict[str, list[Arc]] = {}
        produce_lists: dict[str, list[Arc]] = {}
        for arc in net.arcs:
            if arc.consume is not None and arc.to_transition is not None:
                input_lists.setdefault(
                    (arc.to_transition, arc.consume.mode), []
                ).append(arc)
                if arc.consume.mode in ("consume", "read"):
                    binding_lists.setdefault(arc.to_transition, []).append(arc)
            elif arc.produce is not None and arc.from_transition is not None:
                produce_lists.setdefault(arc.from_transition, []).append(arc)

        # Every binding arc must be satisfied, so one declaration-first source
        # place is a safe necessary condition for probing that transition.
        # Source/inhibit-only transitions have no such condition and remain
        # candidates on every pass. Bit positions preserve transition order
        # without caching any marking-dependent enablement result.
        candidate_mask_by_place: dict[str, int] = {}
        always_candidate_mask = 0
        for position, tr in enumerate(transitions):
            bit = 1 << position
            tr_binding_arcs = binding_lists.get(tr.name)
            if tr_binding_arcs:
                place = tr_binding_arcs[0].from_place
                assert place is not None
                candidate_mask_by_place[place] = (
                    candidate_mask_by_place.get(place, 0) | bit
                )
            else:
                always_candidate_mask |= bit

        topology = _TopologyIndex(
            transitions=transitions,
            transition_by_name=MappingProxyType(transition_by_name),
            place_by_name=MappingProxyType(place_by_name),
            input_arcs=MappingProxyType(
                {key: tuple(arcs) for key, arcs in input_lists.items()}
            ),
            binding_arcs=MappingProxyType(
                {name: tuple(arcs) for name, arcs in binding_lists.items()}
            ),
            produce_arcs=MappingProxyType(
                {name: tuple(arcs) for name, arcs in produce_lists.items()}
            ),
            candidate_mask_by_place=MappingProxyType(candidate_mask_by_place),
            always_candidate_mask=always_candidate_mask,
        )

        engine_ref = ref(self)

        def discard(dead_ref: ReferenceType[Net]) -> None:
            engine = engine_ref()
            if engine is None:
                return
            current = engine._topology_cache.get(key)
            if current is not None and current[0] is dead_ref:
                engine._topology_cache.pop(key, None)

        self._topology_cache[key] = (ref(net, discard), topology)
        return topology

    def topology_index(self, net: Net) -> _TopologyIndex:
        """The declaration-ordered topology tables this engine holds for ``net``.

        The Runtime's admission seam classifies each transition's consumed /
        read / written places (``Runtime._footprint``) from these tables — ONE
        enumeration of a net's shape, owned by the engine, instead of
        re-deriving arc classification from ``net.arcs`` (ADR 0027). The tables
        are immutable and caching is net-scoped, so this grants no
        marking-dependent state.
        """
        return self._topology(net)

    def _candidate_transitions(
        self, net: Net, marking: Marking
    ) -> Iterator[Transition]:
        """Yield transitions that can be enabled, in declaration order."""
        topology = self._topology(net)
        mask = topology.always_candidate_mask
        for place, place_mask in topology.candidate_mask_by_place.items():
            if marking.get(place, ()):
                mask |= place_mask
        while mask:
            bit = mask & -mask
            yield topology.transitions[bit.bit_length() - 1]
            mask ^= bit

    # ── CEL predicate evaluation ────────────────────────────────────────

    def _compile_cel(self, expr: str) -> Any:
        """Return the cached compiled CEL program for ``expr``.

        Compile at first use, not per token: a predicate's expression is
        stable across the tokens it filters. Runtime eval errors (undeclared
        refs, type errors) are handled by the caller, not here.
        """
        compiled = self._cel_cache.get(expr)
        if compiled is None:
            compiled = self._cel_adapter.compile(expr)  # pyright: ignore[reportUnknownMemberType]
            self._cel_cache[expr] = compiled
        return compiled

    def _eval_predicate(
        self,
        predicate: Predicate | None,
        token: Token,
        ctx: FiringContext,
        *,
        net: Net | None = None,
        transition: str | None = None,
    ) -> bool:
        """Evaluate a single-token arc filter.

        ``None`` predicate -> True (unrestricted consume). A safe exact string
        equality may be evaluated directly; every other CEL predicate is
        evaluated against ``token.data`` through the adapter. A runtime eval
        error (undeclared ref, type error) yields False, not a crash. A named
        predicate handler is resolved and called; any failure (incl.
        :class:`HandlerNotFound`) yields False.

        ``net`` / ``transition`` thread the emitting context for the
        ``predicate_checked`` trace record: with both present and the attached
        journal carrying the hook, every named-handler call gets one record
        (inline CEL predicates are compile/eval, not handlers, and get none).

        References: spec/firing-semantics.md (D6); ADR 0058, Decision 6.
        """
        if predicate is None:
            return True
        cel = predicate.cel
        if cel is not None:
            try:
                fast_path = self._cel_string_equalities[cel]
            except KeyError:
                fast_path = _string_equality(cel)
                self._cel_string_equalities[cel] = fast_path
            if fast_path is not None:
                identifier, expected = fast_path
                actual = token.data.get(identifier, _CEL_FAST_PATH_UNCACHED)
                # A present, exact string is the only data shape whose result
                # is backend-independent. Missing or differently typed values
                # retain the adapter's error/coercion behavior below.
                if type(actual) is str:
                    return actual == expected
            try:
                result = self._cel_adapter.eval(self._compile_cel(cel), token.data)  # pyright: ignore[reportUnknownMemberType]
            except Exception:  # noqa: BLE001 - any eval error => predicate false
                # Runtime eval error (adapter raises CelEvalError) =>
                # predicate false.
                return False
            return result is True
        if predicate.handler is not None:
            handler: Callable[[PredicateHandlerInput], bool] | None = None
            handler_error: HandlerError | None = None
            # Bound before the try: the finally reads it on the success path,
            # and a handler failure leaves it unset. The trace record uses
            # ``handler_error`` to decide which one to report.
            result: bool | None = None
            try:
                handler = self.registry.resolve_predicate(predicate.handler)
                result = handler(PredicateHandlerInput(token=token, firingContext=ctx))
            except Exception as exc:  # noqa: BLE001 - any handler failure => predicate false, symmetric with CEL eval
                # Any handler failure (unresolved ref, runtime error) =>
                # predicate false, symmetric with a CEL eval error.
                handler_error = _trace_error(exc)
            finally:
                # One trace record per named-handler call, on every exit path
                # of the try above (return or raise): the ref in ``handler``,
                # the callable's qualified name in ``method``, the answer in
                # ``result`` or the failure in ``error``. Emitted only when the
                # calling path threaded ``net``/``transition`` (the binding
                # walk) AND the journal carries the hook.
                if net is not None and transition is not None:
                    method = getattr(handler, "__qualname__", None)
                    self._record_trace(
                        "predicate_checked",
                        net=net,
                        ctx=ctx,
                        transition=transition,
                        handler=predicate.handler,
                        method=method,
                        result=None if handler_error is not None else result is True,
                        error=handler_error,
                    )
            if handler_error is not None:
                return False
            return result is True
        # Neither cel nor handler set: unrestricted.
        return True

    def _timer_holds(
        self,
        timer: Timer,
        clock_data: dict[str, Any],
        binding: dict[str, list[Token]],
    ) -> bool:
        """Whether a timer's temporal condition holds for a candidate binding.

        Evaluates ``timer.cel`` against the closed environment: the reserved
        variable ``clock`` is the clock token's ``data`` and each ``bind``
        variable is the ``data`` of the first token bound from its place (the
        parser guarantees every bind place is a binding-arc source, so it is
        present in every candidate binding). A runtime eval error degrades to
        condition-false — the binding is simply not matured — symmetric with a
        predicate's eval error (D6). An instance method: it compiles and
        evaluates CEL.

        References: spec/firing-semantics.md (a, f); ADR 0018.
        """
        env: dict[str, Any] = {"clock": clock_data}
        for var, place in (timer.bind or {}).items():
            env[var] = binding[place][0].data
        try:
            result = self._cel_adapter.eval(self._compile_cel(timer.cel), env)  # pyright: ignore[reportUnknownMemberType]
        except Exception:  # noqa: BLE001 - any eval error => condition false
            # Runtime eval error (missing field, type mismatch) => not
            # matured, never a crash. (D6-symmetric.)
            return False
        return result is True

    def _timer_maturity(
        self,
        timer: Timer,
        clock_data: dict[str, Any],
        binding: dict[str, list[Token]],
        *,
        transition: str,
    ) -> float | None:
        """Evaluate one Runtime scheduling expression without changing enablement.

        ``Timer.cel`` remains the only timer enablement authority.  This
        companion expression only identifies the next future clock timestamp
        worth injecting for a structurally viable candidate binding.
        """
        assert timer.maturity is not None
        env: dict[str, Any] = {"clock": clock_data}
        for var, place in (timer.bind or {}).items():
            env[var] = binding[place][0].data
        try:
            raw = self._cel_adapter.eval(self._compile_cel(timer.maturity), env)  # pyright: ignore[reportUnknownMemberType]
            current = float(clock_data["now"])
            at = float(raw)
        except Exception as exc:  # noqa: BLE001 - scheduling stays non-spinning
            _LOGGER.warning(
                "timer maturity unschedulable",
                extra={
                    "transition": transition,
                    "reason": f"{type(exc).__name__}: {exc}",
                },
            )
            return None
        if isinstance(raw, bool) or not math.isfinite(at):
            _LOGGER.warning(
                "timer maturity unschedulable",
                extra={
                    "transition": transition,
                    "reason": f"expected a finite timestamp, got {raw!r}",
                },
            )
            return None
        if at <= current:
            # A maturity at or behind the clock is not a future wake candidate,
            # so it is excluded silently — like a ready timer (whose cel already
            # holds) is skipped upstream. Reaching here means the cel did *not*
            # hold, so advancing to `at` would not enable the transition anyway:
            # another guard blocks it (e.g. a poll whose deadline upper bound has
            # elapsed). Common on journal replay, where a restored clock token
            # can sit ahead of a restored token's stamped maturity.
            return None
        return at

    def timer_maturities(self, net: Net, marking: Marking) -> tuple[TimerMaturity, ...]:
        """Schedule every timed transition's next future wake, declaration order.

        The one-walk consumer of :meth:`_binding_candidates` for the Runtime's
        advisory wake seam: for each declared transition carrying a
        ``timer.maturity``, the enumeration is consumed until its FIRST
        ``TIMER_HOLD`` rejection — the first structurally valid binding whose
        ``Timer.cel`` does not hold (the timer-predicate failure). That
        binding's ``timer.maturity`` expression declares the next future clock
        timestamp worth injecting; anything it yields at or behind the clock is
        excluded (a wake it would enable is already blocked). The walk stops
        there — lazily: one wake candidate per timed transition is all the
        Runtime's ``min``-wake consumption can act on, and normal
        :meth:`enabled_transitions` remains the sole source of firing
        enablement, including ``Timer.cel`` and guards.

        The Runtime consumes these advisory wake candidates; normal
        enablement never consults this surface.
        """
        maturities: list[TimerMaturity] = []
        for transition in net.transitions:
            timer = transition.timer
            if timer is None or timer.maturity is None:
                continue
            if not marking.get(timer.clock):
                continue
            ctx = self._make_ctx(net, transition.name, attempt=0)
            for step in self._binding_candidates(net, transition.name, marking, ctx):
                if step.rejected is not _BindingRejection.TIMER_HOLD:
                    continue
                assert step.tokens is not None
                at = self._timer_maturity(
                    timer,
                    marking[timer.clock][0].data,
                    step.tokens,
                    transition=transition.name,
                )
                if at is not None:
                    maturities.append(TimerMaturity(transition.name, timer.clock, at))
                break  # first timer-predicate failure ends this transition's walk
        return tuple(maturities)

    # ── Arc helpers ───────────────────────────────────────────────────────

    def _token_matches(
        self,
        consume: ConsumePattern,
        token: Token,
        ctx: FiringContext,
        *,
        net: Net | None = None,
        transition: str | None = None,
    ) -> bool:
        """Whether a token matches a consume pattern's declared type + predicate.

        Shared by the consume-arc candidate filter (`_matching_tokens`) and the
        inhibit zero-test (`_inhibit_satisfied`): both ask the same per-token
        question (right type AND predicate passes), so the logic lives once here.

        ``net`` / ``transition`` thread through to ``_eval_predicate`` for the
        ``predicate_checked`` trace record; the callers inside the binding walk
        pass both, so named predicate handlers get one record per call.
        """
        return token.type == consume.type and self._eval_predicate(
            consume.predicate,
            token,
            ctx,
            net=net,
            transition=transition,
        )

    def _matching_tokens(
        self,
        arc: Arc,
        marking: Marking,
        ctx: FiringContext,
        *,
        net: Net | None = None,
        transition: str | None = None,
    ) -> list[Token]:
        """Tokens in the arc's source place matching its type + predicate.

        Insertion (index) order preserved — the basis for lexicographic
        binding selection.
        """
        consume = arc.consume
        assert consume is not None
        place = arc.from_place
        assert place is not None
        return [
            tok
            for tok in marking.get(place, [])
            if self._token_matches(consume, tok, ctx, net=net, transition=transition)
        ]

    def _arc_candidates(
        self,
        arc: Arc,
        marking: Marking,
        ctx: FiringContext,
        *,
        net: Net | None = None,
        transition: str | None = None,
    ) -> list[tuple[Token, ...]] | None:
        """Weight-combos of matching tokens for one binding arc, or None if
        the arc is unsatisfiable.

        The per-arc satisfiability probe, shared by consume- and read-mode arcs
        (both need ``weight`` matching tokens present): the arc needs at least
        ``weight`` tokens of the declared type passing its predicate. Its
        candidate bindings are the lexicographic ``weight``-combinations of
        those matching tokens, in index order — the per-arc input to the
        cartesian product in ``_binding_candidates``. A read arc is satisfied the
        same way; only firing differs (its tokens are not removed).

        References: spec/firing-semantics.md (§a C1); ADR 0012.
        """
        matching = self._matching_tokens(arc, marking, ctx, net=net, transition=transition)
        assert (
            arc.consume is not None
        )  # _arc_candidates is called only on consume/read arcs.
        weight = arc.consume.weight
        if len(matching) < weight:
            return None
        return list(combinations(matching, weight))

    def _input_arcs(self, net: Net, transition: str, mode: str) -> tuple[Arc, ...]:
        """Input arcs of ``transition`` in ``mode``, in declaration order."""
        return self._topology(net).input_arcs.get((transition, mode), ())

    def _binding_arcs(self, net: Net, transition: str) -> tuple[Arc, ...]:
        """Consume/read input arcs of ``transition``, in declaration order."""
        return self._topology(net).binding_arcs.get(transition, ())

    def _produce_arcs(self, net: Net, transition: str) -> tuple[Arc, ...]:
        """Produce arcs of ``transition``, in declaration order."""
        return self._topology(net).produce_arcs.get(transition, ())

    def _inhibit_satisfied(
        self, net: Net, transition: str, marking: Marking, ctx: FiringContext
    ) -> bool:
        """All UNCORRELATED inhibit arcs of ``transition`` pass their zero-test.

        An inhibit arc gates enablement on emptiness: it is satisfied iff NO
        token in its source place matches the arc's declared type + predicate.
        A single matching token on any inhibit arc fails the whole transition.
        Inhibit arcs consume nothing and never appear in a binding.

        Correlated inhibit arcs (``correlate`` set, ADR 0017) are skipped
        here: their zero-test references the candidate binding, so they are
        evaluated per binding by ``_correlated_inhibit_satisfied`` inside
        ``_binding_candidates``' enumeration — this early whole-place check
        covers only the binding-independent (uncorrelated) arcs, keeping
        their cheap pre-binding evaluation unchanged.

        References: spec/firing-semantics.md (a, D7); ADR 0017.
        """
        for arc in self._input_arcs(net, transition, "inhibit"):
            consume = arc.consume
            place = arc.from_place
            assert consume is not None and place is not None
            if consume.correlate is not None:
                continue  # per-binding zero-test, evaluated in _binding_candidates
            if any(
                self._token_matches(consume, tok, ctx) for tok in marking.get(place, [])
            ):
                return False
        return True

    def _binding_correlates_hold(
        self,
        net: Net,
        transition: str,
        combo: tuple[tuple[Token, ...], ...],
        binding_arcs: Sequence[Arc],
        binding: dict[str, list[Token]],
    ) -> bool:
        """Every correlated consume/read arc's bound tokens satisfy its
        ``correlate`` against the whole candidate ``binding`` (ADR 0030).

        Arcs are checked in declaration order and each arc's ``weight``
        tokens in bound order. Each token is evaluated over ``{token: <that
        token's data>, binding: <place-keyed bound-token data>}``. The binding
        is the complete candidate — every consume and read arc, this arc's own
        tokens included — so the order of the checks never changes the
        result; it only fixes which check stops first.

        Only exact ``true`` passes. An eval error or a non-boolean result
        fails CLOSED and rejects the binding: the arc's join is unproven, so
        the token may not be bound (D6's degrade-toward-not-enabled posture).

        References: spec/firing-semantics.md (a); ADR 0017; ADR 0030.
        """
        binding_data: dict[str, list[dict[str, Any]]] | None = None
        for arc, chosen in zip(binding_arcs, combo):
            consume = arc.consume
            assert consume is not None
            if consume.correlate is None:
                continue
            compiled = self._compile_cel(consume.correlate)
            if binding_data is None:  # built once, shared across arcs
                binding_data = self._cel_binding(net, transition, binding)
            for tok in chosen:
                try:
                    result = self._cel_adapter.eval(  # pyright: ignore[reportUnknownMemberType]
                        compiled, {"token": tok.data, "binding": binding_data}
                    )
                except Exception:  # noqa: BLE001 - eval error rejects the binding (fail-closed)
                    return False
                if result is not True:
                    return False
        return True

    def _correlated_inhibit_satisfied(
        self,
        net: Net,
        transition: str,
        marking: Marking,
        binding: dict[str, list[Token]],
        ctx: FiringContext,
    ) -> bool:
        """All CORRELATED inhibit arcs of ``transition`` pass their per-binding
        zero-test against the candidate ``binding`` (the anti-join, ADR 0017).

        A correlated inhibit arc is satisfied iff NO token in its source place
        — of the declared type, passing the arc's single-token ``predicate``
        (which narrows the correlation candidates) — also satisfies its
        ``correlate`` CEL over ``{token: <candidate data>, binding:
        <place-keyed bound-token data>}``. Any correlated match blocks this
        binding (the caller skips it and advances to the next candidate, so
        the filter never reorders the enumeration).

        A ``correlate`` eval error (missing field, backend raise) fails
        CLOSED: the candidate token is treated as blocking. This is the guard's
        degrade-toward-not-enabled posture (D9), deliberately NOT D6's
        predicate-false rule — on an inhibit test, error-as-false would fail
        open and enable a transition whose safety test crashed.

        Uncorrelated inhibit arcs are not evaluated here; they are handled by
        the early whole-place ``_inhibit_satisfied`` check.

        References: spec/firing-semantics.md (a); ADR 0017.
        """
        binding_data: dict[str, list[dict[str, Any]]] | None = None
        for arc in self._input_arcs(net, transition, "inhibit"):
            consume = arc.consume
            place = arc.from_place
            assert consume is not None and place is not None
            if consume.correlate is None:
                continue  # whole-place zero-test, handled by _inhibit_satisfied
            compiled = self._compile_cel(consume.correlate)
            if binding_data is None:  # built once, shared across arcs
                binding_data = self._cel_binding(net, transition, binding)
            for tok in marking.get(place, []):
                if not self._token_matches(
                    consume, tok, ctx, net=net, transition=transition
                ):
                    continue
                try:
                    result = self._cel_adapter.eval(  # pyright: ignore[reportUnknownMemberType]
                        compiled, {"token": tok.data, "binding": binding_data}
                    )
                except Exception:  # noqa: BLE001 - eval error blocks the binding (fail-closed)
                    return False
                if result is not False:
                    return False
        return True

    def _make_ctx(self, net: Net, transition: str, attempt: int) -> FiringContext:
        """Build the closed four-field firing context for an attempt."""
        return FiringContext(
            firingId=f"{net.name}/{transition}/{attempt}",
            netId=net.name,
            attempt=attempt,
            timestamps=FiringTimestamps(
                fired_at=datetime.now(UTC).isoformat()
            ),
        )

    def _find_transition(self, net: Net, transition: str) -> Transition | None:
        """Look up a transition by name; None if absent (defensive)."""
        return self._topology(net).transition_by_name.get(transition)

    def _cel_binding(
        self, net: Net, transition: str, tokens: Mapping[str, Sequence[Token]]
    ) -> dict[str, list[dict[str, Any]]]:
        """The ``binding`` a transition's CEL sees: bound-token data per key.

        Keyed by place name, or by the transition's ``binding_names`` when it
        declares them (ADR 0032). Two names for one place see the same list.
        """
        tr = self._find_transition(net, transition)
        names = tr.binding_names if tr is not None else None
        if names is None:
            return {pl: [tok.data for tok in toks] for pl, toks in tokens.items()}
        return {
            key: [tok.data for tok in tokens[place]]
            for key, place in names.items()
            if place in tokens
        }

    def _require_transition(self, net: Net, transition: str) -> Transition:
        """Look up a declared transition by name, raising on an unknown name.

        The guard at every public entry point that takes a consumer-supplied
        transition name (``fire``, ``select_binding``): an undeclared name is
        indistinguishable from a declared source transition inside
        ``_binding_candidates`` (both have no binding arcs, so both would yield
        the empty binding), so the declaration check must live here, at the
        name-taking boundary, before any binding work. Navigates ``net``,
        hence an instance method like ``_find_transition``.

        Raises :class:`UnknownTransitionError` when ``transition`` is not
        declared in ``net``.

        References: spec/firing-semantics.md (D10).
        """
        tr = self._find_transition(net, transition)
        if tr is None:
            raise UnknownTransitionError(net.name, transition)
        return tr

    # ── Enablement + binding selection ───────────────────────────────────

    def select_binding(
        self,
        net: Net,
        transition: str,
        marking: Marking,
        *,
        attempt: int = 0,
    ) -> dict[str, list[Token]] | None:
        """Deterministic first-enabled binding, or None if not enabled.

        Returns the FULL binding (consume- and read-mode tokens, keyed by
        source place) that the guard/handler/record see; read tokens are part
        of the binding but are NOT removed on fire (that split lives in
        ``_Binding`` and is applied by ``fire``). Builds the firing context for
        this attempt and delegates to ``_select_binding``. ``fire`` shares one
        context across predicate, guard, and handler evaluation by calling
        ``_select_binding`` directly, so a firing attempt sees a single
        ``firingId`` / ``timestamps`` pair.

        An unknown ``transition`` name (absent from the net's declared
        transitions) raises :class:`UnknownTransitionError` — it must not fall
        into the empty-binding path a declared source transition legitimately
        uses.

        References: ADR 0012.
        """
        self._require_transition(net, transition)
        ctx = self._make_ctx(net, transition, attempt)
        selected = self._select_binding(net, transition, marking, ctx)
        return selected.tokens if selected is not None else None

    def probe_binding(
        self,
        net: Net,
        marking: Marking,
        transition: str,
        *,
        attempt: int,
    ) -> dict[str, list[Token]] | None:
        """Resolve the binding AT ``attempt`` without reserving anything.

        The read-only half of :meth:`reserve`: the same ``_select_binding``
        walk, at the caller's ``attempt``, leaving the marking untouched —
        no consume, no journal record, no restore. Returns the FULL binding
        the firing at that attempt would see (consume- and read-mode tokens,
        per D1), or ``None`` when the transition is not enabled at that
        attempt — including the D9 postures (a raising guard, an unresolved
        guard ref). A checker that needs to judge "which binding would THIS
        attempt select, and is the firing's output determined?" probes here
        instead of ``reserve`` + a private-restore reach-in, because
        ``attempt`` can move the selection (an attempt-branched guard) and
        only a probe at the real attempt judges the set that fires.

        An unknown ``transition`` name raises :class:`UnknownTransitionError`,
        like every name-taking public entry point (D10).

        References: spec/firing-semantics.md (a, D1, D9, D10).
        """
        self._require_transition(net, transition)
        ctx = self._make_ctx(net, transition, attempt)
        selected = self._select_binding(net, transition, marking, ctx)
        return selected.tokens if selected is not None else None

    # ── Binding enumeration ──────────────────────────────────────────────

    def _binding_candidates(
        self,
        net: Net,
        transition: str,
        marking: Marking,
        ctx: FiringContext,
    ) -> Iterator[_CandidateBinding]:
        """THE one binding enumeration: yield each candidate binding and, with
        it, ``why`` it was rejected.

        The single internal walk (ADR 0027) under both binding consumers —
        ``timer_maturities`` used to re-enumerate the product on its own.
        Deterministic order per spec/firing-semantics.md (a, D2); the pure
        gates run in evaluation order:

        1. Walk-level gates (no binding exists to annotate): the timer's clock
           token, the uncorrelated inhibit zero-test, then each binding arc's
           weight-satisfiability. The first failure closes the walk with a
           final ``PER_ARC_MISS`` yield.
        2. The cartesian product of per-arc lexicographic ``weight``-combinations
           (consume- and read-mode arcs in declaration order), each binding
           annotated in order: sub-multiset validity (D1), the consume/read
           correlate join (ADR 0030), the correlated-inhibit anti-join (ADR
           0017), the timer-hold gate (ADR 0018) — a failing
           binding is yielded with its rejection and the walk advances.
        3. A binding passing every pure gate is yielded viable (``rejected`` is
           ``None``). The consumers attach the remaining tests — the possibly
           impure first: the guard (first-success consumer, ADR 0002) and the
           ``timer.maturity`` scheduling expression (first-wake consumer).
        4. A walk whose product never produced a viable binding closes with a
           final ``PRODUCT_MISS`` yield.

        Consumers stop early (lazy): the first-success consumer returns at its
        first accepted binding, abandoning the walk; the first-wake consumer
        returns at the first ``TIMER_HOLD`` rejection. With no binding arcs the
        product is a single empty tuple, so a source transition yields the empty
        binding without a special branch.

        References: spec/firing-semantics.md (a, D1, D2, D9); ADR 0002; ADR
        0012; ADR 0017; ADR 0018; ADR 0027; ADR 0030.
        """
        # Defensive lookup: every current caller reaches here with a declared
        # name (fire/select_binding guard via _require_transition;
        # enabled_transitions iterates net.transitions), so `tr is None` is
        # unreachable today — kept defensive, not asserted, because this
        # private core does not own the name-taking boundary (D10 puts the
        # unknown-name raise at the public entry points, not here).
        tr = self._find_transition(net, transition)

        # Timer (ADR 0018): resolve the clock token before any binding work.
        # An empty clock place means no time reference => not matured => not
        # enabled, regardless of the arcs. The first token in the clock place
        # is the reference (the singleton clock-advance pattern, ADR 0013,
        # keeps it at one in practice).
        timer = tr.timer if tr is not None else None
        clock_data: dict[str, Any] | None = None
        if timer is not None:
            clock_tokens = marking.get(timer.clock, [])
            if not clock_tokens:
                yield _CandidateBinding(None, None, _BindingRejection.PER_ARC_MISS)
                return
            clock_data = clock_tokens[0].data

        # Uncorrelated inhibit arcs gate enablement BEFORE any binding work: a
        # matching token on any such arc fails the whole transition. Correlated
        # inhibit arcs (ADR 0017) reference the candidate binding, so they are
        # deferred to the per-binding check inside the product loop below.
        if not self._inhibit_satisfied(net, transition, marking, ctx):
            yield _CandidateBinding(None, None, _BindingRejection.PER_ARC_MISS)
            return

        binding_arcs = self._binding_arcs(net, transition)

        # Per-arc candidate selections (each a list of weight-tuples), in
        # lexicographic index order so the first is the lowest-index tokens.
        # An unsatisfiable arc (fewer than `weight` matching tokens) means the
        # transition is not enabled.
        per_arc_candidates: list[list[tuple[Token, ...]]] = []
        for arc in binding_arcs:
            cands = self._arc_candidates(arc, marking, ctx, net=net, transition=transition)
            if cands is None:
                yield _CandidateBinding(None, None, _BindingRejection.PER_ARC_MISS)
                return
            per_arc_candidates.append(cands)

        # Cartesian product across binding arcs, in declaration order. With no
        # binding arcs this is a single empty binding (one iteration).
        for combo in product(*per_arc_candidates):
            tokens = Engine._binding_from_combo(combo, binding_arcs)
            consumed = Engine._consumed_from_combo(combo, binding_arcs)
            # When several binding arcs share a source place, the combined
            # bound multiset must be a valid sub-multiset of that place — the
            # same token may not be bound to two arcs (that would let `fire`
            # under-consume and corrupt the marking, and is also the
            # read/consume disjointness rule). Annotated, then advanced past.
            # (D1; ADR 0012.)
            if not self._binding_is_submultiset(tokens, marking):
                yield _CandidateBinding(tokens, consumed, _BindingRejection.SUBMULTISET)
                continue
            # Correlated consume/read arcs (the join, ADR 0030) test their
            # bound tokens against the whole assembled binding, so a
            # correlate sees every other arc's tokens. Pure CEL, so it runs
            # before the correlated inhibits, the timer, and the guard.
            if not self._binding_correlates_hold(
                net, transition, combo, binding_arcs, tokens
            ):
                yield _CandidateBinding(
                    tokens, consumed, _BindingRejection.CORRELATE_MISS
                )
                continue
            # Correlated inhibit arcs (the anti-join, ADR 0017) run their
            # per-binding zero-test here — after the structural sub-multiset
            # check, before the (possibly impure) guard. A blocked binding is
            # annotated, not a reorder: the next candidate in the same
            # enumeration order is tried, so first-surviving selection stays
            # deterministic. An eval error fails closed inside the check.
            if not self._correlated_inhibit_satisfied(
                net, transition, marking, tokens, ctx
            ):
                yield _CandidateBinding(
                    tokens, consumed, _BindingRejection.CORRELATED_INHIBIT
                )
                continue
            # Timer (ADR 0018): evaluated per candidate binding, after the
            # correlated-inhibit zero-test and BEFORE the guard (pure before
            # possibly-impure). An unmatured binding is annotated — not the
            # whole transition — so binding enumeration finds a matured token
            # past an unmatured earlier one, which is what makes per-instance
            # deadline isolation automatic.
            if (
                timer is not None
                and clock_data is not None
                and not self._timer_holds(timer, clock_data, tokens)
            ):
                yield _CandidateBinding(tokens, consumed, _BindingRejection.TIMER_HOLD)
                continue
            # Viable: every pure gate passed. The consumer evaluates the
            # remaining, possibly-impure tests (guard; timer.maturity).
            yield _CandidateBinding(tokens, consumed, None)
        # No combination satisfied the pure-gate constraints.
        yield _CandidateBinding(None, None, _BindingRejection.PRODUCT_MISS)

    def _select_binding(
        self,
        net: Net,
        transition: str,
        marking: Marking,
        ctx: FiringContext,
        choose: BindingChoice | None = None,
    ) -> _Binding | None:
        """Deterministic first-enabled binding core, or None if not enabled.

        The FIRST-SUCCESS consumer of :meth:`_binding_candidates` (ADR 0027):
        resolve the guard once — an unresolved guard ref means the transition
        is not enabled regardless of any binding, before the enumeration's
        pure, side-effect-free gates are consulted — then consume the
        enumeration until the first viable binding the guard accepts. When
        several binding arcs share a source place, the guard-rejected or
        annotation-rejected binding is skipped, never a reorder: the next
        candidate in the same enumeration order is tried, so first-surviving
        selection stays deterministic.

        The returned :class:`_Binding` carries the full bound token set
        (``tokens``, seen by guard/handler/record) and the consume-only subset
        (``consumed``, removed by ``fire``); read-mode tokens appear only in the
        former. A transition with no binding arcs (only inhibit arcs, or a
        source transition) receives the single empty binding from the
        enumeration.

        A guard that raises (an impure guard) degrades to not-enabled — never a
        runtime crash.

        ``choose`` (from :meth:`reserve`) skips viable bindings the caller
        does not want. It runs before the guard, so a possibly impure guard
        is never asked about a binding the caller would discard.

        References: spec/firing-semantics.md (D1, D6, D9); ADR 0002; ADR 0012;
        ADR 0027.
        """
        tr = self._find_transition(net, transition)
        guard: GuardHandler | None = None
        guard_ref = tr.guard if tr is not None else None
        if guard_ref is not None:
            try:
                guard = self.registry.resolve_guard(guard_ref)
            except HandlerNotFound:
                return None  # unresolved guard => not enabled

        for step in self._binding_candidates(net, transition, marking, ctx):
            if step.rejected is not None:
                continue  # annotated rejection — advance to the next candidate
            assert step.tokens is not None and step.consumed is not None
            if choose is not None and not choose(step.tokens):
                continue
            if guard is not None:
                method = getattr(guard, "__qualname__", None)
                try:
                    accepted = guard(
                        GuardHandlerInput(
                            transitionId=transition,
                            inputTokens=step.tokens,
                            firingContext=ctx,
                        )
                    )
                except Exception as exc:
                    # An impure guard that raises degrades to not-enabled,
                    # EXCEPT the replay mixin's own ordering raise (ADR
                    # 0058 Decision 3's catch rule at the guard seam, as
                    # at _serve's): the adapter's own raise is not the
                    # guard's runtime error and propagates out of
                    # ``Engine.fire``. Named by type, imported lazily to
                    # avoid the engine ↔ replay cycle.
                    if type(exc).__name__ == "ReplayOrderError":
                        raise
                    # An impure guard that raises degrades to not-enabled,
                    # symmetric with a predicate handler's runtime error (which
                    # yields predicate false) and an unresolved guard ref
                    # (HandlerNotFound ⇒ not enabled). Never a runtime crash.
                    # (ADR 0002; D9.)
                    self._record_trace(
                        "guard_checked",
                        net=net,
                        ctx=ctx,
                        transition=transition,
                        handler=guard_ref,
                        method=method,
                        result=None,
                        error=_trace_error(exc),
                    )
                    return None
                self._record_trace(
                    "guard_checked",
                    net=net,
                    ctx=ctx,
                    transition=transition,
                    handler=guard_ref,
                    method=method,
                    result=accepted is True,
                )
                if accepted is not True:
                    continue
            # First valid binding (guard absent, or guard accepted): the full
            # bound set plus the consume-only subset `fire` removes.
            return _Binding(tokens=step.tokens, consumed=step.consumed)
        # Walk-level miss (`PER_ARC_MISS`, `PRODUCT_MISS`) — not enabled.
        return None

    @staticmethod
    def _remove_each(available: list[Token], toks: list[Token]) -> bool:
        """Remove each token from ``available`` by equality, counting multiplicities.

        Token is frozen but carries an unhashable ``data`` dict, so multiset
        removal is simulated with ``list.remove`` (equality, not hashing).
        Returns False on the first token absent from ``available`` (leaving
        ``available`` partially mutated); True once every token is removed.
        The shared core of ``_binding_is_submultiset`` (a pre-fire validity
        check) and ``_consume`` (the actual marking mutation): both ask
        "can each bound token be removed once from its source place?".
        """
        for tok in toks:
            try:
                available.remove(tok)
            except ValueError:
                return False
        return True

    @staticmethod
    def _binding_is_submultiset(
        binding: dict[str, list[Token]], marking: Marking
    ) -> bool:
        """Whether each place's bound tokens are a valid sub-multiset of the
        place's current tokens.

        A binding is consumable iff every bound token can be removed from its
        source place by equality, counting multiplicities — the same operation
        ``_consume`` performs via ``_remove_each``. Pure data transform (no
        net/registry/CEL access), hence a ``staticmethod`` like its siblings.
        """
        for place, toks in binding.items():
            if not Engine._remove_each(list(marking.get(place, [])), toks):
                return False
        return True

    @staticmethod
    def _binding_from_combo(
        combo: tuple[tuple[Token, ...], ...], binding_arcs: Sequence[Arc]
    ) -> dict[str, list[Token]]:
        """Group a product-element's per-arc token tuples into a per-place binding.

        ``combo`` is one element of the cartesian product across binding arcs
        (consume- and read-mode, each slot a ``weight``-tuple of tokens for that
        arc, in declaration order). Tokens from arcs sharing a source place are
        concatenated, so the result is the full bound multiset per place —
        including read tokens — the input to the sub-multiset validity check and
        the guard. Pure data transform (no net/registry/CEL access), hence a
        ``staticmethod`` like its siblings (``_remove_each``,
        ``_binding_is_submultiset``).

        References: spec/firing-semantics.md (D1); ADR 0012.
        """
        binding: dict[str, list[Token]] = {}
        for i, arc in enumerate(binding_arcs):
            place = arc.from_place
            assert place is not None
            binding.setdefault(place, []).extend(combo[i])
        return binding

    @staticmethod
    def _consumed_from_combo(
        combo: tuple[tuple[Token, ...], ...], binding_arcs: Sequence[Arc]
    ) -> dict[str, list[Token]]:
        """The consume-only subset of a binding: the tokens ``fire`` removes.

        ``combo`` / ``binding_arcs`` are index-aligned exactly as in
        ``_binding_from_combo``. Read-mode arcs contribute to the full binding
        but are test-without-consume, so they are excluded here; only
        consume-mode arcs' tokens are grouped per source place. ``fire`` removes
        exactly this multiset, leaving read tokens in the marking. With no read
        arcs this equals ``_binding_from_combo``, so the classical case is
        unchanged. Pure data transform, hence a ``staticmethod`` like its
        siblings.

        References: spec/firing-semantics.md (b, D1); ADR 0012.
        """
        consumed: dict[str, list[Token]] = {}
        for i, arc in enumerate(binding_arcs):
            assert arc.consume is not None
            if arc.consume.mode != "consume":
                continue
            place = arc.from_place
            assert place is not None
            consumed.setdefault(place, []).extend(combo[i])
        return consumed

    def enabled_transitions(
        self, net: Net, marking: Marking, *, attempt: int = 0
    ) -> list[str]:
        """Transitions with a satisfiable binding, in declaration order.

        ``attempt`` is threaded to ``select_binding`` so an attempt-sensitive
        guard sees the same attempt the subsequent fire will use.

        References: spec/handler-contract.md; spec/firing-semantics.md (D9).
        """
        enabled: list[str] = []
        for tr in self._candidate_transitions(net, marking):
            ctx = self._make_ctx(net, tr.name, attempt)
            if self._select_binding(net, tr.name, marking, ctx) is not None:
                enabled.append(tr.name)
        return enabled

    def reservations(
        self, net: Net, marking: Marking, *, attempt: int = 0
    ) -> dict[str, list[FiringReservation]]:
        """Every firing ``marking`` admits: each enabled transition, in
        declaration order, with a reservation per binding it can fire with.

        The keys are :meth:`enabled_transitions`. A transition's list holds,
        for each viable binding in enumeration order, the reservation
        :meth:`reserve` makes when ``choose`` accepts just that binding; a
        binding the guard turns away is left out. For a transition without a
        guard this is one walk of the enumeration (ADR 0027). A caller that
        fires every binding, like the prover, would otherwise walk it once
        for ``enabled_transitions``, once to list the bindings, and once
        more per binding to reserve it.

        References: spec/firing-semantics.md (a, D9); ADR 0027.
        """
        found: dict[str, list[FiringReservation]] = {}
        for tr in self._candidate_transitions(net, marking):
            ctx = self._make_ctx(net, tr.name, attempt)
            firings: list[FiringReservation] = []
            if tr.guard is None:
                for step in self._binding_candidates(net, tr.name, marking, ctx):
                    if step.rejected is None:
                        assert step.tokens is not None and step.consumed is not None
                        firings.append(
                            self._reservation(
                                net,
                                marking,
                                tr.name,
                                attempt,
                                ctx,
                                _Binding(tokens=step.tokens, consumed=step.consumed),
                            )
                        )
            elif self._select_binding(net, tr.name, marking, ctx) is not None:
                # The guard sees each binding as ``reserve`` shows it one.
                for step in self._binding_candidates(net, tr.name, marking, ctx):
                    if step.rejected is not None:
                        continue
                    wanted = step.tokens
                    reservation = self.reserve(
                        net,
                        marking,
                        tr.name,
                        attempt=attempt,
                        choose=lambda binding, wanted=wanted: binding == wanted,
                    )
                    if reservation is not None:
                        firings.append(reservation)
            if firings:
                found[tr.name] = firings
        return found

    # ── Enablement explanation ────────────────────────────────────────────

    EXPLAIN_LIMIT = 5
    """How many viable bindings, and distinct messages per gate, an
    :class:`EnablementExplanation` keeps."""

    def explain_enablement(
        self,
        net: Net,
        marking: Marking,
        transition: str,
        *,
        attempt: int = 0,
    ) -> EnablementExplanation:
        """Say why ``transition`` is or is not enabled, with the values.

        The verdict comes from the one binding enumeration and the
        first-success consumer's guard rule, so ``enabled`` and ``binding``
        always agree with :meth:`select_binding`. For each rejection the
        enumeration reports, this method evaluates the rejecting gate again
        on that candidate to name the arc, the token and the values: a
        predicate that is false or failed to evaluate (with the CEL error
        text), a correlate miss, an inhibit or correlated-inhibit hit, a
        timer hold with the clock and bound values, an empty clock place, or
        a named guard with no registered handler.

        Diagnostics only: it re-evaluates pure CEL and may call the guard as
        :meth:`select_binding` would. An unknown name raises
        :class:`UnknownTransitionError`.

        References: ADR 0027; ADR 0030.
        """
        tr = self._require_transition(net, transition)
        ctx = self._make_ctx(net, transition, attempt)
        arc_index = {id(arc): index for index, arc in enumerate(net.arcs)}
        reasons: list[EnablementReason] = []
        messages_by_gate: dict[str, set[str]] = {}

        def add(reason: EnablementReason) -> None:
            messages = messages_by_gate.setdefault(reason.gate, set())
            if reason.message in messages or len(messages) >= self.EXPLAIN_LIMIT:
                return
            messages.add(reason.message)
            reasons.append(reason)

        guard: GuardHandler | None = None
        guard_blocks = False
        if tr.guard is not None:
            try:
                guard = self.registry.resolve_guard(tr.guard)
            except HandlerNotFound:
                guard_blocks = True
                add(
                    EnablementReason(
                        "guard-unresolved",
                        f"guard {json.dumps(tr.guard)} names a handler that is "
                        "not registered, so the transition is not enabled",
                    )
                )

        binding_arcs = self._binding_arcs(net, transition)
        viable: list[Mapping[str, Sequence[Token]]] = []
        chosen: Mapping[str, Sequence[Token]] | None = None
        for step in self._binding_candidates(net, transition, marking, ctx):
            rejected = step.rejected
            if rejected is _BindingRejection.PER_ARC_MISS:
                add(self._explain_walk_miss(net, tr, marking, ctx, arc_index))
                break
            if rejected is _BindingRejection.PRODUCT_MISS:
                break
            assert step.tokens is not None
            if rejected is _BindingRejection.SUBMULTISET:
                add(
                    EnablementReason(
                        "sub-multiset",
                        "the candidate would bind one token to two arcs: "
                        + _binding_text(step.tokens),
                        binding=step.tokens,
                    )
                )
            elif rejected is _BindingRejection.CORRELATE_MISS:
                add(
                    self._explain_correlate_miss(
                        net, transition, binding_arcs, step.tokens, arc_index
                    )
                )
            elif rejected is _BindingRejection.CORRELATED_INHIBIT:
                add(
                    self._explain_correlated_inhibit(
                        net, transition, marking, step.tokens, ctx, arc_index
                    )
                )
            elif rejected is _BindingRejection.TIMER_HOLD:
                assert tr.timer is not None
                add(self._explain_timer_hold(tr.timer, marking, step.tokens))
            else:
                if len(viable) < self.EXPLAIN_LIMIT:
                    viable.append(step.tokens)
                if chosen is None and not guard_blocks:
                    if guard is None:
                        chosen = step.tokens
                    else:
                        try:
                            accepted = guard(
                                GuardHandlerInput(
                                    transitionId=transition,
                                    inputTokens=step.tokens,
                                    firingContext=ctx,
                                )
                            )
                        except Exception as exc:  # noqa: BLE001 - mirrors _select_binding: a raising guard is not-enabled
                            guard_blocks = True
                            add(
                                EnablementReason(
                                    "guard-error",
                                    f"guard {json.dumps(tr.guard)} raised "
                                    f"{type(exc).__name__}: {exc}",
                                    binding=step.tokens,
                                )
                            )
                        else:
                            if accepted is True:
                                chosen = step.tokens
                            else:
                                add(
                                    EnablementReason(
                                        "guard-rejected",
                                        f"guard {json.dumps(tr.guard)} returned "
                                        f"{accepted!r} for "
                                        + _binding_text(step.tokens),
                                        binding=step.tokens,
                                    )
                                )
            if chosen is not None and len(viable) >= self.EXPLAIN_LIMIT:
                break
        return EnablementExplanation(
            transition=transition,
            enabled=chosen is not None,
            binding=chosen,
            viable=tuple(viable),
            reasons=tuple(reasons),
        )

    def _explain_walk_miss(
        self,
        net: Net,
        tr: Transition,
        marking: Marking,
        ctx: FiringContext,
        arc_index: Mapping[int, int],
    ) -> EnablementReason:
        """Name the pre-binding gate behind a ``per-arc-miss``, in walk order."""
        timer = tr.timer
        if timer is not None and not marking.get(timer.clock):
            return EnablementReason(
                "clock-empty",
                f"clock place ({timer.clock}) is empty, so the timer has no "
                "time reference",
                place=timer.clock,
            )
        for arc in self._input_arcs(net, tr.name, "inhibit"):
            consume = arc.consume
            place = arc.from_place
            assert consume is not None and place is not None
            if consume.correlate is not None:
                continue
            for tok in marking.get(place, []):
                if self._token_matches(consume, tok, ctx):
                    return EnablementReason(
                        "inhibit-hit",
                        f"inhibit arc {_arc_text(arc)} forbids "
                        f"{_token_text(tok)}, and ({place}) holds it",
                        place=place,
                        arc=arc_index.get(id(arc)),
                        tokens=(tok,),
                    )
        for arc in self._binding_arcs(net, tr.name):
            consume = arc.consume
            place = arc.from_place
            assert consume is not None and place is not None
            present = list(marking.get(place, []))
            matching = [
                tok for tok in present if self._token_matches(consume, tok, ctx)
            ]
            if len(matching) >= consume.weight:
                continue
            noun = "token" if consume.weight == 1 else "tokens"
            return EnablementReason(
                "arc-short",
                f"arc {_arc_text(arc)} needs {consume.weight} {consume.type} "
                f"{noun}; ({place}) holds {len(matching)} that match, "
                f"of {len(present)}",
                place=place,
                arc=arc_index.get(id(arc)),
                tokens=tuple(present),
                details=tuple(
                    self._token_verdict(consume, tok, ctx) for tok in present
                ),
            )
        raise AssertionError("per-arc-miss without a failing pre-binding gate")

    def _token_verdict(
        self, consume: ConsumePattern, token: Token, ctx: FiringContext
    ) -> str:
        """Why one token does or does not match an arc's color and predicate."""
        text = _token_text(token)
        if token.type != consume.type:
            return f"{text}: color {token.type}, the arc takes {consume.type}"
        predicate = consume.predicate
        if predicate is None:
            return f"{text}: matches"
        if predicate.cel is not None:
            try:
                result = self._cel_adapter.eval(  # pyright: ignore[reportUnknownMemberType]
                    self._compile_cel(predicate.cel), token.data
                )
            except Exception as exc:  # noqa: BLE001 - a diagnostic of the D6 eval-error-is-false rule
                return (
                    f"{text}: predicate `{predicate.cel}` failed to evaluate "
                    f"(counts as false): {exc}"
                )
            if result is True:
                return f"{text}: matches"
            return f"{text}: predicate `{predicate.cel}` is {_cel_value_text(result)}"
        if self._eval_predicate(predicate, token, ctx):
            return f"{text}: matches"
        try:
            self.registry.resolve_predicate(cast(str, predicate.handler))
        except HandlerNotFound:
            return (
                f"{text}: predicate handler {json.dumps(predicate.handler)} is "
                "not registered (counts as false)"
            )
        return f"{text}: predicate handler {json.dumps(predicate.handler)} is false"

    def _explain_correlate_miss(
        self,
        net: Net,
        transition: str,
        binding_arcs: Sequence[Arc],
        tokens: Mapping[str, Sequence[Token]],
        arc_index: Mapping[int, int],
    ) -> EnablementReason:
        """Name the correlated arc and token that rejected this binding."""
        binding_data = self._cel_binding(net, transition, tokens)
        for arc, bound in _arc_slices(binding_arcs, tokens):
            consume = arc.consume
            assert consume is not None
            if consume.correlate is None:
                continue
            for tok in bound:
                env = {"token": tok.data, "binding": binding_data}
                verdict = self._cel_verdict(consume.correlate, env, want=True)
                if verdict is None:
                    continue
                return EnablementReason(
                    "correlate-miss",
                    f"correlate on {_arc_text(arc)} {verdict} for {_token_text(tok)}",
                    place=arc.from_place,
                    arc=arc_index.get(id(arc)),
                    tokens=(tok,),
                    binding=tokens,
                )
        raise AssertionError("correlate-miss without a failing correlate")

    def _explain_correlated_inhibit(
        self,
        net: Net,
        transition: str,
        marking: Marking,
        tokens: Mapping[str, Sequence[Token]],
        ctx: FiringContext,
        arc_index: Mapping[int, int],
    ) -> EnablementReason:
        """Name the inhibit arc and the token that blocked this binding."""
        binding_data = self._cel_binding(net, transition, tokens)
        for arc in self._input_arcs(net, transition, "inhibit"):
            consume = arc.consume
            place = arc.from_place
            assert consume is not None and place is not None
            if consume.correlate is None:
                continue
            for tok in marking.get(place, []):
                if not self._token_matches(consume, tok, ctx):
                    continue
                env = {"token": tok.data, "binding": binding_data}
                verdict = self._cel_verdict(consume.correlate, env, want=False)
                if verdict is None:
                    continue
                return EnablementReason(
                    "correlated-inhibit",
                    f"inhibit arc {_arc_text(arc)}: ({place}) holds "
                    f"{_token_text(tok)}, and its correlate {verdict}",
                    place=place,
                    arc=arc_index.get(id(arc)),
                    tokens=(tok,),
                    binding=tokens,
                )
        raise AssertionError("correlated-inhibit without a blocking token")

    def _explain_timer_hold(
        self,
        timer: Timer,
        marking: Marking,
        tokens: Mapping[str, Sequence[Token]],
    ) -> EnablementReason:
        """Say why the timer does not hold for this binding, with its values."""
        env: dict[str, Any] = {"clock": marking[timer.clock][0].data}
        for var, place in (timer.bind or {}).items():
            env[var] = tokens[place][0].data
        verdict = self._cel_verdict(timer.cel, env, want=True)
        return EnablementReason(
            "timer-hold",
            f"timer {verdict or 'holds'}",
            place=timer.clock,
            tokens=tuple(marking[timer.clock][:1]),
            binding=tokens,
        )

    def _cel_verdict(
        self, expr: str, env: Mapping[str, Any], *, want: bool
    ) -> str | None:
        """``None`` when ``expr`` gives exactly ``want``; otherwise a phrase
        naming the expression, its result or eval error, and the values of
        the fields it selects."""
        try:
            result = self._cel_adapter.eval(self._compile_cel(expr), dict(env))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:  # noqa: BLE001 - diagnostic of the fail-closed / eval-error rules
            outcome = f"failed to evaluate ({exc})"
        else:
            if result is want:
                return None
            outcome = f"is {_cel_value_text(result)}"
        values = _selected_values(expr, env)
        suffix = f" ({values})" if values else ""
        return f"`{expr}` {outcome}{suffix}"

    # ── Firing: consume → invoke → deposit → record ──────────────────────

    @staticmethod
    def _record(
        ctx: FiringContext,
        net: Net,
        transition: str,
        attempt: int,
        status: FiringStatus,
        *,
        input_tokens: dict[str, list[Token]],
        output_tokens: dict[str, list[Token]],
        error: HandlerError | None,
        metadata: dict[str, Any],
    ) -> FiringRecord:
        """Build a ``FiringRecord`` with NO ``sequence``.

        Pure data transform -- it assembles the record from ``ctx`` and
        ``net.name`` without navigating ``net``/``registry``/CEL, hence a
        ``staticmethod`` like its ``_consume``/``_deposit`` siblings.

        References: spec/firing-semantics.md (D4).
        """
        return FiringRecord(
            firingId=ctx["firingId"],
            netId=net.name,
            transition=transition,
            attempt=attempt,
            status=status,
            inputTokens=input_tokens,
            outputTokens=output_tokens,
            error=error,
            metadata=metadata,
            timestamps=ctx["timestamps"],
        )

    def _emit_firing(self, record: FiringRecord) -> None:
        if self.journal is not None:
            self.journal.record_firing(record)

    def _emit_violation(self, record: FiringRecord) -> None:
        if self.journal is not None:
            self.journal.record_deposit_violation(record)

    def _emit_injection(self, record: InjectionRecord) -> None:
        if self.journal is not None:
            self.journal.record_injection(record)

    def _record_trace(
        self,
        event: TraceEvent,
        *,
        net: Net,
        ctx: FiringContext,
        transition: str,
        handler: str | None = None,
        method: str | None = None,
        status: FiringStatus | None = None,
        result: bool | None = None,
        error: HandlerError | None = None,
    ) -> None:
        """Emit one trace record (ADR 0058, Decision 6) when the journal has the hook.

        A no-op when no journal is attached or the journal lacks
        ``record_trace`` — a journal without the capability records exactly
        what it did before. The record carries no tokens (the firing record
        holds them) and no ``sequence`` (the journal numbers records as they
        arrive); a reader joins trace record to firing record on ``firingId``.

        References: spec/firing-semantics.md (d).
        """
        journal = self.journal
        if journal is None or getattr(journal, "record_trace", None) is None:
            return
        journal.record_trace(  # type: ignore[union-attr]
            TraceRecord(
                event=event,
                netId=net.name,
                firingId=ctx["firingId"],
                transition=transition,
                handler=handler,
                method=method,
                at=datetime.now(UTC).isoformat(),
                status=status,
                result=result,
                error=error,
            )
        )

    def _fail(
        self,
        ctx: FiringContext,
        net: Net,
        transition: str,
        attempt: int,
        error: HandlerError | None,
        metadata: dict[str, Any] | None = None,
    ) -> FiringRecord:
        """Build a failed record, emit it through the firing hook, and return it.

        The caller returns its unchanged marking alongside this record (atomic
        rollback — the tentative consume, if any, is discarded).

        Used for the not-enabled, handler-not-found, and handler-``failed``
        branches. The deposit-violation branch is NOT routed here: it emits
        exclusively through ``record_deposit_violation``, never
        ``record_firing``, so each attempt occupies one journal sequence slot.

        References: spec/firing-semantics.md (d).
        """
        record = self._record(
            ctx,
            net,
            transition,
            attempt,
            "failed",
            input_tokens={},
            output_tokens={},
            error=error,
            metadata=metadata or {},
        )
        self._emit_firing(record)
        return record

    @staticmethod
    def _consume(marking: Marking, binding: dict[str, list[Token]]) -> Marking:
        """Tentative consume: a new ``Marking`` with each bound token removed
        once from its source place; untouched places shared structurally.

        Removal uses ``_remove_each`` (Token equality — frozen but unhashable
        ``data``, so simulated multiset removal, matching
        ``_binding_is_submultiset``). The binding per place is exactly the
        multiset consumed from that place across all its arcs, so removing each
        bound token once reproduces the consume. Structural sharing is the
        atomicity seam: on any later failure the caller returns the original
        ``marking`` reference unchanged (it cannot have mutated). The binding
        is pre-validated by ``_binding_is_submultiset``, so removal always
        succeeds here.
        """
        new_marking = marking
        for place, toks in binding.items():
            available = list(marking.get(place, []))
            Engine._remove_each(available, toks)
            new_marking = new_marking.set(place, available)
        return new_marking

    @staticmethod
    def _produce_templates(
        produce_arcs: Sequence[Arc],
    ) -> tuple[ProduceTemplate, ...]:
        """Every produce template in arc declaration order.

        Parallel arcs may share a destination and type.  A tuple preserves
        every declaration without introducing destination-keyed overwrite
        semantics.
        """
        return tuple(cast(ProduceTemplate, arc.produce) for arc in produce_arcs)

    @staticmethod
    def _detect_violation(
        output_tokens: dict[str, list[Token]],
        templates: Sequence[ProduceTemplate],
    ) -> bool:
        """Detect a deposit-contract violation.

        A handler token violates the contract unless some template declares
        its exact destination and type.

        References: spec/firing-semantics.md (D3).
        """
        for dest, toks in output_tokens.items():
            for tok in toks:
                if not any(
                    template.destination == dest and template.type == tok.type
                    for template in templates
                ):
                    return True
        return False

    def _deposit(
        self,
        net: Net,
        transition: str,
        templates: Sequence[ProduceTemplate],
        output_tokens: dict[str, list[Token]],
        binding_tokens: Mapping[str, Sequence[Token]],
    ) -> dict[str, list[Token]]:
        """Deposit per produce template.

        Handler-supplied tokens are preserved once, in handler order.  For
        each declaration-ordered template whose destination/type pair has no
        handler token, literal ``data`` emits one fixed passthrough token and
        ``cel`` (ADR 0023) emits one computed token: the expression evaluated
        over ``{binding: <place-keyed bound-token data>}`` (the ADR 0017
        binding map). An eval error or non-object result, or a deposited
        token outside a declared domain (ADR 0037), raises
        :class:`_DepositError`, which the callers route through the
        deposit-contract-violation handling (D3).

        An instance method, not a ``staticmethod`` like its pure-transform
        siblings (``_consume``, ``_apply_deposit``): evaluating a computed
        fallback resolves CEL through the engine's adapter and compile cache.

        References: spec/net-schema.md (Q3); ADR 0023.
        """
        deposited = {dest: list(toks) for dest, toks in output_tokens.items() if toks}
        binding_data: dict[str, list[dict[str, Any]]] | None = None
        for template in templates:
            handler_tokens = output_tokens.get(template.destination, ())
            if any(tok.type == template.type for tok in handler_tokens):
                continue
            if isinstance(template.data, dict):
                fixed = cast(dict[str, Any], template.data)
                deposited.setdefault(template.destination, []).append(
                    Token(type=template.type, data=deepcopy(fixed))
                )
            elif template.cel is not None:
                if binding_data is None:  # built once, shared across templates
                    binding_data = self._cel_binding(net, transition, binding_tokens)
                try:
                    # One evaluator for the package (ADR 0058, Decision 2):
                    # generated handlers call the same module-level function.
                    result = evaluate_produce_cel(  # pyright: ignore[reportUnknownMemberType]
                        template.cel, binding_data, cel_adapter=self._cel_adapter
                    )
                except Exception as exc:
                    raise _DepositError(
                        f"produce cel into {template.destination!r} failed to "
                        f"evaluate: {error_text(exc)}"
                    ) from exc
                if not isinstance(result, dict):
                    raise _DepositError(
                        f"produce cel into {template.destination!r} must yield "
                        f"a JSON object, got {type(result).__name__}"
                    )
                deposited.setdefault(template.destination, []).append(
                    Token(type=template.type, data=cast("dict[str, Any]", result))
                )
        if net.domains:
            for dest, toks in deposited.items():
                for tok in toks:
                    violation = domain_violation(net, dest, tok)
                    if violation is not None:
                        raise _DepositError(violation)
        return deposited

    @staticmethod
    def _apply_deposit(marking: Marking, deposited: dict[str, list[Token]]) -> Marking:
        """Apply deposited tokens to the marking, returning a new structurally-
        shared ``Marking`` (the deposit phase of ``fire``).

        Each destination's existing tokens are extended with the deposited
        tokens (insertion order preserved); untouched places are shared, not
        copied. Pure data transform (no net/registry/CEL access), hence a
        ``staticmethod`` like ``_consume``. Symmetric with ``_consume``: that
        removes bound tokens per place, this appends deposited tokens per place.
        """
        for dest, toks in deposited.items():
            existing = marking.get(dest, pvector())
            marking = marking.set(dest, existing.extend(toks))
        return marking

    def _handle_violation(
        self,
        ctx: FiringContext,
        net: Net,
        transition: str,
        attempt: int,
        out: TransitionHandlerOutput,
        marking: Marking,
        detail: str | None = None,
    ) -> tuple[Marking, FiringRecord]:
        """Handle a deposit-contract violation per the configured mode.

        The marking is UNCHANGED in every mode (atomic rollback of the
        tentative consume). The violation record routes exclusively through
        ``record_deposit_violation``, never ``record_firing``, so each attempt
        occupies one journal sequence slot. The three modes:

        - ``raise`` — raise :class:`DepositViolation` immediately.
        - ``record_then_raise`` — record the violation, then raise
          :class:`DepositViolation`.
        - ``record_then_drop`` — record the violation and return the original
          marking so the selection loop continues.

        References: spec/firing-semantics.md (D3, d).
        """
        violation_msg = detail or (
            f"transition '{transition}' produced tokens that "
            f"violate its produce contract"
        )
        failed_record = self._record(
            ctx,
            net,
            transition,
            attempt,
            "failed",
            input_tokens={},
            output_tokens={},
            error=HandlerError(type="DepositViolation", message=violation_msg),
            metadata=out.get("metadata", {}),
        )
        if self.deposit_violation == "raise":
            raise DepositViolation(violation_msg)
        # record_then_*: emit through the deposit-violation hook only.
        self._emit_violation(failed_record)
        if self.deposit_violation == "record_then_raise":
            raise DepositViolation(violation_msg)
        # record_then_drop: record and return the original marking.
        return marking, failed_record

    # ── Async-runtime reservation seam ─────────────────────────────────

    def reserve(
        self,
        net: Net,
        marking: Marking,
        transition: str,
        *,
        attempt: int,
        choose: BindingChoice | None = None,
    ) -> FiringReservation | None:
        """Reserve one enabled firing without invoking its transition handler.

        The returned reservation owns the transition's consume-mode tokens;
        read-mode tokens remain in ``reserved_marking`` exactly as they do for
        :meth:`fire`.  No record is emitted until :meth:`settle` receives the
        handler's terminal result.  A caller that keeps several reservations
        live MUST admit only independent footprints: no other live reservation
        may read, consume, or produce into these consumed places.

        ``choose`` narrows the binding: the reservation takes the first
        binding, in the ordinary enumeration order, that passes every gate
        and for which ``choose`` returns ``True``. It cannot make a binding
        viable that the enumeration rejects. A play uses it to pick the
        token a step means (``with``).

        ``None`` means the transition was not enabled at this attempt (or no
        enabled binding passed ``choose``).  Unknown transition names retain
        the public :meth:`fire` / :meth:`select_binding` programmer-error
        behavior.
        """
        self._require_transition(net, transition)
        ctx = self._make_ctx(net, transition, attempt)
        binding = self._select_binding(net, transition, marking, ctx, choose)
        if binding is None:
            return None
        return self._reservation(net, marking, transition, attempt, ctx, binding)

    def _reservation(
        self,
        net: Net,
        marking: Marking,
        transition: str,
        attempt: int,
        ctx: FiringContext,
        binding: _Binding,
    ) -> FiringReservation:
        """The reservation of a selected binding: its consume-mode tokens
        taken out of ``marking``."""
        return FiringReservation(
            net=net,
            original_marking=marking,
            reserved_marking=self._consume(marking, binding.consumed),
            transition=transition,
            attempt=attempt,
            context=ctx,
            input_tokens=binding.tokens,
            consumed_tokens=binding.consumed,
        )

    @staticmethod
    def unreserve(marking: Marking, reservation: FiringReservation) -> Marking:
        """Restore a live reservation's consumed places to their pre-reservation
        state without settling — the public form of the rollback
        :meth:`reserve`/:meth:`settle` use internally. The marking is returned
        byte-for-byte to ``reservation.original_marking``'s consumed places."""
        return Engine._restore_reservation(marking, reservation)

    @staticmethod
    def _restore_reservation(
        marking: Marking, reservation: FiringReservation
    ) -> Marking:
        """Restore each reserved input place to its exact pre-reservation state.

        This is safe when the caller observes :meth:`reserve`'s independent
        footprint rule.  That rule prevents another in-flight firing or source
        update from changing one of these places before settlement, preserving
        the synchronous ``fire`` rollback contract and token insertion order.
        """
        for place in reservation.consumed_tokens:
            marking = marking.set(place, reservation.original_marking.get(place, ()))
        return marking

    def settle(
        self,
        marking: Marking,
        reservation: FiringReservation,
        out: TransitionHandlerOutput,
    ) -> tuple[Marking, FiringRecord]:
        """Commit or roll back a previously reserved asynchronous firing.

        This is the second half of :meth:`reserve`.  It applies the ordinary
        handler-output and deposit contracts, emits exactly one terminal
        firing/deposit-violation record, and returns a new persistent marking.
        A failed result restores the reservation's consumed tokens rather than
        depositing output.  Synchronous :meth:`fire` remains unchanged.
        """
        net = reservation.net
        metadata = out.get("metadata", {})
        if out.get("status") == "failed":
            record = self._record(
                reservation.context,
                net,
                reservation.transition,
                reservation.attempt,
                "failed",
                input_tokens=reservation.input_tokens,
                output_tokens={},
                error=out.get("error"),
                metadata=metadata,
            )
            self._emit_firing(record)
            return self._restore_reservation(marking, reservation), record

        templates = self._produce_templates(
            self._produce_arcs(net, reservation.transition)
        )
        output_tokens = out.get("outputTokens", {}) or {}
        violation_msg: str | None = None
        deposited: dict[str, list[Token]] = {}
        if self._detect_violation(output_tokens, templates):
            violation_msg = (
                f"transition '{reservation.transition}' produced tokens that "
                "violate its produce contract"
            )
        else:
            try:
                deposited = self._deposit(
                    net,
                    reservation.transition,
                    templates,
                    output_tokens,
                    reservation.input_tokens,
                )
            except _DepositError as exc:
                violation_msg = str(exc)
        if violation_msg is not None:
            record = self._record(
                reservation.context,
                net,
                reservation.transition,
                reservation.attempt,
                "failed",
                input_tokens=reservation.input_tokens,
                output_tokens={},
                error=HandlerError(
                    type="DepositViolation",
                    message=violation_msg,
                ),
                metadata=metadata,
            )
            if self.deposit_violation == "raise":
                raise DepositViolation(violation_msg)
            self._emit_violation(record)
            if self.deposit_violation == "record_then_raise":
                raise DepositViolation(violation_msg)
            return self._restore_reservation(marking, reservation), record

        committed = self._apply_deposit(marking, deposited)
        record = self._record(
            reservation.context,
            net,
            reservation.transition,
            reservation.attempt,
            "completed",
            input_tokens=reservation.input_tokens,
            output_tokens=deposited,
            error=None,
            metadata=metadata,
        )
        self._emit_firing(record)
        return committed, record

    def fire(
        self,
        net: Net,
        marking: Marking,
        transition: str,
        *,
        attempt: int,
        strict: bool = False,
    ) -> tuple[Marking, FiringRecord]:
        """Fire one transition: consume → invoke → deposit → record.

        On any failure (not-enabled, handler-not-found, handler-``failed``,
        or a deposit-contract violation under ``record_then_drop``) the
        marking is returned UNCHANGED — atomic rollback of the tentative
        consume. Deposit-violation handling is configurable.

        **Strict** (opt-in, ``strict=True``): a failure raises
        :class:`FailedAttempt` (after the journal got its record) instead of
        returning it, from the exception a ``failed`` handler output carried,
        as a strict :meth:`advance` does; its ``marking`` is ``marking``.

        An unknown ``transition`` name (absent from the net's declared
        transitions) raises :class:`UnknownTransitionError` before any
        binding or firing work — a typo is a programmer bug, not a firing
        outcome; without the guard it would fall into the empty-binding
        path a declared source transition legitimately uses and silently
        execute a handler.

        References: spec/firing-semantics.md (b, e, D3).
        """
        after, record, cause = self._fire(net, marking, transition, attempt=attempt)
        if strict and record["status"] != "completed":
            raise FailedAttempt(net.name, record, marking=after) from cause
        return after, record

    def _fire(
        self,
        net: Net,
        marking: Marking,
        transition: str,
        *,
        attempt: int,
    ) -> tuple[Marking, FiringRecord, BaseException | None]:
        """:meth:`fire`, plus the exception a ``failed`` handler output
        carries (``None`` otherwise): in-process only, never journaled."""
        tr = self._require_transition(net, transition)
        ctx = self._make_ctx(net, transition, attempt)
        binding = self._select_binding(net, transition, marking, ctx)
        if binding is None:
            return (
                marking,
                self._fail(
                    ctx,
                    net,
                    transition,
                    attempt,
                    HandlerError(
                        type="NotEnabled",
                        message=f"transition '{transition}' is not enabled",
                    ),
                ),
                None,
            )

        # Tentative consume of the consume-mode subset only (structural
        # sharing); read-mode tokens stay in the marking (test-without-consume).
        # The original marking is dropped only on success. (ADR 0012.)
        new_marking = self._consume(marking, binding.consumed)

        # Resolve handler. HandlerNotFound is a transition failure, not a crash.
        # `tr` is a declared transition (guaranteed by _require_transition).
        handler_ref = tr.handler
        if handler_ref is None:
            return (
                marking,
                self._fail(
                    ctx,
                    net,
                    transition,
                    attempt,
                    HandlerError(
                        type="HandlerNotFound",
                        message=f"transition '{transition}' has no handler",
                    ),
                ),
                None,
            )
        try:
            handler = self.registry.resolve_transition(handler_ref)
        except HandlerNotFound:
            return (
                marking,
                self._fail(
                    ctx,
                    net,
                    transition,
                    attempt,
                    HandlerError(
                        type="HandlerNotFound",
                        message=f"handler '{handler_ref}' not registered",
                    ),
                ),
                None,
            )

        method = getattr(handler, "__qualname__", None)
        self._record_trace(
            "handler_started",
            net=net,
            ctx=ctx,
            transition=transition,
            handler=handler_ref,
            method=method,
        )
        try:
            out: TransitionHandlerOutput = handler(
                TransitionHandlerInput(
                    transitionId=transition,
                    inputTokens=binding.tokens,
                    firingContext=ctx,
                )
            )
        except Exception as exc:
            # handler_raised: the callable raised OUT of Engine.fire — the
            # Engine's crash behavior is unchanged (no catch: the raise still
            # propagates). (ADR 0058, Decision 6.)
            self._record_trace(
                "handler_raised",
                net=net,
                ctx=ctx,
                transition=transition,
                handler=handler_ref,
                method=method,
                result=None,
                error=_trace_error(exc),
            )
            raise
        self._record_trace(
            "handler_returned",
            net=net,
            ctx=ctx,
            transition=transition,
            handler=handler_ref,
            method=method,
            status=out.get("status"),
            error=out.get("error") if out.get("status") == "failed" else None,
        )

        if out.get("status") == "failed":
            return (
                marking,
                self._fail(
                    ctx,
                    net,
                    transition,
                    attempt,
                    out.get("error"),
                    out.get("metadata", {}),
                ),
                out.get("exception"),
            )

        # status == "completed": deposit per the produce contract.
        templates = self._produce_templates(self._produce_arcs(net, transition))
        output_tokens: dict[str, list[Token]] = out.get("outputTokens", {}) or {}

        if self._detect_violation(output_tokens, templates):
            return (
                *self._handle_violation(ctx, net, transition, attempt, out, marking),
                None,
            )

        try:
            deposited = self._deposit(
                net, transition, templates, output_tokens, binding.tokens
            )
        except _DepositError as exc:
            return (
                *self._handle_violation(
                    ctx, net, transition, attempt, out, marking, detail=str(exc)
                ),
                None,
            )
        new_marking = self._apply_deposit(new_marking, deposited)

        completed_record = self._record(
            ctx,
            net,
            transition,
            attempt,
            "completed",
            input_tokens=binding.tokens,
            output_tokens=deposited,
            error=None,
            metadata=out.get("metadata", {}),
        )
        self._emit_firing(completed_record)
        return new_marking, completed_record, None

    # ── Sandwich-rule validation (opt-in pre-advance seam) ───────────────

    def validate(self, net: Net) -> None:
        """Opt-in pre-advance validation of every net-declared handler ref.

        The sandwich rule: surface a configuration error — a handler referenced
        in the net but unresolvable in the registry — *before* any ``advance``. The
        engine is net-agnostic at construction (``Engine(registry, *, policy,
        ...)`` takes no ``net``), so the net meets the registry for the first
        time at ``advance`` / ``validate``; this seam is the earliest boundary where
        the net exists.

        Walks the net in declaration order and resolves each net-referenced
        handler ref:

        - every transition ``handler`` (when present),
        - every transition ``guard`` (when present), and
        - every consume-arc named predicate ``handler`` (inline CEL predicates
          are compile/eval, not registry-resolved, and are skipped).

        Raises :class:`HandlerNotFound` on the **first** unresolvable ref
        (carrying its ``name``); returns ``None`` on success. Does not mutate
        state, fire, or emit journal records.

        ``advance`` does **not** call this — the sandwich rule is opt-in. The caller
        invokes ``validate(net)`` at a time of their choosing (or not at all);
        ``advance`` retains the locked graceful-degradation contract on the fire path
        (a missing transition handler yields a ``failed`` record, not a raise).
        ``validate`` is the only seam where ``HandlerNotFound`` propagates
        uncaught.

        References: spec/firing-semantics.md (e); operator A1; A4 (ii).
        """
        for tr in net.transitions:
            if tr.handler is not None:
                self.registry.resolve_transition(tr.handler)
            if tr.guard is not None:
                self.registry.resolve_guard(tr.guard)
        for arc in net.arcs:
            if arc.consume is None or arc.consume.predicate is None:
                continue
            pred = arc.consume.predicate
            if pred.handler is not None:
                self.registry.resolve_predicate(pred.handler)

    # ── Environment-arrival seam (consumer token injection) ──────────────

    def inject_token(
        self,
        net: Net,
        marking: Marking,
        place: str,
        token: Token,
        *,
        attempt: int,
        replace: bool = False,
    ) -> tuple[Marking, InjectionRecord]:
        """Inject (or replace) a token in ``place``, recording the event.

        The general **environment-arrival seam** (ADR 0013, as amended): the
        one sanctioned, journaled, replay-deterministic way any external token
        enters a running net between firings — file arrivals, environment
        observations, external events, and clock/deadline tokens alike —
        WITHOUT the consumer reaching into the marking directly. The
        clock/timer case is the seam's motivating origin, and timing still
        enters a net only as token data — the engine never reads a wall clock;
        ``advance``'s ``time=`` mode composes this method with the selection
        loop for native timed transitions (ADR 0018) — but nothing in the
        mechanism is time-specific. This method is the consumer's one write
        primitive:

        - ``replace=False`` (default) — **inject**: append ``token`` to
          ``place`` (the arrival pattern: a new ``deadline`` or observation
          token enables a gated transition).
        - ``replace=True`` — **update**: replace ``place``'s entire contents
          with ``[token]`` (the singleton clock-advance pattern: bump the one
          ``tick``/``clock`` token's ``now``; ``advance``'s ``time=`` mode does
          exactly this). Intended for a place that holds a
          single clock/deadline token.

        Returns the new persistent :class:`Marking` (untouched places shared
        structurally) and the :class:`InjectionRecord`, which is emitted through
        the journal's ``record_injection`` hook (if a journal is attached) as an
        explicit entry sharing the firing sequence stream — so replay stays
        deterministic across injected time. The consumer re-runs
        ``enabled_transitions`` after injecting; this method does not drive the
        loop (that stays the consumer's / ``advance``'s job).

        The token ``type`` is validated against the place's ``accepts`` (an
        unknown place or an unaccepted type is a programmer error →
        :class:`ValueError`), mirroring the deposit contract's type check —
        the seam cannot smuggle an ill-typed token past the net's structure.

        References: spec/firing-semantics.md (f); ADR 0013.
        """
        self._validate_injection(net, place, token)

        existing = list(marking.get(place, []))
        kind: InjectionKind
        if replace:
            kind = "update"
            replaced = existing
            new_marking = marking.set(place, [token])
        else:
            kind = "inject"
            replaced = []
            new_marking = marking.set(place, [*existing, token])

        record = InjectionRecord(
            injectionId=f"{net.name}/@inject/{place}/{attempt}",
            netId=net.name,
            place=place,
            attempt=attempt,
            kind=kind,
            tokens=[token],
            replaced=replaced,
            timestamps=FiringTimestamps(
                fired_at=datetime.now(UTC).isoformat()
            ),
        )
        self._emit_injection(record)
        return new_marking, record

    def inject_tokens(
        self,
        net: Net,
        marking: Marking,
        placements: Sequence[tuple[str, Token]],
        *,
        attempt: int,
    ) -> tuple[Marking, list[InjectionRecord]]:
        """Inject a batch of ``(place, token)`` pairs in one journal-consistent step.

        The batch convenience over :meth:`inject_token` for the arrival
        pattern — several environment tokens land at once (a poll found three
        new observations). Append-only: every placement is an **inject**
        (``kind="inject"``); the singleton clock-advance/replace pattern stays
        on ``inject_token(replace=True)``.

        **All-or-nothing validation**: every placement is validated (unknown
        place, unaccepted token type → :class:`ValueError`) BEFORE any journal
        emission or marking change, so an invalid entry anywhere in the batch
        fails the whole batch with no side effects.

        **Journal shape**: one :class:`InjectionRecord` per token, emitted in
        placement order, so a stream-numbering journal (e.g.
        :class:`JsonlJournal`) gives them consecutive ``sequence`` slots —
        replay-compatible with per-injection tooling. Every record carries the
        batch's ``attempt`` and the unchanged single-injection ``injectionId``
        format; two same-place entries in one batch share an ``injectionId``
        and are disambiguated by ``sequence`` (the journal owns unique
        numbering, D4 — ``injectionId`` is deterministic, not a unique key).

        Returns the new persistent :class:`Marking` and the records in
        placement order.

        References: spec/firing-semantics.md (f); ADR 0013.
        """
        # Validate ALL placements before any journal emission or marking
        # change — the all-or-nothing contract.
        for place, token in placements:
            self._validate_injection(net, place, token)

        # Accumulate each place's additions before touching the persistent
        # marking.  Repeated ``Marking.set`` calls rebuild the outer persistent
        # map and, through ``inject_token``, repeatedly copy the growing
        # per-place vector.  Folding retains placement order within each place
        # while requiring exactly one persistent update per touched place.
        additions: dict[str, list[Token]] = {}
        for place, token in placements:
            tokens = additions.get(place)
            if tokens is None:
                additions[place] = [token]
            else:
                tokens.append(token)

        current = marking
        for place, tokens in additions.items():
            existing = marking.get(place)
            placed = pvector(tokens) if existing is None else existing.extend(tokens)
            current = current.set(place, placed)

        # Records and journal emissions remain per placement and in global
        # input order; only the marking construction above is folded.
        records: list[InjectionRecord] = []
        for place, token in placements:
            record = InjectionRecord(
                injectionId=f"{net.name}/@inject/{place}/{attempt}",
                netId=net.name,
                place=place,
                attempt=attempt,
                kind="inject",
                tokens=[token],
                replaced=[],
                timestamps=FiringTimestamps(
                    fired_at=datetime.now(UTC).isoformat()
                ),
            )
            self._emit_injection(record)
            records.append(record)
        return current, records

    def _validate_injection(self, net: Net, place: str, token: Token) -> None:
        """Validate one injection placement against the net's structure.

        An unknown place, a token ``type`` the place's ``accepts`` rejects,
        or a token outside a declared domain (ADR 0037) is a programmer
        error → :class:`ValueError` — the injection seam cannot smuggle an
        ill-typed token past the net's structure (mirrors the deposit
        contract's checks).
        """
        place_obj = self._topology(net).place_by_name.get(place)
        if place_obj is None:
            raise ValueError(
                f"token injection: net {net.name!r} has no place named {place!r}"
            )
        if token.type not in place_obj.accepts:
            raise ValueError(
                f"token injection: place {place!r} does not accept token type "
                f"{token.type!r} (accepts {place_obj.accepts!r})"
            )
        violation = domain_violation(net, place, token)
        if violation is not None:
            raise ValueError(f"token injection: {violation}")

    @overload
    def advance(
        self,
        net: Net,
        marking: Marking,
        *,
        time: tuple[str, Token] | None = None,
        attempt: int = 0,
        max_steps: int = 1000,
        outputs: None = None,
        strict: bool = False,
    ) -> Marking: ...

    @overload
    def advance(
        self,
        net: Net,
        marking: Marking,
        *,
        time: tuple[str, Token] | None = None,
        attempt: int = 0,
        max_steps: int = 1000,
        outputs: OutputProvider,
        strict: bool = False,
    ) -> AdvanceOutcome: ...

    def advance(
        self,
        net: Net,
        marking: Marking,
        *,
        time: tuple[str, Token] | None = None,
        attempt: int = 0,
        max_steps: int = 1000,
        outputs: OutputProvider | None = None,
        strict: bool = False,
    ) -> Marking | AdvanceOutcome:
        """Fire transitions until quiescence or ``max_steps``.

        Each step: compute enabled transitions, ask the firing policy to pick
        one, fire it. The inner loop's step counter is the firing ``attempt``,
        so firingIds are deterministic across replay runs. Stops when no
        transition is enabled or the policy returns None.

        With ``time=None`` (the default) no time enters the net: this is the
        plain run-to-quiescence.

        With ``time=(place, token)`` the call opens with one
        ``inject_token(replace=True)`` — the singleton clock-advance pattern
        (ADR 0013) — then the same run-to-quiescence, in one call. This is
        the engine-owned re-evaluation loop for timed transitions (ADR 0018,
        ADR 0060). One advance can mature several deadlines; the ordinary
        selection loop fires them all, under the configured firing policy
        (ADR 0014) and failure budget (ADR 0015). The injection and the
        firings share one journal sequence stream, so an advance-driven
        timeline replays deterministically. An unmatured timed transition is
        simply not enabled, so a clock short of every deadline reaches
        quiescence immediately — no spin. ``attempt`` feeds the injection's
        deterministic ``injectionId``; the inner loop numbers its firing
        attempts from its own step counter, as always. Consumers needing
        append-mode injection (a deadline token rather than a clock advance)
        compose ``inject_token`` + ``advance`` directly.

        The enablement probe and the fire share the same ``attempt`` (the step
        counter), so an attempt-sensitive guard sees a consistent attempt.

        **Symbolic advance** (``outputs=``): with an :class:`OutputProvider`
        the loop fires handlerless transitions symbolically — for each
        candidate the provider fills the firing's outputs from the live
        :class:`FiringReservation` (or returns ``None`` to skip the
        transition, no record, which excludes it for the remainder of this
        advance), the policy picks among the determinable candidates, and the
        call returns an :class:`AdvanceOutcome` — the final marking plus, per
        settled firing, its record and the marking that firing alone produced.
        The provider is pure, probed one reservation at a time, and consulted
        afresh at settle time. A settled firing that fails (e.g. a deposit
        violation under ``record_then_drop``) is likewise excluded from the
        remainder of this advance, so a deterministic provider cannot spin;
        the failure budget (below) composes untouched. A handlerless net
        without ``outputs=`` still fails each firing with ``HandlerNotFound`` —
        the provider is what makes the maturation symbolic. Records collected
        into the outcome carry the same ``maturedBy`` stamp as their journaled
        copies when ``time=`` opened the advance. :func:`velocitron_engine.symbolic_outputs`
        is the default provider (the play checker's carry rule).

        **Failure budget** (opt-in, ADR 0015): with ``max_consecutive_failures``
        set, the loop counts each transition's consecutive ``failed`` firings
        (every ``failed`` record ``fire`` returns to this loop counts:
        handler-``failed``, resolve-miss, not-enabled, and a deposit violation
        under ``record_then_drop``). A transition whose count reaches the
        budget is **exhausted** — excluded from the enabled list handed to the
        policy, so selection moves past it. Any ``completed`` firing resets
        every count (the marking changed, so an exhausted transition's inputs
        may differ and it earns fresh retries). When every enabled transition
        is exhausted the advance stops — quiescence-by-exhaustion — instead of
        burning the remaining steps. Counts are scoped to this ``advance``
        call and derived purely from the firing sequence, so replay determinism
        holds; failed fires still advance the step counter, keeping firingIds
        deterministic. The invariant lives on the engine-owned
        :class:`_FailureLedger` — the Runtime's admission loop sits on the same
        ledger rather than re-implementing it. ``fire``/``enabled_transitions``
        primitives are untouched — the budget is a selection concern, like the
        policy.

        **Strict** (opt-in, ``strict=True``): the loop raises
        :class:`Conflict` instead of asking the policy when two or more
        transitions are enabled at once (under the priority policy, two or
        more at the top declared priority), and :class:`FailedAttempt` when an
        attempt fails, instead of retrying it. It is for a net run from a
        projected marking whose choice coverage is proved: a changed net that
        enables two transitions is an error, never a silent pick.

        Returns the final :class:`Marking` when ``outputs`` is ``None`` (the
        shape every existing caller sees), an :class:`AdvanceOutcome` when a
        provider is given.

        References: spec/firing-semantics.md (c, D5, D9, e, f); ADR 0013;
        ADR 0014; ADR 0015; ADR 0018; ADR 0060.
        """
        # Declared Transition.priority per transition (net-static across the
        # advance); the policy input carries the enabled subset each step, keyed
        # by exactly the enabledTransitions entries (absent declaration = 0),
        # so a priority-aware policy needs no access to the net. (ADR 0014.)
        declared_priority = {
            tr.name: tr.priority
            for tr in self._topology(net).transitions
            if tr.priority is not None
        }
        # Per-transition consecutive-failure counts scoped to this advance (ADR
        # 0015): ledgered incrementally per fire, threaded to every policy via
        # consecutiveFailures (absent history = 0) whether or not a budget is
        # configured.
        ledger = self.selection_ledger()

        if outputs is None and time is None:
            return self._advance_loop(
                net, marking, declared_priority, ledger, max_steps, strict=strict
            )

        # With ``time=`` the injection this advance opens with (the clock
        # move) is the origin of every firing the loop then plays: each
        # fired record carries ``maturedBy`` — the injection's deterministic
        # ``injectionId`` — in its ``metadata`` (handler-composable: a
        # handler's own metadata keys are kept, this engine-side key names
        # only the move that matured the firing). A firing asked for another
        # way — a plain ``fire`` call or ``advance`` with ``time=None`` —
        # keeps its records unstamped. The stamp goes onto the emitted
        # records themselves, so a journal attached to this engine sees the
        # same stamped stream the caller gets back.
        matured_by: str | None = None
        if time is not None:
            place, token = time
            current, injection = self.inject_token(
                net, marking, place, token, attempt=attempt, replace=True
            )
            matured_by = injection["injectionId"]
        else:
            current = marking

        firings: list[tuple[FiringRecord, Marking]] = []

        def stamp(
            meta: dict[str, Any],
        ) -> dict[str, Any]:
            if matured_by is None:
                return meta
            return {**meta, "maturedBy": matured_by}

        journal = self.journal
        if journal is not None:
            class _StampingJournal:
                """Stamps every firing record this advance emits, delegating the
                rest of the Journal protocol to the engine's own journal."""

                def record_firing(self, record: FiringRecord) -> None:
                    journal.record_firing(
                        {**record, "metadata": stamp(record["metadata"])}
                    )

                def record_deposit_violation(self, record: FiringRecord) -> None:
                    journal.record_deposit_violation(
                        {**record, "metadata": stamp(record["metadata"])}
                    )

                def record_injection(self, record: InjectionRecord) -> None:
                    journal.record_injection(record)

                def __getattr__(self, name: str) -> Any:
                    return getattr(journal, name)

            self.journal = cast("Journal", _StampingJournal())
        try:
            final = self._advance_loop(
                net,
                current,
                declared_priority,
                ledger,
                max_steps,
                outputs=outputs,
                firings=firings,
                stamp=stamp,
                strict=strict,
            )
        finally:
            self.journal = journal
        if outputs is None:
            return final
        return AdvanceOutcome(final, tuple(firings))

    def _advance_loop(
        self,
        net: Net,
        marking: Marking,
        declared_priority: dict[str, int],
        ledger: _FailureLedger,
        max_steps: int,
        *,
        outputs: OutputProvider | None = None,
        firings: list[tuple[FiringRecord, Marking]] | None = None,
        stamp: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        strict: bool = False,
    ) -> Marking:
        if outputs is None:
            current: Marking = marking
            steps = 0
            while steps < max_steps:
                enabled = ledger.filtered(
                    self.enabled_transitions(net, current, attempt=steps)
                )
                if not enabled:
                    break
                if strict:
                    self._refuse_conflict(net, enabled, declared_priority, current)
                policy_handler = self.registry.resolve_firing_policy(self.policy)
                choice = policy_handler(
                    FiringPolicyInput(
                        marking=current,
                        enabledTransitions=enabled,
                        priorities={
                            name: declared_priority.get(name, 0) for name in enabled
                        },
                        consecutiveFailures=ledger.counts(enabled),
                    )
                )
                if choice is None:
                    break
                current, record, cause = self._fire(
                    net, current, choice, attempt=steps
                )
                ledger.record(choice, record["status"])
                if strict and record["status"] != "completed":
                    raise FailedAttempt(net.name, record, marking=current) from cause
                steps += 1
            return current

        # Symbolic mode: the provider fills each candidate's outputs from a
        # live reservation, or ``None``-skips it — a skip (or a settled
        # failure) excludes the transition for the remainder of this advance,
        # mirroring the play checker's SC303 maturation rule, so a
        # deterministic provider quiesces instead of spinning. Exactly one
        # reservation is live at a time and each probe is released before the
        # next.
        current = marking
        steps = 0
        excluded: set[str] = set()
        collect = firings is not None
        while steps < max_steps:
            enabled = [
                name
                for name in ledger.filtered(
                    self.enabled_transitions(net, current, attempt=steps)
                )
                if name not in excluded
            ]
            if not enabled:
                break

            candidates: list[str] = []
            for name in enabled:
                reservation = self.reserve(net, current, name, attempt=steps)
                if reservation is None:
                    continue
                out = outputs(net, reservation)
                current = self.unreserve(current, reservation)
                if out is not None:
                    candidates.append(name)
                else:
                    excluded.add(name)
            if not candidates:
                break
            if strict:
                self._refuse_conflict(net, candidates, declared_priority, current)

            policy_handler = self.registry.resolve_firing_policy(self.policy)
            choice = policy_handler(
                FiringPolicyInput(
                    marking=current,
                    enabledTransitions=candidates,
                    priorities={
                        name: declared_priority.get(name, 0) for name in candidates
                    },
                    consecutiveFailures=ledger.counts(candidates),
                )
            )
            if choice is None:
                break

            reservation = self.reserve(net, current, choice, attempt=steps)
            if reservation is None:
                excluded.add(choice)
                steps += 1
                continue
            out = outputs(net, reservation)
            if out is None:
                # A pure provider returning None here contradicts its own
                # probe; honor the skip and exclude, like any other.
                excluded.add(choice)
                current = self.unreserve(current, reservation)
                steps += 1
                continue
            current, record = self.settle(reservation.reserved_marking, reservation, out)
            ledger.record(choice, record["status"])
            if record["status"] != "completed":
                if strict:
                    raise FailedAttempt(
                        net.name, record, marking=current
                    ) from out.get("exception")
                excluded.add(choice)
            if collect:
                assert firings is not None
                collected = cast(
                    "FiringRecord",
                    record
                    if stamp is None
                    else {**record, "metadata": stamp(dict(record["metadata"]))},
                )
                firings.append((collected, current))
            steps += 1
        return current

    def _refuse_conflict(
        self,
        net: Net,
        enabled: list[str],
        declared_priority: dict[str, int],
        marking: Marking,
    ) -> None:
        """Raise :class:`Conflict` when the policy would pick among several of
        ``enabled`` in ``marking``: under the priority policy, those at the top
        priority."""
        contenders = enabled
        if self.policy == PRIORITY_FIRING_POLICY:
            top = max(declared_priority.get(name, 0) for name in enabled)
            contenders = [n for n in enabled if declared_priority.get(n, 0) == top]
        if len(contenders) > 1:
            raise Conflict(net.name, contenders, marking=marking)

    def selection_ledger(self) -> _FailureLedger:
        """A fresh ADR 0015 failure ledger bound to this engine's budget.

        The one home for the failure-budget invariant: ``advance`` makes one per
        call (counts scoped to the call), and the long-lived Runtime makes one
        at construction so its admission loop selects against the same
        exhaustion and reset rules instead of keeping its own copy.
        """
        return _FailureLedger(self.max_consecutive_failures)
