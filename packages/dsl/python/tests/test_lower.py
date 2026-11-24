"""Source-tree tests for lowering .petrinet text to contribution IR."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_dsl import PetrinetDslError, lower_petrinet_text
from velocitron_dsl import lower as lower_module

_NET = """\
net coin_deposit "Coin deposit"

(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)
"""
_COMPOSITION = """\
composition wired_pulse

use "pulse_source.petrinet" as source
use "pulse_sink.petrinet" as sink
wire source.(pulse_out) -> sink.(pulse_in)
"""


def test_lower_petrinet_text_lowers_a_net_without_resolving_it() -> None:
    # given: a net with one chain
    # when: the package lowers it
    ir = lower_petrinet_text(_NET, "coin_deposit.petrinet")
    # then: the result is contribution IR, not a resolved net or composition
    assert ir["format"] == "velocitron.petrinet/contribution-ir"
    assert ir["version"] == 1
    assert ir["documentKind"] == "net"
    assert ir["document"] == {"id": "coin_deposit.petrinet"}
    assert "places" not in ir
    assert "nets" not in ir
    contributions = ir["contributions"]
    assert [item["ordinal"] for item in contributions] == list(
        range(len(contributions))
    )
    assert contributions[0]["kind"] == "document.net-header"
    assert contributions[0]["value"]["name"] == "coin_deposit"
    assert "arc.declare" in [item["kind"] for item in contributions]
    assert not hasattr(lower_module, "resolve_contribution_ir")


def test_lower_petrinet_text_lowers_a_composition_without_merging_it() -> None:
    # given: a composition whose use targets are not on disk
    # when: the package lowers it
    ir = lower_petrinet_text(_COMPOSITION, "wired_pulse.petrinet")
    # then: use and wire facts are contributions, and nothing is merged
    assert ir["documentKind"] == "composition"
    assert ir["document"] == {"id": "wired_pulse.petrinet"}
    assert "nets" not in ir
    kinds = [item["kind"] for item in ir["contributions"]]
    assert kinds[0] == "document.composition-header"
    assert ir["contributions"][0]["value"]["namespace"] == "wired_pulse"
    assert kinds.count("composition.use") == 2
    assert "composition.wire" in kinds


def test_lower_petrinet_text_reports_eof_at_source_length() -> None:
    # given: source truncated exactly at EOF
    # when: lowering rejects it
    with pytest.raises(PetrinetDslError) as error:
        lower_petrinet_text("net", "truncated.petrinet")
    # then: EOF is a zero-width span at source length
    assert error.value.diagnostic.span.as_dict() == {
        "source": "truncated.petrinet",
        "start": {"byteOffset": 3, "line": 1, "column": 4},
        "end": {"byteOffset": 3, "line": 1, "column": 4},
    }


def test_copied_lowerer_does_not_import_the_implementation() -> None:
    # given: the synced lowerer source
    text = Path(lower_module.__file__).read_text(encoding="utf-8")
    # when: its import lines are read
    imports = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    # then: nothing imports the umbrella implementation
    assert all(
        not line.startswith(("import velocitron", "from velocitron"))
        for line in imports
    )
    assert "def resolve_contribution_ir" not in text
