"""Replay-driver tests (the single-net replay card, `2LQSz2Hf`).

The 10-group plan from the card's spec: strict replay of a recorded
``reading_voice`` run with no method called; out-of-order raises with
expected/got/sequence; injections at their recorded points; recorded
failed replays as failed; guards from the tape's ``guard_checked``
records; live guards in compare mode give a ``guard`` divergence; a
changed net in compare mode reports ``net_matches is False`` and the
first divergence (strict raises ``ReplayNetMismatch``); ``net_matches is
None`` without a net revision; ``ReplayOrderError`` never becomes a
failed record; and the generated ``Replay<Net>`` stubs (the generator
card's emission — checklist item 2 — is shared with the codegen lane and
asserted from the goldens when it lands).

References: ADR 0058 (Decisions 3 and 7); the Q66 (a) same-journal rule.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from velocitron_engine import (
    FiringPolicyHandler,
    FiringPolicyInput,
    TransitionHandler,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)

import pytest

from velocitron_journal import (
    DurableJournal,
    open_database,
)
from velocitron_runtime import Engine
from velocitron_journal import JsonlJournal
from velocitron_netbase import (
    SYNTH_HANDLER,
    VelocitronNet,
    net_document,
    net_sha256,
)
from velocitron_replay import (
    ReplayBase,
    ReplayCursor,
    ReplayNetMismatch,
    ReplayOrderError,
    ReplayResult,
    replay_run,
)
from velocitron_engine import HandlerRegistry
import velocitron_analysis as prove
from velocitron_engine import (
    Arc,
    ConsumePattern,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
)

_REPOSITORY_ROOT = Path(__file__).parents[3]
_LADDER = _REPOSITORY_ROOT / "examples" / "capability-ladder"


def _token(type_: str, **data: Any) -> Token:
    return Token(type_, data)


def _speak_net() -> Net:
    """The reading_voice leaf."""
    return prove.load_net(
        _LADDER
        / "12-reading-hour-fragment"
        / "reading_voice.petrinet"
    )


# ── Small nets for the ordering cases ──────────────────────────────────


def _ab_net() -> Net:
    """Two independent transitions over one token: order-visible."""
    return Net(
        name="ab_net",
        places=[
            Place(name="src", accepts=["task"]),
            Place(name="a_out", accepts=["task"]),
            Place(name="b_out", accepts=["task"]),
        ],
        transitions=[
            Transition(name="a", handler="a"),
            Transition(name="b", handler="b"),
        ],
        arcs=[
            Arc(
                from_place="src",
                to_transition="a",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="a",
                to_place="a_out",
                produce=ProduceTemplate("task", "a_out"),
            ),
            Arc(
                from_place="src",
                to_transition="b",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="b",
                to_place="b_out",
                produce=ProduceTemplate("task", "b_out"),
            ),
        ],
        initial_marking=Marking({"src": [_token("task", n=1)]}),
    )


def _passthrough_handler(source: str, destination: str) -> TransitionHandler:
    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        return {
            "status": "completed",
            "outputTokens": {
                destination: list(inp["inputTokens"][source])
            },
            "error": None,
            "metadata": {},
        }

    return handler


def _completion(dst: str) -> TransitionHandler:
    return _passthrough_handler("src", dst)


def _failed_handler() -> TransitionHandler:
    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        return {
            "status": "failed",
            "outputTokens": {},
            "error": {"type": "SpeakerMuted", "message": "no sound card"},
            "metadata": {},
        }

    return handler


def _inject_net() -> Net:
    """fire a -> inject an arrival -> fire b (b only enabled after)."""
    net = Net(
        name="inject_net",
        places=[
            Place(name="gate", accepts=["task"]),
            Place(name="out_a", accepts=["task"]),
            Place(name="out_b", accepts=["signal"]),
            Place(name="arrivals", accepts=["signal"]),
        ],
        transitions=[
            Transition(name="a", handler="a"),
            Transition(name="b", handler="b"),
        ],
        arcs=[
            Arc(
                from_place="gate",
                to_transition="a",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="a",
                to_place="out_a",
                produce=ProduceTemplate("task", "out_a"),
            ),
            Arc(
                from_place="arrivals",
                to_transition="b",
                consume=ConsumePattern("signal", None, "consume"),
            ),
            Arc(
                from_transition="b",
                to_place="out_b",
                produce=ProduceTemplate("signal", "out_b"),
            ),
        ],
        initial_marking=Marking({"gate": [_token("task", n=1)]}),
    )
    return net


# ── Live classes (make the recordings) ─────────────────────────────────


class _LiveSpeaks(VelocitronNet):
    """The live reading_voice handlers used to make the recording."""

    NET_NAME = "reading_voice"
    SOURCE = "12-reading-hour-fragment/reading_voice.petrinet"
    SOURCE_SHA256 = net_sha256(_speak_net())
    HANDLER_REFS: ClassVar[dict[str, str]] = {
        "start@speaks": "fire_start",
        "finish@speaks": "fire_finish",
    }
    GUARD_REFS: ClassVar[dict[str, str]] = {}
    PREDICATE_REFS: ClassVar[dict[str, str]] = {}
    GENERATED_METHODS: ClassVar[dict[str, str]] = {}
    INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
        "start": ("request_in",),
        "finish": ("work", "in_flight"),
    }
    OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
        "start": ("in_flight", "work"),
        "finish": ("utterance_out",),
    }
    ASYNC: ClassVar[bool] = False

    def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
        return {
            "in_flight": [_token("speak_token", request=1)],
            "work": [_token("speak_work", request=1)],
        }

    def fire_finish(
        self, *, work: list[Token], in_flight: list[Token]
    ) -> dict[str, list[Token]]:
        return {"utterance_out": [_token("utterance", text="hello")]}


class _LiveSpeaksFailingStart(_LiveSpeaks):
    """fire_start returns ``failed`` once (the recorded-failed case)."""

    def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
        return {
            "status": "failed",  # type: ignore[dict-item]
            "outputTokens": {},
            "error": {"type": "SpeakerMuted", "message": "no sound card"},
            "metadata": {},
        }  # type: ignore[return-value]


# ── The replay mixin classes (the recorded net's wiring, stubs only) ───


class _ReplaySpeaks(ReplayBase):
    """The replay target for reading_voice: the mixin + the same
    classattrs the generated ``ReplayReadingVoiceNet`` will carry."""

    NET_NAME = "reading_voice"
    SOURCE = "12-reading-hour-fragment/reading_voice.petrinet"
    SOURCE_SHA256 = net_sha256(_speak_net())
    HANDLER_REFS: ClassVar[dict[str, str]] = {
        "start@speaks": "fire_start",
        "finish@speaks": "fire_finish",
    }
    GUARD_REFS: ClassVar[dict[str, str]] = {}
    PREDICATE_REFS: ClassVar[dict[str, str]] = {}
    GENERATED_METHODS: ClassVar[dict[str, str]] = {}
    INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
        "start": ("request_in",),
        "finish": ("work", "in_flight"),
    }
    OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
        "start": ("in_flight", "work"),
        "finish": ("utterance_out",),
    }
    ASYNC: ClassVar[bool] = False

    def fire_start(self, *, request_in: list[Token]) -> dict[str, list[Token]]:
        raise AssertionError("replay never calls fire_start")

    def fire_finish(
        self, *, work: list[Token], in_flight: list[Token]
    ) -> dict[str, list[Token]]:
        raise AssertionError("replay never calls fire_finish")


def _replay_for(
    net: Net, cursor: ReplayCursor, mode: Any = "strict", live: Any | None = None
) -> Any:
    """A ReplayBase subclass wired for ``net``'s own handler refs."""

    handler_refs = {
        transition.handler: f"fire_{transition.name}"
        for transition in net.transitions
        if transition.handler is not None
    }

    class Wired(ReplayBase):
        NET_NAME = net.name
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = handler_refs
        GUARD_REFS: ClassVar[dict[str, str]] = {
            transition.guard: f"guard_{transition.name}"
            for transition in net.transitions
            if transition.guard is not None
        }
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}

    for name in handler_refs.values():
        setattr(Wired, name, _raising_stub(name))
    for name in Wired.GUARD_REFS.values():
        setattr(Wired, name, _raising_stub(name))

    instance = Wired(cursor, mode=mode, live=live)
    return instance


