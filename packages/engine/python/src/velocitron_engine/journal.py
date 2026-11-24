"""Journal record shapes the firing engine emits.

This module is the source of truth for the record shapes. ``JsonlJournal``, tape replay,
and sqlite durability ship in ``velocitron_journal``. This module does not
import ``velocitron``.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from .contract import FiringTimestamps, HandlerError
from .schema import Token

# ── Event-log kinds ──────────────────────────────────────────────────────

# The event-log vocabulary (spec/firing-semantics.md D4; ADR 0022). Firing and
# injection carry marking effects; a deposit violation is a failed firing (no
# effect); a net revision is definitional, so the log is self-describing and a
# consumer can recover the net that produced it. A trace is a
# timing/observability record (ADR 0058, Decision 6). The four non-effect
# kinds are skipped by :func:`replay_events`, which reads only FIRING and
# INJECTION.
FIRING = "firing"
DEPOSIT_VIOLATION = "deposit_violation"
INJECTION = "injection"
NET_REVISION = "net_revision"
TRACE = "trace"


# ── FiringRecord ─────────────────────────────────────────────────────────


# The two terminal firing statuses. "pending" is v2.
# spec/firing-semantics.md
FiringStatus = Literal["completed", "failed"]


class FiringRecord(TypedDict):
    """What the engine emits per firing attempt.

    The engine fills every field here except ``sequence`` — the journal
    implementation owns unique-id numbering. This record is a plain
    ``TypedDict``, so callers may construct it directly.

    References: spec/firing-semantics.md (D4).
    """

    firingId: str
    netId: str
    transition: str
    attempt: int
    status: FiringStatus
    inputTokens: dict[str, list[Token]]
    outputTokens: dict[str, list[Token]]
    error: HandlerError | None
    metadata: dict[str, Any]
    timestamps: FiringTimestamps


# The two injection kinds. "inject" appends a token to a place; "update"
# replaces a place's contents (the singleton clock/deadline-advance pattern).
# spec/firing-semantics.md (f); ADR 0013.
InjectionKind = Literal["inject", "update"]


class InjectionRecord(TypedDict):
    """What the engine emits per token injection (any environment arrival).

    A consumer-driven marking event — NOT a firing — recorded so replay stays
    deterministic across injected tokens: the environment arrivals (file
    arrivals, observations, clock/deadline tokens; ADR 0013, as amended) a
    runtime wrapper injects between firings. Like :class:`FiringRecord` it carries no
    ``sequence`` (the journal owns numbering) and its ``timestamps`` are
    metadata-only (excluded from replay comparison).

    - ``injectionId`` — deterministic id, ``<netId>/@inject/<place>/<attempt>``,
      distinct from a firing's ``firingId`` (the ``@inject`` marker).
    - ``attempt`` — the injection attempt counter as a first-class field
      (also embedded in ``injectionId``), so replay tooling reads it directly
      instead of parsing the id.
    - ``kind`` — ``"inject"`` (token appended) or ``"update"`` (place replaced).
    - ``tokens`` — the token(s) now present by this injection.
    - ``replaced`` — the token(s) an ``"update"`` removed (empty for ``"inject"``).

    References: spec/firing-semantics.md (f); ADR 0013.
    """

    injectionId: str
    netId: str
    place: str
    attempt: int
    kind: InjectionKind
    tokens: list[Token]
    replaced: list[Token]
    timestamps: FiringTimestamps


# ── Runtime lifecycle records ───────────────────────────────────────────


RuntimeEvent = Literal["source_failed", "suppressed"]


class RuntimeRecord(TypedDict):
    """A lifecycle event outside the Petri-net firing/injection contract.

    Runtime records are intentionally a separate channel: a detached worker's
    late result was suppressed, so presenting it as another firing would make
    replay incorrectly apply a second terminal outcome.  The journal owns its
    sequence in the same way it owns firing and injection records.
    """

    event: RuntimeEvent
    netId: str
    firingId: str | None
    source: str | None
    detail: str


@runtime_checkable
class RuntimeJournal(Protocol):
    """Optional journal capability used by :class:`velocitron_runtime.Runtime`."""

    def record_runtime(self, record: RuntimeRecord) -> None: ...


# ── Trace records ────────────────────────────────────────────────────────


# The six trace events. "tokens_reserved" is Runtime-only; the rest are
# Engine-side. spec/firing-semantics.md (d); ADR 0058, Decision 6.
TraceEvent = Literal[
    "tokens_reserved",
    "handler_started",
    "handler_returned",
    "handler_raised",
    "guard_checked",
    "predicate_checked",
]


class TraceRecord(TypedDict):
    """A timing/observability record (OpenTelemetry sense), not a causal one.

    The Engine and Runtime emit these at six points when the attached journal
    carries the :class:`TraceJournal` capability. The record carries NO
    ``sequence`` (the journal owns numbering) and NO tokens
    (:class:`FiringRecord.inputTokens` already holds them). A reader joins a
    trace record to its firing record on ``firingId`` — never on ``sequence``,
    because "handler started" is written before the firing record exists.

    - ``handler`` — the ref the Engine resolved (the transition ``handler``,
      the ``guard``, or the predicate ``handler`` string); ``None`` only when
      no ref applies.
    - ``method`` — the callable's ``__qualname__`` when present
      (``getattr(handler, "__qualname__", None)``); informational.
    - ``status`` — for ``handler_returned``: the output's status.
    - ``result`` — for ``guard_checked`` / ``predicate_checked``: the answer.
    - ``error`` — the :class:`HandlerError` when a callable raised.

    References: spec/firing-semantics.md (d); ADR 0058, Decision 6.
    """

    event: TraceEvent
    netId: str
    firingId: str
    transition: str
    handler: str | None
    method: str | None
    at: str
    status: FiringStatus | None
    result: bool | None
    error: HandlerError | None


@runtime_checkable
class TraceJournal(Protocol):
    """Optional trace capability (ADR 0058, Decision 6).

    A journal implementing :class:`Journal` MAY also implement this; the
    Engine and Runtime call :meth:`record_trace` only when the attached
    journal has the hook. A journal without it records exactly what it did
    before — trace emission is invisible to it.
    """

    def record_trace(self, record: TraceRecord) -> None: ...


# ── Journal hook protocol ────────────────────────────────────────────────


@runtime_checkable
class Journal(Protocol):
    """The hook protocol the engine emits records through.

    The engine holds a ``Journal | None`` and calls these methods only when a
    journal is attached. Any class implementing all three methods satisfies it.

    ``record_injection`` is the third hook channel (alongside ``record_firing``
    and ``record_deposit_violation``): the engine routes a token injection
    (any environment arrival — clock/deadline tokens included) exclusively
    through it, never through ``record_firing`` (an injection is not a
    firing). A journal that numbers all channels from one stream (e.g.
    :class:`JsonlJournal`) gives injections and firings a single monotonic
    sequence so replay is deterministic across injected tokens.

    References: spec/firing-semantics.md (D4, f).
    """

    def record_firing(self, record: FiringRecord) -> None: ...

    def record_deposit_violation(self, record: FiringRecord) -> None: ...

    def record_injection(self, record: InjectionRecord) -> None: ...


