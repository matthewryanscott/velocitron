# The library_holds composition's constructor-call type-check fixtures.
# The generator never writes these; regenerate with
# `./.venv/bin/python tests/codegen/regenerate_goldens.py`; never edit.
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from velocitron_nets.library_holds import (
    LibraryHoldsComposition,
    RefinedBorrow,
)
from velocitron_nets.hold_lifecycle import (
    HoldLifecycleComposition,
)
from velocitron_nets.partner_loan import (
    DispatchOutputs,
    FillFormOutputs,
    PackOutputs,
    PartnerLoanNet,
    ReceiveOutputs,
    RequestQuoteOutputs,
)
from velocitron_nets.union_catalog import (
    PollCatalogOutputs,
    UnionCatalogNet,
)
from velocitron_nets.checkout import (
    LoanCheckoutNet,
    NotifyOutputs,
    StampDueOutputs,
)
from velocitron_nets.shelf import HoldShelfNet
from velocitron_nets.notice import OverdueNoticeNet
from velocitron_nets.edition import NewerEditionNet
from velocitron_nets.request import (
    FileHoldOutputs,
    HoldRequestNet,
    ReopenOutputs,
)
from velocitron_engine import Token


class MyRequest(HoldRequestNet):
    def fire_file_hold(self, wishes: list[Token]) -> FileHoldOutputs:
        return {"queued": []}

    def fire_reopen(self, reorder: list[Token]) -> ReopenOutputs:
        return {"queued": []}


class MyLoan(PartnerLoanNet):
    def fire_request_quote(self, offered: list[Token]) -> RequestQuoteOutputs:
        return {"quote_result": []}

    def fire_fill_form(self, priced: list[Token]) -> FillFormOutputs:
        return {"cleared": []}

    def fire_pack(self, cleared: list[Token], cleared_flag: list[Token], crates: list[Token]) -> PackOutputs:
        return {"pack_result": []}

    def fire_dispatch(self, boxed: list[Token], lanes: list[Token]) -> DispatchOutputs:
        return {"dispatch_result": []}

    def fire_receive(self, in_transit: list[Token]) -> ReceiveOutputs:
        return {"loan_ended": [], "union_notice": []}


class MyCatalog(UnionCatalogNet):
    def fire_poll_catalog(self, watching: list[Token], clock: list[Token]) -> PollCatalogOutputs:
        return {"polled": []}


class MyCheckout(RefinedBorrow, LoanCheckoutNet):
    # The mixin fills the refined fire_borrow; the other abstract methods
    # are written here.

    def fire_stamp_due(self, loan_ended: list[Token]) -> StampDueOutputs:
        return {"loaned": [], "stamped": [], "shelf_slot": []}

    def fire_notify(self, loan_ended: list[Token]) -> NotifyOutputs:
        return {"due": []}


lifecycle = HoldLifecycleComposition(
    request=MyRequest(),
    shelf=HoldShelfNet(),
    checkout=MyCheckout(),
    notice=OverdueNoticeNet(),
    edition=NewerEditionNet(),
)
composition = LibraryHoldsComposition(
    lifecycle=lifecycle,
    loan=MyLoan(),
    catalog=MyCatalog(),
)
