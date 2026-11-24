"""Transition refinement in compositions (spec/composition.md; ADR 0034).

``refine shop.[deliver] by courier`` removes ``[shop.deliver]`` and its arcs
from the merged net. The courier net, wired to the same places, takes its
part. The merge first checks that the courier fits: every place the refined
transition takes from is wired to a courier input port of the same color,
and every place it gives to is wired from a courier output port.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from velocitron_petrinet import (
    merge_composition,
    merge_nets,
)
from velocitron_petrinet import (
    compile_petrinet_text,
    parse_petrinet_text,
)
from velocitron_dsl import emit_petrinet
from velocitron_dsl import PetrinetDslError
from velocitron_petrinet import (
    NetValidationError,
    parse_composition,
)
from velocitron_play import (
    PlayError,
    parse_play,
)
from velocitron_play_check import (
    check_play,
)
from velocitron_play_check import load_play_net
from velocitron_engine import (
    Net,
    Refinement,
    Wire,
)
from velocitron_viz import composition_to_dot

_SHOP = """net shop "An order, sent and settled"
(placed) -parcel-> [send] -parcel-> (sending)
@into: (sending) -parcel-> [deliver]
@out: [deliver] -receipt-> (delivered)
@settle_in: (delivered) -receipt-> [settle]
[settle] -receipt-> (settled)
@settle_in correlate cel "token.id == binding.ledger[0].id"
(ledger) -entry->? [settle]
(sending) port output parcel
(delivered) port input receipt
[deliver] annotation trace "abstract"
(settled) annotation lane "done"
decorate [deliver] note "the courier does this"
decorate @settle_in summary "the parcel's entry"
"""

_COURIER = """net courier "A courier delivers one parcel"
(pickup) -parcel-> [pick] -parcel-> (riding)
@drop_in: (riding) -parcel-> [drop]
[drop] -receipt-> (dropped)
(pickup) port input parcel
(dropped) port output receipt
decorate @drop_in summary "the parcel"
"""

_WIRES = [
    Wire("shop", "sending", "courier", "pickup"),
    Wire("courier", "dropped", "shop", "delivered"),
]

_COMPOSITION = """composition refined_shop
use "shop.petrinet" as shop
use "courier.petrinet" as courier
wire shop.(sending) -> courier.(pickup)
wire courier.(dropped) -> shop.(delivered)
refine shop.[deliver] by courier
"""


def _nets(shop: str = _SHOP, courier: str = _COURIER) -> dict[str, Net]:
    return {"shop": parse_petrinet_text(shop), "courier": parse_petrinet_text(courier)}


def _refine(**fields: str) -> Refinement:
    return Refinement(
        **{"net": "shop", "transition": "deliver", "by": "courier", **fields}
    )


def _loader(sources: dict[str, str]) -> Callable[[str], dict[str, Any]]:
    def load(ref: str) -> dict[str, Any]:
        return compile_petrinet_text(sources[ref], ref)

    return load


def _write(directory: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")


# ── Merge ────────────────────────────────────────────────────────────────


def test_merge_removes_the_refined_transition_and_its_arcs() -> None:
    # given: the shop's abstract [deliver] and a courier wired around it
    nets = _nets()

    # when
    merged = merge_nets(nets, _WIRES, [_refine()])

    # then: [shop.deliver] and both its arcs are gone; the courier stays
    names = [t.name for t in merged.transitions]
    assert names == ["shop.send", "shop.settle", "courier.pick", "courier.drop"]
    endpoints = {
        (a.from_place or a.from_transition, a.to_place or a.to_transition)
        for a in merged.arcs
    }
    assert not any("shop.deliver" in pair for pair in endpoints)
    assert ("shop.sending", "courier.pick") in endpoints
    assert ("courier.drop", "courier.dropped") in endpoints


def test_merge_keeps_binding_names_and_annotations_of_the_remaining_nodes() -> None:
    # given
    nets = _nets()

    # when
    merged = merge_nets(nets, _WIRES, [_refine()])

    # then: the settle correlate still reads its local names
    settle = next(t for t in merged.transitions if t.name == "shop.settle")
    assert settle.binding_names == {
        "delivered": "courier.dropped",
        "ledger": "shop.ledger",
    }
    settled = next(p for p in merged.places if p.name == "shop.settled")
    assert settled.annotations == {"lane": "done"}


def test_unrefined_merge_still_competes_for_the_fused_token() -> None:
    # given / when: the same wires, no refinement
    merged = merge_nets(_nets(), _WIRES)

    # then: the abstract transition and the courier both take from the fused place
    takers = sorted(
        str(a.to_transition) for a in merged.arcs if a.from_place == "shop.sending"
    )
    assert takers == ["courier.pick", "shop.deliver"]


def test_extra_ports_of_the_refining_net_are_allowed() -> None:
    # given: a courier with an extra output port nobody wires
    courier = _COURIER + "[drop] -signal-> (photos)\n(photos) port output signal\n"

    # when
    merged = merge_nets(_nets(courier=courier), _WIRES, [_refine()])

    # then
    assert any(p.name == "courier.photos" for p in merged.places)


@pytest.mark.parametrize(
    ("refinement", "message"),
    [
        (
            _refine(by="ghost"),
            "refine shop.[deliver] by ghost: unknown alias ghost",
        ),
        (
            _refine(by="shop"),
            "refine shop.[deliver] by shop: a net cannot refine its own transition",
        ),
        (
            _refine(transition="ship"),
            "refine shop.[ship] by courier: net shop has no transition [ship]",
        ),
    ],
)
def test_merge_rejects_a_refinement_that_names_nothing(
    refinement: Refinement, message: str
) -> None:
    # given
    nets = _nets()

    # when / then
    with pytest.raises(NetValidationError) as raised:
        merge_nets(nets, _WIRES, [refinement])
    assert str(raised.value) == message


def test_merge_rejects_a_transition_refined_twice() -> None:
    # given
    nets = {**_nets(), "bike": parse_petrinet_text(_COURIER)}
    wires = [*_WIRES, Wire("shop", "sending", "bike", "pickup")]

    # when / then
    with pytest.raises(NetValidationError) as raised:
        merge_nets(nets, wires, [_refine(), _refine(by="bike")])
    assert str(raised.value) == (
        "refine shop.[deliver] by bike: shop.[deliver] is already refined by courier"
    )


@pytest.mark.parametrize(
    ("wires", "message"),
    [
        (
            [_WIRES[1]],
            "refine shop.[deliver] by courier: [deliver] takes parcel from "
            "(sending), but (sending) is not wired to an input port of courier",
        ),
        (
            [_WIRES[0]],
            "refine shop.[deliver] by courier: [deliver] gives receipt to "
            "(delivered), but (delivered) is not wired from an output port of courier",
        ),
    ],
)
def test_merge_rejects_a_place_the_refining_net_does_not_take(
    wires: list[Wire], message: str
) -> None:
    # given
    nets = _nets()

    # when / then
    with pytest.raises(NetValidationError) as raised:
        merge_nets(nets, wires, [_refine()])
    assert str(raised.value) == message


def test_merge_rejects_a_port_of_another_color() -> None:
    # given: [deliver] gives a note into (delivered), whose port carries receipt
    shop = _SHOP.replace("@out: [deliver] -receipt->", "@out: [deliver] -note->") + (
        "(delivered) accepts [receipt, note]\n"
    )

    # when / then
    with pytest.raises(NetValidationError) as raised:
        merge_nets(_nets(shop=shop), _WIRES, [_refine()])
    assert str(raised.value) == (
        "refine shop.[deliver] by courier: [deliver] gives note to (delivered), "
        "but the output ports of courier wired to it carry receipt"
    )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            "(stop) -halt->0 [deliver]\n",
            "refine shop.[deliver] by courier: [deliver] has an inhibit arc from "
            "(stop); a refined transition may only consume, read and produce",
        ),
        (
            '(clock) -tick->? [deliver]\n[deliver] timer clock (clock) cel "clock.now > 0"\n',
            "refine shop.[deliver] by courier: [deliver] has a timer; a refined "
            "transition may only consume, read and produce",
        ),
    ],
)
def test_merge_rejects_inhibit_arcs_and_timers(extra: str, message: str) -> None:
    # given
    nets = _nets(shop=_SHOP + extra)

    # when / then
    with pytest.raises(NetValidationError) as raised:
        merge_nets(nets, _WIRES, [_refine()])
    assert str(raised.value) == message


def test_a_read_arc_must_be_wired_to_an_input_port() -> None:
    # given: [deliver] also reads (ledger), which the courier does not take
    nets = _nets(shop=_SHOP + "(ledger) -entry->? [deliver]\n")

    # when / then
    with pytest.raises(NetValidationError, match=r"takes entry from \(ledger\)"):
        merge_nets(nets, _WIRES, [_refine()])


# ── Composition documents and the DSL ────────────────────────────────────


def test_parse_composition_reads_and_merges_refinements() -> None:
    # given
    document = {
        "nets": [
            {"ref": "shop.petrinet", "alias": "shop"},
            {"ref": "courier.petrinet", "alias": "courier"},
        ],
        "wires": [
            {
                "from": {"net": "shop", "port": "sending"},
                "to": {"net": "courier", "port": "pickup"},
            },
            {
                "from": {"net": "courier", "port": "dropped"},
                "to": {"net": "shop", "port": "delivered"},
            },
        ],
        "refinements": [{"net": "shop", "transition": "deliver", "by": "courier"}],
    }
    loader = _loader({"shop.petrinet": _SHOP, "courier.petrinet": _COURIER})

    # when
    composition = parse_composition(document, net_loader=loader)
    merged = merge_composition(composition)

    # then
    assert composition.refinements == (_refine(),)
    assert "shop.deliver" not in {t.name for t in merged.transitions}


def test_dsl_refine_compiles_and_emits_round_trip() -> None:
    # given / when
    document = compile_petrinet_text(_COMPOSITION, "refined_shop.petrinet")

    # then
    assert document["refinements"] == [
        {"net": "shop", "transition": "deliver", "by": "courier"}
    ]
    emitted = emit_petrinet(document)
    assert "refine shop.[deliver] by courier\n" in emitted
    assert compile_petrinet_text(emitted, "again.petrinet") == document


def test_dsl_refine_reports_a_loader_failure_at_the_refined_transition() -> None:
    # given: the refined transition does not exist
    text = _COMPOSITION.replace("shop.[deliver]", "shop.[ship]")
    loader = _loader({"shop.petrinet": _SHOP, "courier.petrinet": _COURIER})

    # when
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(text, "refined_shop.petrinet", net_loader=loader)

    # then
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert (
        diagnostic.message
        == "refine shop.[ship] by courier: net shop has no transition [ship]"
    )
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (6, 8)
    assert diagnostic.help == "refine a transition the net declares"


_CORPUS = Path(__file__).parents[3] / "packages" / "spec" / "conformance" / "petrinet"


@pytest.mark.parametrize(
    "fixture", ["unknown-refined-transition", "unwired-refinement"]
)
def test_loader_owned_corpus_fixtures_match_with_a_loader(fixture: str) -> None:
    # given: the corpus constituent nets and a loader-owned fixture
    case = _CORPUS / "22-refinement"
    sources = {
        f"{name}.petrinet": json.loads((case / f"{name}.source.json").read_text())[
            "text"
        ]
        for name in ("order_flow", "courier")
    }
    expectation = json.loads((case / f"refined_order.{fixture}.json").read_text())
    source = expectation["source"]

    # when
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(
            source["text"], source["sourceId"], net_loader=_loader(sources)
        )

    # then
    diagnostic = raised.value.diagnostic
    expected = expectation["diagnostic"]
    assert diagnostic.code == expected["code"]
    assert diagnostic.message == expected["message"]
    assert diagnostic.help == expected["help"]
    assert diagnostic.span.as_dict() == expected["span"]


# ── Plays and rendering ──────────────────────────────────────────────


def test_a_play_plays_through_a_refined_composition(tmp_path: Path) -> None:
    # given
    _write(
        tmp_path,
        {
            "shop.petrinet": _SHOP,
            "courier.petrinet": _COURIER,
            "comp.petrinet": _COMPOSITION,
        },
    )
    play = parse_play(
        """play refined "The courier delivers"
