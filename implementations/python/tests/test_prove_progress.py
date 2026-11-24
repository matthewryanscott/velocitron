"""velocitron prove: a long exploration says how far it is on the error
stream, and a run stopped at the state cap says what made its markings
(proofs.md, The progress line and What made the markings).
"""

from __future__ import annotations

import ctypes
import gc
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from velocitron_analysis import progress, prove
from velocitron_analysis.progress import Progress, memory_in_use, progress_line
from velocitron_cli import main
from velocitron_petrinet import parse_petrinet_text

_LINES = (
    Path(__file__).parents[3]
    / "packages"
    / "spec"
    / "conformance"
    / "prove"
    / "progress-lines.json"
)
_CASES: list[dict[str, Any]] = json.loads(_LINES.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_the_progress_line_reads_as_the_shared_cases_say(case: dict[str, Any]):
    # given: the figures of one shared case
    # when:
    line = progress_line(
        case["net"],
        markings=case["markings"],
        per_second=case["perSecond"],
        memory_bytes=case["memoryBytes"],
        seconds=case["seconds"],
        max_states=case["maxStates"],
        waiting=case["waiting"],
        trend=case["trend"],
    )
    # then: the words any prover writes for them
    assert line == case["line"]


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_line_comes_every_ten_seconds_with_the_rate_since_the_last():
    # given: an exploration's progress, on a clock the test moves
    clock = _Clock()
    lines: list[str] = []
    seen = Progress(
        "grid",
        50_000,
        lines.append,
        clock=clock,
        memory=lambda: 250_000_000,
    )
    # when: it reports at 9.9 s, 10 s, 15 s, 20.5 s and 30.5 s
    for at, markings, waiting in (
        (9.9, 900, 300),
        (10.0, 1_000, 400),
        (15.0, 1_500, 500),
        (20.5, 2_100, 350),
        (30.5, 2_100, 350),
    ):
        clock.now = 1000.0 + at
        seen.tick(markings, waiting)
    # then: one line at 10 s, one at 20.5 s and one at 30.5 s, each
    # counting the markings a second since the line before
    assert lines == [
        (
            "prove grid: 1 000 markings · 100 a second · 250 MB · 10 s · "
            "2 % of the state cap · 400 waiting, rising\n"
        ),
        (
            "prove grid: 2 100 markings · 104 a second · 250 MB · 20 s · "
            "4 % of the state cap · 350 waiting, falling\n"
        ),
        (
            "prove grid: 2 100 markings · 0 a second · 250 MB · 30 s · "
            "4 % of the state cap · 350 waiting, steady\n"
        ),
    ]


def _return_unused_arenas() -> None:
    """Give freed allocator arenas back to the OS, on Linux.

    A CEL backend can leave a multi-gigabyte arena resident after the
    Python objects are gone. The next allocation is then served from that
    arena, and the resident size does not move. The figure this test
    checks is that resident size, so the unused arenas go back first.
    """
    if not sys.platform.startswith("linux"):
        return
    gc.collect()
    libc = ctypes.CDLL(None)
    trim = getattr(libc, "malloc_trim", None)
    if trim is not None:
        trim(0)


def test_the_memory_figure_follows_what_the_process_holds():
    # given: what the process holds now, after unused arenas are returned
    _return_unused_arenas()
    before = memory_in_use()
    # when: it fills 300 MB more
    held = b"\x01" * 300_000_000
    after = memory_in_use()
    # then: the figure grows by about that much
    assert len(held) == 300_000_000
    assert after - before >= 250_000_000, (before, after)


_GRID = (
    "net grid\n\n"
    "(start) -job->? [a] -x-> (xs)\n"
    "(start) -job->? [b] -y-> (ys)\n"
    "(xs) -x-> [tidy] -job-> (done)\n"
    "(ys) -y-> [tidy]\n"
    "(start) -job-> [tidy]\n"
    "final (done)\n"
)


def test_the_prover_writes_progress_lines_to_the_error_stream_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    # given: a net that runs into its state cap, on a clock that moves
    # four seconds each time the prover reads it
    net = tmp_path / "grid.petrinet"
    net.write_text(_GRID, encoding="utf-8")
    clock = _Clock()

    def ticking() -> float:
        clock.now += 4.0
        return clock.now

    monkeypatch.setattr(progress, "monotonic", ticking)
    # when:
    main(["prove", str(net), "--fact", "soundness", "--max-states", "10", "--json"])
    captured = capsys.readouterr()
    # then: the lines go to the error stream, and the report stays JSON
    lines = [line for line in captured.err.splitlines() if line.startswith("prove ")]
    assert lines, captured.err
    assert all(line.startswith("prove grid: ") for line in lines)
    assert json.loads(captured.out)["status"] == "unknown"


def test_the_fast_path_writes_the_progress_line_in_the_same_words(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    # given: the same net on the fast path, with room for the kernel to
    #   expand a few thousand markings, on a clock that moves four seconds
    #   each time it is read
    net = tmp_path / "grid.petrinet"
    net.write_text(_GRID, encoding="utf-8")
    clock = _Clock()

    def ticking() -> float:
        clock.now += 4.0
        return clock.now

    monkeypatch.setattr(progress, "monotonic", ticking)
    # when:
    main(
        ["prove", str(net), "--fact", "soundness", "--max-states", "3000"]
        + ["--json", "--fast"]
    )
    captured = capsys.readouterr()
    # then: the kernel's lines are the reference's, figures and all, on the
    #   error stream
    lines = [line for line in captured.err.splitlines() if line.startswith("prove ")]
    assert lines, captured.err
    shape = re.compile(
        r"prove grid: [\d ]+ markings · [\d ]+ a second · [\d.]+ [MG]B · "
        r"\d+ (s|min \d\d s) · \d+ % of the state cap · [\d ]+ waiting, "
        r"(rising|falling|steady)"
    )
    assert all(shape.fullmatch(line) for line in lines), lines
    assert json.loads(captured.out)["exploration"]["capped"] is True


def test_a_short_proof_writes_no_progress_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # given: a net the prover explores in well under ten seconds
    net = tmp_path / "grid.petrinet"
    net.write_text(_GRID, encoding="utf-8")
    # when:
    main(["prove", str(net), "--fact", "soundness", "--max-states", "10"])
    # then:
    assert "prove grid:" not in capsys.readouterr().err


def _grid_made() -> dict[str, Any]:
    """What made the grid net's eleven markings at a state cap of 10, worked
    out by hand: the start arrives (1 marking), then [a] and [b] each add a
    token from every marking until the cap; [tidy] finishes once.

    Markings in the order found: {}, {start}, {start, x}, {start, y},
    {start, 2x}, {start, x, y}, {start, 2y}, {start, 3x}, {start, 2x, y},
    {start, x, 2y}, {done}. [b] first reached five of them, [a] three.
    Ignoring (xs) leaves five markings ({}, {start}, {start, y},
    {start, 2y}, {done}): 11 / 5 = 2.2; ignoring (ys) leaves six: 1.8.
    """
    return {
        "markings": 10,
        "steps": [
            {"kind": "firing", "transition": "b", "count": 5, "share": 0.5},
            {"kind": "firing", "transition": "a", "count": 3, "share": 0.3},
            {"kind": "arrival", "place": "start", "count": 1, "share": 0.1},
            {"kind": "firing", "transition": "tidy", "count": 1, "share": 0.1},
        ],
        "places": [
            {"place": "xs", "factor": 2.2},
            {"place": "ys", "factor": 1.8},
        ],
    }


def test_a_capped_run_says_which_steps_and_places_made_its_markings():
    # given: a net whose markings grow in two places until the state cap
    net = parse_petrinet_text(_GRID)
    # when:
    report = prove(net, facts=["soundness"], max_states=10)
    # then: the exploration names the steps that first reached the markings
    # and the places that multiply them
    assert report.exploration is not None
    assert report.exploration["madeBy"] == _grid_made()
    # and: the text report says the same in words
    text = report.text()
    assert (
        "explored 11 markings, 12 moves (state cap hit)\n"
        "what made the markings: the steps that first reached them\n"
        "   50 %  5  firing [b]\n"
        "   30 %  3  firing [a]\n"
        "   10 %  1  arrival in (start)\n"
        "   10 %  1  firing [tidy]\n"
        "places that multiply the markings: how many become one when the "
        "place is ignored\n"
        "   ×2.2  (xs)\n"
        "   ×1.8  (ys)\n"
    ) in text, text


@pytest.mark.parametrize("path", ["--reference", "--fast"])
def test_the_json_report_of_a_capped_run_carries_what_made_its_markings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], path: str
):
    # given: the net, proved on either path
    net = tmp_path / "grid.petrinet"
    net.write_text(_GRID, encoding="utf-8")
    # when:
    main(
        ["prove", str(net), "--fact", "soundness", "--max-states", "10", "--json"]
        + [path]
    )
    # then: both paths say the same, in the same words
    exploration = json.loads(capsys.readouterr().out)["exploration"]
    assert exploration["capped"] is True
    assert exploration["madeBy"] == _grid_made()


