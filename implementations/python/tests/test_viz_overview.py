"""The composition overview: one box per net, the places between them
(``velocitron-viz --overview``)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_petrinet import parse_composition
from velocitron_engine import Composition
from velocitron_cli import viz_main as main
from velocitron_viz import (
    RenderStyle,
    composition_overview_dot,
)

LOCK = Path(__file__).parent / "fixtures" / "lock"

_SHOP = {
    "open.petrinet": """net open "Open an order"
(requests) -parcel-> [open] -parcel-> (open_orders)
@open_note: [open] -signal-> (signals)
@open_note data {}
(open_orders) port output parcel
""",
    "ship.petrinet": """net ship "Ship an open order, or cancel it"
(open_orders) -parcel-> [ship] -parcel-> (shipped_out)
(open_orders) -parcel-> [cancel] -parcel-> (cancelled)
@stock: (stock) -item->? [ship]
@switch: (switch) -flag->? [ship]
@cancel_note: [cancel] -signal-> (signals)
@cancel_note data {}
(open_orders) port input parcel
(cancelled) description "cancelled by the shop"
record "Shipping switch"
(switch) lives in "Shipping switch"
""",
    "audit.petrinet": """net audit
(stock) -item-> [count] -item-> (stock)
""",
    "shop.petrinet": """composition shop
use "open.petrinet" as open
use "ship.petrinet" as ship
use "audit.petrinet" as audit
wire open.(open_orders) -> ship.(open_orders)
share open.(signals) ~ ship.(signals)
share ship.(stock) ~ audit.(stock)
""",
}

_PLAIN = RenderStyle(html_labels=False, tooltips=False)


def _load(directory: Path, name: str) -> Composition:
    def load_reference(ref: str):
        return compile_petrinet_text((directory / ref).read_text(encoding="utf-8"), ref)

    text = (directory / name).read_text(encoding="utf-8")
    return parse_composition(
        compile_petrinet_text(text), origin=directory, net_loader=load_reference
    )


@pytest.fixture
def shop(tmp_path: Path) -> Path:
    for name, text in _SHOP.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.fixture
def lock(tmp_path: Path) -> Path:
    for source in LOCK.iterdir():
        shutil.copy(source, tmp_path / source.name)
    return tmp_path


def test_each_net_is_one_box_named_by_its_description(shop: Path) -> None:
    # when:
    dot = composition_overview_dot(_load(shop, "shop.petrinet"), style=_PLAIN)

    # then: a net with a description shows it; one without shows its name
    assert '"part:open" [shape=box, style="rounded,filled"' in dot
    assert 'label="Open an order"' in dot
    assert 'label="Ship an open order, or cancel it"' in dot
    assert 'label="audit"' in dot
    # and: no transition is drawn
    assert "[open]" not in dot and '"open.open"' not in dot


def test_a_wired_place_sits_between_the_net_that_fills_it_and_the_one_that_takes(
    shop: Path,
) -> None:
    # when:
    dot = composition_overview_dot(_load(shop, "shop.petrinet"), style=_PLAIN)

    # then: one node for both ends of the wire, labeled by its name
    assert '"place:open.open_orders" [shape=ellipse' in dot
    assert 'label="open orders"' in dot
    assert '"part:open" -> "place:open.open_orders" [' in dot
    assert '"place:open.open_orders" -> "part:ship" [' in dot
    assert "ship.open_orders" not in dot


def test_a_place_of_the_case_that_nothing_takes_from_is_an_end(shop: Path) -> None:
    # when:
    dot = composition_overview_dot(_load(shop, "shop.petrinet"), style=_PLAIN)

    # then: the order ends shipped or cancelled
    assert '"place:ship.shipped_out" [shape=doublecircle' in dot
    assert '"place:ship.cancelled" [shape=doublecircle' in dot
    assert '"part:ship" -> "place:ship.shipped_out" [' in dot
    # and: an end is labeled by its name in plain words, not its description
    assert 'label="shipped\\nout"' in dot
    assert 'label="cancelled"' in dot
    assert "by the" not in dot
    # and: a place only one net uses, which it takes from, is left out
    assert "requests" not in dot


def test_a_shared_record_is_labeled_by_what_each_net_does_to_it(
    shop: Path,
) -> None:
    # when:
    dot = composition_overview_dot(_load(shop, "shop.petrinet"), style=_PLAIN)

    # then: audit takes the stock and gives it back; ship reads it
    assert '"place:ship.stock" [shape=cylinder, style=filled' in dot
    assert '"part:audit" -> "place:ship.stock" [style=dashed, dir=none' in dot
    assert 'label="takes, gives back"' in dot
    assert '"part:ship" -> "place:ship.stock" [' in dot
    assert 'fontcolor="#555555", label="reads"];' in dot
    # and: the signals nothing reads or takes draw without labels
    signal_lines = [
        line for line in dot.splitlines() if '-> "place:open.signals"' in line
    ]
    assert len(signal_lines) == 2
    assert all("label=" not in line for line in signal_lines)


def test_a_place_that_lives_in_a_record_column_is_an_outside_record(
    shop: Path,
) -> None:
    # when:
    dot = composition_overview_dot(_load(shop, "shop.petrinet"), style=_PLAIN)

    # then: drawn with a dashed border, though only one net uses it
    assert '"place:ship.switch" [shape=cylinder, style="filled,dashed"' in dot
    assert '"part:ship" -> "place:ship.switch" [' in dot


def test_a_nested_composition_is_a_cluster_and_a_refinement_is_attached(
    lock: Path,
) -> None:
    # when:
    dot = composition_overview_dot(_load(lock, "nested.petrinet"), style=_PLAIN)

    # then: the pair's nets and their lock sit in a dashed cluster titled pair
    pair = dot.index('label="pair"; labeljust=l;')
    assert dot.index('"part:pair.take"', pair) > pair
    assert dot.index('"place:pair.take.lock" [shape=cylinder', pair) > pair
    # and: the busy job crosses into the worker, so it sits outside the cluster
    assert dot.index('"place:pair.take.busy" [') < pair
    # and: the worker sits in a cluster that names the step it refines, joined
    # by a dotted line to the net it refines
    assert 'label="refines: work"; labeljust=l;' in dot
    assert '"part:pair.give" -> "part:worker" [style=dotted' in dot


def test_the_cli_draws_the_overview_titled_by_the_file(
    shop: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # when:
    exit_code = main([str(shop / "shop.petrinet"), "--overview", "--doc"])

    # then:
    assert exit_code == 0
    dot = capsys.readouterr().out
    assert dot.startswith("digraph composition_overview {")
    assert 'label="shop";' in dot


def test_the_cli_gives_no_title_to_a_source_without_an_extension(
    shop: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the composition as JSON in a file named like a stream
    document = compile_petrinet_text((shop / "shop.petrinet").read_text())
    (shop / "stdin").write_text(json.dumps(document), encoding="utf-8")

    # when:
    exit_code = main([str(shop / "stdin"), "--overview", "--doc"])

    # then:
    assert exit_code == 0
    dot = capsys.readouterr().out
    assert "stdin" not in dot
    assert "labelloc" not in dot


def test_the_cli_rejects_the_overview_of_a_net(
    shop: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # when:
    with pytest.raises(SystemExit) as raised:
        main([str(shop / "ship.petrinet"), "--overview"])

    # then:
    assert raised.value.code == 2
    assert "--overview only applies to composition documents" in (
        capsys.readouterr().err
    )
