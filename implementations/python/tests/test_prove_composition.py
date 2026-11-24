"""velocitron prove on a composition: the merged net, and each refinement."""

from __future__ import annotations

import json
import shutil
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
from velocitron_play import (
    read_play,
)
from velocitron_play_check import (
    check_play,
)

SHOP = Path(__file__).parent / "fixtures" / "prove" / "shop"
SWITCHED = Path(__file__).parent / "fixtures" / "prove" / "switched"


def _proof(report: ProofReport, subject: str) -> Proof:
    (proof,) = [p for p in report.proofs if p.subject.startswith(subject)]
    return proof


def _shop(tmp_path: Path, old: str = "", new: str = "") -> Path:
    for name in ("outer", "inner", "shop"):
        shutil.copy(SHOP / f"{name}.petrinet", tmp_path / f"{name}.petrinet")
    inner = tmp_path / "inner.petrinet"
    inner.write_text(
        inner.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )
    return tmp_path / "shop.petrinet"


def test_a_composition_of_petrinet_files_loads_and_keeps_its_constituents():
    # when: the DSL composition is loaded
    net, composed = load(SHOP / "shop.petrinet")
    # then: the merged net lacks the refined transition, and the
    # constituents, their files and the refinement are kept
    assert "outer.work" not in {t.name for t in net.transitions}
    assert composed is not None
    assert list(composed.nets) == ["outer", "inner"]
    assert composed.files["inner"] == SHOP / "inner.petrinet"
    assert composed.fused() == {"inner.out", "outer.queue"}


def test_wired_places_are_not_open_in_the_merged_net():
    # given: the merged shop, whose fused places carry fusion annotations
    net, composed = load(SHOP / "shop.petrinet")
    # when: it is proved
    report = prove(net, composition=composed)
    # then: the instance starts at the outer net's requests, not at a port
    assert report.model["roles"]["start"] == ["outer.requests"]
    assert report.status == "proved"
    assert _proof(report, "choice at (inner.checked)").details["constituent"] == "inner"
    assert report.composition == {
        "nets": {
            "outer": str(SHOP / "outer.petrinet"),
            "inner": str(SHOP / "inner.petrinet"),
        }
    }


def test_a_sound_block_proves_its_refinement():
    # given:
    net, composed = load(SHOP / "shop.petrinet")
    # when:
    report = prove(net, facts=["refinement"], composition=composed)
    # then:
    proof = _proof(report, "refinement outer.[work] by inner")
    assert proof.status == "proved"
    assert proof.details["inputs"] == ["in"]
    assert proof.details["outputs"] == ["out"]
    assert proof.statement.startswith(
        "Each job token that enters inner through (in) leaves as exactly one token "
        "through (out)"
    )


def test_a_block_that_can_get_stuck_refutes_the_refinement_with_a_play(
    tmp_path: Path,
):
    # given: a reject arc that needs a second field, so a job can stay checked
    path = _shop(tmp_path, '"!valid"', '"!valid && urgent"')
    net, composed = load(path)
    # when:
    report = prove(
        net,
        facts=["refinement"],
        composition=composed,
        counterexamples=tmp_path / "cex",
        net_file=path,
    )
    # then: a deadlock in the inner net, written against the inner net
    proof = _proof(report, "refinement")
    assert proof.status == "refuted"
    (finding,) = proof.findings
    assert finding.kind == "deadlock"
    assert finding.summary.startswith("The net stops with the instance in (checked)")
    assert finding.play is not None
    play = read_play(finding.play)
    assert check_play(play).passed
    assert Path(finding.play).read_text(encoding="utf-8").splitlines()[1] == (
        'net "../inner.petrinet"'
    )


def test_a_block_that_emits_two_tokens_refutes_the_refinement(tmp_path: Path):
    # given: accept puts two jobs into the output port
    path = _shop(
        tmp_path,
        "@ok predicate",
        "@twice: [accept] -job-> (out)\n@ok predicate",
    )
    net, composed = load(path)
    # when:
    report = prove(net, facts=["refinement"], composition=composed)
    # then:
    proof = _proof(report, "refinement")
    assert proof.status == "refuted"
    assert [f.summary for f in proof.findings] == [
        "2 tokens leave through (out) for one token that entered."
    ]


