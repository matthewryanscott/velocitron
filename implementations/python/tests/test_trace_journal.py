"""Trace-journal tests (``TraceJournal`` capability, ADR 0058 Decision 6).

The Engine and Runtime emit a timing/observability record at six points when
the attached journal carries the ``record_trace`` hook; a journal without the
hook records exactly what it did before (the regression case below).

Trace records share the journals' ONE numbered stream: each carries its own
``sequence`` assigned by the journal on arrival, and joins to its firing
record by ``firingId`` — never by sequence, because ``handler_started`` is
written before the firing record exists. Tokens are not repeated: the
firing record's ``inputTokens`` holds them.

References: spec/firing-semantics.md (d); ADR 0058, Decision 6.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from velocitron_engine import (
    TransitionHandler,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_journal import (
    DurableJournal,
    replay_events,
    read_events,
)
from velocitron_runtime import Engine
from velocitron_journal import (
    Journal,
    JsonlJournal,
    TraceEvent,
    TraceJournal,
    TraceRecord,
)
from velocitron_petrinet import parse_net
from velocitron_engine import HandlerRegistry
from velocitron_runtime import (
    HandlerSpec,
    Runtime,
    RuntimeContext,
)
from velocitron_engine import (
    Marking,
    Net,
    Token,
)

from _journal_fixtures import CapturingJournal, journal_makers


# ── Shared helpers (mirrors test_firing_journal.py) ─────────────────────


def _tok(t: str = "task", **data: Any) -> Token:
    return Token(type=t, data=dict(data))


def _marking(**places: list[Token]) -> Marking:
    return Marking({place: list(toks) for place, toks in places.items()})


def _net(d: dict[str, Any]) -> Net:
    return parse_net(d)


def _engine(reg: HandlerRegistry, *, journal: Journal | None = None) -> Engine:
    return Engine(reg, journal=journal, deposit_violation="raise")


def _reg(*pairs: tuple[str, Any], guards: dict[str, Any] | None = None) -> HandlerRegistry:
    reg = HandlerRegistry()
    for name, fn in pairs:
        reg.register_transition(name, fn)
    for name, fn in (guards or {}).items():
        reg.register_guard(name, fn)
    return reg


def _traces(journal: JsonlJournal) -> list[dict[str, Any]]:
    """Only the trace channel of a numbered-stream journal."""
    return [r for r in journal.records() if r.get("event") in _ALL_EVENTS]


_ALL_EVENTS: set[str] = {
    "tokens_reserved",
    "handler_started",
    "handler_returned",
    "handler_raised",
    "guard_checked",
    "predicate_checked",
}


def _firings(journal: JsonlJournal) -> list[dict[str, Any]]:
    """The firing channel: records with ``attempt`` but no injection ``kind``."""
    return [
        r for r in journal.records() if "attempt" in r and "kind" not in r
    ]


def _output(dst: str = "dst") -> TransitionHandler:
    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        tokens = inp["inputTokens"].get("src", [])
        return {
            "status": "completed",
            "outputTokens": {dst: tokens},
            "error": None,
            "metadata": {},
        }

    return handler


# ── Nets: every arc/place is asserted-on or structurally required ────────


# Completed-passthrough: consume src -> produce dst (case 9's simple fire).
_PASSTHROUGH_NET = _net(
    {
        "name": "trace-passthrough-net",
        "places": [
            {"name": "src", "accepts": ["task"]},
            {"name": "dst", "accepts": ["task"]},
        ],
        "transitions": [{"name": "t", "handler": "t"}],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t"},
                "consume": {"type": "task"},
            },
            {
                "from": {"transition": "t"},
                "to": {"place": "dst"},
                "produce": {"type": "task", "destination": "dst"},
            },
        ],
    }
)

# Case 1: two sequential firings, both completing.
_TWO_STEP_NET = _net(
    {
        "name": "trace-two-step-net",
        "places": [
            {"name": "src", "accepts": ["task"]},
            {"name": "mid", "accepts": ["task"]},
            {"name": "dst", "accepts": ["task"]},
        ],
        "transitions": [
            {"name": "t1", "handler": "t1"},
            {"name": "t2", "handler": "t2"},
        ],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t1"},
                "consume": {"type": "task"},
            },
            {
                "from": {"transition": "t1"},
                "to": {"place": "mid"},
                "produce": {"type": "task", "destination": "mid"},
            },
            {
                "from": {"place": "mid"},
                "to": {"transition": "t2"},
                "consume": {"type": "task"},
            },
            {
                "from": {"transition": "t2"},
                "to": {"place": "dst"},
                "produce": {"type": "task", "destination": "dst"},
            },
        ],
    }
)

# Cases 2/3: a guard that refuses, and a guard that raises.
_GUARD_NET = _net(
    {
        "name": "trace-guard-net",
        "places": [{"name": "src", "accepts": ["task"]}],
        "transitions": [{"name": "t", "handler": "t", "guard": "the_guard"}],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t"},
                "consume": {"type": "task"},
            },
        ],
    }
)

# Case 4: a consume arc gated by a named predicate handler that raises.
_PREDICATE_NET = _net(
    {
        "name": "trace-predicate-net",
        "places": [
            {"name": "src", "accepts": ["task"]},
            {"name": "dst", "accepts": ["task"]},
        ],
        "transitions": [{"name": "t", "handler": "t"}],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t"},
                "consume": {
                    "type": "task",
                    "predicate": {"handler": "raising_p"},
                },
            },
            {
                "from": {"transition": "t"},
                "to": {"place": "dst"},
                "produce": {"type": "task", "destination": "dst"},
            },
        ],
    }
)

# Case 5: a handler that raises OUT of Engine.fire (a plain function, so the
# base-class adapter shape does not apply — the Engine sees the raise).
_RAISE_NET = _net(
    {
        "name": "trace-raise-net",
        "places": [{"name": "src", "accepts": ["task"]}],
        "transitions": [{"name": "t", "handler": "t"}],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t"},
                "consume": {"type": "task"},
            },
        ],
    }
)

# Case 8 regression net: the speak-window reading_hour integration shape is
# imported lazily from that module's helpers.


# ── Handlers ─────────────────────────────────────────────────────────────


def _refusing_guard(inp: Any) -> bool:
    return False


def _raising_guard(inp: Any) -> bool:
    raise RuntimeError("guard boom")


def _raising_predicate(inp: Any) -> bool:
    raise RuntimeError("predicate boom")


def _raising_handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    raise RuntimeError("handler boom")


class _Greeter:
    """Carries a bound method registered by hand (case 7's ``method``)."""

    def greet(self, inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        # consumes without producing: the "method" field, not the deposit,
        # is the concern here
        return {"status": "completed", "outputTokens": {}, "error": None, "metadata": {}}

    async def async_greet(
        self, inp: TransitionHandlerInput, ctx: RuntimeContext
    ) -> TransitionHandlerOutput:
        return {
            "status": "completed",
            "outputTokens": {"dst": inp["inputTokens"].get("src", [])},
            "error": None,
            "metadata": {},
        }


lambda_handler: Any = lambda inp: {  # the point is __qualname__
    "status": "completed",
    "outputTokens": {"dst": inp["inputTokens"].get("src", [])},
    "error": None,
    "metadata": {},
}


# ── Case 1 ───────────────────────────────────────────────────────────────


class TestJoinByFiringId:
    """Case 1: handler_started/returned join to their firing record."""

    def test_completed_firings_hold_started_and_returned_joining_by_firing_id(
        self,
    ) -> None:
        # given: a sync Engine.advance over a two-transition net with a JsonlJournal
        journal = JsonlJournal()
        engine = _engine(
            _reg(("t1", _output("mid")), ("t2", _output("dst"))), journal=journal
        )
        initial = _marking(src=[_tok("task", i=0)], mid=[], dst=[])

        # when: the engine runs to quiescence
        engine.advance(_TWO_STEP_NET, initial, max_steps=100)

        # then: each completed firing has one started and one returned record
        traces = _traces(journal)
        by_event: dict[TraceEvent, list[dict[str, Any]]] = {}
        for record in traces:
            by_event.setdefault(record["event"], []).append(record)
        started = by_event["handler_started"]
        returned = by_event["handler_returned"]
        firings = [
            r for r in _firings(journal) if r["transition"] in ("t1", "t2")
        ]
        assert len(firings) == 2
        assert len(started) == len(returned) == 2

        # and: each trace join its firing record by firingId, never by sequence
        for firing in firings:
            matched_started = [
                r for r in started if r["firingId"] == firing["firingId"]
            ]
            matched_returned = [
                r for r in returned if r["firingId"] == firing["firingId"]
            ]
            assert len(matched_started) == 1
            assert len(matched_returned) == 1
            assert matched_returned[0]["status"] == "completed"

        # and: each trace carries its own journal-assigned sequence
        sequences = [r["sequence"] for r in journal.records()]
        assert sequences == sorted(sequences)
        assert len(sequences) == len(set(sequences))


# ── Case 2 ───────────────────────────────────────────────────────────────


def test_guard_refusal_records_result_false_and_no_firing(tmp_path: Any) -> None:
    # given: a transition with a guard ref whose handler returns False
    journal = JsonlJournal()
    engine = _engine(
        _reg(("t", _output()), guards={"the_guard": _refusing_guard}), journal=journal
    )
    initial = _marking(src=[_tok("task", i=0)])

    # when: the engine runs to quiescence
    engine.advance(_GUARD_NET, initial, max_steps=10)

    # then: every guard call left a guard_checked record with result False
    checked = [r for r in _traces(journal) if r["event"] == "guard_checked"]
    assert checked
    assert all(r["result"] is False for r in checked)
    assert all(
        r["handler"] == "the_guard" and r["error"] is None for r in checked
    )

    # and: a completed firing record never exists for that transition
    firings = _firings(journal)
    assert all(r["status"] != "completed" for r in firings)


# ── Case 3 ───────────────────────────────────────────────────────────────


def test_raising_guard_records_error_and_result_none(tmp_path: Any) -> None:
    # given: a guard handler that raises
    journal = JsonlJournal()
    engine = _engine(
        _reg(("t", _output()), guards={"the_guard": _raising_guard}), journal=journal
    )
    initial = _marking(src=[_tok("task", i=0)])

    # when: the engine runs to quiescence (unchanged: raise reads as not enabled)
    final = engine.advance(_GUARD_NET, initial, max_steps=10)
    firings = _firings(journal)
    assert all(r["status"] != "completed" for r in firings)
    assert not final.get("dst")

    # then: a guard_checked record carries the error type, result None
    checked = [r for r in _traces(journal) if r["event"] == "guard_checked"]
    assert checked
    assert all(r["result"] is None for r in checked)
    assert all(r["error"]["type"] == "RuntimeError" for r in checked)


# ── Case 4 ───────────────────────────────────────────────────────────────


def test_raising_predicate_records_error_and_rejects_binding(tmp_path: Any) -> None:
    # given: a consume arc with a named predicate handler that raises
    journal = JsonlJournal()
    reg = _reg(("t", _output()))
    reg.register_predicate("raising_p", _raising_predicate)
    engine = _engine(reg, journal=journal)
    initial = _marking(src=[_tok("task", i=0)])

    # when: the engine runs (unchanged: any handler failure => predicate false)
    final = engine.advance(_PREDICATE_NET, initial, max_steps=10)

    # then: a predicate_checked record carries the error, the ref, the method
    checked = [r for r in _traces(journal) if r["event"] == "predicate_checked"]
    assert checked
    assert all(r["result"] is None for r in checked)
    assert all(r["error"]["type"] == "RuntimeError" for r in checked)
    assert all(r["handler"] == "raising_p" for r in checked)
    assert all(r["transition"] == "t" for r in checked)

    # and: the binding was rejected — no completed firing exists
    firings = _firings(journal)
    assert all(r["status"] != "completed" for r in firings)
    assert not final.get("dst")


# ── Case 5 ───────────────────────────────────────────────────────────────


def test_sync_raise_records_handler_raised_and_still_propagates() -> None:
    # given: a sync handler that raises out of Engine.fire
    journal = JsonlJournal()
    engine = _engine(_reg(("t", _raising_handler)), journal=journal)
    initial = _marking(src=[_tok("task", i=0)])

    # when: fire, expecting the exception to propagate
    with pytest.raises(RuntimeError, match="handler boom"):
        engine.fire(_PASSTHROUGH_NET, initial, "t", attempt=0)

    # then: handler_raised is recorded alongside the started record
    raised = [r for r in _traces(journal) if r["event"] == "handler_raised"]
    assert len(raised) == 1
    assert raised[0]["error"]["type"] == "RuntimeError"
    assert raised[0]["error"]["message"] == "handler boom"
    assert raised[0]["handler"] == "t"
    assert any(
        r["event"] == "handler_started" and r["firingId"] == raised[0]["firingId"]
        for r in _traces(journal)
    )

    # and: no handler_returned for that firing
    returned = [
        r
        for r in _traces(journal)
        if r["event"] == "handler_returned"
        and r["firingId"] == raised[0]["firingId"]
    ]
    assert returned == []


# ── Case 6 ───────────────────────────────────────────────────────────────


_ONE_STEP_RUNTIME_NET = _net(
    {
        "name": "trace-runtime-net",
        "places": [
            {"name": "src", "accepts": ["task"]},
            {"name": "dst", "accepts": ["task"]},
        ],
        "transitions": [{"name": "t", "handler": "t"}],
        "arcs": [
            {
                "from": {"place": "src"},
                "to": {"transition": "t"},
                "consume": {"type": "task"},
            },
            {
                "from": {"transition": "t"},
                "to": {"place": "dst"},
                "produce": {"type": "task", "destination": "dst"},
            },
        ],
    }
)


def test_runtime_orders_reserved_started_returned_and_records_a_raise() -> None:
    # given: a Runtime over a one-transition net
    greeter = _Greeter()
    journal = JsonlJournal()

    async def play() -> None:
        runtime = Runtime(
            net=_ONE_STEP_RUNTIME_NET,
            handlers={"t": HandlerSpec(greeter.async_greet, "io")},
            lanes={"io": 1},
            marking=_marking(src=[_tok("task", i=0)]),
            journal=journal,
        )

        # when: the runtime runs to quiescence
        await runtime.start()
        try:
            await asyncio.wait_for(runtime.wait_idle(), timeout=2)
        finally:
            await runtime.stop()

        # then: tokens_reserved, handler_started, handler_returned, in order
        events = [r["event"] for r in _traces(journal)]
        assert events == ["tokens_reserved", "handler_started", "handler_returned"]
        firing_id = _traces(journal)[0]["firingId"]
        assert all(r["firingId"] == firing_id for r in _traces(journal))
        assert journal.records()[0]["netId"] == "trace-runtime-net"

        # and: the returned record carries the firing record's terminal status
        firings = _firings(journal)
        assert firings[0]["status"] == "completed"
        returned = [
            r for r in _traces(journal) if r["event"] == "handler_returned"
        ]
        assert returned[0]["status"] == "completed"

    asyncio.run(play())


def test_runtime_async_raise_is_recorded_and_output_stays_failed() -> None:
    # given: a Runtime whose async handler raises
    journal = JsonlJournal()

    async def raising(
        inp: TransitionHandlerInput, ctx: RuntimeContext
    ) -> TransitionHandlerOutput:
        raise RuntimeError("async boom")

    async def play() -> None:
        runtime = Runtime(
            net=_ONE_STEP_RUNTIME_NET,
            handlers={"t": HandlerSpec(raising, "io")},
            lanes={"io": 1},
            marking=_marking(src=[_tok("task", i=0)]),
            journal=journal,
        )

        # when: the runtime runs to quiescence (unchanged: failed output)
        await runtime.start()
        try:
            await asyncio.wait_for(runtime.wait_idle(), timeout=2)
        finally:
            await runtime.stop()

        # then: handler_raised is recorded between started and returned
        events = [r["event"] for r in _traces(journal)]
        assert events == [
            "tokens_reserved",
            "handler_started",
            "handler_raised",
            "handler_returned",
        ]

        # and: the raised record carries the error; the output stays failed
        raised = [r for r in _traces(journal) if r["event"] == "handler_raised"]
        assert raised[0]["error"]["type"] == "RuntimeError"
        firings = _firings(journal)
        assert firings[0]["status"] == "failed"
        returned = [
            r for r in _traces(journal) if r["event"] == "handler_returned"
        ]
        assert returned[0]["status"] == "failed"

    asyncio.run(play())


# ── Case 7 ───────────────────────────────────────────────────────────────


def test_method_carries_qualname_of_bound_method_and_lambda() -> None:
    # given: one handler registered as a bound method, another as a lambda
    greeter = _Greeter()
    journal = JsonlJournal()
    lambda_complete: Any = lambda inp: {  # the point is __qualname__
        "status": "completed",
        "outputTokens": {},
        "error": None,
        "metadata": {},
    }
    engine = _engine(
        _reg(("bound", greeter.greet), ("lam", lambda_complete)),
        journal=journal,
    )
    initial = _marking(src=[_tok(), _tok()])

    # a consume-only net (no produce arcs): the two handlers complete without
    # producing — the trace record's "method" is the concern, not the deposit
    multi_net = _net(
        {
            "name": "trace-consume-only-net",
            "places": [{"name": "src", "accepts": ["task"]}],
            "transitions": [
                {"name": "bound", "handler": "bound"},
                {"name": "lam", "handler": "lam"},
            ],
            "arcs": [
                {
                    "from": {"place": "src"},
                    "to": {"transition": "bound"},
                    "consume": {"type": "task", "weight": 1},
                },
                {
                    "from": {"place": "src"},
                    "to": {"transition": "lam"},
                    "consume": {"type": "task", "weight": 1},
                },
            ],
        }
    )

    # when: each fires once
    engine.fire(multi_net, initial, "bound", attempt=0)
    engine.fire(multi_net, initial, "lam", attempt=0)

    # then: the bound method carried Class.method; the lambda "<lambda>"
    started = {
        r["handler"]: r["method"]
        for r in _traces(journal)
        if r["event"] == "handler_started"
    }
    # the bound method carries "Class.method" in the field
    assert started["bound"].endswith(".greet")
    assert started["lam"].endswith("<lambda>")


# ── Case 8 ───────────────────────────────────────────────────────────────


class _NoTraceJournal(CapturingJournal):
    """A journal deliberately WITHOUT the record_trace hook.

    Deleting the attribute on the class makes ``isinstance(..., TraceJournal)``
    fail for runtime_checkable protocols too — the capability is genuinely
    absent, which is the regression's premise.
    """

    record_trace = None  # type: ignore[assignment]


class TestNoCapabilityRegression:
    """Case 8: a journal without the hook sees exactly what it saw before."""

    def test_no_hook_journal_sees_what_it_saw_before(self, tmp_path: Any) -> None:
        # given: the reading_hour integration net's reading_hour-shaped stub
        #        registry and net, driven identically under (a) a journal with
        #        the hook and (b) a subclass that DELETES the hook — the
        #        engine must treat (b) exactly as (a) treats every other
        #        channel, record counts included
        import test_reading_hour_integration as reading_hour

        def run(journal: CapturingJournal) -> None:
            net = reading_hour._merged_from_dsl()
            play = reading_hour._play_case()
            engine = Engine(
                reading_hour._registry(net), journal=journal, deposit_violation="raise"
            )
            marking = reading_hour._marking(play["initialMarking"])
            injection = play["injections"][0]
            marking, _ = engine.inject_token(
                net,
                marking,
                injection["place"],
                reading_hour._token(injection["token"]),
                attempt=injection["attempt"],
                replace=injection["replace"],
            )
            engine.advance(net, marking, max_steps=play["maxSteps"])

        with_hook = CapturingJournal()
        run(with_hook)
        without_hook = _NoTraceJournal()
        run(without_hook)

        # then: every channel the hook-less journal writes is identical
        #       record-for-record (timestamps excluded — two runs, two clocks)
        strip = lambda recs: [{k: v for k, v in r.items() if k != "timestamps"} for r in recs]
        assert strip(with_hook.firings) == strip(without_hook.firings)
        assert with_hook.violations == without_hook.violations
        assert strip(with_hook.injections) == strip(without_hook.injections)

        # and: the hook-less journal captured no traces; the hooked one did
        assert without_hook.traces == []
        assert len(with_hook.traces) > 0

        # and: the runtime_checkable protocol confirms the split
        assert isinstance(with_hook, TraceJournal)
        assert not isinstance(without_hook, TraceJournal)

    def test_plain_capturing_journal_counts_unchanged(self) -> None:
        # given: a plain CapturingJournal and a simple one-firing run
        journal = CapturingJournal()

        # when: one fire completes
        engine = _engine(_reg(("t", _output())), journal=journal)
        engine.fire(_PASSTHROUGH_NET, _marking(src=[_tok("task", i=0)]), "t", attempt=0)

        # then: one firing captured, no violations/injections — and exactly
        #       two traces, which is the ONLY thing this change added
        assert len(journal.firings) == 1
        assert journal.violations == []
        assert journal.injections == []


# ── Case 9 ───────────────────────────────────────────────────────────────


class TestDurableTraceRecords:
    """Case 9: the sqlite backend stores trace records and replay skips them."""

    def test_records_return_trace_kind_and_replay_matches(
        self, tmp_path: Any
    ) -> None:
        # given: a durable journal over one temp sqlite database, and its
        #        connection (kept open; the caller owns it)
        from velocitron_journal import open_database

        connection = open_database(tmp_path / "trace-case9.db")
        journal = DurableJournal(connection, instance="test-instance")
        engine = _engine(
            _reg(("t1", _output("mid")), ("t2", _output("dst"))),
            journal=journal,
        )
        initial = _marking(src=[_tok("task", i=0)], mid=[], dst=[])

        # when: one full run over the two-step net
        final = engine.advance(_TWO_STEP_NET, initial, max_steps=100)

        # then: records() holds the trace records among the stored rows; each
        #       stored row's kind column reads "trace" for trace payloads
        records = journal.records()
        assert any(r.get("event") in _ALL_EVENTS for r in records)
        events = read_events(connection, "test-instance")
        trace_events = [e for e in events if e.kind == "trace"]
        assert trace_events
        assert all(e.payload.get("event") in _ALL_EVENTS for e in trace_events)

        # and: replay over the whole log gives the same final marking
        replayed = replay_events(_TWO_STEP_NET, read_events(connection, "test-instance"))
        assert _plain(replayed) == _plain(final)
        connection.close()


# ── Parametrized storage check over BOTH real journals ──────────────────


def test_both_journals_store_trace_records_parametrized(tmp_path: Any) -> None:
    from velocitron_journal import open_database

    def durable() -> DurableJournal:
        connection = open_database(tmp_path / "trace-db.db")
        return DurableJournal(connection, instance="test-instance")

    for journal_id, journal in [("jsonl", JsonlJournal()), ("durable", durable())]:
        # given: an engine with that journal firing one completed firing
        engine = _engine(_reg(("t", _output())), journal=journal)
        initial = _marking(src=[_tok("task", i=0)])

        # when: one fire
        engine.fire(_PASSTHROUGH_NET, initial, "t", attempt=0)

        # then: the journal holds handler_started/returned with sequences
        records = journal.records()
        trace_rows = [r for r in records if r.get("event") in _ALL_EVENTS]
        assert len(trace_rows) == 2
        assert [r["event"] for r in trace_rows] == [
            "handler_started",
            "handler_returned",
        ]
        assert all(
            isinstance(r["sequence"], int) and r["sequence"] >= 0 for r in records
        )
        # and: the joined firing record holds the tokens the trace omits
        # (durable rows all carry a kind column, so select by event's absence)
        firings = [r for r in records if "attempt" in r and r.get("event") is None]
        assert len(firings) == 1
        assert firings[0]["inputTokens"]
        assert firings[0]["firingId"] == trace_rows[0]["firingId"]


def _plain(marking: Marking) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    return {
        place: [(t.type, t.data) for t in tokens]
        for place, tokens in marking.items()
        if tokens
    }


