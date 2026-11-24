"""The prover's benchmark command: its rows and its comparison with the record."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "prover_bench", ROOT / "tools" / "prover_bench.py"
)
assert _SPEC is not None and _SPEC.loader is not None
prover_bench = importlib.util.module_from_spec(_SPEC)
sys.modules["prover_bench"] = prover_bench
_SPEC.loader.exec_module(prover_bench)

_TOY = """\
net toy "A job is accepted or rejected"
@yes: (ready) -job-> [accept]
[accept] -job-> (done)
@no: (ready) -job-> [reject]
[reject] -job-> (done)
@yes predicate cel "ok"
@no predicate cel "{no}"
(ready) port input job
domain job.ok true false
final (done)
"""

_SET = """\
{{
  root: "nets",
  nets: [
    {{ net: "toy.petrinet"{measured} }},
    {{
      name: "toy-capped",
      net: "toy.petrinet",
      maxStates: 3,
      heavy: "stands for a net too large to explore whole",
    }},{fast}
  ],
}}
"""


def _bench_set(
    tmp_path: Path,
    *,
    no: str = "!ok",
    measured_only: bool = False,
    fast_only: bool = False,
) -> Path:
    """A set of two nets: the toy, and the same toy marked heavy with a cap;
    with ``fast_only``, a third: the toy run on the fast path alone."""
    nets = tmp_path / "nets"
    nets.mkdir(exist_ok=True)
    (nets / "toy.petrinet").write_text(_TOY.format(no=no), encoding="utf-8")
    (nets / "toy.domains.json5").write_text('{ instance: "job" }\n', encoding="utf-8")
    measured = ', measuredOnly: "a composition"' if measured_only else ""
    fast = (
        '\n    { name: "toy-fast", net: "toy.petrinet", '
        'fastOnly: "stands for a net the reference takes too long on" },'
        if fast_only
        else ""
    )
    bench_set = tmp_path / "set.json5"
    bench_set.write_text(_SET.format(measured=measured, fast=fast), encoding="utf-8")
    return bench_set


def _run(bench_set: Path, *args: str) -> int:
    numbers = bench_set.parent / "numbers"
    return prover_bench.main(
        ["--set", str(bench_set), "--numbers", str(numbers), *args]
    )


def _lines(bench_set: Path, name: str) -> list[dict[str, Any]]:
    text = (bench_set.parent / "numbers" / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _rewrite(bench_set: Path, name: str, records: list[dict[str, Any]]) -> None:
    (bench_set.parent / "numbers" / name).write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def test_a_row_for_each_net_with_its_counts_cost_and_each_proofs_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a set of two nets, the second capped and marked heavy
    bench_set = _bench_set(tmp_path)
    # when: the command records them
    code = _run(bench_set, "--record")
    # then: each net gets a row with markings, edges, seconds and peak memory
    out = capsys.readouterr().out
    rows = {
        line.split()[0]: line for line in out.splitlines() if line.startswith("toy")
    }
    assert rows["toy"].split()[1:3] == ["5", "4"]
    assert " s " in rows["toy"] and " MB " in rows["toy"]
    # and: the capped net stops at its cap and says it is heavy, and why
    assert rows["toy-capped"].split()[1] == "3"
    assert "heavy, cap 3" in rows["toy-capped"]
    assert "heavy: stands for a net too large to explore whole" in out
    # and: each proof's result is printed under its net
    assert "PROVED   choice: choice at (ready): [accept] | [reject]" in out
    assert "UNKNOWN  soundness: option to complete" in out
    # and: recording is not a difference
    assert code == 0


def test_the_counts_and_the_timings_are_recorded_apart(tmp_path: Path) -> None:
    # given:
    bench_set = _bench_set(tmp_path)
    # when:
    _run(bench_set, "--record")
    # then: the counts file has one line a net: settings, counts, each proof's result
    toy, capped = _lines(bench_set, "counts.jsonl")
    assert toy == {
        "net": "toy",
        "domains": "toy.domains.json5",
        "maxStates": 50_000,
        "capped": False,
        "markings": 5,
        "edges": 4,
        "proofs": {
            "choice: choice at (ready): [accept] | [reject]": "proved",
            "invariant: place invariant 1": "proved",
            "soundness: option to complete": "proved",
            "soundness: proper completion": "proved",
            "soundness: no dead transitions": "proved",
        },
    }
    assert (capped["net"], capped["maxStates"], capped["capped"]) == (
        "toy-capped",
        3,
        True,
    )
    # and: the timings file has the time and memory, and the machine they come from
    timing = _lines(bench_set, "timings.jsonl")[0]
    assert (timing["net"], timing["path"]) == ("toy", "reference")
    assert timing["seconds"] > 0 and timing["peakMB"] > 0
    assert {"machine", "cel", "velocitron", "date"} <= timing.keys()


def test_a_second_run_with_nothing_changed_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: recorded timings that differ from any new run
    bench_set = _bench_set(tmp_path)
    _run(bench_set, "--record")
    timings = _lines(bench_set, "timings.jsonl")
    for timing in timings:
        timing["seconds"], timing["peakMB"] = 41.0, 9000.0
    _rewrite(bench_set, "timings.jsonl", timings)
    capsys.readouterr()
    # when: the command runs again
    code = _run(bench_set)
    # then: time and memory are shown beside the record, never compared
    assert code == 0
    assert "(was 41.0 s)" in capsys.readouterr().out


def test_a_changed_count_of_markings_exits_1_and_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a record that says the toy had 6 markings
    bench_set = _bench_set(tmp_path)
    _run(bench_set, "--record")
    counts = _lines(bench_set, "counts.jsonl")
    counts[0]["markings"] = 6
    _rewrite(bench_set, "counts.jsonl", counts)
    capsys.readouterr()
    # when:
    code = _run(bench_set)
    # then:
    assert code == 1
    assert "toy: markings 5, recorded 6" in capsys.readouterr().out


def test_a_changed_result_exits_1_and_names_the_proof(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the record of the toy, then a change that lets both ways take a token
    bench_set = _bench_set(tmp_path)
    _run(bench_set, "--record")
    _bench_set(tmp_path, no="true")
    capsys.readouterr()
    # when:
    code = _run(bench_set, "--net", "toy")
    # then:
    out = capsys.readouterr().out
    assert code == 1
    assert (
        "toy: choice: choice at (ready): [accept] | [reject] REFUTED, recorded PROVED"
        in out
    )


def test_a_net_measured_only_shows_its_difference_and_never_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the toy marked measured only, as the compositions are, and changed
    bench_set = _bench_set(tmp_path, measured_only=True)
    _run(bench_set, "--record")
    _bench_set(tmp_path, no="true", measured_only=True)
    capsys.readouterr()
    # when:
    code = _run(bench_set, "--net", "toy")
    # then:
    out = capsys.readouterr().out
    assert code == 0
    assert "differences on nets measured only, which never fail:" in out
    assert "REFUTED, recorded PROVED" in out


def test_a_net_with_no_record_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: no record at all
    bench_set = _bench_set(tmp_path)
    # when:
    code = _run(bench_set, "--net", "toy")
    # then:
    assert code == 1
    assert "toy: no recorded numbers" in capsys.readouterr().out


def test_quick_leaves_out_nets_recorded_over_a_minute(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a record where the capped toy took two minutes
    bench_set = _bench_set(tmp_path)
    _run(bench_set, "--record")
    timings = _lines(bench_set, "timings.jsonl")
    timings[1]["seconds"] = 120.0
    _rewrite(bench_set, "timings.jsonl", timings)
    capsys.readouterr()
    # when:
    code = _run(bench_set, "--quick")
    # then: the slow net is named as left out, and not run
    out = capsys.readouterr().out
    assert code == 0
    assert "left out by --quick: toy-capped (recorded 120.0 s)" in out
    assert not any(line.startswith("toy-capped ") for line in out.splitlines())


def test_recording_part_of_the_set_keeps_the_other_lines(tmp_path: Path) -> None:
    # given: a record of both nets
    bench_set = _bench_set(tmp_path)
    _run(bench_set, "--record")
    before = _lines(bench_set, "timings.jsonl")
    # when: only the toy is recorded again
    _run(bench_set, "--record", "--net", "toy")
    # then: the capped toy's lines are kept as they were, in set order
    after = _lines(bench_set, "timings.jsonl")
    assert [line["net"] for line in after] == ["toy", "toy-capped"]
    assert after[1] == before[1]
    assert [line["net"] for line in _lines(bench_set, "counts.jsonl")] == [
        "toy",
        "toy-capped",
    ]


def test_a_net_the_set_runs_on_the_fast_path_alone_is_left_out_of_a_reference_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the toy, the capped toy, and the toy marked fast only, all recorded
    bench_set = _bench_set(tmp_path, fast_only=True)
    _run(bench_set, "--record")
    _run(bench_set, "--fast", "--record", "--net", "toy-fast")
    fast_lines = [
        _lines(bench_set, name)[2] for name in ("counts.jsonl", "timings.jsonl")
    ]
    capsys.readouterr()
    # when: the reference records the set
    code = _run(bench_set, "--record")
    # then: the fast-only net is named as left out, and not run
    out = capsys.readouterr().out
    assert code == 0
    assert "left out of the reference: toy-fast (fast only)" in out
    assert not any(line.startswith("toy-fast ") for line in out.splitlines())
    # and: its lines stay as the fast path recorded them
    assert [
        _lines(bench_set, name)[2] for name in ("counts.jsonl", "timings.jsonl")
    ] == fast_lines


def test_a_fast_record_writes_only_the_fast_only_nets_with_their_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the reference's record of the toy and the capped toy
    bench_set = _bench_set(tmp_path, fast_only=True)
    _run(bench_set, "--record")
    before = _lines(bench_set, "timings.jsonl")
    capsys.readouterr()
    # when: the fast path records the whole set
    code = _run(bench_set, "--fast", "--record")
    # then: the fast-only net runs and gets its lines, in set order
    out = capsys.readouterr().out
    assert code == 0
    assert any(line.startswith("toy-fast ") for line in out.splitlines())
    counts = _lines(bench_set, "counts.jsonl")
    assert [line["net"] for line in counts] == ["toy", "toy-capped", "toy-fast"]
    assert (counts[2]["markings"], counts[2]["edges"]) == (5, 4)
    timings = _lines(bench_set, "timings.jsonl")
    assert (timings[2]["net"], timings[2]["path"]) == ("toy-fast", "fast (every core)")
    # and: the reference's timings stay as the reference recorded them
    assert timings[:2] == before


def test_a_fast_one_core_record_names_its_mode(tmp_path: Path) -> None:
    # given:
    bench_set = _bench_set(tmp_path, fast_only=True)
    # when:
    _run(bench_set, "--fast", "--one-core", "--record", "--net", "toy-fast")
    # then:
    (timing,) = _lines(bench_set, "timings.jsonl")
    assert timing["path"] == "fast (one core)"


def test_a_fast_record_still_fails_on_a_difference_it_does_not_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the reference's record, where the toy had 6 markings
    bench_set = _bench_set(tmp_path, fast_only=True)
    _run(bench_set, "--record")
    counts = _lines(bench_set, "counts.jsonl")
    counts[0]["markings"] = 6
    _rewrite(bench_set, "counts.jsonl", counts)
    capsys.readouterr()
    # when: the fast path records, which records the fast-only net alone
    code = _run(bench_set, "--fast", "--record")
    # then: the toy's difference fails the run, and its line is kept
    assert code == 1
    assert "toy: markings 5, recorded 6" in capsys.readouterr().out
    assert _lines(bench_set, "counts.jsonl")[0]["markings"] == 6


def test_naming_a_fast_only_net_without_fast_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given:
    bench_set = _bench_set(tmp_path, fast_only=True)
    # when: a reference run names only the fast-only net
    with pytest.raises(SystemExit) as refused:
        _run(bench_set, "--record", "--net", "toy-fast")
    # then: the command says why, and records nothing
    assert refused.value.code == 2
    assert "runs on the fast path alone: toy-fast" in capsys.readouterr().err
    assert not (bench_set.parent / "numbers").exists()


def test_a_net_proved_without_soundness_has_no_markings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the toy asked for its choices only, which explore nothing
    _bench_set(tmp_path)
    bench_set = tmp_path / "choices.json5"
    bench_set.write_text(
        '{ root: "nets", nets: [{ net: "toy.petrinet", facts: ["choice"] }] }\n',
        encoding="utf-8",
    )
    # when:
    code = _run(bench_set, "--record")
    # then: its row has no markings and no edges, and its record says so
    out = capsys.readouterr().out
    assert code == 0
    toy = next(line for line in out.splitlines() if line.startswith("toy "))
    assert toy.split()[1:3] == ["—", "—"]
    (counts,) = _lines(bench_set, "counts.jsonl")
    assert (counts["facts"], counts["markings"], counts["edges"]) == (
        ["choice"],
        None,
        None,
    )