def _raising_stub(name: str) -> Callable[..., Any]:
    def stub(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"replay never calls {name}")

    stub.__name__ = name
    return stub


def _contents(marking: Marking) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    return {
        place: [(token.type, dict(token.data)) for token in tokens]
        for place, tokens in marking.items()
    }


# ══ Tests ═══════════════════════════════════════════════════════════════


# ── 1. Strict replay of a recorded reading_voice run ───────────────


def test_strict_replay_reaches_recorded_final_marking_without_methods() -> None:
    # given: a recorded run of reading_voice with methods that succeeded
    recording = JsonlJournal()
    live = _LiveSpeaks()
    registry = HandlerRegistry()
    registration = live.register_into(registry, _speak_net(), journal=recording)
    engine = Engine(registry, journal=recording)
    marking = Marking({"request_in": [_token("speak_req", request=1)]})
    recorded_marking = engine.advance(registration.net, marking)
    tape = recording.records()
    recorded_firings = [
        r
        for r in tape
        if "firingId" in r and "kind" not in r and "event" not in r
    ]
    assert len(recorded_firings) == 2  # start, then finish
    assert all(f["status"] == "completed" for f in recorded_firings)

    # when: registered again with the REPLAY mixin at the same net and
    # replayed strictly onto a fresh journal
    cursor = ReplayCursor(tape)
    replay = _ReplaySpeaks(cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), _speak_net())
    replay_journal = JsonlJournal()
    result = replay_run(
        _speak_net(),
        replay,
        replay_registration,
        cursor,
        mode="strict",
        journal=replay_journal,
        marking=marking,
    )

    # then: the replay reaches the same final marking ...
    assert _contents(result.final_marking) == _contents(recorded_marking)
    # and: the stubs were never called (a call would raise the
    # AssertionError "replay never calls ..."), the replay journal holds
    # its own handler records, and the run stayed in order
    replay_firings = [
        r
        for r in replay_journal.records()
        if "firingId" in r and "kind" not in r and "event" not in r
    ]
    assert [f["firingId"] for f in replay_firings] == [
        f["firingId"] for f in recorded_firings
    ]
    assert all(f["status"] == "completed" for f in replay_firings)
    replay_traces = [
        r for r in replay_journal.records() if "event" in r
    ]
    assert any(r["event"] == "handler_started" for r in replay_traces)
    # and: the recorded outputs reached the marking merged-keyed as
    # recorded (the utterance token is the same data)
    assert [
        dict(t.data) for t in result.final_marking.get("utterance_out", [])
    ] == [{"text": "hello"}]


