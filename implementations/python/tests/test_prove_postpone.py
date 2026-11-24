"""velocitron prove: ticks and record changes wait until something can use them,
and before the start the environment writes only what a step can read."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from velocitron_analysis import (
    ProofReport,
    ProofSettings,
    load,
    prove,
    soundness,
)

FIXTURES = Path(__file__).parent / "fixtures" / "prove"
RECORD_VERDICT = 'record "Shelf note"\n(verdicts) lives in "Shelf note"\n'
RECORD_SWITCH = 'record "Branch home"\n(switch) lives in "Branch home"\n'


def _prove(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    *,
    postpone: bool,
    settings: ProofSettings | None = None,
) -> ProofReport:
    explore = soundness.explore

    def explore_with(*args: Any, **kwargs: Any) -> soundness.Explorer:
        # ADR 0055's reductions alone: ADR 0061's are compared in
        # test_prove_arrivals.py.
        # prove passes its own wait_arrivals; this switch wins.
        return explore(
            *args,
            **{
                **kwargs,
                "postpone": postpone,
                "wait_arrivals": False,
                "group_tokens": False,
            },
        )

    net, composition = load(path)
    with monkeypatch.context() as patch:
        patch.setattr(soundness, "explore", explore_with)
        return prove(
            net, facts=["soundness"], settings=settings, composition=composition
        )


def _verdicts(report: ProofReport) -> list[tuple[str, str, list[str]]]:
    return [
        (p.subject, p.status, sorted(f.kind for f in p.findings)) for p in report.proofs
    ]


def _with(tmp_path: Path, name: str, extra: str) -> Path:
    target = tmp_path / f"{name}.petrinet"
    text = (FIXTURES / f"{name}.petrinet").read_text(encoding="utf-8")
    target.write_text(text + extra, encoding="utf-8")
    return target


def _fixtures(tmp_path: Path) -> list[Path]:
    return [
        *sorted(FIXTURES.glob("*.petrinet")),
        FIXTURES / "kept" / "watched.petrinet",
        FIXTURES / "shop" / "shop.petrinet",
        FIXTURES / "switched" / "switched.petrinet",
        _with(tmp_path, "held-verdict", RECORD_VERDICT),
        _with(tmp_path, "owner-switch", RECORD_SWITCH),
    ]


def test_every_fixture_gets_the_same_verdicts_with_and_without_waiting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    for path in _fixtures(tmp_path):
        # when:
        waiting = _prove(monkeypatch, path, postpone=True)
        eager = _prove(monkeypatch, path, postpone=False)
        # then:
        assert _verdicts(waiting) == _verdicts(eager), path.name
        assert waiting.exploration is not None and eager.exploration is not None
        assert waiting.exploration["states"] <= eager.exploration["states"], path.name


def test_a_timer_that_can_never_fire_does_not_make_time_pass(
    monkeypatch: pytest.MonkeyPatch,
):
    # given: the alarm waits a day, and the check's clock stops at 2
    path = FIXTURES / "never-due.petrinet"
    # when:
    waiting = _prove(monkeypatch, path, postpone=True)
    eager = _prove(monkeypatch, path, postpone=False)
    # then: the clock never ticks, and the verdicts stay the same
    assert waiting.exploration is not None and eager.exploration is not None
    assert (waiting.exploration["states"], eager.exploration["states"]) == (9, 27)
    assert _verdicts(waiting) == _verdicts(eager)
    assert [f.transition for p in waiting.proofs for f in p.findings] == ["alarm"]


def test_a_record_changes_only_when_a_step_that_reads_it_is_ready(
    monkeypatch: pytest.MonkeyPatch,
):
    # given: the verdict is read at the gate only, and a shelved request may go round again
    path = FIXTURES / "late-gate.petrinet"
    settings = ProofSettings(firings={"again": 2})
    # when:
    waiting = _prove(monkeypatch, path, postpone=True, settings=settings)
    eager = _prove(monkeypatch, path, postpone=False, settings=settings)
    # then: no extra copy per verdict, and the same verdicts
    assert waiting.exploration is not None and eager.exploration is not None
    assert (waiting.exploration["states"], eager.exploration["states"]) == (42, 48)
    assert _verdicts(waiting) == _verdicts(eager)
    assert waiting.status == "proved"


def test_a_record_move_held_back_where_it_was_enabled_is_not_dead(
    monkeypatch: pytest.MonkeyPatch,
):
    # given: the job always has a step to take, and only a parked job reads the switch
    path = FIXTURES / "waiting-switch.petrinet"
    # when:
    waiting = _prove(monkeypatch, path, postpone=True)
    eager = _prove(monkeypatch, path, postpone=False)
    # then: the flip never fires while it waits, but it could, so only the
    # parked job's steps are dead
    dead = [p for p in waiting.proofs if p.subject == "no dead transitions"]
    assert [f.transition for f in dead[0].findings] == ["park", "use"]
    assert _verdicts(waiting) == _verdicts(eager)


def _always_started(*_: object) -> bool:
    return True


def _prove_holding(
    monkeypatch: pytest.MonkeyPatch, path: Path, *, hold: bool = True
) -> ProofReport:
    net, composition = load(path)
    with monkeypatch.context() as patch:
        if not hold:
            # The environment writes every place at any time.
            patch.setattr(soundness.Explorer, "_started", _always_started)
        return prove(net, facts=["soundness"], composition=composition)


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


def test_a_clerk_can_ask_which_branch_holds_a_title_before_opening(
    monkeypatch: pytest.MonkeyPatch,
):
    # given: the desk refers a title only after it asked, and it asks before opening
    path = FIXTURES / "asked-before-opening.petrinet"
    # when:
    report = _prove_holding(monkeypatch, path)
    # then: asking and skipping both fire
    assert _dead(report) == []
    assert report.status == "proved"


def test_every_fixture_gets_the_same_verdicts_as_without_holding_writes_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    for path in _fixtures(tmp_path):
        # when:
        holding = _prove_holding(monkeypatch, path)
        eager = _prove_holding(monkeypatch, path, hold=False)
        # then:
        assert _statuses(holding) == _statuses(eager), path.name
        assert _dead(holding) == _dead(eager), path.name
        assert holding.exploration is not None and eager.exploration is not None
        assert holding.exploration["states"] <= eager.exploration["states"], path.name