def test_a_run_that_ends_says_nothing_of_what_made_its_markings():
    # given: the same net, with room to finish the markings it reaches
    net = parse_petrinet_text(
        "net once\n\n(start) -job-> [work] -job-> (done)\nfinal (done)\n"
    )
    # when:
    report = prove(net, facts=["soundness"])
    # then:
    assert report.exploration is not None and not report.exploration["capped"]
    assert "madeBy" not in report.exploration
    assert "what made the markings" not in report.text()


def test_more_than_ten_kinds_of_step_leave_one_line_for_the_rest():
    # given: twelve producers, each adding a token of its own from the start
    producers = "".join(
        f"(start) -job->? [p{n:02}] -t-> (out{n:02})\n(out{n:02}) -t-> [tidy]\n"
        for n in range(12)
    )
    net = parse_petrinet_text(
        "net many\n\n" + producers + "(start) -job-> [tidy] -job-> (done)\n"
        "final (done)\n"
    )
    # when:
    report = prove(net, facts=["soundness"], max_states=200)
    # then: ten steps are named and the rest are counted on one line
    assert report.exploration is not None
    made = report.exploration["madeBy"]
    assert len(made["steps"]) == 10
    named = sum(step["count"] for step in made["steps"])
    assert made["rest"]["count"] == made["markings"] - named > 0
    assert made["rest"]["steps"] == 13 - 10
    assert any(
        line.endswith(f"everything else ({made['rest']['steps']} kinds of step)")
        for line in report.text().splitlines()
    ), report.text()