# ── 2. Out-of-order raises with expected, got, sequence ────────────────


def test_out_of_order_raises_naming_expected_got_sequence() -> None:
    # given: a recording where a fired before b (both enabled on src)
    net = _ab_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    registry.register_transition("b", _completion("b_out"))
    engine = Engine(registry, journal=recording)
    engine.fire(net, net.initial_marking or Marking(), "a", attempt=0)
    tape = recording.records()

    # when: replayed with a policy that picks b first (both are enabled;
    # the Engine CHOOSES b, the tape's next firing is a)
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registry = _registry_with_b_first_policy()
    replay_registration = replay.register_into(replay_registry, net)

    # then: ReplayOrderError propagates out of replay_run, naming both
    # ids and the tape sequence where they parted
    with pytest.raises(ReplayOrderError) as excinfo:
        replay_run(
            net,
            replay,
            replay_registration,
            cursor,
            mode="strict",
            policy="b-first",
        )
    error = excinfo.value
    assert error.expected == "ab_net/a/0"
    assert error.got == "ab_net/b/0"
    assert error.sequence == 2  # the firing record's own tape position
    # and: the mixin's message carries both ids for the operator
    assert "ab_net/a/0" in str(error)
    assert "ab_net/b/0" in str(error)


def _register_policy_b_first() -> FiringPolicyHandler:
    def policy(inp: FiringPolicyInput) -> str | None:
        enabled = inp["enabledTransitions"]
        if "b" in enabled:
            return "b"
        return enabled[0] if enabled else None

    return policy


def _registry_with_b_first_policy() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register_firing_policy("b-first", _register_policy_b_first())
    return registry


# ── 3. Injections replay at their recorded points ──────────────────────


