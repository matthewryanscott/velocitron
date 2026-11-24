"""Slice 12 CLI, visualization, and end-to-end reading-hour contracts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import pytest

from velocitron_petrinet import merge_composition
from velocitron_petrinet import compile_petrinet_text
from velocitron_cli import main as dsl_main
from velocitron_runtime import Engine
from velocitron_journal import JsonlJournal
from velocitron_petrinet import parse_composition
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
)
from velocitron_cli import viz_main


_REPOSITORY_ROOT = Path(__file__).parents[3]
_FIXTURE_ROOT = (
    _REPOSITORY_ROOT
    / "examples"
    / "capability-ladder"
    / "12-reading-hour-fragment"
)
_CADENCE_DSL = _FIXTURE_ROOT / "reading_cadence.petrinet"
_CADENCE_JSON = _FIXTURE_ROOT / "reading_cadence.json"
_CURATE_DSL = _FIXTURE_ROOT / "reading_pick.petrinet"
_CURATE_JSON = _FIXTURE_ROOT / "reading_pick.json"
_SPEAKS_DSL = _FIXTURE_ROOT / "reading_voice.petrinet"
_SPEAKS_JSON = _FIXTURE_ROOT / "reading_voice.json"
_COMPOSITION_DSL = _FIXTURE_ROOT / "reading_hour.petrinet"
_COMPOSITION_JSON = _FIXTURE_ROOT / "reading_hour.json"
_FIXTURE_JSON = _FIXTURE_ROOT / "reading_hour.test.json"
_HANDLERS_PATH = _FIXTURE_ROOT / "handlers.py"
_ALL_PAIRS = [
    (_CADENCE_DSL, _CADENCE_JSON, "net"),
    (_CURATE_DSL, _CURATE_JSON, "net"),
    (_SPEAKS_DSL, _SPEAKS_JSON, "net"),
    (_COMPOSITION_DSL, _COMPOSITION_JSON, "composition"),
]


def _document(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _compile(path: Path) -> dict[str, Any]:
    return compile_petrinet_text(path.read_text(encoding="utf-8"), str(path))


def _merged_from_dsl() -> Net:
    def load_net(ref: str) -> dict[str, Any]:
        return _compile(_FIXTURE_ROOT / ref)

    composition = cast(Any, parse_composition)(
        _compile(_COMPOSITION_DSL), origin=_FIXTURE_ROOT, net_loader=load_net
    )
    return merge_composition(composition)


def _merged_from_json() -> Net:
    composition = cast(Any, parse_composition)(
        _document(_COMPOSITION_JSON), origin=_FIXTURE_ROOT
    )
    return merge_composition(composition)


def _destinations(net: Net, transition: str) -> list[str]:
    return [
        cast(str, arc.to_place)
        for arc in net.arcs
        if arc.from_transition == transition and arc.produce is not None
    ]


def _registry(net: Net) -> HandlerRegistry:
    """Bind fixture factories to destinations resolved from this merged instance."""
    spec = importlib.util.spec_from_file_location(
        "reading_hour_handlers", _HANDLERS_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert _destinations(net, "cadence.on_tick") == [
        "cadence.tick_latch",
        "cadence.refresh_due_out",
    ]
    assert _destinations(net, "curate.curate") == ["curate.speak_request"]
    assert _destinations(net, "speaks.start") == [
        "speaks.in_flight",
        "speaks.work",
    ]
    assert _destinations(net, "speaks.finish") == ["speaks.utterance_out"]

    registry = HandlerRegistry()
    module.register_instance(
        registry,
        cadence_scope="cadence",
        curate_scope="curate",
        speaks_scope="speaks",
        latch_destination=_destinations(net, "cadence.on_tick")[0],
        refresh_due_destination=_destinations(net, "cadence.on_tick")[1],
        speak_request_destination=_destinations(net, "curate.curate")[0],
        in_flight_destination=_destinations(net, "speaks.start")[0],
        work_destination=_destinations(net, "speaks.start")[1],
        utterance_destination=_destinations(net, "speaks.finish")[0],
    )
    return registry


def _token(raw: dict[str, Any]) -> Token:
    return Token(type=raw["type"], data=raw["data"])


def _marking(raw: dict[str, Any]) -> Marking:
    return Marking(
        {
            place: [_token(cast(dict[str, Any], token)) for token in tokens]
            for place, tokens in raw.items()
        }
    )


def _plain_tokens(tokens: dict[str, list[Token]]) -> dict[str, list[dict[str, Any]]]:
    return {
        place: [{"type": token.type, "data": token.data} for token in values]
        for place, values in tokens.items()
    }


def _plain_marking(marking: Marking) -> dict[str, list[dict[str, Any]]]:
    return _plain_tokens(
        {place: list(tokens) for place, tokens in marking.items() if tokens}
    )


def _play_case() -> dict[str, Any]:
    return cast(dict[str, Any], _document(_FIXTURE_JSON)["cases"][0])


def _run(net: Net) -> tuple[list[dict[str, Any]], Marking, tuple[dict[str, Any], ...]]:
    play = _play_case()
    journal = JsonlJournal()
    engine = Engine(_registry(net), journal=journal, deposit_violation="raise")
    marking = _marking(play["initialMarking"])
    injection = play["injections"][0]
    marking, _ = engine.inject_token(
        net,
        marking,
        injection["place"],
        _token(injection["token"]),
        attempt=injection["attempt"],
        replace=injection["replace"],
    )
    final = engine.advance(net, marking, max_steps=play["maxSteps"])
    records = journal.records()
    # the firing channel only: injection records carry ``attempt`` too but
    # have a ``kind``; trace records (ADR 0058, Decision 6) carry neither
    # firingId nor kind and are excluded by the firingId check
    firings = [
        record
        for record in records
        if "attempt" in record and "kind" not in record
    ]
    return firings, final, records


def _stable_firing(record: dict[str, Any]) -> dict[str, Any]:
    # ``sequence`` is a stream slot trace rows interleave (ADR 0058, Decision
    # 6), so it is projected out; the ORDER of ``firings`` is already asserted.
    return {
        "transition": record["transition"],
        "status": record["status"],
        "attempt": record["attempt"],
        "inputTokens": _plain_tokens(record["inputTokens"]),
        "outputTokens": _plain_tokens(record["outputTokens"]),
        "error": record["error"],
        "metadata": record["metadata"],
    }


def test_cli_validates_and_converts_all_four_documents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Public CLI paths resolve portable refs and preserve each paired document."""
    for dsl_path, json_path, kind in _ALL_PAIRS:
        expected = _document(json_path)
        authored_expected = _document(json_path)
        if kind == "composition":
            for item in authored_expected["nets"]:
                item["ref"] = item["ref"].replace(".json", ".petrinet")

        assert dsl_main(["validate", str(dsl_path)]) == 0
        validated = capsys.readouterr()
        assert validated.out == f"{kind}\n" and validated.err == ""

        assert dsl_main(["to-json", str(dsl_path)]) == 0
        converted_json = capsys.readouterr()
        assert json.loads(converted_json.out) == authored_expected
        assert converted_json.err == ""

        assert dsl_main(["to-petrinet", str(json_path)]) == 0
        converted_dsl = capsys.readouterr()
        assert compile_petrinet_text(converted_dsl.out, str(dsl_path)) == expected
        assert converted_dsl.err == ""


