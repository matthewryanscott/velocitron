"""The public compile seam turns .petrinet text into canonical JSON."""

from __future__ import annotations

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