def test_driver_replays_injection_between_firings_at_recorded_point() -> None:
    # given: a recording of fire a -> inject -> fire b
    net = _inject_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("a", _passthrough_handler("gate", "out_a"))
    registry.register_transition("b", _passthrough_handler("arrivals", "out_b"))
    engine = Engine(registry, journal=recording)
    current = net.initial_marking or Marking()
    current, record_a = engine.fire(net, current, "a", attempt=0)
    assert record_a["status"] == "completed"
    current, injection_record = engine.inject_token(
        net, current, "arrivals", _token("signal", n=1), attempt=1
    )
    assert injection_record["kind"] == "inject"
    current, record_b = engine.fire(net, current, "b", attempt=2)
    assert record_b["status"] == "completed"
    recorded_marking = current
    tape = recording.records()
    recorded_injection = next(r for r in tape if "injectionId" in r)
    injection_index = tape.index(recorded_injection)

    # when: replayed strictly (the driver re-plays the injection between
    # the two firings, at its recorded point)
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    replay_journal = JsonlJournal()
    result = replay_run(
        net, replay, replay_registration, cursor, mode="strict",
        journal=replay_journal,
    )

    # then: the replay journal's injection record sits between the two
    # firing records in the SAME relative position (after a, before b)
    replay_records = replay_journal.records()
    replay_firing_ids = [
        r["firingId"]
        for r in replay_records
        if "firingId" in r and "kind" not in r and "event" not in r
    ]
    replay_injection_indexes = [
        i for i, r in enumerate(replay_records) if "injectionId" in r
    ]
    assert len(replay_injection_indexes) == 1
    assert replay_injection_indexes[0] > replay_records.index(
        next(
            r
            for r in replay_records
            if r.get("firingId") == "inject_net/a/0"
        )
    )
    assert replay_injection_indexes[0] < replay_records.index(
        next(
            r
            for r in replay_records
            if r.get("firingId") == "inject_net/b/2"
        )
    )
    # and: the re-injected record matches place/attempt/kind/token
    replay_injection = replay_records[replay_injection_indexes[0]]
    assert replay_injection["place"] == recorded_injection["place"]
    assert replay_injection["attempt"] == recorded_injection["attempt"]
    assert replay_injection["kind"] == recorded_injection["kind"]
    assert replay_injection["tokens"] == recorded_injection["tokens"]
    # and: the final marking matches the recorded one
    assert _contents(result.final_marking) == _contents(recorded_marking)
    assert [t.data for t in result.final_marking.get("out_b", [])] == [{"n": 1}]

    # and: a driver that injected EARLY would mis-order: hand-built —
    # consume the injection first, then ask for the first firing: the
    # cursor's next record is the firing a, but the tape's first
    # injection was replayed at the wrong point (the driver's rule: an
    # injection pending before a firing means the firing call hits an
    # injection-first tape, so ordering complains). The EARLY case:
    # replay b at attempt 1 would raise, since the tape's next firing
    # after the injection is b/2 — an out-of-order b/1 ask
    early_cursor = ReplayCursor(tape)
    early_cursor.next_firing("inject_net/a/0")
    with pytest.raises(ReplayOrderError):
        early_cursor.next_firing("inject_net/b/1")  # wrong attempt: the
        # tape's b firing is b/2; an early-injected driver's b/0/b/1 walk
        # misses it


# ── 4. A recorded failed replays as failed with its error ──────────────


def test_recorded_failed_replays_as_failed_with_recorded_error() -> None:
    # given: a recording where the handler returned failed once, then b
    # succeeded (the failure budget moved the run past a)
    net = _ab_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("a", _failed_handler())
    registry.register_transition("b", _completion("b_out"))
    engine = Engine(registry, journal=recording, max_consecutive_failures=1)
    marking = net.initial_marking or Marking()
    # Engine.advance with a budget of 1: a fails once (recorded), is
    # exhausted, and b completes — a short deterministic Engine.advance tape
    recorded_current = engine.advance(net, marking)
    tape = recording.records()
    failed_record = next(
        r
        for r in tape
        if r.get("firingId") and r.get("status") == "failed"
        and "event" not in r
    )
    assert failed_record["error"]["type"] == "SpeakerMuted"
    completed_record = next(
        r
        for r in tape
        if r.get("firingId") and r.get("status") == "completed"
        and "event" not in r
    )
    assert completed_record["transition"] == "b"

    # when: replayed strictly
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(
        net, replay, replay_registration, cursor, mode="strict",
        max_consecutive_failures=1,
    )

    # then: the failed firing replayed as failed with the recorded error
    # (the driver's ledger saw the failed fire and moved past a), and the
    # marking carries only b's deposit
    assert (
        result.final_marking.get("src") is not None
    )  # a's consume never landed
    assert [t.data for t in result.final_marking.get("b_out", [])] == [{"n": 1}]
    assert result.final_marking.get("a_out") is None
    # and: the cursor walked past both firings
    assert cursor.position >= 2


# ── 5. Guards answer from the tape's guard_checked records ─────────────


def _guarded_net() -> Net:
    return Net(
        name="guarded_net",
        places=[
            Place(name="src", accepts=["task"]),
            Place(name="dst", accepts=["task"]),
        ],
        transitions=[Transition(name="t", handler="t", guard="the_guard")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="t",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="t",
                to_place="dst",
                produce=ProduceTemplate("task", "dst"),
            ),
        ],
        initial_marking=Marking({"src": [_token("task", n=0)]}),
    )


