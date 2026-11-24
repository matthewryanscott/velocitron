"""velocitron prove: an arrival waits while no step can use it, and the
environment tries one token per class its readers cannot tell apart (ADR 0061);
a copy into a side output tells no tokens apart (ADR 0065); a place the net
only counts keeps as many tokens as its readers count (ADR 0062).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from velocitron_analysis import (
    ProofReport,
    ProofSettings,
    load,
    prove,
    read_settings,
    soundness,
)
from velocitron_cli import main

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "prove"
# Nets that do not end are stopped here. Every net that does end does so
# under this cap, so the comparison covers it. A cap in the thousands only
# spends memory on the nets the comparison then skips. On the C++ CEL
# backend one of those runs is several gigabytes, and the CI runner is shut
# down (exit 143) while this file is still going.
MAX_STATES = 300
# Without ADR 0062 each try is a new marking and [escalate] binds every three
# of them, so the search that compares against no reduction needs a cap.
CAPS = {
    "redelivery.petrinet": ProofSettings(firings={"redeliver": 3}),
    "side-copy-count.petrinet": ProofSettings(firings={"redeliver": 3}),
}

Explored = tuple[soundness.Explorer, ProofReport]


def _explore(
    path: Path,
    *,
    wait_arrivals: bool,
    group_tokens: bool,
    saturate: bool = True,
    settings: ProofSettings | None = None,
    max_states: int = MAX_STATES,
) -> Explored:
    found: list[soundness.Explorer] = []
    explore = soundness.explore

    def explore_with(*args: Any, **kwargs: Any) -> soundness.Explorer:
        # prove passes its own wait_arrivals; the test's switches win.
        explorer = explore(
            *args,
            **{
                **kwargs,
                "wait_arrivals": wait_arrivals,
                "group_tokens": group_tokens,
                "saturate": saturate,
            },
        )
        found.append(explorer)
        return explorer

    net, composition = load(path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(soundness, "explore", explore_with)
        report = prove(
            net,
            facts=["soundness"],
            settings=settings,
            composition=composition,
            max_states=max_states,
        )
    return found[0], report


def _statuses(report: ProofReport) -> list[tuple[str, str]]:
    # The first refuted marking found may differ, so the kind of finding may too.
    return [(p.subject, p.status) for p in report.proofs]


def _dead(report: ProofReport) -> list[Any]:
    return [
        f.transition
        for p in report.proofs
        if p.subject == "no dead transitions"
        for f in p.findings
    ]


def _edges(explorer: soundness.Explorer) -> int:
    return sum(len(state.edges) for state in explorer.states)


def _arrivals(explorer: soundness.Explorer, place: str) -> list[tuple[int, Any]]:
    """Each arrival into ``place``: the marking it starts from, and its token."""
    return [
        (index, explorer.moves[move].token)
        for index, state in enumerate(explorer.states)
        for move, _, kind in state.edges
        if kind == soundness.ARRIVAL and explorer.moves[move].place == place
    ]


def test_an_arrival_waits_until_a_step_that_reads_it_is_ready():
    # given: the approval is read only once the request is pending
    path = FIXTURES / "late-approval.petrinet"
    # when:
    waiting, waiting_report = _explore(path, wait_arrivals=True, group_tokens=False)
    eager, eager_report = _explore(path, wait_arrivals=False, group_tokens=False)
    # then: it arrives only where the request is pending, with every level
    sources = {i for i, _ in _arrivals(waiting, "approvals")}
    assert sources and all(waiting.states[i].marking.get("pending") for i in sources)
    assert any(
        not eager.states[i].marking.get("pending")
        for i, _ in _arrivals(eager, "approvals")
    )
    assert len(waiting.states) < len(eager.states)
    assert _edges(waiting) < _edges(eager)
    assert _statuses(waiting_report) == _statuses(eager_report)
    assert waiting_report.status == "proved"


def test_the_arrival_wait_is_off_unless_asked_for(
    capsys: pytest.CaptureFixture[str],
):
    # given: a net whose approval can arrive before the request is pending
    path = FIXTURES / "late-approval.petrinet"
    net, composition = load(path)
    # when: proved by default, with the API switch, and with the CLI flag
    plain = prove(net, facts=["soundness"], composition=composition)
    waiting = prove(
        net, facts=["soundness"], composition=composition, wait_arrivals=True
    )
    main(["prove", str(path), "--fact", "soundness", "--json"])
    flag_off = capsys.readouterr().out
    main(["prove", str(path), "--fact", "soundness", "--json", "--wait-arrivals"])
    flag_on = capsys.readouterr().out
    # then: only the switch holds arrivals back (ADR 0061, note of 2026-11-02)
    assert plain.exploration and waiting.exploration
    assert waiting.exploration["states"] < plain.exploration["states"]
    assert f'"states": {plain.exploration["states"]}' in flag_off
    assert f'"states": {waiting.exploration["states"]}' in flag_on
    assert _statuses(plain) == _statuses(waiting)


def test_tokens_a_reader_cannot_tell_apart_arrive_once():
    # given: the steps test the level against 3, and a sent request copies who approved
    path = FIXTURES / "late-approval.petrinet"
    # when:
    grouped, grouped_report = _explore(path, wait_arrivals=True, group_tokens=True)
    every, every_report = _explore(path, wait_arrivals=True, group_tokens=False)
    # then: the first level each side of 3, in the domain's order, per approver
    tried = {
        (t.data["level"], t.data["by"]) for _, t in _arrivals(grouped, "approvals")
    }
    assert tried == {(1, "ann"), (1, "bob"), (3, "ann"), (3, "bob")}
    assert {
        (t.data["level"], t.data["by"]) for _, t in _arrivals(every, "approvals")
    } == {(level, by) for level in (1, 2, 3, 4, 5) for by in ("ann", "bob")}
    assert len(grouped.states) < len(every.states)
    assert _edges(grouped) < _edges(every)
    assert _statuses(grouped_report) == _statuses(every_report)


def test_a_record_value_a_predicate_cannot_tell_apart_is_not_tried():
    # given: the gate's verdict is only ever compared with 'hold'
    path = FIXTURES / "late-gate.petrinet"
    settings = ProofSettings(firings={"again": 2})
    # when:
    grouped, grouped_report = _explore(
        path, wait_arrivals=True, group_tokens=True, settings=settings
    )
    every, every_report = _explore(
        path, wait_arrivals=True, group_tokens=False, settings=settings
    )
    # then: 'released' passes the gate as 'pass' does, so only 'pass' and 'hold' come
    assert {t.data["result"] for _, t in _arrivals(grouped, "verdicts")} == {
        "pass",
        "hold",
    }
    assert len(grouped.states) < len(every.states)
    assert _statuses(grouped_report) == _statuses(every_report)


def _findings(report: ProofReport) -> list[tuple[str, str, list[tuple[str, str]]]]:
    return [
        (p.subject, p.status, sorted({(f.kind, f.summary) for f in p.findings}))
        for p in report.proofs
    ]


def _page_events(explorer: soundness.Explorer) -> set[tuple[str, Any]]:
    return {
        (t.data["status"], t.data["running"]) for _, t in _arrivals(explorer, "page")
    }


EVERY_PAGE_EVENT = {
    (status, running)
    for status in ("waiting", "review", "done")
    for running in (True, False)
}


def test_a_copy_into_a_side_output_does_not_keep_page_events_apart():
    # given: [follow] copies a page event into (followed), which no step reads
    path = FIXTURES / "side-copy.petrinet"
    # when:
    grouped, grouped_report = _explore(path, wait_arrivals=False, group_tokens=True)
    every, every_report = _explore(path, wait_arrivals=False, group_tokens=False)
    # then: one page event per answer of the arc tests, the first in the domains' order
    assert _page_events(grouped) == {("waiting", True), ("done", True)}
    assert _page_events(every) == EVERY_PAGE_EVENT
    assert len(grouped.states) < len(every.states)
    assert _findings(grouped_report) == _findings(every_report)
    assert _dead(grouped_report) == _dead(every_report)


def test_a_copy_a_step_reads_keeps_page_events_apart():
    # given: the same copy, and [log] tests whether the copied job runs
    path = FIXTURES / "side-copy-read.petrinet"
    # when:
    grouped, grouped_report = _explore(path, wait_arrivals=False, group_tokens=True)
    every, every_report = _explore(path, wait_arrivals=False, group_tokens=False)
    # then: every page event is tried, as with no classes
    assert _page_events(grouped) == EVERY_PAGE_EVENT
    assert len(grouped.states) == len(every.states)
    assert _findings(grouped_report) == _findings(every_report)


def test_a_page_event_whose_copy_the_engine_refuses_is_tried_apart():
    # given: a domains file lets a page event hold running = 'unset', which
    # the net's own domain refuses in the copy
    path = FIXTURES / "side-copy.petrinet"
    settings = read_settings(FIXTURES / "side-copy-outside.domains.json5")
    # when:
    grouped, grouped_report = _explore(
        path, wait_arrivals=False, group_tokens=True, settings=settings
    )
    _, every_report = _explore(
        path, wait_arrivals=False, group_tokens=False, settings=settings
    )
    # then: a refused and an accepted event are tried for each answer of the
    # arc tests, and the failed deposit gives the same results in both
    assert _page_events(grouped) == {
        ("waiting", True),
        ("waiting", "unset"),
        ("done", True),
        ("done", "unset"),
    }
    assert _statuses(grouped_report) == _statuses(every_report)
    assert _statuses(every_report) == [
        ("option to complete", "refuted"),
        ("proper completion", "unknown"),
        ("no dead transitions", "unknown"),
    ]
    assert _dead(grouped_report) == _dead(every_report)


def test_a_copied_job_the_engine_refuses_keeps_its_page_event_apart():
    # given: [follow] puts the job a page event carries into a side output,
    # and a domains file lets a job hold running = 'unset'
    path = FIXTURES / "side-copy-embedded.petrinet"
    settings = read_settings(FIXTURES / "side-copy-embedded-outside.domains.json5")
    # when:
    _, grouped_report = _explore(
        path, wait_arrivals=False, group_tokens=True, settings=settings
    )
    _, every_report = _explore(
        path, wait_arrivals=False, group_tokens=False, settings=settings
    )
    # then: the failed deposit of the job is found with the classes too
    assert _statuses(grouped_report) == _statuses(every_report)
    assert "unknown" in {status for _, status in _statuses(every_report)}


def test_a_place_read_beside_an_output_into_a_side_output_is_counted():
    # given: [escalate] reads three tries and puts a try into (noted), which
    # no step reads
    path = FIXTURES / "side-copy-count.petrinet"
    capped = ProofSettings(firings={"redeliver": 3})
    # when: with a low state cap, as a loop that does not close binds every
    # three of its tries
    counted, counted_report = _explore(
        path, wait_arrivals=False, group_tokens=True, max_states=100
    )
    _, capped_report = _explore(
        path, wait_arrivals=False, group_tokens=True, saturate=False, settings=capped
    )
    # then: the loop closes with no firing cap, as redelivery.petrinet's does,
    # with the verdicts of [redeliver] capped at 3
    assert not counted.capped
    assert _statuses(counted_report) == _statuses(capped_report)


def _corpus() -> list[Path]:
    """The examples' and the fixtures' nets, the library-hold ones included."""
    return [
        path
        for base in ("examples", "implementations/python/tests/fixtures")
        for path in sorted((ROOT / base).rglob("*.petrinet"))
    ]


def _settings(path: Path) -> ProofSettings | None:
    domains = path.with_name(f"{path.stem}.domains.json5")
    if domains.exists():
        return read_settings(domains)
    return CAPS.get(path.name)


@pytest.mark.parametrize(
    ("wait_arrivals", "group_tokens", "saturate"),
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, True),
    ],
    ids=["arrivals wait", "tokens group", "counted places", "all"],
)
def test_every_net_gets_the_same_verdicts_with_and_without_the_reductions(
    wait_arrivals: bool, group_tokens: bool, saturate: bool
):
    compared = 0
    for path in _corpus():
        name = path.relative_to(ROOT).as_posix()
        settings = _settings(path)
        # when:
        reduced, reduced_report = _explore(
            path,
            wait_arrivals=wait_arrivals,
            group_tokens=group_tokens,
            saturate=saturate,
            settings=settings,
        )
        eager, eager_report = _explore(
            path,
            wait_arrivals=False,
            group_tokens=False,
            saturate=False,
            settings=settings,
        )
        # then: where the eager search ends, the reduced one ends too, no
        # larger, with the same verdicts
        if eager.capped:
            continue
        compared += 1
        assert not reduced.capped, name
        assert len(reduced.states) <= len(eager.states), name
        assert _edges(reduced) <= _edges(eager), name
        assert _statuses(reduced_report) == _statuses(eager_report), name
        assert _dead(reduced_report) == _dead(eager_report), name
    assert compared >= 60
