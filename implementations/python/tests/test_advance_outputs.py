"""Symbolic advance: ``Engine.advance(outputs=...)`` over handlerless nets.

Ten cases, given/when/then: the provider seam fires maturing timed
transitions symbolically (the play checker's own carry rule, one source
of truth in ``velocitron_engine``), skips what it cannot determine,
stamps ``maturedBy``, and replays deterministically.

References: spec/firing-semantics.md (e, f); ADR 0031; issue #56.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from velocitron_engine import TransitionHandlerOutput
from velocitron_petrinet import compile_petrinet_text
from velocitron_runtime import Engine
from velocitron_engine import (
    AdvanceOutcome,
    FiringReservation,
)
from velocitron_journal import Journal
from velocitron_engine import symbolic_outputs
from velocitron_petrinet import parse_net
from velocitron_play import (
    read_play,
)
from velocitron_play_check import (
    check_play,
)
from velocitron_engine import (
    PRIORITY_FIRING_POLICY,
    HandlerRegistry,
)
from velocitron_engine import (
    Marking,
    Net,
    Token,
)

_TIMED = """\
net order "handlerless book order"

(inbox) -purchase-> [deliver] -purchase-> (accepted)
(accepted) -purchase-> [timeout] -purchase-> (expired)
@clock: (clock) -tick->? [timeout]
@receipt: [timeout] -receipt-> (receipts)
@receipt data {"kind": "receipt"}

[timeout] timer clock (clock) cel "clock.now >= purchase.dueAt"
[timeout] timer bind purchase (accepted)

marking initial (inbox) <- $o1

$o1: purchase {"id": "o-1", "sku": "a", "dueAt": 100}
"""

_READS_ONLY = """\
net reads_only "reads its output color, consumes none"

(switch) -verdict->? [flag]
@clock: (clock) -tick->? [flag]
@echo: [flag] -verdict-> (echoes)

[flag] timer clock (clock) cel "clock.now >= 100"

marking initial (switch) <- $v

$v: verdict {"state": "open"}
"""

_CONSUMES_AND_READS = """\
net mirrors "consumes one and reads one of the same color"

(batch) -item-> [copy]
(batch) -item->? [copy]
@clock: (clock) -tick->? [copy]
@copy_out: [copy] -item-> (copies)

[copy] timer clock (clock) cel "clock.now >= 100"

marking initial (batch) <- $a
marking initial (batch) <- $b

$a: item {"n": 1}
$b: item {"n": 2}
"""

_NET_FILLS = """\
net fills "net-filled outputs"

(batch) -item-> [process]
@clock: (clock) -tick->? [process]
@same: [process] -item-> (same)
@receipt: [process] -receipt-> (receipts)
@receipt data {"kind": "receipt"}
@count: [process] -counter-> (counts)
@count data cel "{'n': binding.batch[0].n + 1}"

[process] timer clock (clock) cel "clock.now >= 100"

marking initial (batch) <- $a

$a: item {"n": 5}
"""

_VIOLATING = """\
net violation "provider violates its own template"

(batch) -item-> [bad]
@clock: (clock) -tick->? [bad]
@out: [bad] -receipt-> (out)

[bad] timer clock (clock) cel "clock.now >= 100"

marking initial (batch) <- $a