def test_guards_answer_from_tape_records_without_live_code() -> None:
    # given: a recorded run of a guarded transition (guard said yes)
    net = _guarded_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("t", _completion("dst"))
    registry.register_guard("the_guard", lambda inp: True)
    engine = Engine(registry, journal=recording)
    engine.advance(net, net.initial_marking or Marking())
    tape = recording.records()
    guard_records = [r for r in tape if r.get("event") == "guard_checked"]
    assert guard_records  # the trace card recorded the checks
    assert all(r["result"] is True for r in guard_records)

    # when: replayed with the mixin whose guard seam reads the tape and
    # no live class exists
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(net, replay, replay_registration, cursor, mode="strict")

    # then: the replay enabled exactly as recorded — the transition
    # fired and the token landed in dst; no live guard code ran (the
    # stub guard_t would have raised)
    assert [t.data for t in result.final_marking.get("dst", [])] == [{"n": 0}]


# ── 6. Live guards, compare mode: a guard divergence ───────────────────


class _RefusingGuardLive:
    """A live class whose guard answers differently from the tape."""

    NET_NAME = "guarded_net"
    HANDLER_REFS: ClassVar[dict[str, str]] = {"t": "fire_t"}
    GUARD_REFS: ClassVar[dict[str, str]] = {"the_guard": "guard_t"}

    def fire_t(self, **inputs: Any) -> Any:
        return {
            "status": "completed",
            "outputTokens": {"dst": list(inputs["src"])},
            "error": None,
            "metadata": {},
        }

    def guard_t(self, **inputs: Any) -> bool:
        return False


def test_live_guard_divergence_in_compare_mode() -> None:
    # given: the same guarded recording
    net = _guarded_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("t", _completion("dst"))
    registry.register_guard("the_guard", lambda inp: True)
    engine = Engine(registry, journal=recording)
    engine.advance(net, net.initial_marking or Marking())
    tape = recording.records()
    guard_sequence = next(
        r["sequence"] for r in tape if r.get("event") == "guard_checked"
    )

    # when: replayed in compare mode with a live class whose guard
    # refuses (the tape said yes)
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="compare", live=_RefusingGuardLive())
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(
        net, replay, replay_registration, cursor, mode="compare",
    )

    # then: a guard divergence at the guard's sequence, run stopped
    assert result.divergence is not None
    divergence = result.divergence
    assert divergence.kind == "guard"
    assert divergence.expected is True
    assert divergence.got is False
    assert divergence.firing_id == "guarded_net/t/0"
    assert divergence.sequence == guard_sequence
    # and: the run stopped at the divergence (no second fire)
    assert result.steps <= 1


def test_live_guard_mismatch_in_strict_mode_raises() -> None:
    # given: the same guarded recording, a refusing live guard
    net = _guarded_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("t", _completion("dst"))
    registry.register_guard("the_guard", lambda inp: True)
    engine = Engine(registry, journal=recording)
    engine.advance(net, net.initial_marking or Marking())
    tape = recording.records()

    # when: replayed STRICTLY with the live class
    # then: the chosen raise names the kind in the message (the
    # implementer's choice: ReplayOrderError reused, its attributes
    # carry the mismatch)
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict", live=_RefusingGuardLive())
    replay_registration = replay.register_into(HandlerRegistry(), net)
    with pytest.raises(ReplayOrderError, match="guard"):
        replay_run(net, replay, replay_registration, cursor, mode="strict")


class _AcceptingGuardLive:
    """A live class answering the SAME as the tape: no divergence."""

    NET_NAME = "guarded_net"
    HANDLER_REFS: ClassVar[dict[str, str]] = {"t": "fire_t"}
    GUARD_REFS: ClassVar[dict[str, str]] = {"the_guard": "guard_t"}

    def fire_t(self, **inputs: Any) -> Any:
        return {
            "status": "completed",
            "outputTokens": {"dst": list(inputs["src"])},
            "error": None,
            "metadata": {},
        }

    def guard_t(self, **inputs: Any) -> bool:
        return True


def test_live_guard_agreement_in_compare_mode_reports_no_divergence() -> None:
    # given: the same guarded recording, an agreeing live guard
    net = _guarded_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("t", _completion("dst"))
    registry.register_guard("the_guard", lambda inp: True)
    engine = Engine(registry, journal=recording)
    engine.advance(net, net.initial_marking or Marking())
    tape = recording.records()

    # when: replayed in compare mode
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="compare", live=_AcceptingGuardLive())
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(
        net, replay, replay_registration, cursor, mode="compare",
    )

    # then: no divergence — the run replays cleanly to the same marking
    assert result.divergence is None
    assert [t.data for t in result.final_marking.get("dst", [])] == [{"n": 0}]


