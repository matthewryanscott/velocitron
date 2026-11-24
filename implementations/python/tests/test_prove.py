"""velocitron prove: choice coverage, place invariants and soundness."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from velocitron_petrinet import parse_petrinet_text
from velocitron_cli import main
from velocitron_analysis import (
    Invariant,
    Proof,
    ProofReport,
    ProofSettings,
    load,
    load_net,
    prove,
    read_settings,
)
from velocitron_analysis.analysis import NetModel
from velocitron_analysis.firing import MarkingKeys
from velocitron_engine import Marking, Token
from velocitron_analysis.soundness import (
    Environment,
    explore,
)
from velocitron_play import (
    read_play,
)
from velocitron_play_check import (
    check_play,
)

FIXTURES = Path(__file__).parent / "fixtures" / "prove"


def _proof(report: ProofReport, subject: str) -> Proof:
    (proof,) = [p for p in report.proofs if p.subject.startswith(subject)]
    return proof


def _net_from(
    tmp_path: Path, name: str, extra: str = "", drop: str | None = None
) -> Path:
    text = (FIXTURES / f"{name}.petrinet").read_text(encoding="utf-8")
    if drop is not None:
        text = "\n".join(line for line in text.splitlines() if line != drop) + "\n"
    target = tmp_path / f"{name}.petrinet"
    target.write_text(text + extra, encoding="utf-8")
    return target


def _plays_pass(report: ProofReport) -> list[str]:
    files = [f.play for p in report.proofs for f in p.findings if f.play]
    for file in files:
        result = check_play(read_play(file))
        assert result.passed, (file, [d.render() for d in result.diagnostics()])
    return files


def test_a_sound_workflow_net_proves_every_soundness_fact():
    # given:
    net = load_net(FIXTURES / "sound-workflow.petrinet")
    # when:
    report = prove(net)
    # then:
    assert report.status == "proved"
    assert [p.details["weights"] for p in report.proofs if p.fact == "invariant"] == [
        {"i": 1, "p1": 1, "p3": 1, "o": 1},
        {"i": 1, "p2": 1, "p4": 1, "o": 1},
    ]
    assert _proof(report, "place invariant 1").statement.startswith(
        "i + p1 + p3 + o = 1"
    )


def test_a_choice_joined_by_an_and_join_deadlocks_and_its_join_is_dead(tmp_path: Path):
    # given:
    path = FIXTURES / "deadlock-workflow.petrinet"
    # when:
    report = prove(
        load_net(path), facts=["soundness"], counterexamples=tmp_path, net_file=path
    )
    # then:
    option = _proof(report, "option to complete")
    assert option.status == "refuted"
    assert option.findings[0].kind == "deadlock"
    assert [m.transition for m in option.findings[0].path] == ["a"]
    dead = _proof(report, "no dead transitions")
    assert [f.transition for f in dead.findings] == ["join"]
    assert len(_plays_pass(report)) == 1


def test_a_branch_left_running_refutes_proper_completion(tmp_path: Path):
    # given:
    path = FIXTURES / "improper-workflow.petrinet"
    # when:
    report = prove(
        load_net(path), facts=["soundness"], counterexamples=tmp_path, net_file=path
    )
    # then:
    assert _proof(report, "option to complete").status == "proved"
    proper = _proof(report, "proper completion")
    assert proper.status == "refuted"
    assert "(p2)" in proper.findings[0].summary
    _plays_pass(report)


def test_choice_coverage_reports_a_gap_and_an_overlap_with_witnesses(tmp_path: Path):
    # given:
    path = FIXTURES / "orders.petrinet"
    # when:
    report = prove(
        load_net(path), facts=["choice"], counterexamples=tmp_path, net_file=path
    )
    # then:
    choice = _proof(report, "choice at (orders)")
    assert choice.status == "refuted"
    gap, overlap = choice.findings
    assert gap.kind == "gap" and gap.cases == {"status": "⟨other⟩"}
    assert overlap.kind == "overlap" and overlap.enabled == ("cancel", "refund")
    assert overlap.cases == {"amount": "101", "status": '"cancelled"'}
    assert overlap.witness == {
        "orders": [{"type": "purchase", "data": {"amount": 101, "status": "cancelled"}}]
    }
    assert len(_plays_pass(report)) == 2


def test_choice_gaps_are_disjoint_and_name_ranges_in_plain_terms():
    # given: a poll result no branch takes when it has notes and a high wear share
    net = load_net(FIXTURES / "polled.petrinet")
    # when:
    report = prove(net, facts=["choice"])
    # then: the second gap leaves out the ⟨other⟩ state the first one holds
    other, high_share = _proof(report, "choice at (polled)").findings
    assert other.cases == {"state": "⟨other⟩"}
    assert high_share.cases is not None
    assert high_share.cases["state"] == '"SUCCEEDED"'
    # and: numbers and sizes read as the ranges the CEL compares
    assert high_share.summary == (
        "no transition takes the copy token when size(notes) > 0"
        ' and state is "SUCCEEDED" and wearShare ≥ 0.01'
    )


def test_a_two_sided_number_range_names_both_ends(tmp_path: Path):
    # given: orders that nothing ships between two amounts
    path = _net_from(
        tmp_path,
        "orders",
        "@ship_in predicate cel \"status == 'paid' && (amount < 10 || amount > 50)\"\n",
        drop="@ship_in predicate cel \"status == 'paid'\"",
    )
    # when:
    report = prove(load_net(path), facts=["choice"])
    # then:
    summaries = [f.summary for f in _proof(report, "choice at (orders)").findings]
    assert (
        "no transition takes the purchase token"
        ' when 10 ≤ amount ≤ 50 and status is "paid"'
    ) in summaries


def test_a_suppression_annotation_waives_an_overlap(tmp_path: Path):
    # given:
    path = _net_from(
        tmp_path,
        "orders",
        '[refund] annotation lint {"suppress": ["choice-overlap"]}\n',
    )
    # when:
    report = prove(load_net(path), facts=["choice"])
    # then:
    kinds = [f.kind for f in _proof(report, "choice at (orders)").findings]
    assert kinds == ["gap", "waived"]


def test_a_field_the_net_only_sets_from_literals_has_no_other_value():
    # given: a verdict result that only the two checks set, each to a literal
    net = load_net(FIXTURES / "verdicts.petrinet")
    # when:
    report = prove(net, facts=["choice"])
    # then: the choice on the result has no ⟨other⟩ gap
    assert _proof(report, "choice at (verdicts)").status == "proved"
    assert report.model["domains"]["verdict.result"]["values"] == [
        "approved",
        "escalated",
    ]


def test_a_field_another_producer_may_set_keeps_its_other_value(tmp_path: Path):
    # given: an appeal that carries in a verdict the environment wrote
    path = _net_from(
        tmp_path, "verdicts", "(appeals) -verdict-> [appeal] -verdict-> (verdicts)\n"
    )
    # when:
    report = prove(load_net(path), facts=["choice"])
    # then:
    (gap,) = _proof(report, "choice at (verdicts)").findings
    assert gap.kind == "gap" and gap.cases == {"result": "⟨other⟩"}


def test_a_domain_override_closes_the_gap():
    # given:
    settings = ProofSettings(domains={"purchase.status": ["paid", "cancelled"]})
    # when:
    report = prove(
        load_net(FIXTURES / "orders.petrinet"), facts=["choice"], settings=settings
    )
    # then:
    kinds = [f.kind for f in _proof(report, "choice at (orders)").findings]
    assert kinds == ["overlap"]


@pytest.mark.parametrize(
    "test", ["tool != 'x'", "tool != null", "!(tool == 'x')", "!(tool in ['x'])"]
)
def test_a_field_a_test_excludes_a_literal_from_also_takes_other_values(
    tmp_path: Path, test: str
):
    # given: [a] takes a job whose tool is not the one literal, [b] the rest
    literal = "null" if "null" in test else "'x'"
    path = tmp_path / "split.petrinet"
    path.write_text(
        "net split\n"
        "@a_in: (asked) -job-> [a]\n"
        "[a] -job-> (done)\n"
        f'@a_in predicate cel "{test}"\n'
        "@b_in: (asked) -job-> [b]\n"
        "[b] -job-> (done)\n"
        f'@b_in predicate cel "tool == {literal}"\n'
        "(asked) port input job\n"
        "final (done)\n",
        encoding="utf-8",
    )
    # when:
    report = prove(load_net(path), facts=["soundness"])
    # then: the environment writes a tool other than the literal, so [a] fires
    assert report.status == "proved"
    assert report.model["domains"]["job.tool"]["values"][-1] == "⟨other⟩"
    assert "soundnessValues" not in report.model["domains"]["job.tool"]


def test_the_mutex_lock_invariant_is_a_semiflow_and_a_declared_invariant_is_proved():
    # given:
    net = load_net(FIXTURES / "mutex.petrinet")
    lock = Invariant({"free": 1, "crit1": 1, "crit2": 1}, constant=1, name="lock")
    wrong = Invariant({"free": 1, "crit1": 1}, constant=1, name="half lock")
    # when:
    report = prove(net, facts=["invariants"], invariants=[lock, wrong])
    # then:
    flows = [
        p.details["weights"] for p in report.proofs if p.subject.startswith("place")
    ]
    assert {"crit1": 1, "crit2": 1, "free": 1} in flows
    assert all(
        p.details["initial"] == 1
        for p in report.proofs
        if p.subject.startswith("place")
    )
    assert _proof(report, "lock").status == "proved"
    half = _proof(report, "half lock")
    assert half.status == "refuted"
    assert [f.transition for f in half.findings] == ["enter2", "exit2"]


def test_an_invariant_names_no_key_that_only_a_copy_joins():
    # given: [t] copies the job's dest into a note; no correlate names it
    net = parse_petrinet_text(
        "net copied\n\n"
        "@t_out: (a) -job-> [t] -note-> (b)\n"
        "@t_out data cel \"{'dest': binding.a[0].dest}\"\n"
    )
    # when:
    report = prove(net, facts=["invariants"])
    # then: the count is proved, and no per-key reading is offered
    (flow,) = [p for p in report.proofs if p.subject.startswith("place")]
    assert "correlate" not in flow.statement and "per dest" not in flow.statement
    assert "sharedKey" not in flow.details


def test_an_invariant_names_the_key_a_correlate_joins():
    # given: [t] reads the job's route by its dest
    net = parse_petrinet_text(
        "net routed\n\n"
        "(a) -job-> [t] -job-> (b)\n"
        "@route: (routes) -route->? [t]\n"
        '@route correlate cel "token.dest == binding.a[0].dest"\n'
    )
    # when:
    report = prove(net, facts=["invariants"])
    # then:
    (flow,) = [
        p
        for p in report.proofs
        if p.subject.startswith("place") and "a" in p.details["weights"]
    ]
    assert flow.details["sharedKey"] == "dest"
    assert "likely holds per dest" in flow.statement


def test_a_net_without_a_final_place_leaves_option_to_complete_unknown():
    # when:
    report = prove(load_net(FIXTURES / "mutex.petrinet"), facts=["soundness"])
    # then:
    assert _proof(report, "option to complete").status == "unknown"


def test_soundness_depends_on_the_timer_priority(tmp_path: Path):
    # given:
    with_priority = load_net(FIXTURES / "deadline.petrinet")
    without = _net_from(tmp_path, "deadline", drop="[give_up] priority 1")
    # when:
    kept = prove(with_priority)
    dropped = prove(
        load_net(without), counterexamples=tmp_path / "cex", net_file=without
    )
    # then:
    assert _proof(kept, "option to complete").status == "proved"
    assert [f.kind for f in _proof(kept, "choice at (waiting)").findings] == [
        "resolved"
    ]
    assert _proof(dropped, "option to complete").status == "refuted"
    assert _proof(dropped, "option to complete").findings[0].kind == "deadlock"
    assert [f.kind for f in _proof(dropped, "choice at (waiting)").findings] == [
        "overlap"
    ]
    _plays_pass(dropped)


_ROOT = Path(__file__).resolve().parents[3]
# Each timer compares the clock with arithmetic on a field, such as
# `clock.now >= latch.fired_at + latch.cadence_s`.
_ARITHMETIC_TIMERS = [
    "examples/capability-ladder/09-cadence-tick/cadence-tick.petrinet",
    "examples/capability-ladder/12-reading-hour-fragment/reading_cadence.petrinet",
    "examples/capability-ladder/12-reading-hour-fragment/reading_hour.petrinet",
    "implementations/python/tests/fixtures/prove/arithmetic-timer.petrinet",
]


@pytest.mark.parametrize("name", _ARITHMETIC_TIMERS)
def test_a_timer_with_arithmetic_on_derived_domains_leaves_soundness_unknown(
    name: str,
):
    # given: a timer compares the clock with a sum, under the default domains
    net, composition = load(_ROOT / name)
    # when:
    report = prove(net, facts=["soundness"], composition=composition)
    # then: the clock takes time slots, the search ends, and no slot can say
    # when the sum is due, so no verdict is given
    clocks = {tr.timer.clock for tr in net.transitions if tr.timer is not None}
    colors = {p.accepts[0] for p in net.places if p.name in clocks}
    domains = report.model["domains"]
    found = [d for key, d in domains.items() if key.split(".")[0] in colors]
    assert found and all(d["kind"] == "clock" for d in found), domains
    assert all(isinstance(v, int) for d in found for v in d["values"])
    assert report.exploration is not None and not report.exploration["capped"]
    assert [p.status for p in report.proofs] == ["unknown"] * 3
    reason = _proof(report, "no dead transitions").reason or ""
    assert "compares the clock with arithmetic" in reason, reason


def test_a_timer_with_arithmetic_is_proved_on_the_values_a_domains_file_gives(
    tmp_path: Path,
):
    # given: the cadence with times its sum can reach
    path = _ROOT / _ARITHMETIC_TIMERS[0]
    domains = tmp_path / "cadence.domains.json5"
    domains.write_text(
        '{domains: {"clock.now": [0, 300, 600], "tick_latch.fired_at": [0, 300],'
        ' "tick_latch.cadence_s": [300]}}',
        encoding="utf-8",
    )
    # when:
    report = prove(load_net(path), facts=["soundness"], settings=read_settings(domains))
    # then: the tick is due at 300, so it fires
    assert _proof(report, "no dead transitions").status == "proved"


@pytest.mark.parametrize(
    "timer",
    ["clock.now >= idle.since + idle.wait", "clock.now - idle.since >= idle.wait"],
)
def test_a_timer_that_adds_a_wait_to_a_time_copied_from_the_clock_is_proved(
    tmp_path: Path, timer: str
):
    # given: `since` is copied from the clock, and the domains file gives the
    # clock and the wait values
    text = (FIXTURES / "idle-since.petrinet").read_text(encoding="utf-8")
    path = tmp_path / "idle-since.petrinet"
    path.write_text(
        text.replace("clock.now >= idle.since + idle.wait", timer), encoding="utf-8"
    )
    domains = read_settings(FIXTURES / "idle-since.domains.json5")
    # when:
    report = prove(load_net(path), settings=domains)
    # then: `since` holds clock times, as a deadline field does, so the sum
    # is due at a time slot and every fact has a verdict
    assert {p.subject: p.status for p in report.proofs if p.status != "proved"} == {}
    assert _proof(report, "choice at (idle)").status == "proved"


def test_a_timer_that_adds_a_wait_with_derived_values_leaves_soundness_unknown(
    tmp_path: Path,
):
    # given: the wait has no values from a domains file
    domains = tmp_path / "idle-since.domains.json5"
    domains.write_text('{domains: {"tick.now": [0, 600]}}', encoding="utf-8")
    # when:
    report = prove(
        load_net(FIXTURES / "idle-since.petrinet"), settings=read_settings(domains)
    )
    # then: only the wait is named; `since` holds clock times
    reason = _proof(report, "no dead transitions").reason or ""
    assert "the derived values of vm.wait cannot say" in reason, reason
    assert _proof(report, "choice at (idle)").status == "unknown"


def test_a_choice_at_the_input_port_the_instance_arrives_at_is_proved():
    # given: [retry] and [keep] take the arriving teardown at its input port
    net = load_net(FIXTURES / "port-choice.petrinet")
    # when:
    report = prove(net, facts=["choice"])
    # then: the port's choice is checked like any other
    assert _proof(report, "choice at (asked)").status == "proved"


def test_an_overlap_at_the_input_port_is_refuted(tmp_path: Path):
    # given: [keep] also takes a retry answer
    path = tmp_path / "port-choice.petrinet"
    text = (FIXTURES / "port-choice.petrinet").read_text(encoding="utf-8")
    path.write_text(
        text.replace("choice != 'retry'", "choice == 'retry'"), encoding="utf-8"
    )
    # when:
    report = prove(load_net(path), facts=["choice"])
    # then:
    choice = _proof(report, "choice at (asked)")
    assert choice.status == "refuted"
    assert "overlap" in [f.kind for f in choice.findings]


def test_a_retry_dated_from_a_late_clock_matures_at_its_own_time():
    # given: the reminder may fire at 1060, past its 1000; the retry is then
    # due at 1120, a time the domains file does not list
    net = load_net(FIXTURES / "retry-after.petrinet")
    settings = read_settings(FIXTURES / "retry-after.domains.json5")
    # when:
    report = prove(net, facts=["soundness"], settings=settings)
    # then: time moves to the retry's maturity, so the net completes
    assert _proof(report, "option to complete").status == "proved"
    assert _proof(report, "no dead transitions").status == "proved"


def test_a_maturity_copied_from_the_clock_closes_the_state_space():
    # given: each idle look latches `since` from the clock, and [stop] matures
    # at `since + wait`; a latch taken at that maturity dates a later one
    net = load_net(FIXTURES / "idle-latch.petrinet")
    settings = read_settings(FIXTURES / "idle-latch.domains.json5")
    # when:
    report = prove(net, facts=["soundness"], settings=settings, max_states=5_000)
    # then: the exploration ends well inside the cap, and every fact holds
    assert {p.subject: p.status for p in report.proofs} == {
        "option to complete": "proved",
        "proper completion": "proved",
        "no dead transitions": "proved",
    }


def test_a_latch_on_the_last_listed_time_still_matures_past_it():
    # given: the latch copies 600, the clock's last listed time, and only
    # [stop]'s timer, due at 1200, ends the instance
    net = load_net(FIXTURES / "latch-late.petrinet")
    settings = read_settings(FIXTURES / "latch-late.domains.json5")
    # when:
    report = prove(net, facts=["soundness"], settings=settings)
    # then: time moves to the maturity of a latch on a listed time
    assert _proof(report, "option to complete").status == "proved"
    assert _proof(report, "no dead transitions").status == "proved"


def test_a_maturity_past_the_last_latch_leaves_completion_unknown_not_refuted():
    # given: idle-latch with no way out but [stop]; a latch taken at 1200, a
    # maturity, is due at 1800, where the exploration does not move time
    net = load_net(FIXTURES / "latch-loop.petrinet")
    settings = read_settings(FIXTURES / "latch-loop.domains.json5")
    # when:
    report = prove(net, facts=["soundness"], settings=settings, max_states=5_000)
    # then: time would end it there, so it is not a deadlock
    option = _proof(report, "option to complete")
    assert option.status == "unknown"
    assert "[stop]'s maturity at 1800" in (option.reason or ""), option.reason


def test_a_release_that_meets_the_same_verdict_is_a_livelock(tmp_path: Path):
    # given:
    path = FIXTURES / "release.petrinet"
    # when:
    report = prove(
        load_net(path), facts=["soundness"], counterexamples=tmp_path, net_file=path
    )
    # then:
    option = _proof(report, "option to complete")
    finding = option.findings[0]
    assert option.status == "refuted" and finding.kind == "livelock"
    assert [m.transition for m in finding.cycle] == ["hold", "release"]
    assert "an update of (verdicts)" in finding.summary
    (file,) = _plays_pass(report)
    assert "fire [hold]" in Path(file).read_text(encoding="utf-8")


def test_a_domain_fact_closes_the_gap_and_a_domains_file_still_wins(tmp_path: Path):
    # given: the orders net with a closed status
    path = _net_from(tmp_path, "orders", 'domain purchase.status "paid" "cancelled"\n')
    # when: proved from the net alone, then with a domains file
    declared = prove(load_net(path), facts=["choice"])
    overridden = prove(
        load_net(path),
        facts=["choice"],
        settings=ProofSettings(
            domains={"purchase.status": ["paid", "cancelled", "lost"]}
        ),
    )
    # then: the declared domain has no ⟨other⟩, so only the overlap stays
    assert [f.kind for f in _proof(declared, "choice at (orders)").findings] == [
        "overlap"
    ]
    assert declared.model["domains"]["purchase.status"] == {
        "kind": "declared",
        "values": ["paid", "cancelled"],
        "source": "declared",
    }
    # and: the file's value set wins and opens a gap again
    assert [f.kind for f in _proof(overridden, "choice at (orders)").findings] == [
        "gap",
        "overlap",
    ]


def test_a_declared_field_the_cel_never_reads_is_set_on_built_tokens(tmp_path: Path):
    # given: a closed field no CEL reads
    path = _net_from(tmp_path, "release", 'domain request.channel "web" "mail"\n')
    # when:
    report = prove(load_net(path), facts=["soundness"])
    # then: no built token breaks the domain, so no fact is unknown for it
    assert all("deposit failed" not in (proof.reason or "") for proof in report.proofs)
    assert report.model["domains"]["request.channel"]["values"] == ["web", "mail"]


def test_final_and_invariant_facts_are_proved_from_the_net(tmp_path: Path):
    # given: release with its final place named and the request counted
    path = _net_from(
        tmp_path,
        "release",
        "final (sent)\n"
        'invariant "one request" (requests) + (pending) + (held) + (sent) = 1\n'
        'invariant "wrong" (pending) + (held) = 1\n',
    )
    # when:
    report = prove(load_net(path), facts=["invariants", "soundness"])
    # then: the environment's one request makes the sum 1
    one = _proof(report, "one request")
    assert one.status == "proved"
    assert one.details["arrivals"] == 1
    assert one.statement.endswith(
        "once the environment has put its tokens into (requests)"
    )
    wrong = _proof(report, "wrong")
    assert wrong.status == "refuted"
    assert [f.summary for f in wrong.findings][0] == (
        "The initial marking gives 0, not 1."
    )
    assert report.model["roles"]["final"] == ["sent"]


def test_the_report_is_deterministic():
    # given:
    net = load_net(FIXTURES / "release.petrinet")
    # when:
    first, second = prove(net).json(), prove(net).json()
    # then:
    assert first == second


@pytest.mark.parametrize("name", ["deadline", "mutex", "release"])
def test_the_json_report_has_the_same_bytes_in_every_process(name: str):
    # given: two processes whose string hashes, and so set orders, differ
    command = [sys.executable, "-m", "velocitron_cli", "prove", "--json"]
    path = str(FIXTURES / f"{name}.petrinet")
    # when:
    outputs = [
        subprocess.run(
            [*command, path],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=False,
        ).stdout
        for seed in ("1", "7")
    ]
    # then:
    assert outputs[0] and outputs[0] == outputs[1]


def test_read_settings_accepts_json5_and_rejects_unknown_keys(tmp_path: Path):
    # given:
    good = tmp_path / "good.json5"
    good.write_text(
        '{domains: {"purchase.status": ["paid"]}, final: ["shipped"]}', encoding="utf-8"
    )
    bad = tmp_path / "bad.json"
    bad.write_text('{"domain": {}}', encoding="utf-8")
    # when:
    settings = read_settings(good)
    # then:
    assert settings.domains == {"purchase.status": ["paid"]}
    assert settings.final == ["shipped"]
    with pytest.raises(ValueError, match="unknown key 'domain'"):
        read_settings(bad)


def test_the_cli_prints_each_fact_and_exits_1_on_a_refutation(
    capsys: pytest.CaptureFixture[str],
):
    # when:
    code = main(["prove", str(FIXTURES / "orders.petrinet"), "--fact", "choice"])
    # then:
    out = capsys.readouterr().out
    assert code == 1
    assert "REFUTED  choice at (orders): [ship] | [cancel] | [refund]" in out
    assert "result: REFUTED" in out


def test_the_cli_exits_0_and_prints_json_when_nothing_is_refuted(
    capsys: pytest.CaptureFixture[str],
):
    # when:
    code = main(["prove", str(FIXTURES / "sound-workflow.petrinet"), "--json"])
    # then:
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["version"] == 1 and payload["status"] == "proved"
    assert {f["fact"] for f in payload["facts"]} == {"invariant", "soundness"}
    assert payload["exploration"]["states"] > 0


def test_the_report_and_the_cli_name_the_tool_version(
    capsys: pytest.CaptureFixture[str],
):
    # when: the version is asked for
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    printed = capsys.readouterr().out.strip()
    # and: a report is printed
    main(["prove", str(FIXTURES / "sound-workflow.petrinet"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    # then: both name the same tool and version
    assert raised.value.code == 0
    assert printed.startswith("velocitron ") and printed == payload["tool"]


def test_the_cli_reports_an_unreadable_net(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # when:
    code = main(["prove", str(tmp_path / "missing.petrinet")])
    # then:
    assert code == 1
    assert "error[PN200]" in capsys.readouterr().err


def test_an_abstract_step_wraps_the_token_it_takes(tmp_path: Path) -> None:
    # given: [borrow] has no data; its hold token carries the loan,
    # and [done] reads a field of that embedded loan
    (tmp_path / "outcome.petrinet").write_text(
        """net outcome "One borrow and its outcome"
