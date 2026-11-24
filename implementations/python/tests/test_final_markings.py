"""Final markings of more than one place, on a net and on a composition (ADR 0049)."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import emit_petrinet
from velocitron_dsl import PetrinetDslError
from velocitron_equiv import compare
from velocitron_analysis import (
    Proof,
    ProofReport,
    load,
    prove,
)

TWO_SIDES = """net two_sides
(order) -> [split] -> (left_pending)
[split] -> (right_pending)
(left_pending) -> [left_done] -> (left_end)
(right_pending) -> [right_done] -> (right_end)
"""

FIRST = """net first
(order) -> [split] -> (handed_on)
[split] -> (pending) -> [work] -> (end)
(handed_on) port output token
final (end)
"""

SECOND = """net second
(start) -> [work] -> (end)
(start) port input token
final (end)
"""

BOTH_SIDES = """composition both_sides
use "first.petrinet" as first
use "second.petrinet" as second
wire first.(handed_on) -> second.(start)
"""


def _proof(report: ProofReport, subject: str) -> Proof:
    (proof,) = [p for p in report.proofs if p.subject == subject]
    return proof


def _net(tmp_path: Path, final: str) -> Path:
    tmp_path.mkdir(exist_ok=True)
    path = tmp_path / "two_sides.petrinet"
    path.write_text(TWO_SIDES + final + "\n", encoding="utf-8")
    return path


def _composition(tmp_path: Path, final: str = "") -> Path:
    (tmp_path / "first.petrinet").write_text(FIRST, encoding="utf-8")
    (tmp_path / "second.petrinet").write_text(SECOND, encoding="utf-8")
    path = tmp_path / "both_sides.petrinet"
    path.write_text(BOTH_SIDES + final + "\n", encoding="utf-8")
    return path


def test_a_final_marking_of_two_places_lowers_and_emits_back():
    # given:
    text = TWO_SIDES + "final (left_end) + (right_end), (left_end)\n"
    # when:
    document = compile_petrinet_text(text)
    # then: a marking of one place stays a string
    assert document["proofs"]["final"] == [["left_end", "right_end"], "left_end"]
    assert "final (left_end) + (right_end), (left_end)" in emit_petrinet(document)


@pytest.mark.parametrize(
    ("final", "message"),
    [
        (
            "final (left_end) + (left_end)",
            "final names (left_end) more than once in one marking",
        ),
        (
            "final (left_end) + (right_end), (right_end) + (left_end)",
            "final names (right_end) + (left_end) more than once",
        ),
    ],
)
def test_a_final_fact_names_each_marking_and_place_once(final: str, message: str):
    # when:
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(TWO_SIDES + final + "\n")
    # then:
    assert raised.value.diagnostic.code == "PN202"
    assert raised.value.diagnostic.message == message


def test_two_final_places_alone_leave_the_other_side_behind(tmp_path: Path):
    # given: either side's end alone is final
    net, _ = load(_net(tmp_path, "final (left_end), (right_end)"))
    # when:
    report = prove(net, facts=["soundness"])
    # then: the instance is finished while the other side still works
    assert _proof(report, "proper completion").status == "refuted"


def test_a_final_marking_waits_for_both_sides(tmp_path: Path):
    # given: the instance is finished only when both ends hold a token
    net, _ = load(_net(tmp_path, "final (left_end) + (right_end)"))
    # when:
    report = prove(net, facts=["soundness"])
    # then:
    assert report.status == "proved"
    assert report.model["roles"]["final"] == ["left_end", "right_end"]


def test_a_composition_final_replaces_its_nets_final_places(tmp_path: Path):
    # given: each net declares its own end final
    path = _composition(tmp_path, "final first.(end) + second.(end)")
    # when:
    net, composed = load(path)
    report = prove(net, composition=composed, facts=["soundness"])
    # then: the composition's marking is the only final marking
    assert net.proofs is not None
    assert net.proofs.final == [("first.end", "second.end")]
    assert report.status == "proved"


def test_without_a_composition_final_either_net_ends_the_instance(tmp_path: Path):
    # given:
    net, composed = load(_composition(tmp_path))
    # when:
    report = prove(net, composition=composed, facts=["soundness"])
    # then:
    assert net.proofs is not None
    assert net.proofs.final == [("first.end",), ("second.end",)]
    assert _proof(report, "proper completion").status == "refuted"


def test_a_composition_final_must_name_a_declared_place(tmp_path: Path):
    # given:
    path = _composition(tmp_path, "final first.(end) + second.(finish)")
    # when:
    with pytest.raises(PetrinetDslError) as raised:
        load(path)
    # then:
    assert raised.value.diagnostic.code == "PN202"
    assert raised.value.diagnostic.message == (
        "final first.(end) + second.(finish): net 'second' has no place named 'finish'"
    )


def test_a_composition_final_emits_back():
    # given:
    document = compile_petrinet_text(BOTH_SIDES + "final first.(end) + second.(end)\n")
    # when:
    text = emit_petrinet(document)
    # then:
    assert document["final"] == [
        [{"net": "first", "place": "end"}, {"net": "second", "place": "end"}]
    ]
    assert text.endswith("final first.(end) + second.(end)\n")


def test_equiv_tells_a_final_marking_from_two_final_places(tmp_path: Path):
    # given:
    together, _ = load(_net(tmp_path / "together", "final (left_end) + (right_end)"))
    apart, _ = load(_net(tmp_path / "apart", "final (left_end), (right_end)"))
    # when:
    result = compare(together, apart)
    # then:
    assert not result.equivalent
    assert any(
        difference.startswith("final markings of more than one place")
        for difference in result.differences
    )