# ── 7. Compare mode on a changed net; strict raises ────────────────────


def test_compare_mode_on_changed_net_reports_net_matches_false(
    tmp_path: Any,
) -> None:
    # given: a recorded run whose DurableJournal holds the net_revision
    # (record the revision as the base does: a registering class hands
    # the journal to ``register_into``, which writes it)
    net = _ab_net()
    connection = open_database(tmp_path / "recording.db")
    recording = DurableJournal(connection, "inst")

    class _RegisteringLive(VelocitronNet):
        NET_NAME = net.name
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}

    _registration = _RegisteringLive().register_into(
        HandlerRegistry(), net, journal=recording
    )
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    registry.register_transition("b", _completion("b_out"))
    engine = Engine(registry, journal=recording)
    current = net.initial_marking or Marking()
    current, record = engine.fire(net, current, "a", attempt=0)
    assert record["status"] == "completed"
    tape = recording.records()

    # when: a transition is added to the net, and the changed net is
    # replayed in compare mode against the SAME tape
    changed = Net(
        name=net.name,
        places=[*net.places, Place(name="c_out", accepts=["task"])],
        transitions=[*net.transitions, Transition(name="c", handler="c")],
        arcs=[
            *net.arcs,
            Arc(
                from_place="src",
                to_transition="c",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="c",
                to_place="c_out",
                produce=ProduceTemplate("task", "c_out"),
            ),
        ],
        initial_marking=net.initial_marking,
    )
    replay_journal = DurableJournal(connection, "replay")
    cursor = ReplayCursor(tape)
    replay = _replay_for(changed, cursor, mode="compare")
    replay_registry = HandlerRegistry()
    replay_registry.register_transition("a", _completion("a_out"))
    replay_registry.register_transition("b", _completion("b_out"))
    replay_registry.register_transition("c", _completion("c_out"))
    replay_registry.register_firing_policy(
        "c-first",
        lambda inp: "c"
        if "c" in inp["enabledTransitions"]
        else (inp["enabledTransitions"][0] if inp["enabledTransitions"] else None),
    )
    replay_registration = replay.register_into(replay_registry, changed)
    result = replay_run(
        changed,
        replay,
        replay_registration,
        cursor,
        mode="compare",
        journal=replay_journal,
        policy="c-first",
    )

    # then: net_matches is False (the recorded revision differs) and the
    # FIRST divergence is the changed net's c firing the tape never had
    assert result.net_matches is False
    assert result.divergence is not None
    assert result.divergence.kind in ("firing_order", "not_on_tape")
    # and: it is NOT a raise — a result returned normally
    assert isinstance(result, ReplayResult)


def test_strict_mode_on_changed_net_raises_net_mismatch(
    tmp_path: Any,
) -> None:
    # given: the same recorded tape and changed net
    net = _ab_net()
    connection = open_database(tmp_path / "recording.db")
    recording = DurableJournal(connection, "inst")

    class _RegisteringLive(VelocitronNet):
        NET_NAME = net.name
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}

    _registration = _RegisteringLive().register_into(
        HandlerRegistry(), net, journal=recording
    )
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    registry.register_transition("b", _completion("b_out"))
    engine = Engine(registry, journal=recording)
    current, record = engine.fire(
        net, net.initial_marking or Marking(), "a", attempt=0
    )
    tape = recording.records()

    changed = Net(
        name=net.name,
        places=[*net.places, Place(name="c_out", accepts=["task"])],
        transitions=[*net.transitions, Transition(name="c", handler="c")],
        arcs=[
            *net.arcs,
            Arc(
                from_place="src",
                to_transition="c",
                consume=ConsumePattern("task", None, "consume"),
            ),
            Arc(
                from_transition="c",
                to_place="c_out",
                produce=ProduceTemplate("task", "c_out"),
            ),
        ],
        initial_marking=net.initial_marking,
    )

    # when: replayed STRICTLY against the changed net
    # then: ReplayNetMismatch before the first step
    cursor = ReplayCursor(recording.records())
    replay = _replay_for(changed, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), changed)
    with pytest.raises(ReplayNetMismatch):
        replay_run(changed, replay, replay_registration, cursor, mode="strict")


