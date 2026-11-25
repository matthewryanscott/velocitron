"""The public compile seam turns .petrinet text into canonical JSON."""

from __future__ import annotations

from velocitron_dsl import emit_petrinet
from velocitron_petrinet import compile_petrinet_text, parse_net

_NET = """net coin_deposit "Coin deposit"

(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)
"""


def test_compile_petrinet_text_returns_a_canonical_net() -> None:
    # given: one net with a single chain
    # when: the package compiles it
    document = compile_petrinet_text(_NET, "coin_deposit.petrinet")
    # then: the result is a canonical net, not contribution IR
    assert document["name"] == "coin_deposit"
    assert document["description"] == "Coin deposit"
    assert {place["name"] for place in document["places"]} == {"coin_slot", "cash_box"}
    assert "contributions" not in document
    assert "format" not in document
    # and: the closing parser accepts that document
    net = parse_net(document)
    assert net.name == "coin_deposit"


_UNSHARED = """\
net copies

(idle) -job-> [go]
(clock) -now->? [go]
(clock) annotation fusion true
decorate (clock) beside unshared
"""

_SIDED = """\
net copies

(idle) -job-> [go]
(clock) -now->? [go]
(clock) annotation fusion true
decorate (clock) beside left unshared
"""

_SHARED = """\
net copies

(idle) -job-> [go]
(clock) -now->? [go]
(clock) annotation fusion true
decorate (clock) beside
"""


def _beside(source: str) -> dict[str, object]:
    document = compile_petrinet_text(source, "copies.petrinet")
    decorations = document["annotations"]["petrinet.dsl/v1"]["decorations"]
    return decorations["place:clock"]["beside"]


def test_beside_unshared_lowers_to_share_false_and_round_trips() -> None:
    # given: a fusion place decorated beside unshared
    # when: the package compiles it and emits the canonical source
    document = compile_petrinet_text(_UNSHARED, "copies.petrinet")
    emitted = emit_petrinet(document)
    # then: the payload opts out of sharing, and emission restores the modifier
    assert _beside(_UNSHARED) == {"share": False}
    assert "decorate (clock) beside unshared\n" in emitted
    assert compile_petrinet_text(emitted, "copies.petrinet") == document
    assert emit_petrinet(compile_petrinet_text(emitted, "copies.petrinet")) == emitted


def test_beside_left_unshared_keeps_the_side_and_round_trips() -> None:
    # given: a fixed side together with unshared
    document = compile_petrinet_text(_SIDED, "copies.petrinet")
    emitted = emit_petrinet(document)
    # then: both facts survive, and the source round-trips
    assert _beside(_SIDED) == {"side": "left", "share": False}
    assert "decorate (clock) beside left unshared\n" in emitted
    assert compile_petrinet_text(emitted, "copies.petrinet") == document


def test_beside_without_unshared_omits_share() -> None:
    # given: beside with no modifier
    document = compile_petrinet_text(_SHARED, "copies.petrinet")
    # then: sharing stays the default, and emission does not add unshared
    assert _beside(_SHARED) == {}
    assert "unshared" not in emit_petrinet(document)
