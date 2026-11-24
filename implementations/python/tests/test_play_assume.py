"""The ``assume`` statement: an assumed guard or predicate answer.

`assume [t] guard true` scopes an assumed answer for a transition's `guard`
ref from the step to the end of its path (or the next `assume` for the same
transition), so `fire [t]` and `expect enabled [t]` reach a guarded
transition (ADR 0058, Decision 2; N17). Answers come from stub handlers the
checker registers per path; the marking is untouched.

References: spec/play-language.md, "Assumptions"; ADR 0031.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_play import (
    PlayError,
    read_play,
)
from velocitron_play_check import (
    PlayReport,
    check_play,
    render_walkthrough,
    walkthrough_document,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "play"

_GUARDED = """net shop "One guarded transition"
(inbox) -task-> [go] -task-> (out)
[go] guard "g"
marking initial (inbox) <- $o1
$o1: task {"id": "t-1"}
"""

_GUARDED_WITH_PREDICATE = """net shop "A named predicate and a guard"
@p: (inbox) -task-> [go] -task-> (out)
@p predicate handler "is_ready"
[go] guard "g"
marking initial (inbox) <- $o1
$o1: task {"id": "t-1"}
"""


def _net(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "n.petrinet"
    path.write_text(source, encoding="utf-8")
    return path


def _check(tmp_path: Path, net: Path, body: str) -> PlayReport:
    play = tmp_path / "s.play"
    play.write_text(f'play s\nnet "{net.name}"\n' + body, encoding="utf-8")
    return check_play(read_play(play))


def _resolve_error(tmp_path: Path, net: Path, body: str) -> PlayError:
    with pytest.raises(PlayError) as caught:
        _check(tmp_path, net, body)
    return caught.value


def test_assume_true_lets_a_guarded_transition_fire(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when: the assume step scopes its answer, then the fire plays
    report = _check(tmp_path, net, "assume [go] guard true\nfire [go]\n")

    # then: the firing went through on the assumed answer
    (trace,) = report.traces
    assert trace.passed
    fired = trace.steps[1]
    assert [s.step.kind for s in trace.steps] == ["assume", "fire"]
    assert fired.records[0]["transition"] == "go"  # type: ignore[typeddict-item]
    assert list(fired.after["out"]) == [fired.consumed["inbox"][0]]


def test_without_the_assume_the_guarded_fire_fails_sc301(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when
    report = _check(tmp_path, net, "fire [go]\n")

    # then: the unregistered guard holds the transition back, as before
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC301"
    assert 'guard "g" names a handler that is not registered' in diagnostic.details[0]
    assert report.traces[0].failure is not None


def test_assume_false_holds_expect_enabled_and_names_the_assumption(
    tmp_path: Path,
) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when
    report = _check(tmp_path, net, "assume [go] guard false\nexpect enabled [go]\n")

    # then: the condition fails and the detail names the assumed answer
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC307"
    (trace,) = report.traces
    assert trace.failure is not None
    detail = trace.failure.diagnostic.details[0]
    assert 'guard "g"' in detail
    assert "returned False" in detail


def test_assume_on_an_unguarded_transition_is_sc308(tmp_path: Path) -> None:
    # given: the same net without the guard fact
    net = _net(tmp_path, _GUARDED.replace('[go] guard "g"\n', ""))

    # when / then
    error = _resolve_error(tmp_path, net, "assume [go] guard true\n")
    assert error.diagnostic.code == "SC308"
    assert "[go] has no `guard` fact" in error.diagnostic.message


def test_assume_for_an_unknown_transition_reuses_sc203(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when / then
    error = _resolve_error(tmp_path, net, "assume [nope] guard true\n")
    assert error.diagnostic.code == "SC203"
    assert "no transition [nope]" in error.diagnostic.message


def test_assume_predicate_for_an_unknown_ref_is_sc310(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when / then
    error = _resolve_error(tmp_path, net, 'assume predicate "nope" true\n')
    assert error.diagnostic.code == "SC310"
    assert 'predicate handler "nope"' in error.diagnostic.message


def test_assume_true_ends_at_the_path_end_and_a_branch_replays_it(
    tmp_path: Path,
) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when: the trunk's assume stays out of the branch started before it
    body = (
        "@second: fire [go]\n\n"
        "path bare from @second\n"
        "expect not enabled [go]\n"
    )
    report = _check(tmp_path, net, "assume [go] guard true\n" + body)

    # then: the trunk passes, the branch replays the prefix steps (whose
    # results stay in the owner path) and its expect sees no assumption
    assert report.passed
    trunk, bare = report.traces
    assert trunk.passed
    assert bare.inherited == 2
    assert [s.step.kind for s in bare.steps] == ["fire", "expect"]
    assert bare.failure is None


def test_a_second_assume_for_the_same_transition_re_scopes(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when: fire under true, re-scope to false, stay not enabled
    body = (
        "assume [go] guard true\n"
        "fire [go]\n"
        "inject (inbox) <- task {\"id\": \"t-2\"}\n"
        "assume [go] guard false\n"
        "expect not enabled [go]\n"
    )
    report = _check(tmp_path, net, body)

    # then
    (trace,) = report.traces
    assert trace.passed, trace.failure


def test_assume_predicate_true_fills_the_named_predicates_arcs(
    tmp_path: Path,
) -> None:
    # given
    net = _net(tmp_path, _GUARDED_WITH_PREDICATE)

    # when: the consume arc's named predicate is assumed true (the guard too,
    # so the predicate is the only open question)
    report = _check(
        tmp_path,
        net,
        'assume predicate "is_ready" true\nassume [go] guard true\nfire [go]\n',
    )

    # then: the firing went through on the assumed predicate
    (trace,) = report.traces
    assert trace.passed, trace.failure


def test_assume_predicate_false_filters_the_arc(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED_WITH_PREDICATE)

    # when
    report = _check(
        tmp_path,
        net,
        'assume predicate "is_ready" false\nassume [go] guard true\nfire [go]\n',
    )

    # then: the predicate's assumed answer holds the token back (SC301, the
    # arc's per-token line names the handler as false)
    (diagnostic,) = report.diagnostics()
    assert diagnostic.code == "SC301"
    detail = "\n".join(diagnostic.details)
    assert 'predicate handler "is_ready" is false' in detail


def test_the_walkthrough_shows_the_assumption_as_a_distinct_line(
    tmp_path: Path,
) -> None:
    # given
    net = _net(tmp_path, _GUARDED)

    # when
    report = _check(tmp_path, net, "assume [go] guard true\nfire [go]\n")
    document = walkthrough_document(report.traces[0])

    # then: the assume step is its own section, no graphs, its caption names
    # the assumed answer; the fire keeps its graphs
    assumed, fired = document["steps"]
    assert assumed["status"] == "assumed"
    assert "before_dot" not in assumed and "after_dot" not in assumed
    assert assumed["caption"] == "From here, guard go's answer is assumed true."
    assert "before_dot" in fired and "after_dot" in fired
    markdown = render_walkthrough(report.traces[0])
    assert "## Step 1 — `assume [go] guard true` · assumed" in markdown
    assert "## Step 2 — `fire [go]`" in markdown


def test_the_walkthrough_names_an_assumed_predicate(tmp_path: Path) -> None:
    # given
    net = _net(tmp_path, _GUARDED_WITH_PREDICATE)

    # when
    report = _check(
        tmp_path, net, 'assume predicate "is_ready" false\nfire [go]\n'
    )
    document = walkthrough_document(report.traces[0])

    # then
    (assumed, _fired) = document["steps"]
    assert (
        assumed["caption"]
        == 'From here, predicate handler is_ready is assumed false.'
    )