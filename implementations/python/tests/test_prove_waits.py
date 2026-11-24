"""Intended waits: one case of a choice waits on purpose (ADR 0057)."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_cli import main
from velocitron_analysis import (
    Proof,
    ProofReport,
    ProofSettings,
    load,
    prove,
)

FIXTURES = Path(__file__).parent / "fixtures" / "prove"
WAITING = FIXTURES / "waiting-for-shelf.petrinet"
WAIT_FACT = "[fill] annotation wait"


def _choice(report: ProofReport) -> Proof:
    (proof,) = [p for p in report.proofs if p.fact == "choice"]
    return proof


def _variant(tmp_path: Path, old: str, new: str) -> Path:
    text = WAITING.read_text(encoding="utf-8")
    assert old in text
    target = tmp_path / "net.petrinet"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return target


def _without_wait(tmp_path: Path) -> Path:
    text = WAITING.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.startswith(WAIT_FACT)]
    target = tmp_path / "net.petrinet"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _prove(path: Path, settings: ProofSettings | None = None) -> ProofReport:
    net, composition = load(path)
    return prove(net, facts=["choice"], settings=settings, composition=composition)


def test_the_declared_case_is_an_intended_wait():
    # when:
    report = _prove(WAITING)
    # then: the choice holds, and the report names the wait
    proof = _choice(report)
    assert proof.status == "proved"
    (wait,) = proof.findings
    assert wait.kind == "wait"
    assert wait.summary == (
        "the hold token waits for the main branch to confirm the copy when (home) is "
        'route {"branch": "main", "confirmed": false, "damaged": false, "isbn": "own-isbn"}; '
        "[fill] declares this wait"
    )
    assert "    - intended wait: the hold token waits for" in report.text()


def test_without_the_wait_the_case_is_a_gap(tmp_path: Path):
    # when:
    report = _prove(_without_wait(tmp_path))
    # then:
    proof = _choice(report)
    assert proof.status == "refuted"
    assert [f.kind for f in proof.findings] == ["gap"]


def test_another_gap_at_the_same_choice_still_refutes():
    # given: an owner that neither step expects
    settings = ProofSettings(domains={"route.branch": ["main", "annex", "kiosk"]})
    # when:
    report = _prove(WAITING, settings)
    # then: only the declared case waits
    proof = _choice(report)
    assert proof.status == "refuted"
    assert sorted(f.kind for f in proof.findings) == ["gap", "wait"]
    (gap,) = [f for f in proof.findings if f.kind == "gap"]
    assert gap.cases is not None
    assert all('"kiosk"' in case for case in gap.cases["(home)"])


def test_a_condition_that_fails_to_evaluate_waits_for_nothing(tmp_path: Path):
    # given: a condition that reads a key the binding does not have
    path = _variant(tmp_path, "binding.home.exists", "binding.lock.exists")
    # when:
    report = _prove(path)
    # then:
    assert [f.kind for f in _choice(report).findings] == ["gap"]


def test_a_wait_in_a_composition_reads_the_net_s_own_names(tmp_path: Path):
    # given:
    path = tmp_path / "c.petrinet"
    path.write_text(f'composition c\nuse "{WAITING}" as gate\n', encoding="utf-8")
    # when:
    report = _prove(path)
    # then:
    proof = _choice(report)
    assert proof.status == "proved"
    assert [f.kind for f in proof.findings] == ["wait"]
    assert "[gate.fill] declares this wait" in proof.findings[0].summary


_CLOSING = """\
net closing

// A close ends the job, paused or parked, unless an answer for it is there:
// the answer's step takes the job then, and the close waits.
(paused) -job-> [end] -job-> (ended)
@end_close: (closed) -close-> [end]
@end_close correlate cel "token.id == binding.paused[0].id"
@end_none: (answered) -answer->0 [end]
@end_none correlate cel "token.id == binding.paused[0].id"
[end] priority 1

(parked) -job-> [end_parked] -job-> (ended)
@endp_close: (closed) -close-> [end_parked]
@endp_close correlate cel "token.id == binding.parked[0].id"
@endp_none: (answered) -answer->0 [end_parked]
@endp_none correlate cel "token.id == binding.parked[0].id"

(closed) port input close
"""
_INHIBITED_WAIT = (
    '[end] annotation wait {"when": "binding.answered.exists(a, '
    'a.id == binding.paused[0].id)", "for": "the answer\'s step"}\n'
)


def _closed(report: ProofReport) -> Proof:
    return next(p for p in report.proofs if p.subject.startswith("choice at (")
                and "closed)" in p.subject)


@pytest.mark.parametrize("composed", [False, True])
def test_a_wait_reads_a_place_the_transition_only_inhibits(
    tmp_path: Path, composed: bool
):
    # given: [end]'s wait names (answered), which [end] only inhibits
    net = tmp_path / "closing.petrinet"
    net.write_text(_CLOSING + _INHIBITED_WAIT, encoding="utf-8")
    path = net
    if composed:
        path = tmp_path / "c.petrinet"
        path.write_text(f'composition c\nuse "{net}" as gate\n', encoding="utf-8")
    # when:
    report = _prove(path)
    # then: the case with the job's answer there is the declared wait
    proof = _closed(report)
    assert proof.status == "proved", report.text()
    assert "wait" in [f.kind for f in proof.findings]
    # and: without the wait that case is a gap
    net.write_text(_CLOSING, encoding="utf-8")
    assert "gap" in [f.kind for f in _closed(_prove(path)).findings]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ('{"when": "true"}', 'must be {"when": "<CEL>", "for": "<what it waits for>"}'),
        ('{"when": "binding.switch.(", "for": "x"}', "is not valid CEL"),
        ("[]", "or a list of them"),
    ],
)
def test_a_malformed_wait_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str, message: str
):
    # given:
    text = WAITING.read_text(encoding="utf-8")
    (fact,) = [line for line in text.splitlines() if line.startswith(WAIT_FACT)]
    path = _variant(tmp_path, fact, f"{WAIT_FACT} {value}")
    # when:
    code = main(["validate", str(path)])
    # then: the error points at the wait
    err = capsys.readouterr().err
    assert code == 1
    assert message in err
    line = text.splitlines().index(fact) + 1
    assert f"{path}:{line}:1: error[PN202]" in err


def test_a_well_formed_wait_validates(capsys: pytest.CaptureFixture[str]):
    # when:
    code = main(["validate", str(WAITING)])
    # then:
    assert code == 0, capsys.readouterr().err
