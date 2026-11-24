"""Replay one net's recorded run from its journal (ADR 0058, Decision 7).

:class:`ReplayBase` subclasses :class:`velocitron_netbase.VelocitronNet`, the
registration base codegen emits, and :func:`replay_run` drives
:meth:`Engine.fire` from the tape. ``packages/journal`` only folds recorded
effects into a marking, so taking this driver would make the journal fire a
net. ``packages/runtime`` reserves and settles asynchronous handlers and does
not call ``Engine.fire``. ``packages/netbase`` owns the registration base.
This package calls :func:`velocitron_petrinet.parse_net` for the recorded
revision check and injects :func:`velocitron_cel.get_default_adapter` when
the caller does not pass a CEL adapter. It does not import ``velocitron``.

``velocitron_replay`` re-exports this public seam. Generated ``Replay<Net>``
modules import that name.

The tape is the recorded journal's records in sequence order. A
:class:`ReplayCursor` is its one reader: a snapshot of ``journal.records()``
taken before the run. :class:`ReplayBase` is the mixin the generated
``Replay<Net>`` class puts first: it answers every handler call from the
next firing record and every guard or predicate call from the recorded
trace records — the methods underneath are NEVER called. The driver
:func:`replay_run` builds an Engine over the registration's registry,
re-plays every recorded injection at its recorded point, and lets the
Engine fire between them; the tape supplies injections, attempt numbers,
and outputs, while the Engine still chooses which enabled transition to
fire.

Two modes:

- **strict** (default) reproduces the run: the first out-of-order firing
  raises :class:`ReplayOrderError` out of ``Engine.fire`` (the base's
  ``_serve`` seam keeps the adapter's own raises outside the method
  ``try``, ADR 0058 Decision 3), and a recorded net revision whose
  canonical hash differs from the registration raises
  :class:`ReplayNetMismatch` before the first step.
- **compare** runs a changed net or changed handlers against the
  recording and reports the FIRST divergence (a :class:`Divergence` on
  the cursor and on the result) instead of raising; it stops at that
  divergence.

In a composition (N20) the member ``Replay<Net>`` classes do NOT each get
a cursor over their own slice: the tape interleaves the members' records
in merge order, so the composition class owns ONE cursor and hands it to
every member unchanged — never copied, never reset. The helper the
generated ``<Name>Composition`` class emits is
``replay(cursor, *, mode="strict", live=None) -> <Name>Composition`` (the
hand-built composition classes in the composition tests spell it the same
way). The driver accepts the composition's members as a
``Sequence[ReplayBase]``.

The fast check: a ``net_revision`` record the base wrote at registration
compares by ``net_sha256`` against the registered net; ``net_matches`` is
``None`` when the tape carries no net revision (a journal without the
``record_net_revision`` hook — the registration writes the revision only
when the hook exists). Both reference journals write one: a
``DurableJournal`` as a ``net_revision`` event row, a ``JsonlJournal`` as
the document's own keys in the shared stream. The revision is a fast CHECK,
not a refusal: replaying against a changed net works in either mode (N21).

Reading while writing: the cursor reads a snapshot, so the replay Engine
may write to the same journal object or a new one — the snapshot is
immune to the replay run's own writes, and the replay run's trace
records go wherever ``journal`` points. First cut replays ``Engine.advance``
recordings only: a Runtime recording's attempt counter and lanes differ.

Decisions: Q18/Q30/Q35/Q56/Q60 (a), Q50/Q52 (a) with N21's note, Q64
(d); strict-mode-with-live and the attempt-alignment rule are the
single-net card's choices, stated at the relevant definitions; N20's
choices (one owned cursor, divergence on the cursor, the composition
replay shape) are the composition card's.

References: ADR 0058 (Decisions 3 and 7); spec/firing-semantics.md (D4, f).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from velocitron_cel import CelAdapter, get_default_adapter
from velocitron_engine import (
    DEFAULT_FIRING_POLICY,
    Engine,
    FiringPolicyInput,
    Marking,
    Net,
    Token,
    TransitionHandlerOutput,
)
from velocitron_journal import FiringRecord, InjectionRecord
from velocitron_netbase import Registration, VelocitronNet, net_sha256
from velocitron_petrinet import parse_net

__all__ = [
    "Divergence",
    "ReplayBase",
    "ReplayCursor",
    "ReplayNetMismatch",
    "ReplayOrderError",
    "ReplayResult",
    "replay_run",
]


class ReplayOrderError(Exception):
    """Replay answered from the tape but the Engine's call missed its order.

    ``ReplayBase`` reads a handler call's ``firingId`` and asks the cursor
    for the next firing record; when the tape's next firing names another
    id, the cursor raises this — ``expected`` naming the tape's firingId,
    ``got`` naming the call's, and ``sequence`` the tape position where
    they parted. The mixin's own raise sits outside the method ``try``
    (the adapter seam's shape), so it propagates out of ``Engine.fire`` —
    Decision 3's catch rule covers the method call only, and it never
    becomes a ``failed`` firing record (test 9). In compare mode the
    mixin catches it itself and turns it into a ``firing_order``
    divergence instead.

    One exception class covers every strict-mode tape break (Q56 (a):
    reuse the mixin's attribute shape, no sibling classes): an order
    mismatch, an un-re-played injection standing in front of the asked
    firing, an exhausted tape, or a live guard/predicate that answers
    differently in strict mode — the message names which.
    """

    def __init__(
        self, expected: str, got: str, sequence: int, *, owner: str | None = None
    ) -> None:
        self.expected = expected
        self.got = got
        self.sequence = sequence
        self.owner = owner
        message = (
            f"replay asked for {got!r} but the tape's next firing is "
            f"{expected!r} (sequence {sequence})"
        )
        if owner is not None:
            message += f" [tape owned by {owner!r}]"
        super().__init__(message)


class ReplayNetMismatch(Exception):
    """Strict mode only: the recorded net revision differs from the net.

    The tape was recorded under a different revision of this net than
    the registration carries, so the attempts and order could not be
    reproduced faithfully; strict replay refuses before the first step.
    Compare mode does NOT raise — the result reports
    ``net_matches=False`` and runs (N21).
    """


@dataclass(frozen=True)
class Divergence:
    """The first point where the replay parted from the tape.

    - ``kind`` — which seam parted: ``firing_order`` (the Engine chose a
      transition the tape's next firing does not name), ``guard`` /
      ``predicate`` (a live answer differs from the taped one),
      ``not_on_tape`` (the Engine chose a transition the tape never
      fired). ``net`` is never set on a divergence — a net difference
      shows only in ``ReplayResult.net_matches`` (kept in the literal
      for the composition card's exhaustive match).
    - ``sequence`` — the tape position where they parted (``None`` when
      the tape was exhausted).
    - ``expected`` — the tape's answer; ``got`` — the replay's.
    - ``firing_id`` — the firing the divergence attaches to, where one
      applies.
    """

    kind: Literal["firing_order", "guard", "predicate", "not_on_tape", "net"]
    sequence: int | None
    expected: Any
    got: Any
    firing_id: str | None = None


@dataclass(frozen=True)
class TapeAnswer:
    """One resolved trace-record answer, with its tape sequence."""

    value: bool
    sequence: int | None


def _journal_snapshots_are_copies(journal: Any) -> bool:
    """Whether ``journal.records()`` returns detached copies (a
    JsonlJournal's in-memory buffer copies per read), so the same journal
    as snapshot-source and sink cannot race (Q66 (a)).

    Decided here by the journal class NAME string, not a capability
    attribute: only the two core journal kinds exist today. Unknown
    journal classes read as copies, so a third-party journal needing the
    guard must be spelled here explicitly; see the ValueError site.
    """
    return type(journal).__name__ != "DurableJournal"


def _tokens_from_record(tokens: Any) -> list[Token]:
    """A record's serialized ``tokens`` list as :class:`Token` values.

    The snapshot records carry JSON-serialized tokens
    (``{"type": ..., "data": ...}``); already-materialized
    :class:`Token` values pass through unchanged.
    """
    if not tokens:
        return []
    return [
        token
        if isinstance(token, Token)
        else Token(type=token["type"], data=token.get("data", {}))
        for token in tokens
    ]


class ReplayCursor:
    """The one reader of the tape: a snapshot of ``journal.records()``.

    Records identify themselves structurally, not by the journals'
    differing event-kind vocabularies:

    - a **firing** record — has ``firingId`` and ``status`` and neither
      an injection ``kind`` nor a trace ``event``;
    - an **injection** record — has ``injectionId`` (each also has the
      injection ``kind``, ``inject`` or ``update``);
    - a **trace** record (Q52 (a): guards from the tape read the trace
      card's records) — has ``event`` (``guard_checked``,
      ``predicate_checked`` and the other timing events);
    - a **net_revision** record — none of the above (no ``firingId``, no
      ``injectionId``, no ``event``).

    Snapshot discipline: ``__init__`` copies the records once; the
    replay Engine may write to the same journal (or another) while this
    cursor walks the recording's own records.
    """

    def __init__(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        source_journal: Any | None = None,
        owner: str | None = None,
    ) -> None:
        self._records: tuple[dict[str, Any], ...] = tuple(
            dict(record) for record in records
        )
        # The journal the snapshot came from (Q66 (a)): ``replay_run``
        # refuses the same DurableJournal as sink unless the caller opts
        # in; ``None`` when the caller snapshotted the records another
        # way (no identity to check).
        self.source_journal = source_journal
        # The instance that owns the tape (ADR 0058 open item 5: in a
        # composition the composition class owns the cursor, standalone
        # the base). Error messages only — reading never distinguishes;
        # every ``Replay<Member>`` holds one shared instance.
        self.owner = owner
        self.position = 0
        # Compare mode's FIRST divergence (N20): set by whichever member
        # ``ReplayBase`` hit it — one tape, one report — and read there
        # by :func:`replay_run`; strict mode never sets it.
        self.divergence: Divergence | None = None

    @classmethod
    def from_journal(cls, journal: Any, *, owner: str | None = None) -> ReplayCursor:
        """A cursor over ``journal.records()`` NOW, remembering the source.

        The recommended construction: the snapshot is taken before the
        run, and ``replay_run`` can then enforce the Q66 (a) rule.
        ``owner`` stamps the tape's owner (the composition's merged name,
        or the standalone net's) — error messages only.
        """
        return cls(
            journal.records(),
            source_journal=journal,
            owner=owner,
        )

    # ── identity helpers ─────────────────────────────────────────────

    @staticmethod
    def _kind_of(record: Mapping[str, Any]) -> str:
        """Which channel a snapshot record belongs to, by its keys.

        ``event`` covers both trace AND runtime records (each carries one
        event name); both are skipped by the ordering walk — a runtime
        record is a lifecycle note, never a firing or an arrival. The
        ``kind`` vocabulary the journals write is deliberately not
        consulted: payloads differ between journal implementations, keys
        do not.
        """
        if "event" in record:
            return "trace"
        if "injectionId" in record:
            return "injection"
        if "firingId" in record:
            return "firing"
        return "net_revision"

    # ── the read API ─────────────────────────────────────────────────

    def next_firing(self, firing_id: str) -> FiringRecord:
        """The next firing record, advancing the cursor; it MUST name
        ``firing_id``.

        Advances past interleaved trace and net-revision records to the
        next firing record — then orders it: when the firing the tape
        holds next names another id, raise :class:`ReplayOrderError`.
        Replaying against a CHANGED net still works when the order lines
        up — the recorded revision is a fast check, not a refusal
        (N21); the ids here are what the Engine built from its own
        state, and only sequencing is enforced.

        An injection standing un-replayed in front of the asked firing
        means the driver missed its inject step, so it is the same
        ordering break.
        """
        while self.position < len(self._records):
            record = self._records[self.position]
            kind = self._kind_of(record)
            if kind in ("trace", "net_revision"):
                self.position += 1
                continue
            self.position += 1
            if kind == "injection":
                raise ReplayOrderError(
                    expected=f"an injection record ({record['injectionId']})",
                    got=firing_id,
                    sequence=record.get("sequence", self.position - 1),
                    owner=self.owner,
                )
            # kind == "firing"
            if record["firingId"] == firing_id:
                return record  # type: ignore[return-value]
            raise ReplayOrderError(
                expected=record["firingId"],
                got=firing_id,
                sequence=record.get("sequence", self.position - 1),
                owner=self.owner,
            )
        raise ReplayOrderError(
            expected="<tape exhausted>",
            got=firing_id,
            sequence=self._records[-1]["sequence"] + 1 if self._records else 0,
            owner=self.owner,
        )

    def next_guard(self, firing_id: str, ref: str) -> TapeAnswer:
        """The first ``guard_checked`` answer for this firingId + ref.

        Scans at-or-after the cursor WITHOUT advancing: guard checks for
        a firing interleave before its firing record, and the Engine
        re-probes (each ``enabled_transitions`` steps through them), so
        one ref reads only its own records — nothing is consumed, and
        the first matching record at-or-after the cursor is the answer.
        """
        return _require_tape(
            self._scan_trace("guard_checked", firing_id, ref),
            "guard_checked",
            firing_id,
            ref,
            self.position,
            owner=self.owner,
        )

    def next_predicate(self, firing_id: str, ref: str) -> TapeAnswer:
        """The first ``predicate_checked`` answer for this firingId +
        ref. Same at-or-after scan as :meth:`next_guard`."""
        return _require_tape(
            self._scan_trace("predicate_checked", firing_id, ref),
            "predicate_checked",
            firing_id,
            ref,
            self.position,
            owner=self.owner,
        )

    def _scan_trace(self, event: str, firing_id: str, ref: str) -> TapeAnswer | None:
        """The first ``event`` record for firingId and handler ref at or
        after the cursor; ``None`` when absent. Does NOT advance."""
        index = self.position
        while index < len(self._records):
            record = self._records[index]
            if self._kind_of(record) != "trace":
                index += 1
                continue
            if (
                record["event"] == event
                and record.get("firingId") == firing_id
                and record.get("handler") == ref
            ):
                return TapeAnswer(
                    value=record.get("result") is True,
                    sequence=record.get("sequence", index),
                )
            index += 1
        return None

    def pending_injection(self) -> InjectionRecord | None:
        """The next record when it is an injection, else ``None``.

        A trace record never stands between the cursor and an injection
        (the trace records around an injection attribute to earlier and
        later firings, not to the injection itself). A firing record
        first means the run fired again before the next arrival: the
        injection is NOT yet pending, so fire first. A net-revision
        record stands aside (it is read once, by :meth:`net_revision`)
        and is SKIPPED here the same way a trace record is: the base
        wrote it at registration, before the first record of the run,
        so an injection may sit directly after it.
        """
        index = self.position
        while index < len(self._records):
            record = self._records[index]
            kind = self._kind_of(record)
            if kind == "injection":
                return record  # type: ignore[return-value]
            if kind == "firing":
                return None
            index += 1
        return None

    def next_injection(self) -> InjectionRecord:
        """Consume the pending injection: advance the cursor past the
        trace records before it AND the injection record itself."""
        record = self.pending_injection()
        if record is None:
            raise ReplayOrderError(
                expected="an injection record",
                got="the tape holds none pending",
                sequence=self.position,
                owner=self.owner,
            )
        while self.position < len(self._records):
            current = self._records[self.position]
            self.position += 1
            if self._kind_of(current) == "injection":
                return record  # type: ignore[return-value]
        return record  # unreachable: record came from this snapshot's
        # remaining records; the loop always reaches it

    def net_revision(self) -> dict[str, Any] | None:
        """The tape's recorded net document, or ``None`` when absent.

        A ``DurableJournal`` stores it as the ``net_revision`` event kind;
        ``records()`` returns it with ``kind`` attached and the net
        document decoded as the payload. A ``JsonlJournal`` stores the
        document's own keys in the shared stream (``record_net_revision``),
        recognized here by the same key-shape rule every snapshot record is
        classified by. It does NOT advance — the
        ordering walk (``next_firing`` / ``pending_injection``) skips it
        by identity wherever it sits (the base recorded it at
        registration, before the first record of the run).
        """
        for record in self._records:
            if self._kind_of(record) == "net_revision":
                return record
        return None

    def peek_attempt(self) -> int | None:
        """The ``attempt`` of the tape's next firing or injection record,
        or ``None`` when the tape is exhausted.

        The driver aligns each Engine step's attempt to this value without
        consuming anything (the Engine's own attempt counter must be told
        where the recording stood); trace and net-revision records never
        stand between the cursor and the answer.
        """
        index = self.position
        while index < len(self._records):
            record = self._records[index]
            kind = self._kind_of(record)
            if kind in ("firing", "injection"):
                return cast(int, record["attempt"])
            index += 1
        return None


def _require_tape(
    tape: TapeAnswer | None,
    event: str,
    firing_id: str,
    ref: str,
    position: int,
    owner: str | None = None,
) -> TapeAnswer:
    """An answer the tape never recorded is an ordering break.

    The tape recorded every guard/predicate call the original run
    made; one missing now means the replay's walk has already
    diverged (the run is re-probing a part of the state space the
    recording never reached). Strict mode raises
    :class:`ReplayOrderError` with the gap in the message; compare
    mode reports it as a ``guard``/``predicate`` divergence with
    ``expected=None`` instead — call the cursor's ``next_guard`` /
    ``next_predicate`` through the mixin's ``_serve_guard`` /
    ``_serve_predicate`` (which mode-check); the DRIVER calls
    ``next_firing`` / ``pending_injection`` / ``peek_attempt``
    directly.
    """
    if tape is None:
        raise ReplayOrderError(
            expected=f"a {event} record for {firing_id!r} ref {ref!r}",
            got="none on the tape",
            sequence=position,
            owner=owner,
        )
    return tape


# ── The mixin the generated Replay<Net> class puts first ────────────────


class ReplayBase(VelocitronNet):
    """Answers every handler call from the cursor; no method runs.

    The mixin overrides the adapter seams — ``_serve`` for transition
    handlers and the guard/predicate seams the base card's adapters
    reach — so the generated ``Replay<Net>`` class needs nothing of its
    own except the stubs that make it concrete under the abc contract
    (they exist so instantiation passes and are NEVER invoked).

    Strict-mode-with-live is ALLOWED (open point, implementer's choice,
    stated): a live class whose guard or predicate answers DIFFERENTLY
    from the tape raises :class:`ReplayOrderError` in strict mode, the
    kind named in the message (its attribute shape is reused, no
    sibling class). Compare mode never raises on a mismatch: the LIVE
    answer is used and the difference becomes a ``guard`` /
    ``predicate`` divergence — recorded on the SHARED cursor
    (``cursor.divergence``, N20), so a composition's driver sees it
    whichever member set it.
    """

    def __init__(
        self,
        cursor: ReplayCursor,
        *,
        mode: Literal["strict", "compare"] = "strict",
        live: Any | None = None,
        **kwargs: Any,
    ) -> None:
        self.cursor = cursor
        self.mode: Literal["strict", "compare"] = mode
        self.live = live
        # The net base's ``cel_adapter`` and any generated-class kwargs
        # pass through the MRO's next __init__.
        super().__init__(**kwargs)

    # ── the transition-handler seam ──────────────────────────────────

    def _serve(
        self,
        transition: str,
        inp: Mapping[str, Any],
        method: object,
    ) -> TransitionHandlerOutput:
        """Answer from the tape's next firing record; ``method`` is unused
        and uninvoked — no user method ever runs.

        The mixin's own raise (the cursor's :class:`ReplayOrderError`)
        sits in this seam, outside the method ``try`` — exactly the base
        seam's shape — so it propagates out of ``Engine.fire`` and never
        becomes a ``failed`` record (test 9). In compare mode an order
        mismatch sets ``cursor.divergence`` and returns ``failed`` with
        ``error.type = "ReplayDiverged"`` so the Engine leaves the
        marking unchanged; the driver stops after that step.
        """
        del method  # replay never calls the user method
        firing_id = inp["firingContext"]["firingId"]
        record = self._ordered_firing(firing_id)
        if record is None:
            # compare mode only (strict raises inside _ordered_firing):
            # fail the fire — the marking is unchanged — and stop.
            return TransitionHandlerOutput(
                status="failed",
                outputTokens={},
                error={
                    "type": "ReplayDiverged",
                    "message": f"firing {firing_id!r} is not where the tape goes",
                },
                metadata={},
            )
        return self._record_output(record)

    def _record_output(self, record: FiringRecord) -> TransitionHandlerOutput:
        """A firing record as the adapter's output: ``outputTokens``
        merged-keyed EXACTLY as recorded (the base's
        ``_translate_outputs`` is skipped — no local-name translation is
        needed), with each recorded token MATERIALIZED back into a
        :class:`Token` — the tape's payload is the JSON round-trip
        (``{"type": ..., "data": ...}``), and the Engine deposits real
        tokens. A recorded ``failed`` replays failed with its recorded
        ``error``.
        """
        outputs: dict[str, list[Token]] = {}
        for place, tokens in (record.get("outputTokens") or {}).items():
            outputs[place] = _tokens_from_record(tokens)
        return TransitionHandlerOutput(
            status=record["status"],
            outputTokens=outputs,
            error=None if record["status"] == "completed" else record.get("error"),
            metadata=record.get("metadata", {}),
        )

    def _ordered_firing(self, firing_id: str) -> FiringRecord | None:
        """The next firing record when in order; in compare mode a
        divergence instead, and ``None`` (a ``ReplayDiverged`` fire)."""
        try:
            return self.cursor.next_firing(firing_id)
        except ReplayOrderError as error:
            if self.mode == "strict":
                raise
            self.cursor.divergence = Divergence(
                kind="firing_order",
                sequence=error.sequence,
                expected=error.expected,
                got=error.got,
                firing_id=error.got,
            )
            return None

    # ── the guard and predicate seams ────────────────────────────────

    def _serve_guard(
        self, firing_id: str, ref: str, transition: str, inp: Mapping[str, Any]
    ) -> bool:
        """The guard's answer: from the tape (the trace card's
        ``guard_checked`` records read by ``next_guard``), or from
        ``live`` when the mixin was constructed with one."""
        return self._answer(
            kind="guard", firing_id=firing_id, ref=ref, transition=transition, inp=inp
        )

    def _serve_predicate(
        self, firing_id: str, ref: str, inp: Mapping[str, Any]
    ) -> bool:
        """The predicate's answer, the same two sources as the guard's."""
        return self._answer(
            kind="predicate", firing_id=firing_id, ref=ref, transition=None, inp=inp
        )

    def _answer(
        self,
        *,
        kind: Literal["guard", "predicate"],
        firing_id: str,
        ref: str,
        transition: str | None,
        inp: Mapping[str, Any],
    ) -> bool:
        """One reconciliation point for both handler kinds.

        - tape-only: answer from the trace records; a missing record is
          the same class of break as an out-of-order firing
          (:class:`ReplayOrderError`, strict) or a ``guard`` /
          ``predicate`` divergence (compare, ``expected=None`` — the
          Engine's degrade-toward-not-enabled applies).
        - live given: the LIVE answer is used in both modes; in compare
          mode the taped answer is read too and a difference becomes a
          divergence; in strict mode a difference raises
          :class:`ReplayOrderError` (implementer's choice, stated).
        """
        if self.live is not None:
            live_answer = self._call_live(kind, ref, transition, inp)
            tape_answer = self._tape_read(kind, firing_id, ref)
            if isinstance(tape_answer, TapeAnswer) and tape_answer.value != live_answer:
                if self.mode == "strict":
                    raise ReplayOrderError(
                        expected=f"the tape's {kind} answer {tape_answer.value!r}",
                        got=f"live {kind} for {ref!r} answered {live_answer!r}",
                        sequence=tape_answer.sequence or 0,
                    )
                self.cursor.divergence = Divergence(
                    kind=kind,
                    sequence=tape_answer.sequence,
                    expected=tape_answer.value,
                    got=live_answer,
                    firing_id=firing_id,
                )
            elif tape_answer is None and self.mode == "compare":
                # No taped answer for this probe at all: the changed
                # handlers walked somewhere the tape never went.
                self.cursor.divergence = Divergence(
                    kind=kind,
                    sequence=None,
                    expected=None,
                    got=live_answer,
                    firing_id=firing_id,
                )
            return live_answer
        tape_answer = self._tape_read(kind, firing_id, ref)
        if tape_answer is None:
            raise ReplayOrderError(
                expected=f"a {kind}_checked record for {firing_id!r} ref {ref!r}",
                got="none on the tape",
                sequence=self.cursor.position,
            )
        return tape_answer.value

    def _tape_read(
        self, kind: Literal["guard", "predicate"], firing_id: str, ref: str
    ) -> TapeAnswer | None:
        """A trace-record answer, ``None`` when the tape holds none."""
        try:
            return (
                self.cursor.next_guard(firing_id, ref)
                if kind == "guard"
                else self.cursor.next_predicate(firing_id, ref)
            )
        except ReplayOrderError:
            # The cursor's "nothing on the tape" raise collapsed to None;
            # the caller's mode decides what that break is.
            return None

    def _call_live(
        self,
        kind: Literal["guard", "predicate"],
        ref: str,
        transition: str | None,
        inp: Mapping[str, Any],
    ) -> bool:
        """One live guard/predicate call through the live class's own
        wiring (its GUARD_REFS / PREDICATE_REFS tables)."""
        live = self.live
        assert live is not None
        if kind == "guard":
            method_name = live.GUARD_REFS.get(ref)
            if method_name is None:
                raise KeyError(
                    f"live class {type(live).__qualname__} has no guard ref {ref!r}"
                )
            method = getattr(live, method_name)
            # Argument translation: a live VelocitronNet translates
            # through its own binding tables; a plain live object (a
            # test double) receives the adapter's binding directly.
            translate = getattr(live, "_method_arguments", None)
            if translate is not None:
                arguments = translate(transition or inp["transitionId"], inp)
            else:
                input_places = getattr(live, "INPUT_PLACES", {})
                arguments = {
                    place: list(inp["inputTokens"].get(place, []))
                    for place in input_places.get(inp["transitionId"], ())
                }
            return bool(method(**arguments))
        method_name = live.PREDICATE_REFS.get(ref)
        if method_name is None:
            raise KeyError(
                f"live class {type(live).__qualname__} has no predicate ref {ref!r}"
            )
        method = getattr(live, method_name)
        return bool(method(inp["token"]))


@dataclass(frozen=True)
class ReplayResult:
    """What :func:`replay_run` did.

    - ``final_marking`` — the marking at stop.
    - ``net_matches`` — ``None`` when the tape carries no net revision;
      else whether the recorded document hashes equal to the registered
      net (a fast check, never a refusal in compare mode — N21).
    - ``divergence`` — compare mode only: the FIRST divergence, and the
      run stopped there (a member wrote it to the shared cursor; the
      result carries it). Strict mode leaves ``None`` on every path that
      returns.
    - ``steps`` — the fires the driver made through the Engine (a
      ``failed`` fire counts too, matching ``Engine.advance``).
    """

    final_marking: Marking
    net_matches: bool | None
    divergence: Divergence | None
    steps: int


def replay_run(
    net: Net,
    replay: ReplayBase | Sequence[ReplayBase],
    registration: Registration,
    cursor: ReplayCursor,
    *,
    mode: Literal["strict", "compare"] = "strict",
    marking: Marking | None = None,
    journal: Any | None = None,
    policy: str = DEFAULT_FIRING_POLICY,
    max_steps: int = 1000,
    max_consecutive_failures: int | None = None,
    allow_same_journal: bool = False,
    cel_adapter: CelAdapter | None = None,
) -> ReplayResult:
    """Walk the tape: inject what it injected, let the Engine fire between.

    The Engine chooses which enabled transition to fire (the replay
    mixin answers the handler call from the tape); the tape supplies
    the injections, the attempt numbers, and the outputs.

    ``replay`` is one member's mixin (standalone) or the members of a
    composition in alias order (N20): a composition's merged run interleaves
    the members' firings on one tape, so every member shares the ONE
    ``cursor`` and this ONE driver — the divergence is read from the cursor
    (``cursor.divergence``), not from any one instance, so whichever member
    hit it reports it exactly once (the card's other option, reading it
    back from a composition instance, adds a new type for what a sequence
    already says).

    The attempt-alignment rule (the card's reading of "lets the Engine
    fire between injections"): each step aligns the Engine's ``attempt``
    to the NEXT tape firing's ``attempt`` when the next tape record is a
    firing — so the Engine's ``firingId`` line up with the tape's — and
    to the pending injection's own ``attempt`` while injections replay.
    Reviewer confirms.

    Strict mode: a :class:`ReplayOrderError` out of ``Engine.fire``
    (from whichever member the Engine called) propagates out of
    :func:`replay_run`; a recorded revision whose
    hash differs raises :class:`ReplayNetMismatch` before the first
    step. Compare mode: the run stops at the FIRST divergence, which
    the members write to the cursor and the result carries; a transition
    the Engine chose that the tape never fires is ``not_on_tape`` at the
    exhausted tape.

    Reading while writing: the cursor is a snapshot, so ``journal`` may
    be the recording's own journal object or a fresh one — the replay
    run's records (its firings, injections, and traces) go to
    ``journal``, and the tape is never re-read from it.

    ``cel_adapter`` is passed to the Engine. When it is omitted the driver
    uses ``get_default_adapter()``. ``velocitron_engine.Engine`` requires
    an adapter and does not bundle a backend.
    """
    net_copy = registration.net

    # Q66 (a): the SAME DurableJournal instance as snapshot-source AND
    # sink raises unless ``allow_same_journal=True``. The gate is on
    # journal identity (the cursor carries the journal object it snapshotted
    # in ``source_journal`` when built from ``records()``; ``None`` when
    # the caller built the cursor from records it read another way). A
    # DurableJournal's ``records()`` re-reads sqlite live, so its
    # snapshot is NOT immune to the replay's writes; a JsonlJournal's
    # ``records()`` is a fresh copy of an in-memory buffer, so the same
    # journal as both is fine (the snapshot is a copy).
    if (
        journal is not None
        and not allow_same_journal
        and cursor.source_journal is journal
        and not _journal_snapshots_are_copies(journal)
    ):
        raise ValueError(
            "the same DurableJournal instance is both the replay's "
            "snapshot source and its sink; pass allow_same_journal=True "
            "to opt in (the snapshot must have been taken before the run)"
        )
    registry = registration.registry
    if registry is None:
        raise ValueError(
            "replay_run requires the registration's registry; "
            "register_into and build_registry attach the registry the "
            "Engine and the replay driver share"
        )
    engine = Engine(
        registry,
        journal=journal,
        policy=policy,
        max_consecutive_failures=max_consecutive_failures,
        cel_adapter=(cel_adapter if cel_adapter is not None else get_default_adapter()),
    )
    current = (
        marking
        if marking is not None
        else (
            net_copy.initial_marking
            if net_copy.initial_marking is not None
            else Marking()
        )
    )

    # The fast check: the tape's net revision against the registration's
    # net. The revision is a fast CHECK, not a refusal (N21): strict
    # raises ReplayNetMismatch before the first step on a DIFFERENT
    # hash; compare records the difference (net_matches=False) and runs.
    revision = cursor.net_revision()
    net_matches: bool | None = None
    if revision is not None:
        # The record payload may carry the journal's own metadata keys
        # (DurableJournal's kind/sequence/recorded_at); strip them —
        # parse_net validates shape, not provenance.
        document = {
            key: value
            for key, value in revision.items()
            if key not in ("kind", "sequence", "recorded_at")
        }
        try:
            recorded_hash = net_sha256(parse_net(document))
        except Exception:  # noqa: BLE001 - an unreadable revision is a mismatch, not a crash
            recorded_hash = None
        net_matches = recorded_hash == net_sha256(net_copy)
        if not net_matches and mode == "strict":
            raise ReplayNetMismatch(
                "the tape was recorded under a different revision of "
                f"{net_copy.name!r} than the registration carries"
            )

    divergence: Divergence | None = None
    steps = 0
    ledger = engine.selection_ledger()
    while steps < max_steps:
        # 1. Replay every pending injection at its recorded point: the
        #    recorded ``kind`` maps to ``Engine.inject_token``'s
        #    ``replace`` (an ``update`` is the replacement), each recorded
        #    token injected under the record's own ``attempt``.
        while (injection := cursor.pending_injection()) is not None:
            for token in _tokens_from_record(injection["tokens"]):
                current, _ = engine.inject_token(
                    net_copy,
                    current,
                    injection["place"],
                    token,
                    attempt=injection["attempt"],
                    replace=injection["kind"] == "update",
                )
            cursor.next_injection()

        # 2. The next tape record decides the attempt (the alignment
        #    rule) and whether anything awaits the Engine at all: a
        #    firing means one more fire is on the tape; nothing
        #    (exhausted tape) ends the run.
        tape_attempt = cursor.peek_attempt()
        if tape_attempt is None:
            break

        # 3. Enabled under the tape's attempt (the alignment rule),
        #    filtered through the driver's own failure ledger exactly as
        #    ``Engine.advance`` filters its loop's list — a replayed ``failed``
        #    fire counts, so a replay with a budget walks like the
        #    recording's run did.
        enabled = ledger.filtered(
            engine.enabled_transitions(net_copy, current, attempt=tape_attempt)
        )
        if not enabled:
            break  # the recording had nothing enabled here either (or it
            # stopped by policy); the tape's remaining records would have
            # fired — this is quiescence, not a divergence the compare
            # mode reports (the tape cannot force the Engine to fire a
            # transition whose binding is unsatisfiable).

        # 4. The Engine's own policy (Q64 (d)): the policy chooses.
        policy_handler = engine.registry.resolve_firing_policy(policy)
        choice = policy_handler(
            FiringPolicyInput(
                marking=current,
                enabledTransitions=enabled,
                priorities={
                    transition.name: transition.priority or 0
                    for transition in net_copy.transitions
                },
                consecutiveFailures=ledger.counts(enabled),
            )
        )
        if choice is None:
            break

        # 5. Fire through the mixin: the outputs come from the tape.
        current, record = engine.fire(net_copy, current, choice, attempt=tape_attempt)
        ledger.record(choice, record["status"])
        steps += 1

        # 6. Compare mode stops at the FIRST divergence (the members
        #    write it to the cursor — firing_order, guard, or predicate —
        #    so whichever member hit it, it is visible here).
        if mode == "compare" and cursor.divergence is not None:
            divergence = cursor.divergence
            break

    if divergence is None and cursor.divergence is not None:
        # A divergence the run discovered AFTER its last fire (the tape
        # ended mid-ordering): report it.
        divergence = cursor.divergence
    return ReplayResult(
        final_marking=current,
        net_matches=net_matches,
        divergence=divergence,
        steps=steps,
    )