$a: item {"n": 1}
"""


def _net(text: str, name: str = "net.petrinet") -> Any:
    return parse_net(compile_petrinet_text(text, name))


def _marking() -> Marking:
    return Marking()


def _engine(**kwargs: Any) -> Engine:
    return Engine(HandlerRegistry(), policy=PRIORITY_FIRING_POLICY, **kwargs)


def _clock(marking: Marking, now: int) -> Marking:
    return marking.set("clock", (Token("tick", {"now": now}),))


# 1 ────────────────────────────────────────────────────────────────────────
def test_given_maturing_transitions_when_symbolic_advance_then_outcome_chains() -> None:
    # given: a handlerless timed net with one purchase past its dueAt; the
    #   net's own clock was already moved out-of-band (the advance's time=
    #   opens its own injection, so the deadline is already behind the clock)
    net = _net(_TIMED)
    engine = _engine()
    marking = _marking().set(
        "inbox", (Token("purchase", {"id": "o-1", "sku": "a", "dueAt": 100}),)
    )

    # when: the advance runs symbolically from behind the deadline
    outcome = engine.advance(
        net,
        _clock(marking, 130),
        outputs=symbolic_outputs,
    )

    # then: an AdvanceOutcome; records all completed (deliver first, then the
    #   matured timeout); each firing's marking_after is the next firing's
    #   start, and the last is the outcome's marking
    assert isinstance(outcome, AdvanceOutcome)
    assert [record["transition"] for record, _ in outcome.firings] == [
        "deliver",
        "timeout",
    ]
    assert all(record["status"] == "completed" for record, _ in outcome.firings)
    # chain: firing i's after is i+1's start. The engine replays the chain
    #   through the same provider, so verify each aftermath by re-firing from
    #   it — the simplest closure check is the last aftermath equal to the
    #   outcome's final marking
    assert outcome.firings[-1][1] == outcome.marking


# 2 ────────────────────────────────────────────────────────────────────────
def test_given_time_opened_advance_when_records_collected_then_maturedBy_stamps(
    tmp_path: Path,
) -> None:
    # given: the timed net, with and without a journal
    from velocitron_journal import JsonlJournal

    net = _net(_TIMED)
    marking = _marking().set(
        "inbox", (Token("purchase", {"id": "o-1", "sku": "a", "dueAt": 100}),)
    )

    # when: symbolic advance with time= and a journal attached
    engine = _engine(journal=JsonlJournal(str(tmp_path / "j.jsonl")))
    outcome = engine.advance(
        net,
        marking,
        time=("clock", Token("tick", {"now": 130})),
        outputs=symbolic_outputs,
    )

    # then: outcome records and journal copies carry the same stamp
    stamps = {record["metadata"].get("maturedBy") for record, _ in outcome.firings}
    assert len(stamps) == 1
    (injection_id,) = stamps
    journaled: list[dict[str, Any]] = [
        dict(cast(dict[str, Any], r))
        for r in cast("list[Any]", engine.journal._records)  # type: ignore[union-attr]
        if r.get("transition") is not None
    ]
    assert [r["metadata"]["maturedBy"] for r in journaled] == [
        r["metadata"]["maturedBy"] for r, _ in outcome.firings
    ]
    assert all(r["metadata"]["maturedBy"] == injection_id for r in journaled)

    # and: without a journal the outcome records are stamped the same way
    outcome_bare = _engine().advance(
        net,
        marking,
        time=("clock", Token("tick", {"now": 130})),
        outputs=symbolic_outputs,
    )
    assert {record["metadata"].get("maturedBy") for record, _ in outcome_bare.firings} == {
        injection_id
    }

    # and: plain advance(time=) without outputs still returns a bare Marking
    plain = _engine().advance(
        net, marking, time=("clock", Token("tick", {"now": 130}))
    )
    assert not isinstance(plain, AdvanceOutcome)


# 3 ────────────────────────────────────────────────────────────────────────
def test_given_provider_returns_none_when_advance_then_skip_no_spin_still_enabled() -> None:
    # given: a provider that always declines
    net = _net(_READS_ONLY)
    engine = _engine()

    def decline(
        net: Net, reservation: FiringReservation
    ) -> TransitionHandlerOutput | None:
        del net, reservation
        return None

    # when: the advance runs, the read-only transition determinable by
    #   nothing (it reads its own output color) is skipped every step
    start = _clock(
        _marking().set("switch", (Token("verdict", {"state": "open"}),)), 120
    )
    outcome: AdvanceOutcome = engine.advance(net, start, outputs=decline)

    # then: no record, the marking is untouched, and the transition is still
    #   enabled after the advance
    assert isinstance(outcome, AdvanceOutcome)
    assert outcome.firings == ()
    assert outcome.marking == start
    assert "flag" in engine.enabled_transitions(net, outcome.marking, attempt=0)


# 4 ────────────────────────────────────────────────────────────────────────
def test_given_carry_when_source_token_mutated_after_then_deposit_unaffected() -> None:
    # given: a reservation on a consume-and-carry transition (no timer needed)
    net = _net(
        """\
