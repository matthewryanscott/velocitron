"""Regenerate the golden modules from their fixtures (a maintainer script).

Run after a deliberate, reviewed change to the generator:

    ./.venv/bin/python tests/codegen/regenerate_goldens.py

Each golden is the byte-exact output of `velocitron codegen` on its
fixture with the flags in `GOLDENS`; never hand-edit one.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYTHON_ROOT = Path(__file__).parents[2]
_REPO_ROOT = _PYTHON_ROOT.parents[1]
sys.path.insert(0, str(_PYTHON_ROOT / "src"))

from velocitron_codegen.generator import generate_module
from velocitron_codegen import generate_composition
from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import parse_net

_ACTOR = "circulation desk"

# (out name, fixture path relative to the repo root, actor, is_async)
# The leaf/net goldens land in `velocitron_nets/` (the package the
# composition modules import their member classes from); the composition
# goldens land beside them in `golden/` itself.
GOLDENS: list[tuple[str, Path, str | None, bool]] = [
    (
        "velocitron_nets/reading_voice.py",
        _REPO_ROOT
        / "examples/capability-ladder/12-reading-hour-fragment/reading_voice.petrinet",
        None,
        False,
    ),
    (
        "velocitron_nets/reading_voice_async.py",
        _REPO_ROOT
        / "examples/capability-ladder/12-reading-hour-fragment/reading_voice.petrinet",
        None,
        True,
    ),
    (
        "velocitron_nets/reading_cadence.py",
        _REPO_ROOT
        / "examples/capability-ladder/12-reading-hour-fragment/reading_cadence.petrinet",
        None,
        False,
    ),
    (
        "velocitron_nets/reading_pick.py",
        _REPO_ROOT
        / "examples/capability-ladder/12-reading-hour-fragment/reading_pick.petrinet",
        None,
        False,
    ),
    (
        "velocitron_nets/pulse_source.py",
        _REPO_ROOT / "examples/capability-ladder/10-wired-pulse/pulse_source.petrinet",
        None,
        False,
    ),
    (
        "velocitron_nets/pulse_sink.py",
        _REPO_ROOT / "examples/capability-ladder/10-wired-pulse/pulse_sink.petrinet",
        None,
        False,
    ),
    (
        "velocitron_nets/partner_loan.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/partner-loan.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/union_catalog.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/union-catalog.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/request.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/desk/request.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/shelf.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/desk/shelf.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/checkout.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/desk/checkout.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/notice.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/desk/notice.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/edition.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/desk/edition.petrinet",
        _ACTOR,
        False,
    ),
    (
        "velocitron_nets/branch_policy.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/branch-policy.petrinet",
        _ACTOR,
        False,
    ),
]

# The composition goldens: every composition module INSIDE the members
# package (a composition module is a member module to whatever imports
# it — an outer composition's imports need the inner class there, so all
# of them live in `velocitron_nets/`).
COMPOSITION_GOLDENS: list[tuple[str, Path, str | None]] = [
    (
        "velocitron_nets/wired_pulse.py",
        _REPO_ROOT / "examples/capability-ladder/10-wired-pulse/wired_pulse.petrinet",
        None,
    ),
    (
        "velocitron_nets/reading_hour.py",
        _REPO_ROOT
        / "examples/capability-ladder/12-reading-hour-fragment/reading_hour.petrinet",
        None,
    ),
    (
        "velocitron_nets/hold_lifecycle.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/hold-lifecycle.petrinet",
        _ACTOR,
    ),
    (
        "velocitron_nets/library_holds.py",
        _PYTHON_ROOT / "tests/fixtures/codegen/library_holds/library-holds.petrinet",
        _ACTOR,
    ),
]

# The planted bad subclass: the goldens' partner_loan base with one
# abstract method (fire_key_matches) missing, instantiated.
BAD_SUBCLASS_HEADER = """\
# A generated class's subclass that omits one abstract method. The type
# check test expects exactly the reportAbstractUsage error at the marked
# instantiation line, so this file is a golden too -- but a failing one.
# The generator never writes this file; it documents what reportAbstractUsage
# says, and the typed subclass one directory above it satisfies its base.
"""


def main() -> int:
    for out_name, fixture, actor, is_async in GOLDENS:
        relative = fixture.relative_to(_REPO_ROOT).as_posix()
        text = fixture.read_text(encoding="utf-8")
        lowered = lower_petrinet_text(text, relative)
        net = parse_net(compile_petrinet_text(text, relative))
        module = generate_module(
            net,
            source=relative,
            source_name=relative,
            text=text,
            contributions=lowered["contributions"],
            actor=actor,
            is_async=is_async,
        )
        out = _PYTHON_ROOT / "tests" / "fixtures" / "codegen" / "golden" / out_name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(module.text, encoding="utf-8")
        print(f"wrote {out} ({len(module.text)} bytes)")
    for out_name, fixture, actor in COMPOSITION_GOLDENS:
        # The generator produces the composition's module AND every
        # nested member's; only the ones whose stem matches an entry
        # above (the ones beside an on-disk composition file) are written.
        # The goldens import their members through `velocitron_nets` (the
        # package beside them): the `members_package` flag's value is the
        # import scheme's package spelling.
        generated = generate_composition(
            str(fixture), actor=actor, members_package="velocitron_nets"
        )
        golden_dir = _PYTHON_ROOT / "tests" / "fixtures" / "codegen" / "golden"
        for stem, module_text in sorted(generated.items()):
            if stem == Path(out_name).stem:
                out = golden_dir / out_name
            else:
                # A nested level's module: beside its own fixture file.
                out = _nested_module_path(fixture, stem, golden_dir, out_name)
                if out is None:
                    continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(module_text, encoding="utf-8")
            print(f"wrote {out} ({len(module_text)} bytes)")
    write_bad_subclass()
    return 0


def _nested_module_path(
    fixture: Path, stem: str, golden_dir: Path, composition_stem: str
) -> Path | None:
    """A nested level's golden path: inside the members package
    (`velocitron_nets/<stem>.py`), where the outer composition's imports
    find it.

    The nesting's own `use` lines resolve the nested file relative to
    `fixture`'s directory; the stem carries that file's stem (its
    hyphens underscored).
    """
    candidates = sorted(fixture.parent.rglob(f"{stem}.petrinet"))
    if not candidates:
        return None
    return golden_dir / "velocitron_nets" / f"{stem}.py"




def write_bad_subclass() -> None:
    """The partner_loan golden, subclassed with one abstract method gone.

    The test asserts exactly the ONE reportAbstractUsage error, at the
    instantiation line; never hand-edit — regenerate with this script.
    """
    body = '''\
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
'''
    out = _PYTHON_ROOT / "tests/fixtures/codegen/golden/velocitron_nets/bad_subclass.py"
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out}")
    write_library_holds_subclass_fixtures()


def write_library_holds_subclass_fixtures() -> None:
    """The library_holds constructor's two pyright fixtures.

    The GOOD one type-checks at the composition constructor. The BAD one
    omits ``fire_notify``, so the Protocol-typed ``checkout=`` argument
    fails basedpyright at that call. Regenerate with this script.
    """
    header = '''\
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
from velocitron_nets.request import (
    FileHoldOutputs,
    HoldRequestNet,
    ReopenOutputs,
)
from velocitron_engine import Token
'''
    stubs = '''

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
'''
    outcome_good = '''

class MyCheckout(RefinedBorrow, LoanCheckoutNet):
    # The mixin fills the refined fire_borrow; the other abstract methods
    # are written here.

    def fire_stamp_due(self, loan_ended: list[Token]) -> StampDueOutputs:
        return {"loaned": [], "stamped": [], "shelf_slot": []}

    def fire_notify(self, loan_ended: list[Token]) -> NotifyOutputs:
        return {"due": []}
'''
    # Shelf, notice, and edition have no abstract methods. Import their
    # concrete classes and construct them. Done as text so the fixtures
    # stay the generator's output.
    header = header.replace(
        "from velocitron_nets.request import (",
        "from velocitron_nets.shelf import HoldShelfNet\n"
        "from velocitron_nets.notice import OverdueNoticeNet\n"
        "from velocitron_nets.edition import NewerEditionNet\n"
        "from velocitron_nets.request import (",
    )
    good_tail = '''

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
'''
    bad_tail = '''

lifecycle = HoldLifecycleComposition(
    request=MyRequest(),
    shelf=HoldShelfNet(),
    checkout=MyCheckout(),  # the Protocol call site: MyCheckout lacks fire_notify
    notice=OverdueNoticeNet(),
    edition=NewerEditionNet(),
)
composition = LibraryHoldsComposition(
    lifecycle=lifecycle,
    loan=MyLoan(),
    catalog=MyCatalog(),
)
'''
    good = header + stubs + outcome_good + good_tail
    bad = (
        header
        + stubs
        + outcome_good.replace(
            '''    def fire_notify(self, loan_ended: list[Token]) -> NotifyOutputs:
        return {"due": []}
''',
            "",
        )
        + bad_tail
    ).replace("    NotifyOutputs,\n", "")
    root = _PYTHON_ROOT / "tests/fixtures/codegen/golden"
    out_good = root / "good_library_holds_subclass.py"
    out_bad = root / "bad_library_holds_composition_subclass.py"
    out_good.write_text(good, encoding="utf-8")
    out_bad.write_text(bad, encoding="utf-8")
    print(f"wrote {out_good}")
    print(f"wrote {out_bad}")


if __name__ == "__main__":
    raise SystemExit(main())
