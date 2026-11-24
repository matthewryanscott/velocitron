"""Kept records: a record this system keeps, there from the start (ADR 0051)."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import emit_petrinet
from velocitron_cli import main
from velocitron_equiv import compare
from velocitron_petrinet import (
    parse_composition,
    parse_net,
)
from velocitron_play import (
    parse_play,
    read_play,
)
from velocitron_play_check import (
    check_play,
)
from velocitron_analysis import (
    ProofReport,
    ProofSettings,
    load,
    load_net,
    prove,
)
from velocitron_analysis.analysis import NetModel
from velocitron_analysis.soundness import (
    Environment,
    explore,
)
from velocitron_engine import Token
from velocitron_viz import (
    RenderStyle,
    composition_overview_dot,
)

FIXTURES = Path(__file__).parent / "fixtures" / "prove"
KEPT = FIXTURES / "kept-record.petrinet"
KEPT_FACT = (
    '(condition) kept by "circulation desk" starts as cel '
    "\"{'isbn': instance.isbn, 'damaged': false}\""
)


def _status(report: ProofReport, subject: str) -> str:
    (proof,) = [p for p in report.proofs if p.subject.startswith(subject)]
    return proof.status


def _variant(tmp_path: Path, old: str, new: str, name: str = "net") -> Path:
    text = KEPT.read_text(encoding="utf-8")
    assert old in text
    target = tmp_path / f"{name}.petrinet"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return target


def _validate(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = main(["validate", str(path)])
    return code, capsys.readouterr().err


# ── The language ────────────────────────────────────────────────────────


def test_a_kept_fact_lowers_to_a_kept_annotation():
    # given:
    text = KEPT.read_text(encoding="utf-8")
    # when:
    net = parse_net(compile_petrinet_text(text, "kept-record.petrinet"))
    # then:
    (condition,) = [p for p in net.places if p.name == "condition"]
    assert condition.annotations == {
        "kept": {
            "by": "circulation desk",
            "start": {"cel": "{'isbn': instance.isbn, 'damaged': false}"},
        }
    }


def test_canonical_output_writes_the_kept_fact_back():
    # given:
    document = compile_petrinet_text(KEPT.read_text(encoding="utf-8"), "k.petrinet")
    # when:
    text = emit_petrinet(document)
    # then:
    assert KEPT_FACT in text.splitlines()
    assert compile_petrinet_text(text, "again.petrinet") == document


def test_kept_and_starts_stay_usable_as_names():
    # given:
    text = "net n\n(kept) -> [starts] -> (by)\n"
    # when:
    net = parse_net(compile_petrinet_text(text, "n.petrinet"))
    # then:
    assert [p.name for p in net.places] == ["kept", "by"]


# ── Validation ──────────────────────────────────────────────────────────


def test_a_well_formed_kept_record_validates(capsys: pytest.CaptureFixture[str]):
    # when:
    code, err = _validate(KEPT, capsys)
    # then:
    assert code == 0, err


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("(condition) annotation fusion true\n", "remove `annotation fusion true`"),
        ("(condition) port output condition\n", "cannot be a port"),
        (
            'record "Condition"\n(condition) lives in "Condition"\n',
            'lives in the record column "Condition"',
        ),
        (
            'marking initial (condition) <- $clean\n$clean: condition {"isbn": "d", "damaged": false}\n',
            "not from the initial marking",
        ),
    ],
)
def test_a_kept_record_supplied_from_outside_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: str, message: str
):
    # given:
    path = tmp_path / "net.petrinet"
    path.write_text(KEPT.read_text(encoding="utf-8") + extra, encoding="utf-8")
    # when:
    code, err = _validate(path, capsys)
    # then: the error points at the kept fact
    assert code == 1
    assert message in err
    line = KEPT.read_text(encoding="utf-8").splitlines().index(KEPT_FACT) + 1
    assert f"{path}:{line}:1: error[PN202]" in err


@pytest.mark.parametrize(
    ("start", "message"),
    [
        (
            "{'isbn': instance.isbn}",
            "sets no 'damaged', which domain condition.damaged requires",
        ),
        (
            "{'isbn': instance.isbn, 'damaged': 'no'}",
            "outside domain condition.damaged",
        ),
        (
            "{'damaged': false}",
            "sets no 'isbn', which the net reads from (condition)",
        ),
        (
            "{'isbn': binding.returns[0].isbn, 'damaged': false}",
            "may read only `instance`, not `binding`",
        ),
        ("instance", "is a map of the record's fields"),
    ],
)
def test_a_start_that_does_not_fit_the_record_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], start: str, message: str
):
    # given:
    path = _variant(
        tmp_path, "{'isbn': instance.isbn, 'damaged': false}", start
    )
    # when:
    code, err = _validate(path, capsys)
    # then:
    assert code == 1
    assert message in err


# ── Prove ───────────────────────────────────────────────────────────────


def test_prove_starts_the_record_from_the_checks_instance():
    # given:
    net = load_net(KEPT)
    # when:
    model = NetModel(net)
    # then: the record's isbn is the instance's own isbn
    assert model.roles.kept == frozenset({"condition"})
    assert model.initial_marking().get("condition") == [
        Token("condition", {"isbn": "own-isbn", "damaged": False})
    ]
    assert "condition" not in model.roles.open | model.roles.instance | model.roles.final


def test_a_kept_record_correlated_on_the_instance_is_sound():
    # when:
    report = prove(load_net(KEPT))
    # then: both answers fire, and the record left behind is no unfinished work
    assert report.status == "proved", report.text()
    assert report.model["roles"]["kept"] == ["condition"]


def test_a_record_written_into_the_initial_marking_is_not_the_same():
    # given: the same record as a starting token with a literal isbn
    text = KEPT.read_text(encoding="utf-8").replace(
        KEPT_FACT,
        'marking initial (condition) <- $clean\n$clean: condition {"isbn": "978-014", "damaged": false}',
    )
    net = parse_net(compile_petrinet_text(text, "initial.petrinet"))
    # when:
    report = prove(net, facts=["soundness"])
    # then: no step meets the record, which also stays behind as work
    assert _status(report, "no dead transitions") == "refuted"
    assert _status(report, "option to complete") == "refuted"


def test_the_environment_never_writes_a_kept_record():
    # given:
    net = load_net(KEPT)
    model = NetModel(net)
    # when:
    explorer = explore(net, model, environment=Environment(), max_states=10_000)
    # then:
    written = {m.place for m in explorer.moves if m.kind in ("inject", "update")}
    assert "condition" not in written
    assert all(state.marking.get("condition") for state in explorer.states)


def test_a_domains_file_that_injects_a_kept_record_is_an_error():
    # given:
    settings = ProofSettings(injections={"condition": 1})
    # when/then:
    with pytest.raises(ValueError, match=r"\(condition\) is a kept record"):
        prove(load_net(KEPT), settings=settings)


def test_proper_completion_and_final_markings_ignore_kept_records():
    # given: a final marking that names the instance's end only
    net = load_net(KEPT)
    model = NetModel(net)
    explorer = explore(net, model, environment=Environment(), max_states=10_000)
    # when:
    finals = [state for state in explorer.states if state.final]
    # then: every final marking still holds the record
    assert finals
    assert all(state.marking.get("condition") for state in finals)
    assert {p.status for p in explorer.check()} == {"proved"}


def test_a_kept_record_is_not_a_choice():
    # given: the same place, not kept
    text = KEPT.read_text(encoding="utf-8").replace(KEPT_FACT, "")
    plain = parse_net(compile_petrinet_text(text, "plain.petrinet"))
    # when:
    kept = prove(load_net(KEPT), facts=["choice"])
    not_kept = prove(plain, facts=["choice"])
    # then: both steps take the record and give it back; that is no decision.
    # The return's input port is one: the steps decide what a return does
    assert [p.details["place"] for p in not_kept.proofs] == ["returns", "condition"]
    assert [p.details["place"] for p in kept.proofs] == ["returns"]


def test_a_counterexample_states_the_instance_its_record_starts_from(tmp_path: Path):
    # given: a damaged copy that waits to be checked again
    path = _variant(
        tmp_path,
        "[damaged] -copy-> (shelved)",
        "[damaged] -copy-> (waiting)\n"
        "@retry: (waiting) -copy-> [retry] -copy-> (shelved)\n"
        "@retry predicate cel \"state == 'clean'\"",
    )
    out = tmp_path / "cex"
    # when:
    report = prove(
        load_net(path), facts=["soundness"], counterexamples=out, net_file=path
    )
    # then: the written play replays from the same record
    files = [f.play for p in report.proofs for f in p.findings if f.play]
    assert files
    for file in files:
        assert "\ninstance copy {" in Path(file).read_text(encoding="utf-8")
        result = check_play(read_play(file))
        assert result.passed, [d.render() for d in result.diagnostics()]


# ── Compositions ────────────────────────────────────────────────────────


def test_a_shared_kept_record_stays_kept_in_the_merged_net():
    # given:
    net, composed = load(FIXTURES / "kept" / "watched.petrinet")
    # when:
    report = prove(net, composition=composed)
    # then: the merged place is fused, but still kept and never open
    assert report.model["roles"]["kept"] == ["alerter.condition__poller.condition"]
    assert report.status == "proved", report.text()


def test_a_share_with_a_place_that_is_not_kept_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # given: the alerter reads the record as one the outside world supplies
    source = FIXTURES / "kept"
    for name in ("poller", "watched"):
        (tmp_path / f"{name}.petrinet").write_text(
            (source / f"{name}.petrinet").read_text(encoding="utf-8"), encoding="utf-8"
        )
    alerter = (source / "alerter.petrinet").read_text(encoding="utf-8")
    alerter = "\n".join(
        line
        if not line.startswith("(condition) kept by")
        else "(condition) annotation fusion true"
        for line in alerter.splitlines()
    )
    (tmp_path / "alerter.petrinet").write_text(alerter + "\n", encoding="utf-8")
    # when:
    code, err = _validate(tmp_path / "watched.petrinet", capsys)
    # then:
    assert code == 1
    assert (
        "joins the kept record poller.(condition) with alerter.(condition), which is not kept"
        in err
    )
    assert f"{tmp_path / 'watched.petrinet'}:7:1: error[PN202]" in err


# ── Plays ───────────────────────────────────────────────────────────


def _story(tmp_path: Path, body: str, net: Path = KEPT) -> Path:
    path = tmp_path / "story.play"
    path.write_text(f'play story\nnet "{net}"\nmarking none\n{body}', encoding="utf-8")
    return path


def test_a_story_that_names_its_instance_starts_with_the_record(tmp_path: Path):
    # given:
    path = _story(
        tmp_path,
        'instance copy {"isbn": "978-014"}\n'
        'expect (condition) == condition {"isbn": "978-014", "damaged": false}\n'
        'inject (returns) <- copy {"isbn": "978-014", "state": "damaged"}\n'
        "fire [damaged]\n"
        'expect (condition) == condition {"isbn": "978-014", "damaged": true}\n',
    )
    # when:
    result = check_play(read_play(path))
    # then:
    assert result.passed, [d.render() for d in result.diagnostics()]


def test_a_story_without_an_instance_injects_the_record_itself(tmp_path: Path):
    # given: the start reads the instance, and the story names none
    path = _story(
        tmp_path,
        "expect (condition) empty\n"
        'inject (condition) <- condition {"isbn": "978-014", "damaged": false}\n'
        'inject (returns) <- copy {"isbn": "978-014", "state": "clean"}\n'
        "fire [accepted]\n",
    )
    # when:
    result = check_play(read_play(path))
    # then:
    assert result.passed, [d.render() for d in result.diagnostics()]


def test_a_start_that_needs_no_instance_is_always_there(tmp_path: Path):
    # given: one record for every isbn
    net = _variant(
        tmp_path, "'isbn': instance.isbn", "'isbn': 'any'"
    )
    path = _story(
        tmp_path,
        'expect (condition) == condition {"isbn": "any", "damaged": false}\n',
        net,
    )
    # when:
    result = check_play(read_play(path))
    # then:
    assert result.passed, [d.render() for d in result.diagnostics()]


def test_injecting_a_record_the_story_already_keeps_is_an_error(tmp_path: Path):
    # given:
    path = _story(
        tmp_path,
        'instance copy {"isbn": "978-014"}\n'
        'inject (condition) <- condition {"isbn": "978-014", "damaged": true}\n',
    )
    # when:
    result = check_play(read_play(path))
    # then:
    (diagnostic,) = result.diagnostics()
    assert diagnostic.code == "SC305"
    assert (
        "(condition) is a kept record and already holds its record" in diagnostic.message
    )
    assert "`update`" in diagnostic.message


def test_an_instance_the_start_cannot_use_is_an_error(tmp_path: Path):
    # given:
    path = _story(tmp_path, 'instance copy {"title": "f"}\n')
    # when/then:
    with pytest.raises(Exception, match=r"the start of \(condition\) cannot be built"):
        check_play(read_play(path))


def test_the_instance_setting_parses_a_template_or_a_token():
    # when:
    play = parse_play(
        'play s\nnet "n.petrinet"\n$u: copy {"isbn": "d"}\ninstance $u\n'
    )
    # then:
    assert play.instance is not None


# ── Drawing ─────────────────────────────────────────────────────────────


def test_the_overview_draws_a_kept_record_as_a_record():
    # given:
    directory = FIXTURES / "kept"

    def load_reference(ref: str):
        return compile_petrinet_text((directory / ref).read_text(encoding="utf-8"), ref)

    composition = parse_composition(
        compile_petrinet_text(
            (directory / "watched.petrinet").read_text(encoding="utf-8")
        ),
        origin=directory,
        net_loader=load_reference,
    )
    # when:
    dot = composition_overview_dot(
        composition, style=RenderStyle(html_labels=False, tooltips=False)
    )
    # then: one cylinder with a solid border, joined to both nets
    assert '"place:poller.condition" [shape=cylinder, style=filled,' in dot
    assert '"part:poller" -> "place:poller.condition" [' in dot
    assert '"part:alerter" -> "place:poller.condition" [' in dot


def test_equiv_tells_a_kept_record_from_a_place_that_is_not_kept():
    # given:
    kept, _ = load(KEPT)
    text = KEPT.read_text(encoding="utf-8").replace(KEPT_FACT, "")
    plain = parse_net(compile_petrinet_text(text, "plain.petrinet"))
    # when:
    result = compare(kept, plain, None, None)
    # then:
    assert not result.equivalent
    assert any("(condition)" in line and "kept" in line for line in result.differences)