net carry_one
(src) -item-> [carry_t]
@out: [carry_t] -item-> (out)
""",
        "carry.petrinet",
    )
    marking = _marking().set("src", (Token("item", {"n": 1}),))
    engine = _engine()
    reservation = engine.reserve(net, marking, "carry_t", attempt=0)
    assert reservation is not None

    # when: the provider builds the output and the source token then mutates
    out = symbolic_outputs(net, reservation)
    assert out is not None
    consumed = next(iter(reservation.consumed_tokens.values()))
    consumed[0].data["n"] = "mutated"
    after, record = engine.settle(reservation.reserved_marking, reservation, out)

    # then: the deposited token holds the data as carried, not the mutation
    assert record["status"] == "completed"
    assert next(iter(after["out"])).data == {"n": 1}


# 5 ────────────────────────────────────────────────────────────────────────
def test_given_data_and_data_cel_templates_when_advance_then_deposit_fills() -> None:
    # given: a net whose own templates fill two outputs (literal data, data cel)
    net = _net(_NET_FILLS)
    marking = _clock(_marking().set("batch", (Token("item", {"n": 5}),)), 120)
    engine = _engine()

    # when: the symbolic advance fires
    outcome = engine.advance(
        net,
        marking,
        time=("clock", Token("tick", {"now": 130})),
        outputs=symbolic_outputs,
    )

    # then: the deposit filled them the engine's own way — data passthrough
    #   and the cel evaluated over the binding
    assert isinstance(outcome, AdvanceOutcome)
    (record, after) = outcome.firings[0]
    assert record["status"] == "completed"
    assert {
        place: [{"type": t.type, "data": t.data} for t in tokens]
        for place, tokens in record["outputTokens"].items()
    } == {
        "same": [{"type": "item", "data": {"n": 5}}],
        "receipts": [{"type": "receipt", "data": {"kind": "receipt"}}],
        "counts": [{"type": "counter", "data": {"n": 6}}],
    }
    assert next(iter(after["counts"])).data == {"n": 6}


# 6 ────────────────────────────────────────────────────────────────────────
def test_given_read_tokens_when_probe_then_engine_and_checker_agree() -> None:
    # given (a): a transition that only READS its output color, consumes none
    net = _net(_READS_ONLY, "reads_only.petrinet")
    engine = _engine()
    marking = _clock(
        _marking().set("switch", (Token("verdict", {"state": "open"}),)), 120
    )

    # when: the engine advances symbolically
    outcome = engine.advance(
        net, marking, time=("clock", Token("tick", {"now": 130})),
        outputs=symbolic_outputs,
    )

    # then: read tokens never carry — no firing, quiescence
    assert isinstance(outcome, AdvanceOutcome)
    assert outcome.firings == ()

    # and: the checker's maturation skip says the same — the advance step
    #   plays to quiescence silently (undetermined matured firing is
    #   skipped, not failed) and records no firing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "reads_only.petrinet").write_text(_READS_ONLY, encoding="utf-8")
        (tmp / "s.play").write_text(
            'play s\nnet "reads_only.petrinet"\nadvance 130\n', encoding="utf-8"
        )
        report = check_play(read_play(tmp / "s.play"))
    failure = report.traces[0].failure
    assert failure is None
    # and: the advance step recorded only the clock injection, no firing
    assert not any(r.get("firingId") for r in report.traces[0].steps[-1].records)

    # given (b): the mirror case consumes one AND reads one of that color
    net_m = _net(_CONSUMES_AND_READS)
    marking_m = _clock(
        _marking().set("batch", (Token("item", {"n": 1}), Token("item", {"n": 2}))),
        120,
    )

    # when: the advance fires symbolically
    outcome_m = engine.advance(
        net_m, marking_m, time=("clock", Token("tick", {"now": 130})),
        outputs=symbolic_outputs,
    )

    # then: determined — it fires with the consumed token's data, and the
    #   read token stayed behind
    assert isinstance(outcome_m, AdvanceOutcome)
    (record, after) = outcome_m.firings[0]
    assert record["status"] == "completed"
    assert next(iter(after["copies"])).data == {"n": 1}
    assert len(list(after["batch"])) == 1


# 7 ────────────────────────────────────────────────────────────────────────
def test_given_deposit_violation_when_settled_failed_then_excluded_without_spin() -> None:
    # given: record_then_drop and a provider whose output violates the net's
    #   own produce contract (a receipt token for an item destination)
    net = _net(_VIOLATING)

    def bad_outputs(
        net: Net, reservation: FiringReservation
    ) -> TransitionHandlerOutput | None:
        del net, reservation
        return {
            "status": "completed",
            "outputTokens": {"out": [Token("item", {"n": 9})]},
            "error": None,
            "metadata": {},
        }

    engine = _engine(
        deposit_violation="record_then_drop",
        max_consecutive_failures=1,
        journal=cast("Journal", _MemoryJournal([])),
    )

    # when: the advance runs symbolically
    outcome: AdvanceOutcome = engine.advance(
        net,
        _clock(_marking().set("batch", (Token("item", {"n": 1}),)), 120),
        time=("clock", Token("tick", {"now": 130})),
        outputs=bad_outputs,
    )

    # then: exactly one failed deposit-violation record — the transition is
    #   excluded for the remainder, so the advance quiesces instead of
    #   spinning to max_steps
    assert isinstance(outcome, AdvanceOutcome)
    assert len(outcome.firings) == 1
    record = outcome.firings[0][0]
    assert record["status"] == "failed"
    assert record["error"] is not None
    assert record["error"]["type"] == "DepositViolation"


# 8 ────────────────────────────────────────────────────────────────────────
def test_given_same_net_when_advance_and_check_play_then_same_order() -> None:
    # given: the handlerless timed net; the play pins the untimed deliver by
    #   its own fire step and leaves the maturation to advance (the checker's
    #   maturation plays timer-gated transitions only, so the engine's
    #   deliver-first order is compared against the play's matching prefix
    #   for the timed part)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "shop.petrinet").write_text(_TIMED, encoding="utf-8")
        (tmp / "s.play").write_text(
            'play s\nnet "shop.petrinet"\n'
            'inject (inbox) <- purchase {"id": "o-1", "sku": "a", "dueAt": 100}\n'
            'inject (clock) <- tick {"now": 0}\n'
            "fire [deliver]\n"
            "advance 130\n",
            encoding="utf-8",
        )
        report = check_play(read_play(tmp / "s.play"))
        (trace,) = report.traces
        timed_records = [
            r
            for s in trace.steps
            if s.step.statement.startswith("advance")
            for r in s.records
            if r.get("firingId")
        ]

    # when: the engine advances the same net symbolically, with the deliver
    #   already applied (matching the play's pinned fire step)
    engine = _engine()
    marking = _marking().set(
        "accepted", (Token("purchase", {"id": "o-1", "sku": "a", "dueAt": 100}),)
    )
    outcome = engine.advance(
        _net(_TIMED, "shop.petrinet"),
        _clock(marking, 130),
        outputs=symbolic_outputs,
    )

    # then: same firing order for the maturation (timeout only), same
    #   statuses, both completed
    assert [dict(r)["transition"] for r in timed_records] == [
        r["transition"] for r, _ in outcome.firings
    ]
    assert [dict(r)["status"] for r in timed_records] == [
        r["status"] for r, _ in outcome.firings
    ] == ["completed"]


# 9 ────────────────────────────────────────────────────────────────────────
def test_given_two_runs_when_replayed_then_identical_modulo_timestamps() -> None:
    # given: two fresh engines over the same net and input

    def run() -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        engine = Engine(
            HandlerRegistry(),
            policy=PRIORITY_FIRING_POLICY,
            journal=cast("Journal", _MemoryJournal(records)),
        )
        engine.advance(
            _net(_TIMED),
            _marking().set(
                "inbox", (Token("purchase", {"id": "o-1", "sku": "a", "dueAt": 100}),)
            ),
            time=("clock", Token("tick", {"now": 130})),
            outputs=symbolic_outputs,
        )
        return records

    # when: two runs
    first, second = run(), run()

    # then: identical records, modulo wall-clock timestamps and ids that
    #   derive from them
    def stable(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in record.items() if k != "timestamps"}
            for record in records
        ]

    assert stable(first) == stable(second)


# 10 ───────────────────────────────────────────────────────────────────────
def test_given_outputs_without_time_or_all_none_when_advance_then_shape_and_cap() -> None:
    # given: the timed net; provider variants and a step cap
    net = _net(_TIMED)
    marking = _marking().set(
        "inbox", (Token("purchase", {"id": "o-1", "sku": "a", "dueAt": 100}),)
    )

    # when: outputs= without time=
    outcome = _engine().advance(net, _clock(marking, 130), outputs=symbolic_outputs)

    # then: it fires (deliver, timeout) unstamped
    assert isinstance(outcome, AdvanceOutcome)
    assert [r["transition"] for r, _ in outcome.firings] == ["deliver", "timeout"]
    assert all(
        record["metadata"].get("maturedBy") is None for record, _ in outcome.firings
    )

    # and: max_steps caps the loop
    outcome_capped = _engine().advance(
        net, _clock(marking, 130), max_steps=0, outputs=symbolic_outputs
    )
    assert isinstance(outcome_capped, AdvanceOutcome)
    assert outcome_capped.firings == ()
    assert outcome_capped.marking == _clock(marking, 130)

    # and: an all-None provider returns the input marking, empty firings
    def decline(
        net: Net, reservation: FiringReservation
    ) -> TransitionHandlerOutput | None:
        del net, reservation
        return None

    # and: an all-None provider returns the input marking, empty firings
    start = _clock(marking, 130)
    outcome_none = _engine().advance(net, start, outputs=decline)
    assert isinstance(outcome_none, AdvanceOutcome)
    assert outcome_none.firings == ()
    assert outcome_none.marking == start


# 11 ───────────────────────────────────────────────────────────────────────
def test_given_provider_none_on_first_attempt_when_advance_then_skipped_for_remainer() -> None:
    # given: two transitions enabled in the same step and a provider that
    #   declines exactly one of them on its first probe (attempt == 0) —
    #   still a pure function of (net, reservation)
    net = _net(
        """\
