"""Replay inside a composition (the N20 card, ``bqj8BJFb``).

The composition replay contract, proven on the two-member wired_pulse
recording and the three-member reading_hour recording:

1. The member ``Replay<Member>`` instances share the ONE cursor the
   composition class owns (never copied, never reset): after a clean
   replay ``cursor.position`` equals the number of firing records on the
   merged tape, the final marking matches the recorded one, and no stub
   method was called.
2. An order change across members raises :class:`ReplayOrderError` out
   of ``replay_run`` in strict mode, naming expected/got qualified ids,
   whichever member raised.
3. In compare mode the divergence is reported ONCE, from the cursor
   (``cursor.divergence``), with the member's qualified transition in
   ``firing_id``.
4. Writing while reading, JsonlJournal: the recording journal object
   itself works as the replay's sink — the snapshot is a copy, so the
   recording's records stay intact and the replay appends after them.
5. Writing while reading, DurableJournal: the SAME instance as snapshot
   source and sink raises ``ValueError`` unless
   ``allow_same_journal=True``; with the flag the log holds
   recording-then-replay, and ``replay_events`` over the whole log
   CANNOT end at the recorded marking (documented why, test 5).
6. Nested (library_holds): the inner members share the same cursor.
   The mandated shape is documented at the test.

The hand-built composition classes here mirror the shape the generator
(the compositions card, ``Mywzh5HN``) will emit: a classmethod
``replay(cursor, *, mode="strict", live=None) -> <Name>Composition``
that builds one ``Replay<Member>`` per alias with the SAME cursor.
``replay_run`` takes the members as a ``Sequence[ReplayBase]`` (the
card's stated choice) and reads the divergence from the cursor.

References: ADR 0058 (Decision 7).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, ClassVar, Literal

from velocitron_engine import (
    FiringPolicyHandler,
    FiringPolicyInput,
)

import pytest

from velocitron_petrinet import merge_composition
from velocitron_petrinet import compile_petrinet_text
from velocitron_journal import (
    DurableJournal,
    open_database,
    read_events,
    replay_events,
)
from velocitron_runtime import Engine
from velocitron_journal import JsonlJournal
from velocitron_netbase import (
    Registration,
    VelocitronNet,
    net_sha256,
)
from velocitron_petrinet import (
    parse_composition,
    parse_net,
)
from velocitron_engine import HandlerRegistry
from velocitron_replay import (
    ReplayBase,
    ReplayCursor,
    ReplayOrderError,
    replay_run,
)
from velocitron_engine import (
    Marking,
    Token,
)

_REPOSITORY_ROOT = Path(__file__).parents[3]
_PULSE_ROOT = _REPOSITORY_ROOT / "examples" / "capability-ladder" / "10-wired-pulse"
_READING_HOUR_ROOT = (
    _REPOSITORY_ROOT
    / "examples"
    / "capability-ladder"
    / "12-reading-hour-fragment"
)
_GOLDEN = (
    _REPOSITORY_ROOT
    / "implementations/python/tests/fixtures/codegen/golden"
)


def _token(raw: dict[str, Any]) -> Token:
    return Token(type=raw["type"], data=dict(raw["data"]))


def _marking(raw: dict[str, Any]) -> Marking:
    return Marking(
        {
            place: [_token(raw_token) for raw_token in tokens]
            for place, tokens in raw.items()
        }
    )


def _contents(marking: Marking) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    return {
        place: [(token.type, dict(token.data)) for token in tokens]
        for place, tokens in marking.items()
    }


def _pulse_registry() -> HandlerRegistry:
    """The wired_pulse fixture handlers bound to the merged destinations."""
    spec = importlib.util.spec_from_file_location(
        "replay_comp_wp_handlers", _PULSE_ROOT / "handlers.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = HandlerRegistry()
    module.register_instance(
        registry,
        pulse_destination="source.pulse_out",
        receipt_destination="sink.received",
    )
    return registry


def _merged_pulse() -> Any:
    """The merged wired_pulse Net."""
    def compile_doc(path: Path) -> dict[str, Any]:
        return compile_petrinet_text(path.read_text(encoding="utf-8"), str(path))

    document = compile_doc(_PULSE_ROOT / "wired_pulse.petrinet")
    composition = parse_composition(
        document,
        origin=_PULSE_ROOT,
        net_loader=lambda ref: compile_doc(_PULSE_ROOT / ref),
    )
    return merge_composition(composition)


def _pulse_member_nets() -> dict[str, Any]:
    return {
        "source": parse_net(
            json.loads((_PULSE_ROOT / "pulse_source.json").read_text(encoding="utf-8"))
        ),
        "sink": parse_net(
            json.loads((_PULSE_ROOT / "pulse_sink.json").read_text(encoding="utf-8"))
        ),
    }


# ── Wired pulse: the two-member composition (the proof shape) ──────────


class _ReplayPulseSource(ReplayBase):
    """The pulse_source replay member: stubs so ANY real call fails the test."""

    NET_NAME = "pulse_source"
    SOURCE = "10-wired-pulse/pulse_source.petrinet"
    HANDLER_REFS: ClassVar[dict[str, str]] = {"emit@source": "fire_emit"}
    GUARD_REFS: ClassVar[dict[str, str]] = {}
    PREDICATE_REFS: ClassVar[dict[str, str]] = {}
    GENERATED_METHODS: ClassVar[dict[str, str]] = {}
    INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"emit": ("seed",)}
    OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"emit": ("pulse_out",)}
    ASYNC: ClassVar[bool] = False

    def fire_emit(self, seed: list[Any]) -> dict[str, list[Any]]:
        raise AssertionError("replay never calls fire_emit")


class _ReplayPulseSink(ReplayBase):
    """The pulse_sink replay member."""

    NET_NAME = "pulse_sink"
    SOURCE = "10-wired-pulse/pulse_sink.petrinet"
    HANDLER_REFS: ClassVar[dict[str, str]] = {"receive@sink": "fire_receive"}
    GUARD_REFS: ClassVar[dict[str, str]] = {}
    PREDICATE_REFS: ClassVar[dict[str, str]] = {}
    GENERATED_METHODS: ClassVar[dict[str, str]] = {}
    INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"receive": ("pulse_in",)}
    OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"receive": ("received",)}
    ASYNC: ClassVar[bool] = False

    def fire_receive(self, pulse_in: list[Any]) -> dict[str, list[Any]]:
        raise AssertionError("replay never calls fire_receive")


def _make_replay_pulse_source() -> tuple[type[_ReplayPulseSource], type[_ReplayPulseSink]]:
    """The source member class with its member-file hash bound (parsed once)."""
    member_nets = _pulse_member_nets()
    source_sha = net_sha256(member_nets["source"])
    sink_sha = net_sha256(member_nets["sink"])

    class _Source(_ReplayPulseSource):
        SOURCE_SHA256 = source_sha

    class _Sink(_ReplayPulseSink):
        SOURCE_SHA256 = sink_sha

    return _Source, _Sink


class WiredPulseComposition:
    """The hand-built composition under test: mirrors the generated shape.

    ``replay(cursor, *, mode, live)`` builds one replay member per alias
    with the SAME cursor (N20: the composition owns the tape's one
    reader), ``build_registry`` registers both members into one registry,
    and the merged ``Registration`` comes from one outer net base making
    the merged copy — the composition class's own job once the generator
    emits it.
    """

    def __init__(self, source: Any, sink: Any, cursor: ReplayCursor) -> None:
        self.source = source
        self.sink = sink
        self.cursor = cursor
        self.members: tuple[ReplayBase, ...] = (source, sink)

    @classmethod
    def replay(
        cls,
        cursor: ReplayCursor,
        *,
        mode: Literal["strict", "compare"] = "strict",
        live: Any | None = None,
    ) -> WiredPulseComposition:
        source_cls, sink_cls = _make_replay_pulse_source()
        return cls(
            source_cls(cursor, mode=mode, live=live),
            sink_cls(cursor, mode=mode, live=live),
            cursor,
        )

    def build_registry(self, merged: Any) -> HandlerRegistry:
        registry = HandlerRegistry()
        self.source.register_into(registry, merged, alias="source", validate=False)
        self.sink.register_into(registry, merged, alias="sink", validate=False)
        return registry


def _merged_registration(net: Any, journal: Any | None = None) -> Registration:
    """The composition's Registration: one outer base makes the merged copy.

    The generated composition class does this itself (ADR 0058 Decision 4,
    "the outermost class makes the net copy and builds the one registry");
    the hand-built test spells the same steps through a small ``VelocitronNet``
    subclass carrying only the merged hash.
    """

    class _Outer(VelocitronNet):
        NET_NAME = net.name
        SOURCE = "in-code"
        SOURCE_SHA256 = net_sha256(net)
        HANDLER_REFS: ClassVar[dict[str, str]] = {}
        GUARD_REFS: ClassVar[dict[str, str]] = {}
        PREDICATE_REFS: ClassVar[dict[str, str]] = {}
        GENERATED_METHODS: ClassVar[dict[str, str]] = {}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
        ASYNC: ClassVar[bool] = False

    return _Outer().register_into(HandlerRegistry(), net, journal=journal)


def _record_pulse(
    recording: Any,
) -> tuple[Any, Any, Any, dict[str, Any]]:
    """One recorded wired_pulse run: (merged net, initial, final marking, tape)."""
    net = _merged_pulse()
    play = json.loads(
        (_PULSE_ROOT / "wired_pulse.test.json").read_text(encoding="utf-8")
    )["cases"][0]
    initial = _marking(play["initialMarking"])
    _merged_registration(net, journal=recording)  # writes the net revision
    engine = Engine(_pulse_registry(), journal=recording)
    final = engine.advance(net, initial, max_steps=play["maxSteps"])
    tape = recording.records()
    return net, initial, final, tape


def _firing_ids(records: Any) -> list[str]:
    """The firing-channel ids of a numbered-stream recording."""
    return [
        record["firingId"]
        for record in records
        if "firingId" in record
        and "kind" not in record
        and "event" not in record
    ]


def _merged_library_holds() -> Any:
    """The merged library_holds Net (the nested composition fixture).

    Test 6's subject: the compositions lane's generated classes replay
    this two-level composition.
    """
    fixture = _REPOSITORY_ROOT / "implementations" / "python" / "tests" / "fixtures" / "codegen" / "library_holds"

    def compile_doc(path: Path) -> dict[str, Any]:
        return compile_petrinet_text(path.read_text(encoding="utf-8"), str(path))

    composition = parse_composition(
        compile_doc(fixture / "library-holds.petrinet"),
        origin=fixture,
        net_loader=lambda ref: compile_doc(fixture / ref),
    )
    return merge_composition(composition)


# ── The reading_hour composition (three members) ──────────────────


def _reading_hour_merged() -> tuple[Any, dict[str, Any]]:
    """The merged reading_hour Net and its member nets by alias."""
    def compile_doc(path: Path) -> dict[str, Any]:
        return compile_petrinet_text(path.read_text(encoding="utf-8"), str(path))

    composition = parse_composition(
        compile_doc(_READING_HOUR_ROOT / "reading_hour.petrinet"),
        origin=_READING_HOUR_ROOT,
        net_loader=lambda ref: compile_doc(_READING_HOUR_ROOT / ref),
    )
    net = merge_composition(composition)
    members = {
        "cadence": parse_net(
            json.loads(
                (_READING_HOUR_ROOT / "reading_cadence.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
        "curate": parse_net(
            json.loads(
                (_READING_HOUR_ROOT / "reading_pick.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
        "speaks": parse_net(
            json.loads(
                (_READING_HOUR_ROOT / "reading_voice.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
    }
    return net, members


def _reading_hour_registry() -> HandlerRegistry:
    spec = importlib.util.spec_from_file_location(
        "replay_comp_gg_handlers", _READING_HOUR_ROOT / "handlers.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    net = _reading_hour_merged()[0]

    def destinations(transition: str) -> list[str]:
        return [
            arc.to_place
            for arc in net.arcs
            if arc.from_transition == transition and arc.produce is not None
        ]

    registry = HandlerRegistry()
    module.register_instance(
        registry,
        cadence_scope="cadence",
        curate_scope="curate",
        speaks_scope="speaks",
        latch_destination=destinations("cadence.on_tick")[0],
        refresh_due_destination=destinations("cadence.on_tick")[1],
        speak_request_destination=destinations("curate.curate")[0],
        in_flight_destination=destinations("speaks.start")[0],
        work_destination=destinations("speaks.start")[1],
        utterance_destination=destinations("speaks.finish")[0],
    )
    return registry


def _record_reading_hour_with_mid_tape_tick() -> tuple[Any, Any, Any]:
    """A recording whose tape holds a cadence firing BETWEEN two speaks
    firings: on_tick, curate, start, [clock 600 update], on_tick, finish.

    The clock update is injected manually between the fire calls
    (``Engine.advance`` cannot inject mid-run), which is exactly the
    environment-arrival shape the injection tape exists for.
    """
    net, _members = _reading_hour_merged()
    play = json.loads(
        (_READING_HOUR_ROOT / "reading_hour.test.json").read_text(
            encoding="utf-8"
        )
    )["cases"][0]
    initial = _marking(play["initialMarking"])
    journal = JsonlJournal()
    _merged_registration(net, journal=journal)  # the net revision
    engine = Engine(_reading_hour_registry(), journal=journal, deposit_violation="raise")
    marking = initial
    marking, _ = engine.inject_token(
        net, marking, "cadence.clock", Token("clock", {"now": 300}),
        attempt=0, replace=True,
    )
    for name, attempt in (
        ("cadence.on_tick", 1),
        ("curate.curate", 2),
        ("speaks.start", 3),
    ):
        marking, record = engine.fire(net, marking, name, attempt=attempt)
        assert record["status"] == "completed"
    marking, _ = engine.inject_token(
        net, marking, "cadence.clock", Token("clock", {"now": 600}),
        attempt=4, replace=True,
    )
    marking, record = engine.fire(net, marking, "cadence.on_tick", attempt=5)
    assert record["status"] == "completed"
    marking, record = engine.fire(net, marking, "speaks.finish", attempt=6)
    assert record["status"] == "completed"
    return net, initial, journal


class _ReadingHourComposition:
    """The three-member hand-built composition, same mandated shape."""

    def __init__(self, cadence: Any, curate: Any, speaks: Any, cursor: ReplayCursor):
        self.cadence = cadence
        self.curate = curate
        self.speaks = speaks
        self.cursor = cursor
        self.members: tuple[ReplayBase, ...] = (cadence, curate, speaks)

    @classmethod
    def replay(
        cls,
        cursor: ReplayCursor,
        *,
        mode: Literal["strict", "compare"] = "strict",
        live: Any | None = None,
    ) -> _ReadingHourComposition:
        _net, members = _reading_hour_merged()
        hashes = {alias: net_sha256(member) for alias, member in members.items()}

        class _Cadence(ReplayBase):
            NET_NAME = "reading_cadence"
            SOURCE = "in-code"
            SOURCE_SHA256 = hashes["cadence"]
            HANDLER_REFS: ClassVar[dict[str, str]] = {"on_tick@cadence": "fire_on_tick"}
            INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
                "on_tick": ("tick_latch", "clock")
            }
            OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
                "on_tick": ("tick_latch", "refresh_due_out")
            }

            def fire_on_tick(self, *a: Any, **k: Any) -> dict[str, list[Any]]:
                raise AssertionError("replay never calls fire_on_tick")

        class _Curate(ReplayBase):
            NET_NAME = "reading_pick"
            SOURCE = "in-code"
            SOURCE_SHA256 = hashes["curate"]
            HANDLER_REFS: ClassVar[dict[str, str]] = {"curate@curate": "fire_curate"}
            INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
                "curate": ("refresh_due_in",)
            }
            OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
                "curate": ("speak_request",)
            }

            def fire_curate(self, *a: Any, **k: Any) -> dict[str, list[Any]]:
                raise AssertionError("replay never calls fire_curate")

        class _Speaks(ReplayBase):
            NET_NAME = "reading_voice"
            SOURCE = "in-code"
            SOURCE_SHA256 = hashes["speaks"]
            HANDLER_REFS: ClassVar[dict[str, str]] = {
                "start@speaks": "fire_start",
                "finish@speaks": "fire_finish",
            }
            INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
                "start": ("request_in",),
                "finish": ("work", "in_flight"),
            }
            OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {
                "start": ("in_flight", "work"),
                "finish": ("utterance_out",),
            }

            def fire_start(self, *a: Any, **k: Any) -> dict[str, list[Any]]:
                raise AssertionError("replay never calls fire_start")

            def fire_finish(self, *a: Any, **k: Any) -> dict[str, list[Any]]:
                raise AssertionError("replay never calls fire_finish")

        return cls(
            _Cadence(cursor, mode=mode, live=live),
            _Curate(cursor, mode=mode, live=live),
            _Speaks(cursor, mode=mode, live=live),
            cursor,
        )

    def build_registry(self, merged: Any) -> HandlerRegistry:
        registry = HandlerRegistry()
        self.cadence.register_into(registry, merged, alias="cadence", validate=False)
        self.curate.register_into(registry, merged, alias="curate", validate=False)
        self.speaks.register_into(registry, merged, alias="speaks", validate=False)
        return registry


def _finish_first_policy() -> FiringPolicyHandler:
    """Reorders the walk: speaks.finish before everything else it sees."""

    def policy(inp: FiringPolicyInput) -> str | None:
        enabled = inp["enabledTransitions"]
        for name in ("speaks.finish", "speaks.start", "curate.curate"):
            if name in enabled:
                return name
        return enabled[0] if enabled else None

    return policy


def _run_reading_hour_replay(
    cursor: ReplayCursor,
    *,
    mode: Literal["strict", "compare"],
    policy: FiringPolicyHandler | None,
    journal: Any,
) -> Any:
    net, _members = _reading_hour_merged()
    composition = _ReadingHourComposition.replay(cursor, mode=mode)
    registration = _merged_registration(net)
    merged_registry: HandlerRegistry = registration.registry  # type: ignore[assignment]
    member_registry = composition.build_registry(net)
    for name, handler in member_registry._transitions.items():
        merged_registry.register_transition(name, handler)
    for name, handler in member_registry._guards.items():
        merged_registry.register_guard(name, handler)
    for name, handler in member_registry._predicates.items():
        merged_registry.register_predicate(name, handler)
    if policy is not None:
        merged_registry.register_firing_policy("test-reorder", policy)
    play = json.loads(
        (_READING_HOUR_ROOT / "reading_hour.test.json").read_text(
            encoding="utf-8"
        )
    )["cases"][0]
    return replay_run(
        net,
        composition.members,
        registration,
        cursor,
        mode=cast_mode(mode),
        journal=journal,
        marking=_marking(play["initialMarking"]),
        policy="test-reorder" if policy is not None else "first-found",
    )


def cast_mode(mode: str) -> Any:
    return mode  # the literal narrows at the call sites


# ══ Tests ═══════════════════════════════════════════════════════════════

def test_wired_pulse_replay_shares_one_cursor_and_reaches_recorded_marking() -> None:
    # given: a recorded merged Engine.advance over wired_pulse
    recording = JsonlJournal()
    net, initial, recorded_marking, tape = _record_pulse(recording)
    assert _firing_ids(tape) == [
        "wired_pulse/source.emit/0",
        "wired_pulse/sink.receive/1",
    ]

    # when: one cursor is built and the composition's replay helper hands
    # that SAME object to both members (never copied, never reset)
    cursor = ReplayCursor.from_journal(recording, owner="wired_pulse")
    composition = WiredPulseComposition.replay(cursor)
    assert composition.source.cursor is cursor
    assert composition.sink.cursor is cursor

    # and: replayed through ONE driver: the members in alias order, the
    # composition's merged registration
    registration = _merged_registration(net)
    merged_registry: HandlerRegistry = registration.registry  # type: ignore[assignment]
    member_registry = composition.build_registry(net)
    for name, handler in member_registry._transitions.items():
        merged_registry.register_transition(name, handler)
    replay_journal = JsonlJournal()
    result = replay_run(
        net,
        composition.members,
        registration,
        cursor,
        mode="strict",
        journal=replay_journal,
        marking=initial,
    )

    # then: the same final marking ...
    assert _contents(result.final_marking) == _contents(recorded_marking)
    # and: the two members shared the cursor and walked the whole tape:
    # position ends PAST the last firing record, at the tape's end; the
    # ordering walk skips interleaved non-firing records (trace, and now
    # the net revision a register_into on a JsonlJournal writes) without
    # stopping.
    assert cursor.position == len(tape)
    assert result.steps == 2
    # and: no stub method was called (any call would have raised the
    # AssertionError "replay never calls ...")
    assert _firing_ids(replay_journal.records()) == _firing_ids(tape)

# ── 2. Order error across members (strict) ─────────────────────────────


def test_order_error_across_members_names_qualified_ids() -> None:
    # given: a reading-hour recording with cadence between the two speaks
    # firings, replayed with a policy that reorders them (finish first —
    # the SPEAKS member is the one the Engine's reordered choice runs
    # through, and its cursor ask misses the tape's cadence firing)
    net, _initial, journal = _record_reading_hour_with_mid_tape_tick()
    tape = journal.records()
    recorded_ids = _firing_ids(tape)
    assert recorded_ids.index("reading_hour/cadence.on_tick/5") > recorded_ids.index(
        "reading_hour/speaks.start/3"
    ) and recorded_ids.index("reading_hour/cadence.on_tick/5") < recorded_ids.index(
        "reading_hour/speaks.finish/6"
    )

    # when: replayed strictly with the reordering policy
    cursor = ReplayCursor.from_journal(journal, owner="reading_hour")
    composition = _ReadingHourComposition.replay(cursor)
    registration = _merged_registration(net)
    merged_registry: HandlerRegistry = registration.registry  # type: ignore[assignment]
    member_registry = composition.build_registry(net)
    for name, handler in member_registry._transitions.items():
        merged_registry.register_transition(name, handler)
    for name, handler in member_registry._guards.items():
        merged_registry.register_guard(name, handler)
    merged_registry.register_firing_policy("test-reorder", _finish_first_policy())
    with pytest.raises(ReplayOrderError) as excinfo:
        replay_run(
            net,
            composition.members,
            registration,
            cursor,
            mode="strict",
            policy="test-reorder",
        )

    # then: the error names the expected and got QUALIFIED ids —
    # whichever member raised it, the ids spell the composition member
    error = excinfo.value
    assert error.expected == "reading_hour/cadence.on_tick/5"
    assert error.got == "reading_hour/speaks.finish/5"
    # and: the owner stamp names the composition (the card's ``owner``
    # is for error messages only)
    assert error.owner == "reading_hour"


# ── 3. Compare mode across members: one divergence, from the cursor ────


def test_compare_mode_divergence_reported_once_from_cursor() -> None:
    # given: the same mid-tape-tick reading-hour recording
    _net, _initial, journal = _record_reading_hour_with_mid_tape_tick()

    # when: replayed in compare mode with the reordering policy
    result = _run_reading_hour_replay(
        ReplayCursor.from_journal(journal),
        mode="compare",
        policy=_finish_first_policy(),
        journal=JsonlJournal(),
    )

    # then: the divergence is the member's firing_order break, reported
    # ONCE — the CURSOR holds it (whichever member hit it), and the
    # result carries exactly it; the firing_id names the member's
    # qualified transition
    divergence = result.divergence
    assert divergence is not None
    assert divergence.kind == "firing_order"
    assert divergence.expected == "reading_hour/cadence.on_tick/5"
    assert divergence.firing_id == "reading_hour/speaks.finish/5"
    # and: the run stopped at the divergence — the steps it kept going
    # are the replayed prefix (injection, on_tick, curate, start) that
    # matched the tape BEFORE the reordered finish missed
    assert divergence.sequence is not None
    assert result.steps == 4


# ── 4. Writing while reading, JsonlJournal: the same object as sink ────


def test_jsonl_same_journal_as_source_and_sink_appends_after() -> None:
    # given: a wired_pulse recording in a JsonlJournal; the REPLAY takes
    # that SAME journal object as its sink (a JsonlJournal snapshot is a
    # fresh copy per read, so this is safe without a flag — Q66 (a)'s
    # decided reading)
    recording = JsonlJournal()
    net, initial, recorded_marking, tape = _record_pulse(recording)
    recorded_count = len(recording.records())
    recorded_ids = _firing_ids(tape)

    # when: replayed with the SAME journal as the sink
    cursor = ReplayCursor.from_journal(recording)
    composition = WiredPulseComposition.replay(cursor)
    registration = _merged_registration(net)
    merged_registry: HandlerRegistry = registration.registry  # type: ignore[assignment]
    member_registry = composition.build_registry(net)
    for name, handler in member_registry._transitions.items():
        merged_registry.register_transition(name, handler)
    result = replay_run(
        net,
        composition.members,
        registration,
        cursor,
        mode="strict",
        journal=recording,  # the recording journal object itself
        marking=initial,
    )

    # then: no ValueError, the replay reached the recorded marking ...
    assert _contents(result.final_marking) == _contents(recorded_marking)
    # and: the recording's records are INTACT (same ids, same count, in
    # the same order) and the replay appended its own after them (the
    # replay's own register_into here writes no second net revision on
    # the RECORDING's tape: only the sink's records are appended, and
    # the recorded count already includes the recording's net revision)
    whole = recording.records()
    assert _firing_ids(whole[:recorded_count]) == recorded_ids
    assert _firing_ids(whole[recorded_count:]) == recorded_ids
    # the replay appends its own net revision here (replay_run's
    # register_into wrote one on the same sink stream), so the whole
    # tape is one net revision + 2 firings + traces SHORT of a second
    # full copy of the recording's 7 records: 13, not 14
    assert len(whole) == 2 * recorded_count - 1


# ── 5. Writing while reading, DurableJournal: the guarded same instance ─


def test_durable_same_journal_refused_unless_flagged(tmp_path: Any) -> None:
    # given: a wired_pulse recording in a DurableJournal (its net revision
    # rides the same instance); the same instance read back as the tape
    connection = open_database(tmp_path / "same-journal.db")
    recording = DurableJournal(connection, "inst")
    net, initial, recorded_marking, _tape = _record_pulse(recording)
    recorded_count = len(recording.records())

    # when: the driver is handed the SAME instance as the sink, no flag
    # then: ValueError — the sqlite journal re-reads live, so the
    # snapshot is not immune to the replay's own rows
    cursor = ReplayCursor.from_journal(recording)
    composition = WiredPulseComposition.replay(cursor)
    registration = _merged_registration(net)
    merged_registry: HandlerRegistry = registration.registry  # type: ignore[assignment]
    member_registry = composition.build_registry(net)
    for name, handler in member_registry._transitions.items():
        merged_registry.register_transition(name, handler)
    with pytest.raises(ValueError, match="allow_same_journal"):
        replay_run(
            net,
            composition.members,
            registration,
            cursor,
            journal=recording,
            marking=initial,
        )

    # and: with allow_same_journal=True the same-instance drive is
    # allowed; with the flag, the log now holds recording-then-replay.
    # ``replay_events`` over the WHOLE log does NOT end at the recorded
    # marking, and that is expected: the replay's completed firings
    # re-apply consumed inputs and re-deposit outputs (the whole-log
    # rebuild counts the recording's effects AND the replay's again —
    # two receipts for wired_pulse). The recorded marking is recovered
    # from the recording prefix alone, not from the combined log; a
    # replay that must rebuild state from a sqlite log reads up to the
    # recording's end, not past it.
    result = replay_run(
        net,
        composition.members,
        registration,
        cursor,
        journal=recording,
        marking=initial,
        allow_same_journal=True,
    )
    assert _contents(result.final_marking) == _contents(recorded_marking)
    whole_log = read_events(connection, "inst")
    assert len(whole_log) > recorded_count  # the replay appended
    whole_log_marking = replay_events(net, whole_log)
    recorded_prefix_marking = replay_events(net, whole_log[:recorded_count])
    # documented, not asserted equal: the whole-log rebuild carries the
    # replay's re-appended effects (here: a SECOND receipt token)
    assert _contents(recorded_prefix_marking) == _contents(recorded_marking)
    assert _contents(whole_log_marking) != _contents(recorded_marking)


# ── 6. Nested (library_holds): inner members share the same cursor ────


def test_library_holds_nested_members_share_the_cursor() -> None:
    # given: the compositional golden imported as a real module (its
    # members package resolves through the goldens' `velocitron_nets`)
    sys.path.insert(0, str(_GOLDEN))
    try:
        import velocitron_nets.library_holds as holds_mod
    finally:
        sys.path.remove(str(_GOLDEN))

    # and: a recorded library_holds run on the merged net
    net = _merged_library_holds()
    recording = JsonlJournal()
    _merged_registration(net, journal=recording)
    cursor = ReplayCursor.from_journal(recording, owner="library_holds")

    # when: `LibraryHoldsComposition.replay(cursor)` builds the nested
    # replay composition — one Replay<Net> per alias, sharing the cursor
    composition = holds_mod.LibraryHoldsComposition.replay(cursor)

    # then: every LEAF replay member — the outer composition's own
    # leaf members (attempt, processing), and the inner composition's
    # members (the nested lifecycle's five) — holds the ONE cursor
    # object (identity, not equality). The inner composition object
    # itself is a non-leaf member (no cursor; the cursor-sharing drive
    # is its members', tests 1-5 prove it) — it is skipped here.
    outer_leafs = [
        member
        for member in composition.members
        if isinstance(member, ReplayBase)
    ]
    inner_leafs = [
        member
        for member in composition.lifecycle.members
        if isinstance(member, ReplayBase)
    ]
    assert len(outer_leafs) == 2  # attempt, processing
    assert len(inner_leafs) == 5  # start, gate, outcome, again, newer_run
    assert all(member.cursor is cursor for member in (*outer_leafs, *inner_leafs))
