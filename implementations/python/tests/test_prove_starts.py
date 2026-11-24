"""Repeated starts: the instance starts more than once, with the same keys (ADR 0052)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from velocitron_petrinet import parse_petrinet_text
from velocitron_cli import main
from velocitron_analysis import (
    Invariant,
    Proof,
    ProofReport,
    ProofSettings,
    load_net,
    prove,
    read_settings,
)
from velocitron_analysis.analysis import NetModel
from velocitron_analysis.refinement import refinement_environment
from velocitron_analysis.soundness import (
    Environment,
    explore,
)
from velocitron_engine import Token

FIXTURES = Path(__file__).parent / "fixtures" / "prove"
REPEAT = FIXTURES / "repeat-start.petrinet"
TWO_STARTS = "the instance starts 2 times, with the same keys each time"


def _proof(report: ProofReport, subject: str) -> Proof:
    (proof,) = [p for p in report.proofs if p.subject.startswith(subject)]
    return proof


def test_a_step_that_needs_an_earlier_start_is_dead_with_one_start():
    # given: [repeat] needs the counter a first job set
    net = load_net(REPEAT)
    # when:
    report = prove(net, facts=["soundness"])
    # then:
    dead = _proof(report, "no dead transitions")
    assert dead.status == "refuted"
    assert [f.summary for f in dead.findings] == ["[repeat] never fires."]


def test_a_second_start_reaches_the_step_and_every_fact_holds():
    # given:
    net = load_net(REPEAT)
    # when:
    report = prove(net, facts=["soundness"], settings=ProofSettings(starts=2))
    # then:
    assert report.status == "proved"
    assert {p.subject: p.assumptions for p in report.proofs} == {
        "option to complete": (TWO_STARTS,),
        "proper completion": (TWO_STARTS,),
        "no dead transitions": (TWO_STARTS,),
    }
    assert report.exploration is not None
    assert report.exploration["starts"] == 2


def test_the_check_stops_only_when_every_start_has_finished():
    # given:
    net = load_net(REPEAT)
    assert net.proofs is not None
    model = NetModel(net, final=net.proofs.final)
    # when:
    explorer = explore(net, model, environment=Environment(starts=2), max_states=100)
    # then: one job done is no end; the second start still comes
    ends = {len(s.marking.get("done", ())) for s in explorer.states if s.final}
    assert ends == {2}
    assert any(len(s.marking.get("done", ())) == 1 for s in explorer.states)


def test_a_final_marking_counts_once_per_start():
    # given: two final markings, one of them needs two places
    net = parse_petrinet_text(
        "net ends\n\n"
        "(start) -> [pair] -> (a)\n"
        "[pair] -> (b)\n"
        "(start) -> [single] -> (c)\n"
        "final (a) + (b), (c)\n"
    )
    assert net.proofs is not None
    roles = NetModel(net, final=net.proofs.final).roles
    token = Token("token", {})

    def marking(**counts: int) -> dict[str, list[Token]]:
        return {place: [token] * count for place, count in counts.items()}

    # when / then: each start needs its own tokens
    assert roles.finished(marking(a=1, b=1), 1)
    assert not roles.finished(marking(a=1, b=1), 2)
    assert roles.finished(marking(a=1, b=1, c=1), 2)
    assert roles.finished(marking(a=2, b=2), 2)
    assert roles.finished(marking(c=2), 2)
    assert not roles.finished(marking(a=2, b=1), 2)


def test_a_refutation_that_needs_the_second_start_says_so():
    # given: a second job waits for a counter that never lets it through
    net = parse_petrinet_text(
        "net stuck\n\n"
        "(jobs) -job-> [take]\n"
        "[take] -job-> (taken)\n"
        "@new: (taken) -job-> [first]\n"
        "[first] -job-> (done)\n"
        "@new_in: (counter) -seen-> [first]\n"
        "@new_out: [first] -seen-> (counter)\n"
        '@new_in predicate cel "!before"\n'
        '@new_in correlate cel "token.account == binding.taken[0].account"\n'
        "@new_out data cel \"{'account': binding.counter[0].account, 'before': true}\"\n"
        "(jobs) port input job\n"
        'system "counter"\n'
        '(counter) kept by "counter" starts as cel '
        "\"{'account': instance.account, 'before': false}\"\n"
        "domain seen.before true false\n"
        "final (done)\n"
    )
    # when:
    one = prove(net, facts=["soundness"])
    two = prove(net, facts=["soundness"], settings=ProofSettings(starts=2))
    # then: the deadlock exists only when the job starts twice, and says so
    assert _proof(one, "option to complete").status == "proved"
    option = _proof(two, "option to complete")
    assert option.status == "refuted"
    assert option.assumptions == (TWO_STARTS,)


def test_a_declared_invariant_counts_every_start():
    # given: every job ends in (done), so jobs + done is the number of starts
    net = load_net(REPEAT)
    total = Invariant({"jobs": 1, "done": 1}, constant=2, name="jobs")
    # when:
    one = prove(net, facts=["invariants"], invariants=[total])
    two = prove(
        net, facts=["invariants"], invariants=[total], settings=ProofSettings(starts=2)
    )
    # then:
    assert _proof(one, "jobs").status == "refuted"
    assert _proof(two, "jobs").status == "proved"


def test_a_refining_net_starts_once():
    # given:
    environment = Environment(firings={"inner.t": 2}, starts=3)
    # when:
    local = refinement_environment("inner", environment)
    # then:
    assert local.starts == 1
    assert local.firings == {"t": 2}


def test_read_settings_reads_starts(tmp_path: Path):
    # given:
    path = tmp_path / "starts.json5"
    path.write_text("{environment: {starts: 2}}", encoding="utf-8")
    # when:
    settings = read_settings(path)
    # then:
    assert settings.starts == 2


@pytest.mark.parametrize("starts", ["0", "-1", "true", "1.5", "'2'"])
def test_read_settings_rejects_starts_that_are_not_a_positive_count(
    tmp_path: Path, starts: str
):
    # given:
    path = tmp_path / "starts.json5"
    path.write_text(f"{{environment: {{starts: {starts}}}}}", encoding="utf-8")
    # when / then:
    with pytest.raises(ValueError, match=r"environment\.starts is a positive count"):
        read_settings(path)


def test_injecting_into_a_start_place_is_an_error():
    # given:
    net = load_net(REPEAT)
    # when / then:
    with pytest.raises(ValueError, match=r"set environment\.starts"):
        prove(net, facts=["soundness"], settings=ProofSettings(injections={"jobs": 2}))


def test_the_report_states_the_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # given:
    settings = tmp_path / "starts.json5"
    settings.write_text("{environment: {starts: 2}}", encoding="utf-8")
    net = str(REPEAT)
    # when:
    main(["prove", net, "--fact", "soundness", "--domains", str(settings)])
    text = capsys.readouterr().out
    main(["prove", net, "--fact", "soundness", "--domains", str(settings), "--json"])
    payload = json.loads(capsys.readouterr().out)
    # then:
    lines = text.splitlines()
    assert (
        "starts: the instance starts 2 times, with the same keys; "
        "a final marking counts once per start"
    ) in lines
    assert lines.count(f"           assumes: {TWO_STARTS}") == 3
    assert payload["exploration"]["starts"] == 2
    assert {f["subject"]: f.get("assumptions") for f in payload["facts"]} == {
        "option to complete": [TWO_STARTS],
        "proper completion": [TWO_STARTS],
        "no dead transitions": [TWO_STARTS],
    }
