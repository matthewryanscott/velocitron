"""Checking plays: resolution (SC2xx) and symbolic-firing playback (SC3xx).

Every step plays through the real engine: injections through
``inject_token(s)``, firings through ``reserve`` + ``settle`` with outputs
from the net, the step, or the carry rule.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from velocitron_engine import (
    GuardHandlerInput,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_journal import (
    FiringRecord,
    InjectionRecord,
)
from velocitron_play import (
    PlayError,
    read_play,
)
from velocitron_play_check import (
    PlayReport,
    check_play,
    trace_json,
)
from velocitron_engine import Token


def _firing(record: FiringRecord | InjectionRecord) -> FiringRecord:
    assert "firingId" in record
    return record


def _injection(record: FiringRecord | InjectionRecord) -> InjectionRecord:
    assert "injectionId" in record
    return record


_FIXTURES = Path(__file__).parent / "fixtures" / "play"
_HEADER = 'play s\nnet "shop.petrinet"\n'


def _play_case(tmp_path: Path, body: str, header: str = _HEADER) -> Path:
    shutil.copy(_FIXTURES / "shop.petrinet", tmp_path / "shop.petrinet")
    path = tmp_path / "s.play"
    path.write_text(header + body, encoding="utf-8")
    return path


def _check(tmp_path: Path, body: str, header: str = _HEADER) -> PlayReport:
    return check_play(read_play(_play_case(tmp_path, body, header)))


def _resolve_error(tmp_path: Path, body: str, header: str = _HEADER) -> PlayError:
    with pytest.raises(PlayError) as caught:
        _check(tmp_path, body, header)
    return caught.value


def _failure_code(report: PlayReport) -> str:
    (diagnostic,) = report.diagnostics()
    return diagnostic.code


def _tok(color: str, **data: object) -> Token:
    return Token(color, dict(data))


_O1 = _tok("purchase", id="o-1", sku="a", dueAt=100)


# ── Firing and outputs ───────────────────────────────────────────────────


def test_carry_rule_moves_the_one_consumed_token(tmp_path: Path) -> None:
    # when: accept consumes one purchase and produces one purchase
    report = _check(
        tmp_path,
        "fire [accept]\nexpect (accepted) == $o1\n"
        + '$o1: purchase {"id": "o-1", "sku": "a", "dueAt": 100}\n',
    )

    # then: the purchase carried over unchanged
    (trace,) = report.traces
    assert trace.passed
    fired = trace.steps[0]
    assert fired.consumed == {"inbox": [_O1]}
    assert list(fired.after["accepted"]) == [_O1]
    assert [s.rule for s in fired.outputs] == ["carry"]


def test_net_data_step_tokens_and_read_tokens(tmp_path: Path) -> None:
    # given: ship reads an item, consumes the purchase, fixes its receipt
    body = 'fire [accept]\nfire [ship] -> (shipped) parcel {"order": "o-1"}\n'

    # when
    (trace,) = _check(tmp_path, body).traces

    # then: the parcel is the step's, the receipt the net's, the item is read
    shipped = trace.steps[1]
    assert [(s.place, s.rule) for s in shipped.outputs] == [
        ("shipped", "play"),
        ("receipts", "net"),
    ]
    assert shipped.read == {"stock": [_tok("item", sku="a")]}
    assert list(shipped.after["receipts"]) == [_tok("receipt", kind="receipt")]
    assert list(shipped.after["stock"]) == [_tok("item", sku="a")]


def test_merge_over_the_carried_token(tmp_path: Path) -> None:
    # when
    (trace,) = _check(
        tmp_path, 'fire [accept] -> (accepted) +{"sku": "z", "rush": true}\n'
    ).traces

    # then
    assert list(trace.steps[0].after["accepted"]) == [
        _tok("purchase", id="o-1", sku="z", dueAt=100, rush=True)
    ]
    assert trace.steps[0].outputs[0].rule == "merge"


def test_nothing_produces_no_token(tmp_path: Path) -> None:
    # when
    (trace,) = _check(
        tmp_path, "fire [accept]\nfire [split] -> (lane_b) nothing\n"
    ).traces

    # then: lane_a carried, lane_b empty
    after = trace.steps[1].after
    assert list(after["lane_a"]) == [_O1]
    assert not after.get("lane_b")


def test_carry_never_copies_a_read_token(tmp_path: Path) -> None:
    # when: copy reads an item and produces an item, with no `->`
    report = _check(tmp_path, "fire [copy]\n")

    # then: the read item does not count as a carry source
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC303"
    assert "item output of [copy] into (copies) is not determined" in diagnostic.message
    assert "found 0" in diagnostic.details[0]
    assert diagnostic.details[1] == "write `-> (copies) item {...}`"


def test_undetermined_output_is_sc303(tmp_path: Path) -> None:
    report = _check(tmp_path, "fire [accept]\nfire [ship]\n")
    assert _failure_code(report) == "SC303"


def test_merge_needs_a_carry_source(tmp_path: Path) -> None:
    report = _check(tmp_path, 'fire [copy] -> (copies) +{"n": 1}\n')
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC303"
    assert "no item token to merge over" in diagnostic.message


def test_a_step_may_not_override_net_data(tmp_path: Path) -> None:
    error = _resolve_error(
        tmp_path, "fire [ship] -> (shipped) parcel {} -> (receipts) receipt {}\n"
    )
    assert error.diagnostic.code == "SC211"
    assert "fixes the receipt output of [ship]" in error.diagnostic.message


def test_output_into_a_place_the_transition_does_not_feed(tmp_path: Path) -> None:
    error = _resolve_error(tmp_path, "fire [accept] -> (shipped) parcel {}\n")
    assert error.diagnostic.code == "SC210"


# ── Choosing the binding ─────────────────────────────────────────────────


_TWO = 'inject (inbox) <- purchase {"id": "o-2", "sku": "a", "dueAt": 5}\n'


@pytest.mark.parametrize(
    "clause",
    [
        'with (inbox) {"id": "o-2"}',
        "with (inbox) $o2",
        "with (inbox) #1",
    ],
)
def test_with_picks_the_meant_token(tmp_path: Path, clause: str) -> None:
    # given: two purchases in the inbox
    body = (
        _TWO
        + '$o2: purchase {"id": "o-2", "sku": "a", "dueAt": 5}\n'
        + f"fire [accept] {clause}\n"
    )

    # when
    (trace,) = _check(tmp_path, body).traces

    # then
    assert trace.passed
    assert trace.steps[1].consumed["inbox"][0].data["id"] == "o-2"


def test_with_that_matches_nothing_is_sc302(tmp_path: Path) -> None:
    report = _check(tmp_path, 'fire [accept] with (inbox) {"id": "o-9"}\n')
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC302"
    assert diagnostic.details[0].startswith("viable binding: (inbox) purchase")


def test_with_on_a_place_the_transition_does_not_bind(tmp_path: Path) -> None:
    error = _resolve_error(tmp_path, 'fire [accept] with (stock) {"sku": "a"}\n')
    assert error.diagnostic.code == "SC209"


# ── Not enabled ──────────────────────────────────────────────────────────


def test_not_enabled_explains_the_gate_with_values(tmp_path: Path) -> None:
    # given: the clock before the purchase's deadline
    body = "fire [accept]\nadvance 40\nfire [expire]\n"

    # when
    report = _check(tmp_path, body)

    # then
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC301"
    assert diagnostic.message == "[expire] is not enabled"
    assert diagnostic.position.line == 5
    assert diagnostic.details[0] == (
        "timer `clock.now >= purchase.dueAt` is false "
        "(clock.now = 40, purchase.dueAt = 100)"
    )
    assert diagnostic.details[-1] == "enabled now: [ship], [split], [copy]"
    failure = report.traces[0].failure
    assert failure is not None and failure.explanation is not None


def test_correlate_miss_and_inhibit_hit_are_explained(tmp_path: Path) -> None:
    # given: a hold on shipping
    body = (
        "fire [accept]\ninject (holds) <- hold {}\nfire [ship] -> (shipped) parcel {}\n"
    )

    # when
    (diagnostic,) = _check(tmp_path, body).diagnostics()

    # then
    assert diagnostic.code == "SC301"
    assert diagnostic.details[0] == (
        "inhibit arc (holds) -hold->0 [ship] forbids hold {}, and (holds) holds it"
    )


def test_an_unregistered_guard_is_not_enabled(tmp_path: Path) -> None:
    (diagnostic,) = _check(
        tmp_path, "fire [accept]\nfire [audit] -> (notes) memo {}\n"
    ).diagnostics()
    assert diagnostic.code == "SC301"
    assert diagnostic.details[0].startswith('guard "audit_ok" names a handler')


# ── Injections and advances ─────────────────────────────────────────────────


def test_inject_update_and_advance(tmp_path: Path) -> None:
    # given: the purchase sits in (accepted) (a firing put it there), so the
    # relative advance has a timer to mature
    body = (
        'inject (holds) <- hold {"a": 1}, hold {"a": 2}\n'
        'update (holds) <- hold {"a": 3}\n'
        "fire [accept]\n"
        "advance 60\n"
        "advance +1m\n"
    )

    # when
    (trace,) = _check(tmp_path, body).traces

    # then: an absolute advance on the empty clock place is update-only; the
    # relative one plays every firing the new time matured ([expire]'s timer
    # is due once now >= purchase.dueAt = 100)
    inject, update, accept, absolute, relative = trace.steps
    assert len(inject.records) == 2
    assert update.replaced == {"holds": [_tok("hold", a=1), _tok("hold", a=2)]}
    assert list(update.after["holds"]) == [_tok("hold", a=3)]
    assert list(absolute.after["clock"]) == [_tok("tick", now=60)]
    assert ["update" if "injectionId" in r else "firing" for r in absolute.records] == [
        "update"
    ]
    assert list(relative.after["clock"]) == [_tok("tick", now=120)]
    assert relative.replaced == {"clock": [_tok("tick", now=60)]}
    assert ["update" if "injectionId" in r else "firing" for r in relative.records] == [
        "update",
        "firing",
    ]
    assert [_firing(r)["transition"] for r in relative.records[1:]] == ["expire"]
    assert list(relative.after["expired"]) == [
        _tok("purchase", id="o-1", sku="a", dueAt=100)
    ]


def test_relative_advance_on_an_empty_clock_is_sc306(tmp_path: Path) -> None:
    assert _failure_code(_check(tmp_path, "advance +5m\n")) == "SC306"


def test_each_record_of_a_step_carries_its_marking(tmp_path: Path) -> None:
    # given: a shop play whose multi-token inject and whose maturing advance
    #   each produce more than one record: the first advance is update-only
    #   (the shop fixture starts with an empty clock place), the second one
    #   (now 60 + 60 = 120, dueAt 100) matures [expire]
    body = (
        'inject (holds) <- hold {"a": 1}, hold {"a": 2}\n'
        "fire [accept]\n"
        "advance 60\n"
        "advance +1m\n"
    )

    # when
    (trace,) = _check(tmp_path, body).traces
    inject, accept, first, maturing = trace.steps

    # then: one marking per record, prefixes of the step's final one; the
    #   maturing advance's second marking already shows the clock's new now
    #   before [expire]'s firing lands
    from velocitron_journal import StoredEvent, replay_events

    assert [len(step.markings) for step in trace.steps] == [2, 1, 1, 2]
    assert inject.markings[-1] == inject.after
    assert list(maturing.markings[0]["clock"]) == [_tok("tick", now=120)]
    assert maturing.markings[-1] == maturing.after
    for step, before in (
        (inject, trace.initial),
        (accept, inject.after),
        (first, accept.after),
        (maturing, first.after),
    ):
        for position, marking in enumerate(step.markings):
            assert marking == replay_events(
                trace.subject.net,
                [
                    StoredEvent(
                        earlier_index,
                        "firing" if "firingId" in earlier else "injection",
                        dict(earlier),
                    )
                    for earlier_index, earlier in enumerate(
                        step.records[: position + 1]
                    )
                ],
                initial=before,
            )


def test_trace_json_exposes_the_marking_after_each_record(tmp_path: Path) -> None:
    # given: one advance that matures a firing after its clock update
    body = "fire [accept]\nadvance 60\nadvance +1m\n"

    # when
    (trace,) = _check(tmp_path, body).traces
    rendered = trace_json(trace)
    advance = rendered["steps"][2]

    # then: afterEach sits beside records, same length, last entry the `after`
    assert len(advance["afterEach"]) == len(advance["records"]) == 2
    assert advance["afterEach"][0] == {
        "accepted": [{"type": "purchase", "data": dict(_O1.data)}],
        "clock": [{"type": "tick", "data": {"now": 120}}],
        "stock": [{"type": "item", "data": {"sku": "a"}}],
    }
    assert advance["afterEach"][-1] == advance["after"]


def test_a_maturing_firing_record_names_its_clock_move(tmp_path: Path) -> None:
    # given: a play whose second advance matures [expire]
    body = "fire [accept]\nadvance 60\nadvance +1m\n"

    # when
    (trace,) = _check(tmp_path, body).traces
    maturing = trace.steps[2]

    # then: the matured firing's metadata carries maturedBy — the clock
    #   injection's deterministic injectionId — while the injection itself
    #   and the click-fired `fire [accept]` records stay unstamped
    clock = _injection(maturing.records[0])
    clock_id = clock["injectionId"]
    assert clock_id == "shop/@inject/clock/2"
    assert [
        None if "injectionId" in record else record["metadata"].get("maturedBy")
        for record in maturing.records
    ] == [
        None,
        clock_id,
    ]
    assert _firing(trace.steps[0].records[0])["metadata"].get("maturedBy") is None
    assert [_firing(r)["status"] for r in maturing.records[1:]] == ["completed"]


# ── Maturation edge cases (Q73–Q77) ─────────────────────────────────────


def test_a_maturation_firing_failure_is_recorded_and_the_pass_continues(
    tmp_path: Path,
) -> None:
    # given: two timer-gated transitions on one clock with the same timer cel
    #   (so one advance matures both): [bad]'s net `data cel` names a missing
    #   binding field, so its settle fails (the engine's deposit violation,
    #   SC304's cause); [ok]'s carry rule is determined.
    (tmp_path / "shop.petrinet").write_text(
        'net mat "a failing maturing firing does not stop the pass"\n'
        "(clock) -tick->? [ok]\n"
        "(clock) -tick->? [bad]\n"
        "(go) -work-> [ok]\n"
        "(go) -work-> [bad]\n"
        "@gx: [bad] -broken-> (broke)\n        @gok: [ok] -done-> (done)\n"
        '[ok] timer clock (clock) cel "clock.now >= 10"\n'
        '[bad] timer clock (clock) cel "clock.now >= 10"\n'
        "[bad] priority 1\n"
        '@gok data {"k": "ok"}\n'
        "@gx data cel \"{'n': binding.missing}\"\n"
        "marking start (go) <- $w1\n"
        "marking start (go) <- $w2\n"
        "marking start (clock) <- $c\n"
        "$w1: work {}\n"
        "$w2: work {}\n"
        '$c: tick {"now": 0}\n',
        encoding="utf-8",
    )
    path = tmp_path / "s.play"
    path.write_text(
        'play s\nnet "shop.petrinet"\nmarking start\nadvance +50\n',
        encoding="utf-8",
    )

    # when
    report = check_play(read_play(path))

    # then: the pass continues past the failed firing — [ok]'s firing plays,
    #   the failed firing is the step's evidence, and the path does not die
    (trace,) = report.traces
    assert trace.passed
    (advance,) = trace.steps
    statuses = [
        (_firing(r)["transition"], _firing(r)["status"]) for r in advance.records[1:]
    ]
    assert ("bad", "failed") in statuses
    assert ("ok", "completed") in statuses


def test_an_advance_leaves_a_timed_handler_transition_for_the_author(
    tmp_path: Path,
) -> None:
    # given: [remind] has a handler, and its output is the carried token only
    #   by accident: the handler writes the real one
    (tmp_path / "shop.petrinet").write_text(
        'net remind "a kept VM is asked about again"\n'
        "(kept) -teardown-> [remind] -teardown-> (asked)\n"
        "@remind_clock: (clock) -tick->? [remind]\n"
        '[remind] timer clock (clock) cel "clock.now >= kept.remindAt"\n'
        "[remind] timer bind kept (kept)\n"
        '[remind] handler "remind@task_vms"\n'
        "marking start (kept) <- $k\n"
        "marking start (clock) <- $c\n"
        '$k: teardown {"n": 1, "reminded": false, "remindAt": 100}\n'
        '$c: tick {"now": 0}\n',
        encoding="utf-8",
    )
    path = tmp_path / "s.play"
    path.write_text(
        'play s\nnet "shop.petrinet"\nmarking start\nadvance 100\n'
        "expect enabled [remind]\n"
        'fire [remind] -> (asked) teardown {"n": 2, "reminded": true, '
        '"remindAt": 100}\n'
        'expect (asked) == teardown {"n": 2, "reminded": true, "remindAt": 100}\n',
        encoding="utf-8",
    )

    # when
    report = check_play(read_play(path))

    # then: the advance matured nothing, and the author's fire gives the output
    (trace,) = report.traces
    assert trace.passed, [d.render() for d in report.diagnostics()]
    assert [_firing(r)["transition"] for r in trace.steps[0].records[1:]] == []


def test_one_advance_maturing_a_transition_twice_gets_distinct_firing_ids(
    tmp_path: Path,
) -> None:
    # given: a timed transition whose firing re-arms its own deadline (+10),
    #   so one advance to 20 matures it into the first deadline (10) and
    #   then the second (20) — the "one advance can mature several
    #   deadlines" case, one transition, two firings
    (tmp_path / "shop.petrinet").write_text(
        'net rearm "one advance, two deadlines, one transition"\n'
        "(clock) -tick->? [rearm]\n"
        "(go) -work-> [rearm]\n"
        "@gj: [rearm] -work-> (go)\n"
        '[rearm] timer clock (clock) cel "clock.now >= work.nextAt"\n'
        "[rearm] timer bind work (go)\n"
        "@gj data cel \"{'nextAt': binding.go[0].nextAt + 10}\"\n"
        "marking initial (go) <- $j1\n"
        "marking initial (clock) <- $c\n"
        '$j1: work {"nextAt": 10}\n'
        '$c: tick {"now": 0}\n',
        encoding="utf-8",
    )
    path = tmp_path / "s.play"
    path.write_text('play s\nnet "shop.petrinet"\nadvance 20\n', encoding="utf-8")

    # when: the advance matures [rearm] at nextAt 10, whose firing deposits
    #   nextAt 20 — which the same pass then matures
    (trace,) = check_play(read_play(path)).traces

    # then
    (advance,) = trace.steps
    firing_ids = [_firing(r)["firingId"] for r in advance.records[1:]]
    assert firing_ids == ["rearm/rearm/1", "rearm/rearm/2"]


def test_a_maturation_that_hits_the_cap_raises_sc315(tmp_path: Path) -> None:
    # given: a timed transition that re-arms forever; raise the cap's floor
    #   by monkeypatching it small so the test explores the SC315 branch
    (tmp_path / "shop.petrinet").write_text(
        'net spin "a maturation that never quiesces"\n'
        "(go) -work-> [rearm] -work-> (go)\n"
        "(clock) -tick->? [rearm]\n"
        '[rearm] timer clock (clock) cel "clock.now >= 10"\n'
        "marking initial (go) <- $w\n"
        "marking initial (clock) <- $c\n"
        "$w: work {}\n"
        '$c: tick {"now": 0}\n',
        encoding="utf-8",
    )
    path = tmp_path / "s.play"
    path.write_text('play s\nnet "shop.petrinet"\nadvance +50\n', encoding="utf-8")
    import velocitron_play_check as check_module

    original = check_module._Player._ADVANCE_MAX_MATURING
    check_module._Player._ADVANCE_MAX_MATURING = 3
    try:
        report = check_play(read_play(path))
    finally:
        check_module._Player._ADVANCE_MAX_MATURING = original

    # then
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC315"
    assert "did not quiesce" in diagnostic.message


def test_an_attempt_branched_guard_probes_the_binding_that_fires(
    tmp_path: Path,
) -> None:
    # given: a net whose guard branches on firingContext.attempt — it wants
    #   an n=2 token before attempt 1 and an n=1 token from attempt 1 on —
    #   and an Engine with that guard registered
    from velocitron_petrinet import compile_petrinet_text
    from velocitron_runtime import Engine
    from velocitron_petrinet import parse_net
    from velocitron_engine import HandlerRegistry
    from velocitron_engine import Marking

    net = parse_net(
        compile_petrinet_text(
            'net probe "attempt-branched guard"\n'
            "(requests) -req-> [gate_check]\n"
            "[gate_check] -req-> (served)\n"
            '[gate_check] guard "wants"\n'
            '[gate_check] handler "doit"\n',
            "probe.petrinet",
        )
    )

    def guard(inp: GuardHandlerInput) -> bool:
        ctx = inp["firingContext"]
        want = 2 if ctx["attempt"] == 0 else 1
        return any(t.data["n"] == want for t in inp["inputTokens"]["requests"])

    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        return {
            "status": "completed",
            "outputTokens": {"served": list(inp["inputTokens"]["requests"])},
            "error": None,
            "metadata": {},
        }

    reg = HandlerRegistry()
    reg.register_guard("wants", guard)
    reg.register_transition("doit", handler)
    engine = Engine(reg)
    marking = Marking(
        {
            "requests": [
                Token("req", {"n": 1}),
                Token("req", {"n": 2}),
                Token("req", {"n": 2}),
            ]
        }
    )

    # when: the probe at the firing's attempt and the firing itself
    probe1 = engine.probe_binding(net, marking, "gate_check", attempt=1)
    _after, record = engine.fire(net, marking, "gate_check", attempt=1)
    probe0 = engine.probe_binding(net, marking, "gate_check", attempt=0)

    # then: the probe at attempt 1 selects the same binding the fire
    #   consumes; the probe at attempt 0 sees the other branch
    assert probe1 is not None
    assert probe0 is not None
    assert [t.data for t in probe1["requests"]] == [{"n": 1}]
    assert record["inputTokens"] == probe1
    assert [t.data for t in probe0["requests"]] == [{"n": 2}]


def test_a_raising_at_zero_guard_is_skipped_like_a_real_not_enabled(
    tmp_path: Path,
) -> None:
    # given: a guard that raises at attempt 0 and accepts at attempt >= 1 —
    #   the probe's skip is attributed the same way a real not-enabled is:
    #   the filter judges it undetermined and leaves it out of maturation
    from velocitron_petrinet import compile_petrinet_text
    from velocitron_runtime import Engine
    from velocitron_petrinet import parse_net
    from velocitron_engine import HandlerRegistry
    from velocitron_engine import Marking, Token

    net = parse_net(
        compile_petrinet_text(
            'net raise_at_zero "probe degrades to None at attempt 0"\n'
            "(requests) -req-> [gate_check]\n"
            "[gate_check] -req-> (served)\n"
            '[gate_check] guard "raises_at_zero"\n'
            '[gate_check] handler "doit"\n',
            "raise_at_zero.petrinet",
        )
    )

    def raising_guard(inp: GuardHandlerInput) -> bool:
        if inp["firingContext"]["attempt"] == 0:
            raise RuntimeError("nope at zero")
        return True

    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        return {
            "status": "completed",
            "outputTokens": {"served": list(inp["inputTokens"]["requests"])},
            "error": None,
            "metadata": {},
        }

    reg = HandlerRegistry()
    reg.register_guard("raises_at_zero", raising_guard)
    reg.register_transition("doit", handler)
    engine = Engine(reg)
    marking = Marking({"requests": [Token("req", {"n": 1})]})

    # when: the probe at the attempt the maturation pass would fire at (0) is
    #   None — the same answer explain_enablement gives a real not-enabled
    #   transition; at an attempt the guard accepts, the binding comes back
    # then
    assert engine.probe_binding(net, marking, "gate_check", attempt=0) is None
    probe1 = engine.probe_binding(net, marking, "gate_check", attempt=1)
    assert probe1 is not None and [t.data for t in probe1["requests"]] == [{"n": 1}]


def test_a_color_the_place_does_not_take_is_sc207(tmp_path: Path) -> None:
    assert _resolve_error(tmp_path, "inject (holds) <- item {}\n").diagnostic.code == (
        "SC207"
    )


def test_unknown_names_are_sc2xx_with_a_suggestion(tmp_path: Path) -> None:
    place = _resolve_error(tmp_path, "inject (hold) <- {}\n")
    assert place.diagnostic.code == "SC202"
    assert place.diagnostic.details == ("did you mean: holds",)
    assert _resolve_error(tmp_path, "fire [shp]\n").diagnostic.code == "SC203"
    assert _resolve_error(tmp_path, "inject (holds) <- $nope\n").diagnostic.code == (
        "SC204"
    )


# ── Expectations ─────────────────────────────────────────────────────────


def test_every_condition_holds(tmp_path: Path) -> None:
    # given: the purchase accepted and the clock past its deadline
    body = (
        '$o1: purchase {"id": "o-1", "sku": "a", "dueAt": 100}\n'
        "fire [accept]\n"
        "advance 200\n"
        "expect (accepted) == $o1, (inbox) empty, (stock) count 1, "
        '(accepted) has {"sku": "a"}, enabled [ship] [expire], '
        "not enabled [accept], next [expire]\n"
        "fire [expire]\n"
    )

    # when
    (trace,) = _check(tmp_path, body).traces

    # then
    assert trace.passed, trace.failure
    checks = trace.steps[2].checks
    assert all(check.ok for check in checks)
    assert checks[-1].detail == (
        "the priority policy picks [expire] of [ship], [expire], [split], [copy]"
    )


def test_quiescent_holds_when_nothing_is_enabled(tmp_path: Path) -> None:
    (trace,) = _check(tmp_path, "expect quiescent\n", _HEADER + "marking none\n").traces
    assert trace.passed
    assert trace.steps[0].checks[0].detail == "enabled now: nothing"


def test_a_failed_expectation_is_sc307_with_the_values(tmp_path: Path) -> None:
    # when
    report = _check(tmp_path, "expect (inbox) empty, (stock) count 1\n")

    # then
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC307"
    assert diagnostic.message == "expected `(inbox) empty` does not hold"
    assert diagnostic.details == (
        '(inbox) empty: (inbox) holds purchase {"dueAt": 100, "id": "o-1", "sku": "a"}',
    )
    failure = report.traces[0].failure
    assert failure is not None
    assert [check.ok for check in failure.checks] == [False, True]


def test_expect_enabled_failure_says_why(tmp_path: Path) -> None:
    (diagnostic,) = _check(
        tmp_path, "fire [accept]\nexpect enabled [expire]\n"
    ).diagnostics()
    assert "[expire]: clock place (clock) is empty" in diagnostic.details[0]


# ── Markings and paths ───────────────────────────────────────────────────


def test_marking_initial_none_and_named(tmp_path: Path) -> None:
    initial = _check(tmp_path, "").traces[0].initial
    assert list(initial["inbox"]) == [_O1]
    none = _check(tmp_path, "", _HEADER + "marking none\n").traces[0].initial
    assert len(none) == 0
    rush = _check(tmp_path, "", _HEADER + "marking rush\n").traces[0].initial
    assert rush["inbox"][0].data["id"] == "o-2"
    error = _resolve_error(tmp_path, "", _HEADER + "marking late\n")
    assert error.diagnostic.code == "SC206"
    assert "named markings: rush" in error.diagnostic.message


_PATHS = """@accepted: fire [accept]
fire [ship] -> (shipped) parcel {}

