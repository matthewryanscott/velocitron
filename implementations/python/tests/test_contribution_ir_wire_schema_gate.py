"""The packaged wire schema gates ``resolve_contribution_ir`` (ADR 0026).

Resolution consults the packaged draft-2020-12 contribution-IR schema before
any handwritten work; only what JSON Schema cannot express (source identities,
ordinal contiguity, span provenance, cross-fact conflicts) stays handwritten.
Schema-path failures keep the pinned PN-coded diagnostics.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import resolve_contribution_ir
from velocitron_dsl import PetrinetDslError

_BASE_SOURCE = (
    "net schema_gate\n\n(queue) accepts [token]\n(queue) -> [start]\n"
    '[start] handler "h@schema_gate"\n@q: (queue) -> [start]\n@q weight 2\n'
)


def _lowered_ir() -> dict[str, Any]:
    return lower_petrinet_text(_BASE_SOURCE, "schema-gate.petrinet")


def _contributions(ir: dict[str, Any]) -> list[dict[str, Any]]:
    contributions = ir["contributions"]
    assert isinstance(contributions, list)
    return [cast(dict[str, Any], entry) for entry in cast("list[Any]", contributions)]


def test_given_extra_root_field_when_resolved_then_document_shape_is_rejected() -> None:
    # given: otherwise-valid portable IR carrying an unknown root member
    ir = _lowered_ir()
    ir["unexpected"] = True

    # when: the wire schema gates resolution
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: the schema-path failure keeps the pinned PN200 envelope diagnostic
    assert raised.value.diagnostic.code == "PN200"
    assert raised.value.diagnostic.message == "invalid Contribution IR document shape"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            {"format": "velocitron.petrinet/contribution-ir-next"},
            "unsupported Contribution IR format or version",
        ),
        ({"version": 2}, "unsupported Contribution IR format or version"),
    ],
)
def test_given_unsupported_wire_identity_when_resolved_then_rejected(
    mutation: dict[str, Any], message: str
) -> None:
    # given: a wire identity the v1 schema does not accept
    ir = _lowered_ir()
    ir.update(mutation)

    # when: the wire schema gates resolution
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: resolution names the unsupported identity, per the pinned surface
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == message


def test_given_extra_contribution_field_when_resolved_then_contribution_shape_is_rejected() -> (
    None
):
    # given: one closed contribution carrying an unknown member
    ir = _lowered_ir()
    _contributions(ir)[0]["extra"] = None

    # when: the wire schema gates resolution
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: the failure is pinned to the closed contribution shape
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == "invalid Contribution IR contribution shape"


def test_given_extra_header_value_field_when_resolved_then_kind_diagnostic_is_kept() -> (
    None
):
    # given: the net header value carrying an unknown member
    ir = _lowered_ir()
    header = next(
        entry for entry in _contributions(ir) if entry["kind"] == "document.net-header"
    )
    header["value"]["extra"] = None

    # when: the wire schema gates resolution
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: the schema-path failure reports the same per-kind message and span
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == "invalid net header contribution"
    assert diagnostic.span.source == "schema-gate.petrinet"
    assert diagnostic.span.start.line == 1


def test_given_weight_below_one_when_resolved_then_pn202_weight_diagnostic_is_kept() -> (
    None
):
    # given: an imported arc weight fact set below the wire minimum
    ir = _lowered_ir()
    weight = next(
        entry for entry in _contributions(ir) if entry["kind"] == "arc.weight"
    )
    weight["value"]["weight"] = 0

    # when: the wire schema gates resolution
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: the pinned PN202 spelling of the weight violation survives
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.message == (
        "arc weight must be an integer greater than or equal to 1; "
        f"got 0 for @{weight['target']['name']}"
    )


def test_given_empty_route_points_when_resolved_then_pn202_points_diagnostic_is_kept() -> (
    None
):
    # given: an imported route fact whose point array violates the wire minimum
    ir = lower_petrinet_text(
        "net routed\n\n@arc: (a) -> [b]\nview window route @arc orthogonal []\n",
        "empty-route.petrinet",
    )

    # when: the wire schema gates resolution
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: the pinned PN202 route diagnostic survives, help text included
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.message == (
        "view 'window' route @arc requires at least one point"
    )
    assert diagnostic.help == 'add at least one {"x": Number, "y": Number} point'


def test_given_ordinal_out_of_order_when_resolved_then_ordinal_diagnostic_is_kept() -> (
    None
):
    # given: schema-valid IR whose ordinals no longer match source order —
    # a cross-item invariant the wire schema cannot express
    ir = _lowered_ir()
    contributions = _contributions(ir)
    contributions[1]["ordinal"], contributions[2]["ordinal"] = (
        contributions[2]["ordinal"],
        contributions[1]["ordinal"],
    )

    # when: resolution runs after a clean schema consult
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(ir)

    # then: the handwritten contiguity check still rejects the reorder
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == (
        "contribution ordinals must be contiguous zero-based integers"
    )