(lending) -hold-> [borrow] -loan-> (ended)
(ended) -loan-> [done]
@out: [done] -hold-> (loaned)
@unlock: [done] -shelf-> (free)
@out data cel "binding.ended[0].hold"
@unlock data cel "{'id': binding.ended[0].hold.branch}"
final (loaned)
""",
        encoding="utf-8",
    )
    net = load_net(tmp_path / "outcome.petrinet")

    # when:
    report = prove(net)

    # then: the loan the prover starts with has the field [done] reads
    assert report.status == "proved"


RECORD_VERDICT = 'record "Shelf note"\n(verdicts) lives in "Shelf note"\n'
RECORD_SWITCH = 'record "Branch home"\n(switch) lives in "Branch home"\n'


def test_a_verdict_that_never_changes_leaves_its_rerun_step_dead():
    # given: the release writes the verdict back, so it is not updatable
    net = load_net(FIXTURES / "held-verdict.petrinet")
    # when:
    report = prove(net, facts=["soundness"])
    # then: once the verdict says hold, nothing makes [passed] possible
    dead = _proof(report, "no dead transitions")
    assert [f.transition for f in dead.findings] == ["passed"]


def test_a_verdict_kept_as_a_record_changes_and_frees_a_held_request(tmp_path: Path):
    # given: the verdict lives in a record column
    path = _net_from(tmp_path, "held-verdict", RECORD_VERDICT)
    # when:
    report = prove(load_net(path), facts=["soundness"])
    # then: the outside world may change the verdict, so [passed] fires
    assert report.status == "proved"
    assert report.model["roles"]["records"] == ["verdicts"]
    assert "verdicts" in report.model["roles"]["updatable"]
    assert "verdicts" not in report.model["roles"]["resources"]


def test_flipping_a_switch_back_and_forth_reads_as_a_livelock():
    # given: the flips consume and produce the switch, so they are net moves
    net = load_net(FIXTURES / "owner-switch.petrinet")
    # when:
    report = prove(net, facts=["soundness"])
    # then:
    option = _proof(report, "option to complete")
    assert option.status == "refuted" and option.findings[0].kind == "livelock"
    assert {m.transition for m in option.findings[0].cycle} == {
        "flip_to_new",
        "flip_back",
    }


def test_flips_of_a_record_are_the_outside_worlds_moves(tmp_path: Path):
    # given: the switch lives in a record column
    path = _net_from(tmp_path, "owner-switch", RECORD_SWITCH)
    # when:
    report = prove(load_net(path), facts=["soundness"])
    # then: a loaned copy waits for its slip; the flips are no loop
    assert report.status == "proved"


def test_a_record_move_that_never_fires_is_dead(tmp_path: Path):
    # given: a flip that no owner value allows
    path = _net_from(
        tmp_path,
        "owner-switch",
        RECORD_SWITCH
        + "@stuck: (switch) -switch->? [never_flip]\n"
        + "@stuck predicate cel \"owner == 'nobody'\"\n"
        + "[never_flip] annotation end true\n",
    )
    # when:
    report = prove(load_net(path), facts=["soundness"])
    # then: a record move still counts for "every transition fires"
    dead = _proof(report, "no dead transitions")
    assert [f.transition for f in dead.findings] == ["never_flip"]


def test_a_built_token_sets_a_declared_field_no_cel_reads():
    # given: [compare] is a handler whose check token nobody reads
    net = load_net(FIXTURES / "compare.petrinet")
    # when:
    report = prove(net, facts=["soundness"])
    # then: the built check has a declared result, so its deposit succeeds
    assert report.status == "proved"


def test_a_capped_search_names_a_read_only_producer_as_the_likely_cause():
    # given: a step that reads the done job and writes a note on every firing
    net = parse_petrinet_text(
        "net notes\n\n"
        "(start) -job-> [work] -job-> (done)\n"
        "(done) -job->? [note] -memo-> (notes)\n"
        "(notes) -memo-> [file] -memo-> (filed)\n"
        "final (filed)\n"
    )
    # when:
    report = prove(net, facts=["soundness"], max_states=20)
    # then: the exploration names the step, and the text report says why
    assert report.exploration is not None
    assert report.exploration["readOnlyProducers"] == ["note"]
    assert (
        "likely cause: [note] reads but consumes nothing, so it can fire again "
        "and again (lint rule read-only-producer)"
    ) in report.text().splitlines()


def test_a_capped_search_that_finds_no_loop_says_so_plainly():
    # given: a sound net, and a state cap too small to see it complete
    net = load_net(FIXTURES / "sound-workflow.petrinet")
    # when:
    report = prove(net, facts=["soundness"], max_states=2)
    # then: the finding names no empty loop
    option = _proof(report, "option to complete")
    assert option.status == "unknown"
    assert option.findings[0].summary == (
        "Net moves from here reach no final marking among the markings "
        "explored, and no loop or stop was found either."
    )


def test_read_settings_reads_firing_caps(tmp_path: Path):
    # given:
    path = tmp_path / "caps.json5"
    path.write_text("{environment: {firings: {redeliver: 2}}}", encoding="utf-8")
    # when:
    settings = read_settings(path)
    # then:
    assert settings.firings == {"redeliver": 2}


@pytest.mark.parametrize("cap", ["0", "-1", "1.5", "true", '"2"'])
def test_read_settings_rejects_a_firing_cap_that_is_not_a_positive_count(
    tmp_path: Path, cap: str
):
    # given:
    path = tmp_path / "caps.json5"
    path.write_text(
        f"{{environment: {{firings: {{redeliver: {cap}}}}}}}", encoding="utf-8"
    )
    # when / then:
    with pytest.raises(ValueError, match=r"firings\.redeliver is a positive count"):
        read_settings(path)


def test_a_firing_cap_on_an_unknown_transition_is_an_error():
    # given:
    net = load_net(FIXTURES / "redelivery.petrinet")
    # when / then:
    with pytest.raises(ValueError, match="unknown transition 'resend'"):
        prove(net, facts=["soundness"], settings=ProofSettings(firings={"resend": 2}))


def test_a_firing_cap_explores_exactly_that_many_turns_of_a_loop():
    # given: each send again leaves a try
    net = load_net(FIXTURES / "redelivery.petrinet")
    assert net.proofs is not None
    model = NetModel(net, final=net.proofs.final)
    # when:
    capped = explore(
        net, model, environment=Environment(firings={"redeliver": 2}), max_states=200
    )
    # then: the search ends after two turns
    assert not capped.capped
    tries = {len(state.marking.get("tries", ())) for state in capped.states}
    assert tries == {0, 1, 2}
    assert sum(state.cut for state in capped.states) == 1


def test_a_place_the_net_only_counts_keeps_as_many_tokens_as_its_readers_count():
    # given: each send again leaves a try that nothing takes, and [escalate]
    # reads three of them
    net = load_net(FIXTURES / "redelivery.petrinet")
    assert net.proofs is not None
    model = NetModel(net, final=net.proofs.final)
    # when:
    counted = explore(net, model, environment=Environment(), max_states=200)
    exact = explore(
        net, model, environment=Environment(), max_states=40, saturate=False
    )
    # then: with every try kept the markings never repeat; with three kept,
    # the loop closes and the search ends
    assert exact.capped
    assert not counted.capped
    tries = {len(state.marking.get("tries", ())) for state in counted.states}
    assert tries == {0, 1, 2, 3}


_SPIN = (
    "net spin\n\n"
    "(pending) -> [send] -> (sent)\n"
    "(sent) -> [redeliver] -> (pending)\n"
    "[redeliver] -try-> (tries)\n"
    "(sent) -> [finish] -> (done)\n"
    "(tries) -try->0 [finish]\n"
    "final (done)\n"
    "marking initial (pending) <- 1\n"
)


def test_the_check_of_a_long_capped_search_walks_its_markings_a_few_times():
    # given: without counting, each try is a new marking, so the search runs
    # into its state cap along one long line of markings
    net = parse_petrinet_text(_SPIN)
    assert net.proofs is not None
    model = NetModel(net, final=net.proofs.final)
    explorer = explore(
        net, model, environment=Environment(), max_states=6_000, saturate=False
    )
    # when:
    started = time.perf_counter()
    proofs = explorer.check()
    elapsed = time.perf_counter() - started
    # then: no loop is looked for from every marking in turn (that took
    # minutes: a search with a path copy per marking, from every marking)
    assert explorer.capped
    assert proofs[0].subject == "option to complete" and proofs[0].status == "unknown"
    assert elapsed < 10, elapsed


def test_a_loop_that_leaves_counted_tokens_is_proved_without_a_cap():
    # given:
    net = load_net(FIXTURES / "redelivery.petrinet")
    # when:
    uncapped = prove(net, facts=["soundness"])
    three = prove(
        net, facts=["soundness"], settings=ProofSettings(firings={"redeliver": 3})
    )
    # then: the same verdicts as three turns give, with no cap to assume
    assert [(p.subject, p.status) for p in uncapped.proofs] == [
        ("option to complete", "proved"),
        ("proper completion", "refuted"),
        ("no dead transitions", "proved"),
    ]
    assert [p.status for p in uncapped.proofs] == [p.status for p in three.proofs]
    assert all(p.assumptions == () for p in uncapped.proofs)


def test_a_step_only_a_further_turn_reaches_is_unknown_not_dead():
    # given: [escalate] needs a third try
    net = load_net(FIXTURES / "redelivery.petrinet")
    # when:
    two = prove(
        net, facts=["soundness"], settings=ProofSettings(firings={"redeliver": 2})
    )
    three = prove(
        net, facts=["soundness"], settings=ProofSettings(firings={"redeliver": 3})
    )
    # then: two turns cannot show [escalate] dead, three turns fire it
    dead = _proof(two, "no dead transitions")
    assert dead.status == "unknown"
    assert dead.findings == ()
    assert dead.reason == (
        "the firing cap stopped [redeliver] (at 2); not fired within the caps: "
        "[escalate]"
    )
    assert _proof(three, "no dead transitions").status == "proved"


def test_a_completion_found_within_the_caps_holds_under_the_caps():
    # given:
    net = load_net(FIXTURES / "redelivery.petrinet")
    # when:
    report = prove(
        net, facts=["soundness"], settings=ProofSettings(firings={"redeliver": 2})
    )
    # then: the proof says what it assumes
    option = _proof(report, "option to complete")
    assert option.status == "proved"
    assert option.assumptions == ("[redeliver] fires at most 2 times on a path",)
    assert option.as_json()["assumptions"] == [
        "[redeliver] fires at most 2 times on a path"
    ]


def test_a_loop_the_cap_cuts_is_unknown_not_a_deadlock_nor_proved():
    # given: once [redeliver] fired, [finish] never can: a real livelock
    net = parse_petrinet_text(
        "net spin\n\n"
        "(pending) -> [send] -> (sent)\n"
        "(sent) -> [redeliver] -> (pending)\n"
        "[redeliver] -try-> (tries)\n"
        "(sent) -> [finish] -> (done)\n"
        "(tries) -try->0 [finish]\n"
        "final (done)\n"
        "marking initial (pending) <- 1\n"
    )
    # when:
    report = prove(
        net, facts=["soundness"], settings=ProofSettings(firings={"redeliver": 2})
    )
    # then:
    option = _proof(report, "option to complete")
    assert option.status == "unknown"
    assert option.reason == (
        "some markings reach a final marking, if at all, only by firing "
        "[redeliver] more often than its firing cap (2) allows"
    )


def test_the_report_lists_every_firing_cap_as_an_assumption(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # given:
    caps = tmp_path / "caps.json5"
    caps.write_text("{environment: {firings: {redeliver: 2}}}", encoding="utf-8")
    net = str(FIXTURES / "redelivery.petrinet")
    # when:
    main(["prove", net, "--fact", "soundness", "--domains", str(caps)])
    text = capsys.readouterr().out
    main(["prove", net, "--fact", "soundness", "--domains", str(caps), "--json"])
    payload = json.loads(capsys.readouterr().out)
    # then:
    lines = text.splitlines()
    assert (
        "firing cap: [redeliver] fires at most 2 times on a path "
        "(stopped it in 1 marking); results hold only within the caps"
    ) in lines
    # and: a refutation's path needs no cap, so only the other facts assume it
    assert (
        lines.count("           assumes: [redeliver] fires at most 2 times on a path")
        == 2
    )
    assert payload["exploration"]["firingCaps"] == {
        "redeliver": {"limit": 2, "stopped": 1}
    }
    assert {f["subject"]: f.get("assumptions") for f in payload["facts"]} == {
        "option to complete": ["[redeliver] fires at most 2 times on a path"],
        "proper completion": None,
        "no dead transitions": ["[redeliver] fires at most 2 times on a path"],
    }


def test_a_marking_key_covers_the_marked_places_asked_for_in_place_order():
    # given: a marking with an empty place, and the keys of three places
    keys = MarkingKeys(["a", "b", "c", "d"])
    marking = Marking(
        {
            "c": [Token("t", {"n": 2}), Token("t", {"n": 1})],
            "a": [Token("t", {"n": 3})],
            "b": [],
            "d": [Token("t", {"n": 4})],
        }
    )
    # when: the caller passes the places that hold tokens
    key = keys.key(marking, {"a", "b", "c"}, frozenset({"a", "c", "d"}))
    # then: each marked place asked for, in place order, its tokens sorted
    assert key == (("a", ('t {"n": 3}',)), ("c", ('t {"n": 1}', 't {"n": 2}')))