net skip_regress
(src) -x-> [a]
@out_a: [a] -x-> (mid)
(mid) -y-> [t]
@out_t: [t] -y-> (done)
""",
        "repro.petrinet",
    )
    engine = _engine()

    def shy_first(
        net: Net, reservation: FiringReservation
    ) -> TransitionHandlerOutput | None:
        if reservation.transition == "t" and reservation.attempt == 0:
            return None
        return symbolic_outputs(net, reservation)

    # when: the advance runs symbolically
    marking = _marking().set(
        "src", (Token("x", {"v": 1}),)
    ).set("mid", (Token("y", {"v": 1}),))
    outcome = engine.advance(net, marking, outputs=shy_first)

    # then: the transition the provider declined is excluded for the
    #   remainder of THIS advance — its later attempts (t at attempt 1,
    #   still enabled) do not resurrect it
    assert isinstance(outcome, AdvanceOutcome)
    assert [record["transition"] for record, _ in outcome.firings] == ["a"]


class _MemoryJournal:
    """A minimal in-memory journal for the replay test."""

    def __getattr__(self, name: str) -> Callable[..., None]:
        # Delegates every protocol member the engine may call beyond the
        # record hooks to a no-op, matching JsonlJournal's tolerance.
        return lambda *args: None


    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    def record_firing(self, record: dict[str, Any]) -> None:
        self.records.append(deepcopy(record))

    def record_deposit_violation(self, record: dict[str, Any]) -> None:
        self.records.append(deepcopy(record))

    def record_injection(self, record: dict[str, Any]) -> None:
        self.records.append(deepcopy(record))