net "comp.petrinet"
marking none
inject (shop.placed) <- parcel {"id": "p-1"}
inject (shop.ledger) <- entry {"id": "p-1"}
fire [shop.send]
expect enabled [courier.pick]
fire [courier.pick]
fire [courier.drop] -> (courier.dropped) receipt {"id": "p-1"}
fire [shop.settle]
expect (shop.settled) == receipt {"id": "p-1"}
""",
        origin=tmp_path,
    )

    # when
    report = check_play(play)

    # then
    assert [trace.failure for trace in report.traces] == [None]


def test_a_play_names_the_refinement_of_a_missing_transition(
    tmp_path: Path,
) -> None:
    # given: inline use, wire and refine lines, and a step on the refined transition
    _write(tmp_path, {"shop.petrinet": _SHOP, "courier.petrinet": _COURIER})
    play = parse_play(
        """play refined
use "shop.petrinet" as shop
use "courier.petrinet" as courier
wire shop.(sending) -> courier.(pickup)
wire courier.(dropped) -> shop.(delivered)
refine shop.[deliver] by courier
marking none
fire [shop.deliver]
""",
        origin=tmp_path,
    )

    # when
    with pytest.raises(PlayError) as raised:
        check_play(play)

    # then
    rendered = raised.value.diagnostic.render()
    assert "error[SC203]: the net has no transition [shop.deliver]" in rendered
    assert "the composition refines [shop.deliver] by courier" in rendered


def test_decorations_follow_their_arcs_past_the_removed_ones(tmp_path: Path) -> None:
    # given
    _write(
        tmp_path,
        {
            "shop.petrinet": _SHOP,
            "courier.petrinet": _COURIER,
            "comp.petrinet": _COMPOSITION,
        },
    )
    play = parse_play('play s\nnet "comp.petrinet"\n', origin=tmp_path)

    # when
    subject = load_play_net(play)

    # then: each arc summary sits on the merged arc it was written for
    summaries = {
        (arc.from_place or arc.from_transition, arc.to_place or arc.to_transition): (
            subject.decorations.arcs[index].summary
        )
        for index, arc in enumerate(subject.net.arcs)
        if index in subject.decorations.arcs
    }
    assert summaries == {
        ("courier.dropped", "shop.settle"): "the parcel's entry",
        ("courier.riding", "courier.drop"): "the parcel",
    }
    assert "transition:shop.deliver" not in subject.decorations.nodes


def test_the_composition_render_leaves_out_the_refined_transition() -> None:
    # given
    composition = parse_composition(
        compile_petrinet_text(_COMPOSITION),
        net_loader=_loader({"shop.petrinet": _SHOP, "courier.petrinet": _COURIER}),
    )

    # when
    dot = composition_to_dot(composition)

    # then
    assert '"shop.deliver"' not in dot
    assert "refines shop.[deliver]" in dot