def test_a_block_that_leaves_a_token_behind_refutes_the_refinement(tmp_path: Path):
    # given: accept also keeps a copy of the job inside the inner net
    path = _shop(
        tmp_path,
        "@ok predicate",
        "@kept: [accept] -job-> (audit)\n@ok predicate",
    )
    net, composed = load(path)
    # when:
    report = prove(net, facts=["refinement"], composition=composed)
    # then: the job leaves through (out) while a token stays in (audit)
    proof = _proof(report, "refinement")
    assert proof.status == "refuted"
    assert [(f.kind, sorted(f.marking or {})) for f in proof.findings] == [
        ("improper", ["audit", "out"])
    ]


def test_a_dead_transition_of_the_block_refutes_the_refinement(tmp_path: Path):
    # given: a reject arc that never matches
    path = _shop(tmp_path, '"!valid"', '"!valid && valid"')
    net, composed = load(path)
    # when:
    report = prove(net, facts=["refinement"], composition=composed)
    # then: an invalid job is stuck, and reject never fires
    proof = _proof(report, "refinement")
    assert proof.status == "refuted"
    assert [(f.kind, f.transition) for f in proof.findings] == [
        ("deadlock", None),
        ("dead", "reject"),
    ]


def test_the_cli_proves_a_composition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # when:
    code = main(["prove", str(SHOP / "shop.petrinet"), "--json"])
    # then:
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert [f["fact"] for f in report["facts"]][-1] == "refinement"
    assert report["facts"][-1]["details"]["file"] == str(SHOP / "inner.petrinet")


def _switched(tmp_path: Path, extra: str = "") -> Path:
    for name in ("flips", "slots", "switched"):
        text = (SWITCHED / f"{name}.petrinet").read_text(encoding="utf-8")
        if name != "switched":
            text += extra
        (tmp_path / f"{name}.petrinet").write_text(text, encoding="utf-8")
    return tmp_path / "switched.petrinet"


def test_a_wired_switch_is_closed_and_never_seeded(tmp_path: Path):
    # given: the flips' switch wired into the slots' switch
    net, composed = load(_switched(tmp_path))
    # when:
    report = prove(net, composition=composed, facts=["soundness"])
    # then: nothing puts a switch down, so no slot is ever served
    dead = _proof(report, "no dead transitions")
    assert {f.transition for f in dead.findings} == {
        "flips.flip_to_new",
        "flips.flip_back",
        "slots.lend",
        "slots.skip",
    }


def test_a_wired_record_is_seeded_by_the_outside_world(tmp_path: Path):
    # given: the same switch, living in a record column in both nets
    path = _switched(
        tmp_path, 'record "Branch home"\n(switch) lives in "Branch home"\n'
    )
    net, composed = load(path)
    # when:
    report = prove(net, composition=composed, facts=["soundness"])
    # then:
    assert report.model["roles"]["records"] == ["flips.switch"]
    assert report.status == "proved"


def test_a_firing_cap_names_a_transition_by_its_merged_name():
    # given:
    net, composed = load(SHOP / "shop.petrinet")
    settings = ProofSettings(firings={"inner.accept": 1})
    # when:
    report = prove(net, settings=settings, composition=composed)
    # then: the merged exploration and the refinement check both assume it,
    # each in its own net's names
    assert _proof(report, "option to complete").assumptions == (
        "[inner.accept] fires at most 1 time on a path",
    )
    assert _proof(report, "refinement").assumptions == (
        "[accept] fires at most 1 time on a path",
    )


def test_a_firing_cap_on_a_constituent_name_points_at_the_merged_name():
    # given:
    net, composed = load(SHOP / "shop.petrinet")
    settings = ProofSettings(firings={"accept": 1})
    # when / then:
    with pytest.raises(ValueError, match="did you mean 'inner.accept'"):
        prove(net, settings=settings, composition=composed)