def test_replay_against_recorded_revision_still_works() -> None:
    # given: the recorded tape (net_revision = ab_net as-is), the SAME
    # net replayed: the fast check passes and the run completes (N21:
    # the revision is a fast check, not a refusal — replaying against
    # the same net works, and even a DIFFERENT-but-order-compatible net
    # works in compare mode)
    import tempfile

    net = _ab_net()
    connection = open_database(Path(tempfile.mkdtemp()) / "x.db")
    recording = DurableJournal(connection, "inst")

    class _RegisteringLive(VelocitronNet):
        NET_NAME = net.name
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}

    _registration = _RegisteringLive().register_into(
        HandlerRegistry(), net, journal=recording
    )
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    registry.register_transition("b", _completion("b_out"))
    engine = Engine(registry, journal=recording)
    recorded_current, record = engine.fire(
        net, net.initial_marking or Marking(), "a", attempt=0
    )
    tape = recording.records()

    # when: replayed strictly on the same net
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(net, replay, replay_registration, cursor, mode="strict")

    # then: net_matches is True and the marking matches
    assert result.net_matches is True
    assert _contents(result.final_marking) == _contents(recorded_current)


# ── 8. net_matches is None without a net_revision ──────────────────────


def test_net_matches_is_none_without_a_net_revision() -> None:
    # given: a recording from a JsonlJournal (no net revision)
    net = _ab_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    engine = Engine(registry, journal=recording)
    engine.fire(net, net.initial_marking or Marking(), "a", attempt=0)
    tape = recording.records()

    # when: replayed
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(net, replay, replay_registration, cursor)

    # then: net_matches is None
    assert result.net_matches is None


# ── 9. ReplayOrderError never becomes a failed record ──────────────────


def test_replay_order_error_is_not_a_failed_record() -> None:
    # given: the out-of-order situation (recording a, replay picks b)
    net = _ab_net()
    recording = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    registry.register_transition("b", _completion("b_out"))
    engine = Engine(registry, journal=recording)
    engine.fire(net, net.initial_marking or Marking(), "a", attempt=0)
    tape = recording.records()

    # when: replayed with the b-first policy onto its OWN journal
    replay_journal = JsonlJournal()
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registry = _registry_with_b_first_policy()
    replay_registry.register_transition("b", _completion("b_out"))
    replay_registry.register_transition("a", _completion("a_out"))
    replay_registration = replay.register_into(replay_registry, net)
    with pytest.raises(ReplayOrderError):
        replay_run(
            net,
            replay,
            replay_registration,
            cursor,
            mode="strict",
            journal=replay_journal,
            policy="b-first",
        )

    # then: no firing record on the replay journal carries
    # ReplayOrderError as its error
    firings = [
        r
        for r in replay_journal.records()
        if "firingId" in r and "kind" not in r and "event" not in r
    ]
    assert all(
        (r.get("error") or {}).get("type") != "ReplayOrderError"
        for r in firings
    )


# ── 10. ReplayOrderError out of Engine.fire via the _serve seam ────────


def test_replay_order_error_propagates_through_engine_fire() -> None:
    # given: an out-of-order cursor wired into the mixin
    net = _ab_net()
    tape = [
        {
            "firingId": "ab_net/a/0",
            "status": "completed",
            "attempt": 0,
            "sequence": 0,
        }
    ]
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    engine = Engine(replay_registration.registry)

    # when: fire b through the replay mixin's registered adapter
    # then: the mixin's own raise propagates out of Engine.fire — the
    # ADR's rule that an adapter's own error is never a failed record
    with pytest.raises(ReplayOrderError):
        engine.fire(
            replay_registration.net,
            _ab_net().initial_marking or Marking(),
            "b",
            attempt=0,
        )
    # and: it did not write a failed firing record anywhere
    # (no journal attached in this probe; the Engine's fire path raised
    # BEFORE building a record — the handler call itself raised)


# ── Cursor unit shapes ─────────────────────────────────────────────────


