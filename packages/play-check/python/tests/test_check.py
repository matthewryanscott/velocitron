"""The public check and walkthrough seam, without the umbrella."""

from __future__ import annotations

from pathlib import Path

from velocitron_play import PlayError, read_play
from velocitron_play_check import check_play, render_walkthrough, walkthrough_document

_NET = """net shop "Shop"

(orders) -purchase-> [accept] -purchase-> (accepted)

marking initial (orders) <- $o
$o: purchase {"id": "o-1"}
"""


def _play(tmp_path: Path, body: str) -> Path:
    (tmp_path / "shop.petrinet").write_text(_NET, encoding="utf-8")
    path = tmp_path / "shop.play"
    path.write_text(body, encoding="utf-8")
    return path


def test_check_play_carries_the_consumed_token_and_steps_a_walkthrough(
    tmp_path: Path,
) -> None:
    # given: a handlerless net and a play that fires the one transition
    path = _play(
        tmp_path,
        'play shop "One purchase"\n'
        'net "shop.petrinet"\n'
        "fire [accept]\n"
        'expect (accepted) has purchase {"id": "o-1"}\n'
        "expect (orders) empty\n",
    )
    # when: the package checks the play and renders the path
    report = check_play(read_play(path))
    # then: symbolic firing moved the token, and the walkthrough names the step
    assert report.passed
    (trace,) = report.traces
    assert trace.final["accepted"][0].data == {"id": "o-1"}
    assert "orders" not in trace.final or not trace.final["orders"]
    document = walkthrough_document(trace)
    assert document["steps"][0]["statement"] == "fire [accept]"
    assert "accept" in render_walkthrough(trace)


def test_an_unknown_place_is_sc202(tmp_path: Path) -> None:
    # given: a play that names a place the net does not have
    path = _play(
        tmp_path,
        'play shop "Missing"\nnet "shop.petrinet"\ninject (missing) <- purchase {}\n',
    )
    # when: the check resolves the play
    try:
        check_play(read_play(path))
    except PlayError as error:
        diagnostic = error.diagnostic
    else:
        raise AssertionError("unknown place resolved")
    # then: resolution fails before anything plays
    assert diagnostic.code == "SC202"


def test_a_failed_expect_stops_the_path(tmp_path: Path) -> None:
    # given: a play whose expect does not match the marking after the firing
    path = _play(
        tmp_path,
        'play shop "Wrong"\n'
        'net "shop.petrinet"\n'
        "fire [accept]\n"
        'expect (orders) has purchase {"id": "o-1"}\n',
    )
    # when: the path plays until the expect
    report = check_play(read_play(path))
    # then: the failure is on the trace, not an exception
    assert not report.passed
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC307"
