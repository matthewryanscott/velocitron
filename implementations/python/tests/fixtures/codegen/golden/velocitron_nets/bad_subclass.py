# A subclass that omits one abstract method (fire_pack), planted for the
# type-check test: the check asserts exactly one reportAbstractUsage error,
# at the instantiation line below. Regenerate with
# `./.venv/bin/python tests/codegen/regenerate_goldens.py`; never edit.
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "velocitron_nets"))

from partner_loan import (
    DispatchOutputs,
    FillFormOutputs,
    PartnerLoanNet,
    ReceiveOutputs,
    RequestQuoteOutputs,
)
from velocitron_engine import Token


class BadLoan(PartnerLoanNet):
    # Omits fire_pack; reportAbstractUsage reports the omission at the instantiation line.

    def fire_request_quote(self, offered: list[Token]) -> RequestQuoteOutputs:
        return {"quote_result": [Token("hold", dict(offered[0].data))]}

    def fire_fill_form(self, priced: list[Token]) -> FillFormOutputs:
        return {"cleared": [Token("hold", dict(priced[0].data))]}

    def fire_dispatch(self, boxed: list[Token], lanes: list[Token]) -> DispatchOutputs:
        return {"dispatch_result": [Token("hold", dict(boxed[0].data))]}

    def fire_receive(self, in_transit: list[Token]) -> ReceiveOutputs:
        return {
            "loan_ended": [Token("result", {"outcome": "loaned", "hold": dict(in_transit[0].data)})],
            "union_notice": [Token("notice", {"isbn": "978"})],
        }


instance = BadLoan()  # the reportAbstractUsage instantiation line