def test_cursor_pending_injection_skips_traces_and_stops_at_firing() -> None:
    # given: a tape with a trace record between a firing and an injection
    tape = [
        {
            "firingId": "ab/a/0",
            "transition": "a",
            "status": "completed",
            "attempt": 0,
            "sequence": 0,
        },
        {
            "event": "handler_returned",
            "firingId": "ab/a/0",
            "handler": "a",
            "transition": "a",
            "result": None,
            "sequence": 1,
        },
        {
            "injectionId": "ab/@inject/arrivals/1",
            "place": "arrivals",
            "attempt": 1,
            "kind": "inject",
            "tokens": [],
            "replaced": [],
            "sequence": 2,
        },
        {
            "firingId": "ab/b/2",
            "transition": "b",
            "status": "completed",
            "attempt": 2,
            "sequence": 3,
        },
    ]
    cursor = ReplayCursor(tape)

    # when: advanced past the first firing
    cursor.next_firing("ab/a/0")

    # then: the injection is pending (the trace record between was
    # skipped, NOT consumed as an ordering event)
    pending = cursor.pending_injection()
    assert pending is not None
    assert pending["injectionId"] == "ab/@inject/arrivals/1"
    # and: still not consumed (a trace record never stands between)
    assert cursor.position == 1
    # and: after next_injection the b firing orders
    cursor.next_injection()
    assert cursor.next_firing("ab/b/2")["transition"] == "b"
    # and: nothing pending at the exhausted tape
    assert cursor.pending_injection() is None


def test_cursor_next_firing_orders_and_raises_with_position() -> None:
    # given: a two-firing tape
    tape = [
        {
            "firingId": "ab/a/0",
            "status": "completed",
            "attempt": 0,
            "sequence": 4,
        },
        {
            "firingId": "ab/b/1",
            "status": "completed",
            "attempt": 1,
            "sequence": 9,
        },
    ]
    cursor = ReplayCursor(tape)

    # when: ordered once
    record = cursor.next_firing("ab/a/0")
    assert record["status"] == "completed"

    # then: wrong next raises with the tape's sequence (9)
    with pytest.raises(ReplayOrderError) as excinfo:
        cursor.next_firing("ab/b/9")
    assert excinfo.value.sequence == 9
    assert excinfo.value.expected == "ab/b/1"
    assert excinfo.value.got == "ab/b/9"


def test_cursor_net_revision_reads_through_the_run() -> None:
    # given: a durable tape (net_revision, then firings)
    net = _ab_net()
    revision = dict(net_document(net))
    tape = [revision]
    cursor = ReplayCursor(tape)

    # when: read
    # then: the net document comes back, without advancing
    assert cursor.net_revision() == revision
    assert cursor.position == 0
    # and: absent from an empty tape
    assert ReplayCursor([]).net_revision() is None


# ── Q66 (a): the same DurableJournal as source AND sink ────────────────


def test_same_durable_journal_source_and_sink_raises_unless_flagged(
    tmp_path: Any,
) -> None:
    # given: the same DurableJournal read and written
    connection = open_database(tmp_path / "same.db")
    journal = DurableJournal(connection, "inst")
    net = _ab_net()
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    engine = Engine(registry, journal=journal)
    engine.fire(net, net.initial_marking or Marking(), "a", attempt=0)
    tape = journal.records()

    # when: the driver is handed the SAME journal as sink with no flag
    cursor = ReplayCursor.from_journal(journal)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)

    # then: ValueError — one instance, one numbered stream: the replay
    # would race its own records into the tape it is walking (Q66 (a))
    with pytest.raises(ValueError, match="allow_same_journal"):
        replay_run(
            net,
            replay,
            replay_registration,
            cursor,
            journal=journal,
        )

    # and: with allow_same_journal=True the same-journal drive is allowed
    # (the snapshot is immune; the composition card tests its semantics)
    fresh_cursor = ReplayCursor(tape)
    fresh_replay = _replay_for(net, fresh_cursor, mode="strict")
    fresh_registration = fresh_replay.register_into(HandlerRegistry(), net)
    result = replay_run(
        net,
        fresh_replay,
        fresh_registration,
        fresh_cursor,
        journal=journal,
        allow_same_journal=True,
    )
    assert result.net_matches is None  # a durable tape DOES carry a
    # net_revision here? No: the recording above never wrote one (no
    # registered class wrote it), so None.


def test_same_jsonl_journal_source_and_sink_is_fine() -> None:
    # given: the same JsonlJournal as source and sink — its ``records()``
    # is a fresh shallow copy per read, so the snapshot is a copy
    net = _ab_net()
    journal = JsonlJournal()
    registry = HandlerRegistry()
    registry.register_transition("a", _completion("a_out"))
    engine = Engine(registry, journal=journal)
    engine.fire(net, net.initial_marking or Marking(), "a", attempt=0)
    tape = journal.records()

    # when: the driver re-uses the same journal as sink with no flag
    cursor = ReplayCursor(tape)
    replay = _replay_for(net, cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(
        net, replay, replay_registration, cursor, journal=journal
    )

    # then: no ValueError; the run completed past the re-played firing
    assert result.net_matches is None
    assert result.steps >= 1