def test_merged_visualization_exposes_the_complete_native_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Merged DOT keeps every native arc and boundary without synthetic routing."""
    assert viz_main([str(_COMPOSITION_DSL), "--merged"]) == 0
    dot = capsys.readouterr().out
    edges = [line for line in dot.splitlines() if " -> " in line]

    assert len(edges) == 14
    assert dot.count("shape=box") == 4
    for name in [
        "cadence.on_tick",
        "cadence.refresh_due_out",
        "curate.curate",
        "curate.speak_request",
        "speaks.start",
        "speaks.finish",
        "speaks.utterance_out",
    ]:
        assert name in dot
    # A fused place's copy is labeled with the member its transition's net
    # (and CEL) knows it by.
    for copy, label in [
        ("cadence.refresh_due_out@curate.curate", "curate.refresh_due_in"),
        ("curate.speak_request@speaks.start", "speaks.request_in"),
    ]:
        line = next(line for line in dot.splitlines() if f'"{copy}" [' in line)
        assert f"<b>{label}</b>" in line
    assert dot.count("arrowhead=odot") == 2
    assert 'color="#1f6feb", style=dashed' in dot
    assert "clock.now &gt;= latch.fired_at + latch.cadence_s" in dot
    assert "port output" in dot and "utterance" in dot
    assert dot.count('class="fusion"') >= 2


def test_clock_replacement_is_passive_then_enables_only_cadence() -> None:
    """Clock injection updates one internal token without an implicit scheduler step."""
    play = _play_case()
    net = _merged_from_dsl()
    journal = JsonlJournal()
    engine = Engine(_registry(net), journal=journal)
    before = _marking(play["initialMarking"])
    assert before == net.initial_marking
    assert (
        engine.enabled_transitions(net, before)
        == play["expectedEnabledTransitions"]
    )

    injection = play["injections"][0]
    after, record = engine.inject_token(
        net,
        before,
        injection["place"],
        _token(injection["token"]),
        attempt=injection["attempt"],
        replace=injection["replace"],
    )

    assert list(after["cadence.clock"]) == [Token("clock", {"now": 300})]
    assert list(after["cadence.tick_latch"]) == list(before["cadence.tick_latch"])
    assert record["kind"] == "update"
    assert record["place"] == "cadence.clock"
    assert (
        engine.enabled_transitions(net, after)
        == play["expectedEnabledTransitionsAfterInjection"]
    )
    assert len(journal.records()) == 1


def test_exact_four_firing_chain_drains_fusions_and_internal_window() -> None:
    """The timer drives Curate and Speaks to one re-exposed utterance."""
    play = _play_case()
    firings, final, records = _run(_merged_from_dsl())

    assert [
        {"transition": record["transition"], "status": record["status"]}
        for record in firings
    ] == play["expectedFiringSequence"]
    assert [
        (
            {"kind": record["kind"], "place": record["place"]}
            if "kind" in record
            else {"transition": record["transition"]}
        )
        # trace records share the numbered stream (ADR 0058, Decision 6) but
        # are not in the play's expectedJournalSequence: keep only the
        # firing/injection records (``attempt``) and compare by ORDER, because
        # interleaved trace rows shift absolute sequence values.
        for record in records
        if "attempt" in record
    ] == [
        # order-preserving shape: kind/place for injections, transition for firings
        {"kind": item["kind"], "place": item["place"]}
        if "kind" in item
        else {"transition": item["transition"]}
        for item in play["expectedJournalSequence"]
    ]
    assert [_stable_firing(record) for record in firings] == [
        {
            "transition": "cadence.on_tick",
            "status": "completed",
            "attempt": 0,
            "inputTokens": {
                "cadence.tick_latch": [
                    {"type": "tick_latch", "data": {"fired_at": 0, "cadence_s": 300}}
                ],
                "cadence.clock": [{"type": "clock", "data": {"now": 300}}],
            },
            "outputTokens": {
                "cadence.tick_latch": [
                    {"type": "tick_latch", "data": {"fired_at": 300, "cadence_s": 300}}
                ],
                "cadence.refresh_due_out": [
                    {"type": "refresh_due", "data": {"trigger": "tick"}}
                ],
            },
            "error": None,
            "metadata": {},
        },
        {
            "transition": "curate.curate",
            "status": "completed",
            "attempt": 1,
            "inputTokens": {
                "cadence.refresh_due_out": [
                    {"type": "refresh_due", "data": {"trigger": "tick"}}
                ]
            },
            "outputTokens": {
                "curate.speak_request": [
                    {"type": "speak_req", "data": {"trigger": "tick"}}
                ]
            },
            "error": None,
            "metadata": {},
        },
        {
            "transition": "speaks.start",
            "status": "completed",
            "attempt": 2,
            "inputTokens": {
                "curate.speak_request": [
                    {"type": "speak_req", "data": {"trigger": "tick"}}
                ]
            },
            "outputTokens": {
                "speaks.in_flight": [
                    {"type": "speak_token", "data": {"trigger": "tick"}}
                ],
                "speaks.work": [{"type": "speak_work", "data": {"trigger": "tick"}}],
            },
            "error": None,
            "metadata": {},
        },
        {
            "transition": "speaks.finish",
            "status": "completed",
            "attempt": 3,
            "inputTokens": {
                "speaks.work": [{"type": "speak_work", "data": {"trigger": "tick"}}],
                "speaks.in_flight": [
                    {"type": "speak_token", "data": {"trigger": "tick"}}
                ],
            },
            "outputTokens": {
                "speaks.utterance_out": [
                    {"type": "utterance", "data": {"trigger": "tick"}}
                ]
            },
            "error": None,
            "metadata": {},
        },
    ]
    assert _plain_marking(final) == play["expectedFinalMarking"]
    for drained in [
        "cadence.refresh_due_out",
        "curate.speak_request",
        "speaks.in_flight",
        "speaks.work",
    ]:
        assert not final.get(drained)


@pytest.mark.parametrize(
    ("stale_place", "stale_token"),
    [
        ("speaks.in_flight", Token("speak_token", {"trigger": "stale"})),
        ("speaks.work", Token("speak_work", {"trigger": "stale"})),
    ],
    ids=["in-flight", "work"],
)
def test_either_stale_internal_token_inhibits_speaks_start(
    stale_place: str, stale_token: Token
) -> None:
    """Each clean-start zero-test independently blocks a queued request."""
    net = _merged_from_dsl()
    engine = Engine(_registry(net))
    marking = _marking(_play_case()["initialMarking"])
    marking, _ = engine.inject_token(
        net,
        marking,
        "cadence.clock",
        Token("clock", {"now": 300}),
        attempt=0,
        replace=True,
    )
    marking = engine.advance(net, marking, max_steps=2)
    assert engine.enabled_transitions(net, marking) == ["speaks.start"]

    blocked = marking.set(stale_place, [stale_token])
    assert blocked.get("curate.speak_request")
    assert "speaks.start" not in engine.enabled_transitions(net, blocked)


def _enabled_sequence(net: Net) -> list[list[str]]:
    play = _play_case()
    engine = Engine(_registry(net), deposit_violation="raise")
    marking = _marking(play["initialMarking"])
    sequence = [engine.enabled_transitions(net, marking)]
    injection = play["injections"][0]
    marking, _ = engine.inject_token(
        net,
        marking,
        injection["place"],
        _token(injection["token"]),
        attempt=injection["attempt"],
        replace=injection["replace"],
    )
    sequence.append(engine.enabled_transitions(net, marking))
    for attempt in range(play["maxSteps"]):
        enabled = sequence[-1]
        assert len(enabled) == 1
        marking, record = engine.fire(net, marking, enabled[0], attempt=attempt)
        assert record["status"] == "completed"
        sequence.append(engine.enabled_transitions(net, marking))
    return sequence


def test_dsl_and_json_runs_have_identical_records_and_final_markings() -> None:
    """Both origins preserve opaque refs, enablement, firing, and token state."""
    dsl_net = _merged_from_dsl()
    json_net = _merged_from_json()
    expected_handlers = [
        "on_tick@cadence",
        "curate@curate",
        "start@speaks",
        "finish@speaks",
    ]
    assert [
        transition.handler for transition in dsl_net.transitions
    ] == expected_handlers
    assert [
        transition.handler for transition in json_net.transitions
    ] == expected_handlers

    assert (
        _enabled_sequence(dsl_net)
        == _enabled_sequence(json_net)
        == [
            [],
            ["cadence.on_tick"],
            ["curate.curate"],
            ["speaks.start"],
            ["speaks.finish"],
            [],
        ]
    )
    dsl_firings, dsl_final, dsl_records = _run(dsl_net)
    json_firings, json_final, json_records = _run(json_net)
    assert [_stable_firing(record) for record in dsl_firings] == [
        _stable_firing(record) for record in json_firings
    ]
    assert [
        (record.get("kind"), record.get("transition"))
        for record in dsl_records
        # trace rows share the numbered stream (ADR 0058, Decision 6): compare
        # the firing/injection membership in order, not absolute sequence
        if "attempt" in record
    ] == [
        (record.get("kind"), record.get("transition"))
        for record in json_records
        if "attempt" in record
    ]
    assert dsl_final == json_final
    assert _plain_marking(dsl_final) == _play_case()["expectedFinalMarking"]