path expired from @accepted
advance 200
fire [expire]
expect (expired) count 1

path expired_then from @accepted
fire [split]
"""


def test_a_branch_replays_its_prefix(tmp_path: Path) -> None:
    # when
    report = _check(tmp_path, _PATHS)

    # then
    assert report.passed
    _trunk, expired, split = report.traces
    assert [s.step.statement for s in expired.steps][:1] == ["fire [accept]"]
    assert expired.inherited == 1
    assert list(expired.final["expired"]) == [_O1]
    assert split.inherited == 1
    for trace in report.traces:
        for left, right in zip(trace.steps, trace.steps[1:], strict=False):
            assert left.after == right.before


def test_a_prefix_failure_is_reported_once_with_blocked_paths(tmp_path: Path) -> None:
    # given: the shared step fails
    body = _PATHS.replace("@accepted: fire [accept]", "@accepted: fire [copy]")

    # when
    report = _check(tmp_path, body)

    # then
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC303"
    assert diagnostic.details[-1] == "blocked paths: expired, expired_then"


def test_only_the_named_paths_play(tmp_path: Path) -> None:
    report = check_play(read_play(_play_case(tmp_path, _PATHS)), paths=["expired"])
    assert [t.path.name for t in report.traces] == ["expired"]


def test_a_path_branches_only_from_an_earlier_label(tmp_path: Path) -> None:
    body = (
        "path early from @later\nadvance 1\npath late from @later\n@later: advance 2\n"
    )
    error = _resolve_error(tmp_path, "advance 0\n" + body)
    assert error.diagnostic.code == "SC205"


def test_playback_is_deterministic(tmp_path: Path) -> None:
    path = _play_case(tmp_path, _PATHS)
    first = [trace_json(t) for t in check_play(read_play(path)).traces]
    second = [trace_json(t) for t in check_play(read_play(path)).traces]
    assert first == second


# ── Composition ──────────────────────────────────────────────────────────


_ORDERS = """net orders
(incoming) -purchase-> [accept] -purchase-> (accepted)
(accepted) port output purchase
"""
_SHIPPING = """net shipping
(inbox) -purchase-> [pack] -parcel-> (packed)
(inbox) port input purchase
@packed: [pack] -receipt-> (receipts)
@packed data cel "{\\"order\\": binding.inbox[0].id}"
"""
_COMPOSED_STEPS = """inject (orders.incoming) <- {"id": "o-1"}
fire [orders.accept]
expect (shipping.inbox) count 1, (orders.accepted) count 1
fire [shipping.pack] -> (shipping.packed) parcel {}
expect (shipping.receipts) == receipt {"order": "o-1"}
"""


def _write_constituents(tmp_path: Path) -> None:
    (tmp_path / "orders.petrinet").write_text(_ORDERS)
    (tmp_path / "shipping.petrinet").write_text(_SHIPPING)


def test_inline_composition_names_a_fused_port_both_ways(tmp_path: Path) -> None:
    # given
    _write_constituents(tmp_path)
    header = (
        'play s\nuse "orders.petrinet" as orders\n'
        'use "shipping.petrinet" as shipping\n'
        "wire orders.(accepted) -> shipping.(inbox)\n"
    )
    (tmp_path / "s.play").write_text(header + _COMPOSED_STEPS)

    # when
    report = check_play(read_play(tmp_path / "s.play"))

    # then: the merged net's computed fallback fills the receipt too
    assert report.passed, report.diagnostics()
    assert report.subject.composed


def test_net_may_name_a_composition_document(tmp_path: Path) -> None:
    # given
    _write_constituents(tmp_path)
    (tmp_path / "shop.petrinet").write_text(
        "composition shop\n"
        'use "orders.petrinet" as orders\n'
        'use "shipping.petrinet" as shipping\n'
        "wire orders.(accepted) -> shipping.(inbox)\n"
    )
    (tmp_path / "s.play").write_text('play s\nnet "shop.petrinet"\n' + _COMPOSED_STEPS)

    # when / then
    assert check_play(read_play(tmp_path / "s.play")).passed


def test_net_and_use_together_is_sc212(tmp_path: Path) -> None:
    _write_constituents(tmp_path)
    error = _resolve_error(tmp_path, 'use "orders.petrinet" as orders\n')
    assert error.diagnostic.code == "SC212"


def test_a_missing_net_is_sc201(tmp_path: Path) -> None:
    (tmp_path / "s.play").write_text('play s\nnet "nope.petrinet"\n')
    with pytest.raises(PlayError) as caught:
        check_play(read_play(tmp_path / "s.play"))
    assert caught.value.diagnostic.code == "SC201"
