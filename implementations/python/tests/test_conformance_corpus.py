"""Manifest-driven Petri-net DSL conformance corpus runner.

Every case in ``packages/spec/conformance/petrinet/manifest.json`` is exercised through
the full pipeline (lowering, resolution, public compilation, canonical
fixed point), with the manifest ``expect`` block pinning the per-case order
facts and marking data. Case-specific probes that cannot be expressed as
manifest data (synthetic sources, imported-IR mutations, merge/loader
machinery, viz rendering) live in the probes section below, distilled from
the per-case parser/resolver files they replaced.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, cast

from velocitron_engine import Wire
from typing import Callable

import pytest
from jsonschema import Draft202012Validator

from velocitron_petrinet import merge_composition
from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import emit_petrinet
from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import resolve_contribution_ir
from velocitron_dsl import (
    Diagnostic,
    PetrinetDslError,
)
from velocitron_petrinet import (
    NetValidationError,
    parse_composition,
    parse_net,
)
from velocitron_engine import (
    Arc,
    Net,
)
from velocitron_viz import (
    NAME_POINT,
    SMALL_POINT,
    apply_view,
    beside_gap,
    net_render_model,
    node_width,
    read_decorations,
)

_REPO_ROOT = Path(__file__).parents[3]
_CORPUS_ROOT = _REPO_ROOT / "packages" / "spec" / "conformance" / "petrinet"
_MANIFEST_PATH = _CORPUS_ROOT / "manifest.json"
_IR_SCHEMA_PATH = (
    _REPO_ROOT / "packages" / "spec" / "petrinet-contribution-ir.schema.json"
)


def _corpus_document(relative: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((_CORPUS_ROOT / relative).read_text(encoding="utf-8")),
    )


def _diagnostic_payload(diagnostic: Diagnostic) -> dict[str, Any]:
    """Serialize a DSL diagnostic exactly like the corpus expectation files."""
    payload: dict[str, Any] = {
        "code": diagnostic.code,
        "column": diagnostic.span.start.column,
        "file": diagnostic.span.source,
        "line": diagnostic.span.start.line,
        "message": diagnostic.message,
        "span": diagnostic.span.as_dict(),
    }
    if diagnostic.help is not None:
        payload["help"] = diagnostic.help
    if diagnostic.related:
        payload["related"] = [
            {"message": item.message, "span": item.span.as_dict()}
            for item in diagnostic.related
        ]
    return payload


_MANIFEST = cast(dict[str, Any], json.loads(_MANIFEST_PATH.read_text(encoding="utf-8")))
_VALID_CASES = [
    (entry["id"], cast(dict[str, Any], entry["valid"]))
    for entry in _MANIFEST["cases"]
    if "valid" in entry
]
_INVALID_CASES = [
    (entry["id"], case, cast(dict[str, Any], fixture))
    for entry in _MANIFEST["cases"]
    for case, fixture in [(entry["id"], f) for f in entry.get("invalid", [])]
]


# --------------------------------------------------------------------------
# Corpus runner
# --------------------------------------------------------------------------


def test_manifest_pins_format_version_and_case_counts() -> None:
    """The manifest identity and exhaustive case counts are frozen."""
    # given: the checked-in corpus manifest
    # when/then: identity and case counts match the conformance contract
    assert _MANIFEST["format"] == "velocitron.petrinet/conformance-corpus"
    assert _MANIFEST["version"] == 1
    assert len(_VALID_CASES) == 42
    assert len(_INVALID_CASES) == 119


@pytest.mark.parametrize(("case_id", "valid"), _VALID_CASES)
def test_valid_case_pipeline_and_order_pins(
    case_id: str, valid: dict[str, Any]
) -> None:
    """Each valid case lowers, resolves, compiles, and canonicalizes exactly."""
    # given: the case's committed source, IR, document, and canonical source
    expect = cast(dict[str, Any], valid["expect"])
    source = _corpus_document(expect.get("source") or valid["canonicalSource"])
    contribution_ir = _corpus_document(valid["contributionIr"])
    is_composition = "canonicalNet" not in valid
    document = _corpus_document(
        valid["canonicalComposition"] if is_composition else valid["canonicalNet"]
    )
    canonical = _corpus_document(valid["canonicalSource"])

    # when: the source is lowered against the portable IR schema
    lowered = lower_petrinet_text(source["text"], source["sourceId"])
    Draft202012Validator(
        json.loads(_IR_SCHEMA_PATH.read_text(encoding="utf-8"))
    ).validate(lowered)  # pyright: ignore[reportUnknownMemberType]

    # then: the IR is the frozen portable contract with the pinned version
    assert lowered == contribution_ir
    assert lowered["format"] == "velocitron.petrinet/contribution-ir"
    assert lowered["version"] == expect["contributionIrVersion"]

    # and: the frozen IR resolves to the frozen document
    assert resolve_contribution_ir(contribution_ir) == document

    # and: public compilation reproduces the same document
    assert compile_petrinet_text(source["text"], source["sourceId"]) == document

    # and: the committed canonical source compiles to the same document
    assert expect["canonicalSourceFixedPoint"] is True
    assert compile_petrinet_text(canonical["text"], canonical["sourceId"]) == document

    # and: emission is a compile-stable fixed point
    emitted = emit_petrinet(document)
    assert compile_petrinet_text(emitted, source["sourceId"]) == document
    assert emit_petrinet(compile_petrinet_text(emitted, source["sourceId"])) == emitted

    # and: the manifest order/token pins apply to the resolved document
    if "placeOrder" in expect:
        assert [place["name"] for place in document["places"]] == expect["placeOrder"]
        assert [transition["name"] for transition in document["transitions"]] == expect[
            "transitionOrder"
        ]
        assert [
            next(iter(arc["from"].values())) + "->" + next(iter(arc["to"].values()))
            for arc in document["arcs"]
        ] == expect["arcOrder"]
    if "tokenOrder" in expect:
        assert document["initialMarking"] == expect["tokenOrder"]


@pytest.mark.parametrize(
    ("case_id", "fixture"),
    sorted(
        (f"{case}/{entry['id']}", entry)
        for case, _, entry in _INVALID_CASES
        if entry["phase"] == "parse"
    ),
)
def test_invalid_parse_phase_diagnostic(case_id: str, fixture: dict[str, Any]) -> None:
    """Parse-phase fixtures fail compilation with their exact committed diagnostic."""
    # given: the frozen expectation file for this parse-phase case
    expectation = _corpus_document(fixture["expectation"])
    source = cast(dict[str, str], expectation["source"])

    # when: the source is compiled through the public API
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source["text"], source["sourceId"])

    # then: the serialized diagnostic is the committed one
    assert _diagnostic_payload(raised.value.diagnostic) == expectation["diagnostic"]
    assert fixture["structureParses"] is False


@pytest.mark.parametrize(
    ("case_id", "fixture"),
    sorted(
        (f"{case}/{entry['id']}", entry)
        for case, _, entry in _INVALID_CASES
        if entry["phase"] == "resolution"
        and entry.get("owner") != "composition-loader"
        and "source" in _corpus_document(entry["expectation"])
    ),
)
def test_invalid_resolution_phase_source_diagnostic(
    case_id: str, fixture: dict[str, Any]
) -> None:
    """Resolution-phase source fixtures fail compilation with the committed diagnostic."""
    # given: the frozen expectation file carrying an authored source
    expectation = _corpus_document(fixture["expectation"])
    source = cast(dict[str, str], expectation["source"])

    # when: the source is compiled through the public API
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source["text"], source["sourceId"])

    # then: the serialized diagnostic is the committed one, structure-aware
    assert _diagnostic_payload(raised.value.diagnostic) == expectation["diagnostic"]
    assert fixture["structureParses"] is True


@pytest.mark.parametrize(
    ("case_id", "fixture"),
    sorted(
        (f"{case}/{entry['id']}", entry)
        for case, _, entry in _INVALID_CASES
        if entry["phase"] == "resolution"
        and "net" in _corpus_document(entry["expectation"])
    ),
)
def test_invalid_resolution_phase_net_diagnostic(
    case_id: str, fixture: dict[str, Any]
) -> None:
    """Net-only fixtures are rejected by the emitter's closed reconstruction."""
    # given: the frozen expectation file carrying only the resolved net
    expectation = _corpus_document(fixture["expectation"])
    net = cast(dict[str, Any], expectation["net"])

    # when: the tampered net is canonicalized
    with pytest.raises(ValueError) as raised:
        emit_petrinet(net)

    # then: the emitter rejects the tampered net (exact messages pinned by probes)
    assert "source" not in expectation
    assert str(raised.value) != ""
    assert fixture["structureParses"] is True


@pytest.mark.parametrize(
    ("case_id", "fixture"),
    sorted(
        (f"{case}/{entry['id']}", entry)
        for case, _, entry in _INVALID_CASES
        if entry.get("owner") == "composition-loader"
    ),
)
def test_invalid_composition_loader_structurally_compiles(
    case_id: str, fixture: dict[str, Any]
) -> None:
    """Composition-loader diagnostics surface downstream of public compilation."""
    # given: a resolution-phase fixture owned by the composition loader
    expectation = _corpus_document(fixture["expectation"])
    source = cast(dict[str, str], expectation["source"])

    # when: the composition source is compiled through the public API
    compiled = compile_petrinet_text(source["text"], source["sourceId"])

    # then: compilation succeeds structurally; the diagnostic is the loader's
    assert "nets" in compiled
    assert "wires" in compiled
    assert fixture["phase"] == "resolution"
    assert fixture["structureParses"] is True


@pytest.mark.parametrize(
    ("case_id", "fixture"),
    sorted(
        (f"{case}/{entry['id']}", entry)
        for case, _, entry in _INVALID_CASES
        if entry.get("owner") == "composition-loader"
    ),
)
def test_invalid_composition_loader_diagnostic_with_a_loader(
    case_id: str, fixture: dict[str, Any]
) -> None:
    """With the case's sibling sources as nets, the diagnostic is at the fact."""
    # given: a loader that compiles `<name>.source.json` beside the fixture
    expectation = _corpus_document(fixture["expectation"])
    source = cast(dict[str, str], expectation["source"])
    directory = Path(fixture["expectation"]).parent

    def load(ref: str) -> dict[str, Any]:
        sibling = _corpus_document(
            str(directory / ref.replace(".petrinet", ".source.json"))
        )
        return compile_petrinet_text(sibling["text"], sibling["sourceId"])

    # when: the composition compiles with its nets loaded
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source["text"], source["sourceId"], net_loader=load)

    # then: the serialized diagnostic is the committed one
    assert _diagnostic_payload(raised.value.diagnostic) == expectation["diagnostic"]


# --------------------------------------------------------------------------
# Distilled case-specific probes (replaced per-case parser/resolver files)
# --------------------------------------------------------------------------

# --- probes distilled from test_coin*_parser_resolver.py ---

_COIN_CHOICE_ANNOTATED_SOURCE = """\
net coin_choice "Coin choice"

@return: (coin_slot) -coin-> [return_coin]
@accept: (coin_slot) -coin-> [accept_coin] -coin-> (cash_box)

[return_coin] handler "return_coin"
[accept_coin] handler "accept_coin"

[accept_coin] order 1
[return_coin] order 1
@return order 2
@accept order 1

marking initial (coin_slot) <- $inserted_coin
$inserted_coin: coin {}
"""


def test_duplicate_transition_order_diagnostic_on_ordered_annotated_source() -> None:
    """The later duplicate points back to its first rank assignment."""
    # given: the ordered annotated source with return_coin demoted to duplicate position 1
    source = _COIN_CHOICE_ANNOTATED_SOURCE.replace(
        "[return_coin] order 2", "[return_coin] order 1"
    )
    # when: the source is compiled
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "coin-choice.petrinet")
    # then: the duplicate transition order diagnostic carries its help and a related span to line 9
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert (
        diagnostic.message == "transition order position 1 is assigned more than once"
    )
    assert (
        diagnostic.help
        == "assign each explicitly ordered transition a unique positive position"
    )
    assert diagnostic.span.start.line == 10
    assert diagnostic.related[0].message == "[accept_coin] first assigned position 1"
    assert diagnostic.related[0].span.start.line == 9


def test_relative_view_positions_render_at_expected_coordinates() -> None:
    """Relative entries ride ADR 0024's render model; the chain resolves."""
    # given: the resolved relative-views corpus net and its render model
    net_doc = _corpus_document("17-relative-views/relative-views.net.json")
    net = parse_net(net_doc)
    model = net_render_model(net)
    # when: the laid view resolves relative positions to absolute coordinates
    dot = apply_view(model, net_doc, "laid")
    # then: emit sits at seed + {3,4}, chain at seed + {10,5}, out at chain + {5,5}
    assert 'pos="3,4!"' in dot
    assert 'pos="13,9!"' in dot
    assert 'pos="18,14!"' in dot


def _coord(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def test_beside_pinned_views_place_copies_and_keep_the_place_anchor() -> None:
    """A pinned beside view places copies; a place position lands on them."""
    # given: the beside corpus net, with lanes and lanes_lock
    net_doc = _corpus_document("20-decoration-beside/beside.net.json")
    net = parse_net(net_doc)
    model = net_render_model(net, decorations=read_decorations(net_doc))
    start = beside_gap(
        node_width([("start", NAME_POINT)]),
        node_width([("switch", NAME_POINT), ("⟨flag⟩", SMALL_POINT)]),
    )
    finish = beside_gap(
        node_width([("finish", NAME_POINT)]),
        node_width([("switch", NAME_POINT), ("⟨flag⟩", SMALL_POINT)]),
    )
    budget = beside_gap(
        node_width([("start", NAME_POINT)]),
        node_width([("budget", NAME_POINT), ("⟨credit⟩", SMALL_POINT)]),
    )

    def node(dot: str, name: str) -> str:
        matches = [
            line for line in dot.splitlines() if line.startswith(f'    "{name}" [')
        ]
        assert len(matches) == 1, (name, matches)
        return matches[0]

    # when: lanes pins the transitions and not the fusion places
    lanes = apply_view(model, net_doc, "lanes")
    # then: switch is left of each transition, and budget is right of start
    assert f'pos="-{_coord(start)},200!"' in node(lanes, "switch@start")
    assert f'pos="-{_coord(finish)},0!"' in node(lanes, "switch@finish")
    assert f'pos="{_coord(budget)},200!"' in node(lanes, "budget@start")
    assert any(
        "constraint=false" in line and "switch@start" in line
        for line in lanes.splitlines()
    )

    # when: lanes_lock also positions (switch), and (done) is relative to it
    locked = apply_view(model, net_doc, "lanes_lock")
    # then: the place point lands on each switch copy, and done uses that anchor
    assert 'pos="40,0!"' in node(locked, "switch@start")
    assert 'pos="40,0!"' in node(locked, "switch@finish")
    assert 'pos="120,0!"' in node(locked, "done")
    # and: budget has no place position, so beside still places it
    assert f'pos="{_coord(budget)},200!"' in node(locked, "budget@start")


# --- probes distilled from test_batch*_parser_resolver.py ---


def _capacity_source(value: str) -> str:
    return (
        "net capacity_shape\n\n"
        "(batches) -batch-> [take]\n"
        '[take] handler "take"\n'
        f"(batches) capacityPerColorKey {value}\n"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('{"key":"batch_id","max":1}', {"key": "batch_id", "max": 1}),
        (
            '{"key":["tenant_id","batch_id"],"max":2}',
            {"key": ["tenant_id", "batch_id"], "max": 2},
        ),
    ],
)
def test_capacity_accepts_scalar_and_composite_key_shapes(
    value: str, expected: dict[str, object]
) -> None:
    """Given a scalar or composite non-empty key, resolution preserves JSON shape."""
    # given: a place fact with exactly key and max
    source = _capacity_source(value)

    # when: the fact resolves onto its declared place
    actual = compile_petrinet_text(source, "capacity-valid.petrinet")

    # then: the first-class schema spelling and scalar/array shape are unchanged
    assert actual["places"] == [
        {
            "name": "batches",
            "accepts": ["batch"],
            "capacityPerColorKey": expected,
        }
    ]


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        '{"key":"batch_id"}',
        '{"max":1}',
        '{"key":"","max":1}',
        '{"key":[],"max":1}',
        '{"key":["batch_id", ""],"max":1}',
        '{"key":true,"max":1}',
        '{"key":["batch_id",1],"max":1}',
        '{"key":"batch_id","max":-1}',
        '{"key":"batch_id","max":true}',
        '{"key":"batch_id","max":1,"extra":false}',
    ],
)
def test_capacity_rejects_invalid_object_shapes(value: str) -> None:
    """Given an invalid capacity object, validation rejects it at authored source."""
    # given: one invalid key, max, boolean-as-integer, or extra-member variant
    source = _capacity_source(value)

    # when: resolution validates the progressive place fact
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "capacity-invalid.petrinet")

    # then: PN202 remains attached to the authored fact, not generated JSON
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.span.source == "capacity-invalid.petrinet"
    assert diagnostic.span.start.line == 5


@pytest.mark.parametrize("weight", ["-1", "true", "1.5"])
def test_weight_rejects_non_positive_or_non_integer_values(weight: str) -> None:
    """Given an invalid consume weight, validation rejects the authored weight fact."""
    # given: an otherwise valid handled consume arc
    source = (
        "net batch_gate_invalid\n\n"
        "@items: (items) -item-> [form_batch]\n"
        '[form_batch] handler "form_batch"\n'
        f"@items weight {weight}\n"
    )

    # when: the progressive weight is parsed and resolved
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "batch_gate_invalid.petrinet")

    # then: PN202 targets the invalid value and identifies the submitted handle
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.span.source == "batch_gate_invalid.petrinet"
    assert diagnostic.span.start.line == 5
    assert "weight" in diagnostic.message
    assert "greater than or equal to 1" in diagnostic.message
    assert "@items" in diagnostic.message


@pytest.mark.parametrize(
    ("topology", "expected"),
    [
        (
            "@input: (items) -item-> [form_batch]",
            {"type": "item"},
        ),
        (
            "@open: (batches) -batch->0 [form_batch]",
            {"type": "batch", "mode": "inhibit"},
        ),
    ],
)
def test_default_weight_one_is_omitted_semantically(
    topology: str, expected: dict[str, object]
) -> None:
    """Given weight one on consume/inhibit, resolution retains the default semantics."""
    # given: a valid consume or inhibit arc with an explicit default weight fact
    handle = topology.split(":", 1)[0][1:]
    source = (
        "net default_weight\n\n"
        f"{topology}\n"
        '[form_batch] handler "form_batch"\n'
        f"@{handle} weight 1\n"
    )

    # when: the weight fact resolves
    actual = compile_petrinet_text(source, "default-weight.petrinet")

    # then: core JSON omits default weight while preserving the arc's input mode
    assert actual["arcs"][0]["consume"] == expected


@pytest.mark.parametrize(
    ("topology", "weight", "expected_fragment"),
    [
        ("@out: [form_batch] -batch-> (batches)", 2, "produce"),
        ("@open: (batches) -batch->0 [form_batch]", 2, "inhibit"),
    ],
)
def test_weight_rejects_non_consumptive_targets(
    topology: str, weight: int, expected_fragment: str
) -> None:
    """Given a non-consumptive target, weight cannot change its arc semantics."""
    # given: a produce arc or an inhibit zero-test carrying a non-default weight
    source = (
        "net invalid_weight_target\n\n"
        f"{topology}\n"
        '[form_batch] handler "form_batch"\n'
        f"@{topology.split(':', 1)[0][1:]} weight {weight}\n"
    )

    # when: the resolver applies the weight fact to the selected arc
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "invalid-weight-target.petrinet")

    # then: PN202 rejects it at the feature fact and names the arc mode
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.span.source == "invalid-weight-target.petrinet"
    assert diagnostic.span.start.line == 5
    assert "weight" in diagnostic.message
    assert expected_fragment in diagnostic.message


# --- probes distilled from test_crossing*_parser_resolver.py ---

_CROSSING_IR_REL = "05-crossing-window/crossing-window.contribution-ir.json"


@pytest.mark.parametrize(("mode", "line"), [("read", 4), ("inhibit", 6)])
def test_ir_rejects_transition_name_span_on_exceptional_arc_declarations(
    mode: str, line: int
) -> None:
    """Given read/inhibit IR, transitionNameSpan remains forbidden and strict."""
    # given: a frozen exceptional declaration extended with consume-only provenance
    portable: dict[str, Any] = deepcopy(_corpus_document(_CROSSING_IR_REL))
    declarations = [
        contribution
        for contribution in portable["contributions"]
        if contribution["kind"] == "arc.declare"
    ]
    consume = next(
        contribution
        for contribution in declarations
        if contribution["value"]["mode"] == "consume"
    )
    exceptional = next(
        contribution
        for contribution in declarations
        if contribution["value"]["mode"] == mode
    )
    exceptional["value"]["transitionNameSpan"] = deepcopy(
        consume["value"]["transitionNameSpan"]
    )

    # when: schema and resolver inspect the extended imported artifact
    schema = cast(
        "dict[str, Any]", json.loads(_IR_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    assert not cast(Any, Draft202012Validator(schema)).is_valid(portable)
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(portable)

    # then: resolution rejects the extra field at the exceptional declaration
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == "invalid consumed arc declaration"
    assert diagnostic.span.start.line == line


def test_ir_rejects_consume_without_transition_name_span() -> None:
    """Given ordinary consume IR, transitionNameSpan remains required and strict."""
    # given: the frozen consume declaration with its required provenance removed
    portable: dict[str, Any] = deepcopy(_corpus_document(_CROSSING_IR_REL))
    consume = next(
        contribution
        for contribution in portable["contributions"]
        if contribution["kind"] == "arc.declare"
        and contribution["value"]["mode"] == "consume"
    )
    del consume["value"]["transitionNameSpan"]

    # when: schema and resolver inspect the incomplete imported artifact
    schema = cast(
        "dict[str, Any]", json.loads(_IR_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    assert not cast(Any, Draft202012Validator(schema)).is_valid(portable)
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(portable)

    # then: resolution rejects the missing provenance on the consume declaration
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == "invalid consumed arc declaration"
    assert diagnostic.span.start.line == 3


# --- probes distilled from test_perkey*_parser_resolver.py ---

# Card 4 probe fragment: perkey (test_per_key_suppression_parser_resolver.py)

_CORRELATE = "token.key == binding.requests[0].key"


def test_resolved_net_parses_and_precompiles_correlate_cel() -> None:
    """Given resolved JSON, parse_net accepts the inhibit arc's CEL inscription."""
    # given: the exact resolved core document from the conformance corpus
    expected = _corpus_document("07-per-key-suppression/per-key-suppression.net.json")

    # when: core parsing validates structure and compiles inline CEL immediately
    net = parse_net(expected)

    # then: the schema-level object is represented as the exact CEL source
    inhibitor = next(arc for arc in net.arcs if arc.from_place == "suppressions")
    assert inhibitor.consume is not None
    assert inhibitor.consume.mode == "inhibit"
    assert inhibitor.consume.correlate == _CORRELATE


@pytest.mark.parametrize(
    ("topology", "mode"),
    [
        ("@target: (requests) -request-> [admit]", "consume"),
        ("@target: (requests) -request->? [admit]", "read"),
        ("@target: (requests) -request->0 [admit]", "inhibit"),
    ],
)
def test_correlate_resolves_on_every_input_arc(topology: str, mode: str) -> None:
    """Given correlate on any input arc, resolution attaches it to that arc."""
    # given: a consume, read, or inhibit handle with a separately authored correlation
    source = (
        "net input_correlate\n\n"
        f"{topology}\n"
        '[admit] handler "admit_request"\n'
        '@target correlate cel "token.key == binding.requests[0].key"\n'
    )

    # when: progressive resolution places the fact on the targeted arc
    document = compile_petrinet_text(source, "input-correlate.petrinet")

    # then: the arc keeps its mode and carries the correlate CEL
    (arc,) = document["arcs"]
    assert arc["consume"].get("mode", "consume") == mode
    assert arc["consume"]["correlate"] == {
        "cel": "token.key == binding.requests[0].key"
    }


def test_correlate_rejected_on_produce_arc() -> None:
    """Given correlate on a produce arc, PN202 identifies the fact and arc."""
    # given: a produce-only handle with a separately authored correlation
    source = (
        "net invalid_correlate\n\n"
        "@target: [admit] -request-> (admitted)\n"
        '[admit] handler "admit_request"\n'
        '@target correlate cel "token.key == binding.requests[0].key"\n'
    )

    # when: progressive resolution checks the targeted arc
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "invalid-correlate-mode.petrinet")

    # then: the error is attached to correlate, names the input-arc rule,
    # and retains the topology declaration as related source context
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.span.source == "invalid-correlate-mode.petrinet"
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (5, 1)
    assert "correlate must target exactly one input arc" in diagnostic.message
    assert len(diagnostic.related) == 1
    assert diagnostic.related[0].span.start.line == 3


def test_malformed_correlate_cel_reports_pn203() -> None:
    """Given invalid CEL, PN203 is raised before parsing or engine execution."""
    # given: a valid inhibit topology carrying syntactically malformed CEL
    source = """\
net invalid_correlate_cel

@blocked: (suppressions) -suppression->0 [admit]
[admit] handler "admit_request"
@blocked correlate cel "token.key ==== binding.requests[0].key"
"""

    # when: resolution compiles the inline expression
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "invalid-correlate-cel.petrinet")

    # then: the stable diagnostic points to the progressive correlate fact
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN203"
    assert diagnostic.message == "invalid CEL correlate for arc @blocked"
    assert diagnostic.help == "fix the CEL expression syntax"
    assert diagnostic.span.source == "invalid-correlate-cel.petrinet"
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (5, 1)


# --- probes distilled from test_cadence*_parser_resolver.py ---


def _cadence_tick_source() -> str:
    """Corpus-identical cadence-tick inline source template."""
    return """\
net cadence_tick "Timed cadence with alert reset"

(tick_latch) -tick_latch-> [on_tick] -tick_latch-> (tick_latch)
@tick_clock: (clock) -clock->? [on_tick]
[on_tick] -refresh_due-> (refresh_due)

(alert) -alert-> [on_alert] -refresh_due-> (refresh_due)
(tick_latch) -tick_latch-> [on_alert] -tick_latch-> (tick_latch)
@alert_clock: (clock) -clock->? [on_alert]

[on_tick] handler "on_tick@cadence"
[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at + latch.cadence_s"
[on_tick] timer bind latch (tick_latch)

[on_alert] handler "on_alert@cadence"
[on_alert] priority 10

marking initial (clock) <- $clock_zero
marking initial (tick_latch) <- $cadence_latch

$clock_zero: clock {"now": 0}
$cadence_latch: tick_latch {"fired_at": 0, "cadence_s": 300}
"""


def test_equal_timed_facts_are_idempotent() -> None:
    """Given repeated equal timed facts, resolution keeps one semantic value."""
    # given: every newly introduced fact is repeated byte-for-byte
    source = (
        _cadence_tick_source()
        .replace(
            "[on_tick] timer bind latch (tick_latch)\n",
            "[on_tick] timer bind latch (tick_latch)\n[on_tick] timer bind latch (tick_latch)\n",
        )
        .replace(
            '[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at + latch.cadence_s"\n',
            '[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at + latch.cadence_s"\n'
            '[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at + latch.cadence_s"\n',
        )
        .replace(
            "[on_alert] priority 10\n",
            "[on_alert] priority 10\n[on_alert] priority 10\n",
        )
    )

    # when: the progressive facts resolve
    actual = compile_petrinet_text(source, "equal-cadence.petrinet")

    # then: scalar and map values occur once in the semantic transition objects
    assert actual["transitions"] == [
        {
            "name": "on_tick",
            "handler": "on_tick@cadence",
            "timer": {
                "clock": "clock",
                "cel": "clock.now >= latch.fired_at + latch.cadence_s",
                "bind": {"latch": "tick_latch"},
            },
        },
        {"name": "on_alert", "handler": "on_alert@cadence", "priority": 10},
    ]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            '[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at"',
            '[on_tick] timer clock (other_clock) cel "clock.now >= latch.fired_at"',
        ),
        (
            '[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at"',
            '[on_tick] timer clock (clock) cel "clock.now > latch.fired_at"',
        ),
        (
            "[on_tick] timer bind latch (tick_latch)",
            "[on_tick] timer bind latch (other_latch)",
        ),
        ("[on_tick] priority 1", "[on_tick] priority 2"),
    ],
    ids=["clock", "cel", "bind", "priority"],
)
def test_unequal_timed_facts_cite_later_and_first_definition_span(
    first: str, second: str
) -> None:
    """Given unequal duplicate facts, the conflict relates both source definitions."""
    # given: valid topology and contradictory facts on consecutive lines
    source = f"""\
net conflicting_cadence
(tick_latch) -tick_latch-> [on_tick] -tick_latch-> (tick_latch)
(other_latch) -tick_latch-> [on_tick]
(clock) -clock->? [on_tick]
(other_clock) -clock->? [on_tick]
[on_tick] handler "on_tick@cadence"
{first}
{second}
"""

    # when: resolution encounters the later contribution
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "conflicting-cadence.petrinet")

    # then: the primary span is later and the related span is the first definition
    diagnostic = raised.value.diagnostic
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (8, 1)
    assert len(diagnostic.related) == 1
    assert (
        diagnostic.related[0].span.start.line,
        diagnostic.related[0].span.start.column,
    ) == (7, 1)


def test_timer_clock_must_resolve_to_a_declared_place() -> None:
    """Given an unknown timer clock, resolution rejects the offending fact."""
    # given: complete topology whose timer alone names ghost_clock
    source = """\
net unknown_clock
(tick_latch) -tick_latch-> [on_tick] -tick_latch-> (tick_latch)
[on_tick] handler "on_tick@cadence"
[on_tick] timer clock (ghost_clock) cel "clock.now >= 0"
"""

    # when: timer references are resolved
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "unknown-clock.petrinet")

    # then: the diagnostic identifies the unresolved clock at its fact
    diagnostic = raised.value.diagnostic
    assert "ghost_clock" in diagnostic.message
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (4, 1)


def test_timer_bind_place_must_feed_the_transition() -> None:
    """Given a non-input bind place, resolution rejects hidden timer topology."""
    # given: alert is declared but feeds another completed transition, not on_tick
    source = """\
net invalid_bind_topology
(tick_latch) -tick_latch-> [on_tick] -tick_latch-> (tick_latch)
(clock) -clock->? [on_tick]
(alert) -alert-> [on_alert] -alert-> (alert)
[on_tick] handler "on_tick@cadence"
[on_alert] handler "on_alert@cadence"
[on_tick] timer clock (clock) cel "clock.now >= latch.fired_at"
[on_tick] timer bind latch (alert)
"""

    # when: the bind environment is resolved against actual input arcs
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "invalid-bind-topology.petrinet")

    # then: the error names both the variable and structurally unrelated place
    diagnostic = raised.value.diagnostic
    assert "latch" in diagnostic.message and "alert" in diagnostic.message
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (8, 1)


def test_timer_bind_rejects_reserved_clock_name() -> None:
    """Given a bind named clock, resolution protects the native timer variable."""
    # given: a structurally valid bind using the reserved environment key
    source = """\
net reserved_clock
(tick_latch) -tick_latch-> [on_tick] -tick_latch-> (tick_latch)
(clock) -clock->? [on_tick]
[on_tick] handler "on_tick@cadence"
[on_tick] timer clock (clock) cel "clock.now >= 0"
[on_tick] timer bind clock (tick_latch)
"""

    # when: the timer environment is resolved
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "reserved-clock.petrinet")

    # then: the reserved identifier is rejected at the bind fact
    diagnostic = raised.value.diagnostic
    assert "clock" in diagnostic.message and "reserved" in diagnostic.message
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (6, 1)


def test_malformed_timer_cel_reports_source_span() -> None:
    """Given malformed timer CEL, ordinary net compilation fails before runtime."""
    # given: syntactically valid DSL wrapping an invalid CEL expression
    source = """\
net malformed_timer
(tick_latch) -tick_latch-> [on_tick] -tick_latch-> (tick_latch)
(clock) -clock->? [on_tick]
[on_tick] handler "on_tick@cadence"
[on_tick] timer clock (clock) cel "clock.now >="
"""

    # when: the complete semantic net is compiled
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "malformed-timer.petrinet")

    # then: CEL compilation is reported on the authored timer fact
    diagnostic = raised.value.diagnostic
    assert "CEL" in diagnostic.message
    assert diagnostic.span.source == "malformed-timer.petrinet"
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (5, 1)


# --- probes distilled from test_cookie*_parser_resolver.py ---

# given: the corpus authored net (byte-identical to the original _COOKIE_SOURCE)
_COOKIE_SOURCE: str = _corpus_document("03-cookie-vending/cookie-vending.source.json")[
    "text"
]

# given: a source whose initial marking uses a multiplicity run of five identical packets
_MULTIPLICITY_SOURCE = """\
net "cookie-vending-multiplicity"

(storage) -packet-> [vend_packet]
[vend_packet] -packet-> (compartment)

[vend_packet] handler "vend_packet"

marking initial (storage) <- 5 * $packet

$packet: packet {}
"""


def test_marking_multiplicity_expands_distinct_token_objects() -> None:
    """Multiplicity expansion produces physically distinct token objects."""
    # given: the multiplicity source expands one template five times
    # when: the source is compiled to portable IR
    actual = compile_petrinet_text(_MULTIPLICITY_SOURCE, "multiplicity.petrinet")

    # then: each of the five storage tokens is a distinct Python object with no aliasing
    assert len(actual["initialMarking"]["storage"]) == 5
    assert all(
        token == {"type": "packet", "data": {}}
        for token in actual["initialMarking"]["storage"]
    )
    assert len({id(token) for token in actual["initialMarking"]["storage"]}) == 5


def test_identical_arc_data_facts_are_idempotent() -> None:
    """Equal repeated data facts merge; conflicting facts point to both spans."""
    # given: the exceptional produce arc receives the same literal fact twice
    identical = _COOKIE_SOURCE.replace(
        "@vend_signal data {}\n", "@vend_signal data {}\n@vend_signal data {}\n"
    )

    # when: equal progressive facts resolve
    resolved = compile_petrinet_text(identical, "cookie-vending.petrinet")

    # then: the duplicate is idempotent and does not duplicate or decorate the arc
    assert resolved == _corpus_document("03-cookie-vending/cookie-vending.net.json")

    # given: a later declaration contradicts the first literal template
    conflicting = """\
net "cookie-vending"

@vend_signal: [accept_coin] -signal-> (signal)
@vend_signal data {"source": "handler"}
@vend_signal data {}
"""

    # when: the contradictory contribution is resolved
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(conflicting, "cookie-vending.petrinet")

    # then: the later declaration is primary and the first declaration is related context
    payload = _diagnostic_payload(raised.value.diagnostic)
    assert payload["code"] == "PN202"
    assert payload["message"] == "conflicting data facts for arc @vend_signal"
    assert payload["span"]["start"]["line"] == 5
    assert payload["span"]["start"]["column"] == 1
    assert len(payload["related"]) == 1
    assert (
        payload["related"][0]["message"]
        == 'first value {"source":"handler"} was declared here'
    )
    assert payload["related"][0]["span"]["start"]["line"] == 4
    assert payload["related"][0]["span"]["start"]["column"] == 1


def test_generic_marking_runs_emit_counts_without_consuming_template_indexes() -> None:
    """Generic empty tokens use count shorthand while every other token uses templates."""
    # given: initial and named markings interleave empty and data-bearing
    # Generic runs, while a separate single-color place carries typed tokens
    generic: dict[str, Any] = {"type": "token", "data": {}}
    job_a = {"type": "job", "data": {"id": "a"}}
    generic_with_data = {"type": "token", "data": {"id": "generic"}}
    job_b = {"type": "job", "data": {"id": "b"}}
    expected: dict[str, object] = {
        "name": "generic-canonical",
        "places": [
            {"name": "ready", "accepts": ["token"]},
            {"name": "done", "accepts": ["job"]},
        ],
        "transitions": [],
        "arcs": [],
        "initialMarking": {
            "ready": [
                generic,
                generic,
                generic_with_data,
                generic,
                generic_with_data,
            ],
            "done": [job_a],
        },
        "annotations": {
            "petrinet.dsl/v1": {
                "arcHandles": {},
                "markings": {
                    "checkpoint": {
                        "ready": [generic, generic_with_data, generic, generic],
                        "done": [job_b, job_a],
                    }
                },
                "views": {},
                "extensions": {},
            }
        },
    }

    # when: JSON is emitted and compiled, then emitted again
    canonical = emit_petrinet(expected)
    round_tripped = compile_petrinet_text(canonical, "generic-canonical.petrinet")

    # then: each Generic run is an integer (including one), nonempty Generic
    # data remains template-backed, and only template-backed runs take ordinals
    assert (
        canonical
        == """\
net "generic-canonical"

(ready) accepts [token]
(done) accepts [job]

marking initial (ready) <- 2
marking initial (ready) <- $token_0
marking initial (ready) <- 1
marking initial (ready) <- $token_0
marking initial (done) <- $token_1
marking checkpoint (ready) <- 1
marking checkpoint (ready) <- $token_0
marking checkpoint (ready) <- 2
marking checkpoint (done) <- $token_2
marking checkpoint (done) <- $token_1
$token_0: token {"id":"generic"}
$token_1: job {"id":"a"}
$token_2: job {"id":"b"}

extensions {}
"""
    )
    assert round_tripped == expected
    assert emit_petrinet(round_tripped) == canonical


@pytest.mark.parametrize(
    ("first_value", "second_value", "first_literal", "second_literal"),
    [
        (True, 1, "true", "1"),
        (False, 0, "false", "0"),
    ],
)
def test_json_scalar_types_remain_distinct_templates_and_marking_runs(
    first_value: bool,
    second_value: int,
    first_literal: str,
    second_literal: str,
) -> None:
    """Given bool/int token data, emission preserves JSON types and run boundaries."""
    # given: adjacent tokens compare equal in Python but differ under JSON equality
    expected: dict[str, Any] = _corpus_document(
        "03-cookie-vending/cookie-vending.net.json"
    )
    expected["initialMarking"] = {
        "coin_slot": [
            {"type": "coin", "data": {"value": first_value}},
            {"type": "coin", "data": {"value": second_value}},
        ]
    }

    # when: the resolved document is emitted and compiled through public behavior
    canonical = emit_petrinet(expected)
    round_tripped = compile_petrinet_text(
        canonical, "cookie-vending.scalar-types.petrinet"
    )

    # then: neither template identity nor adjacent marking runs coalesce
    assert f'$token_0: coin {{"value":{first_literal}}}' in canonical
    assert f'$token_1: coin {{"value":{second_literal}}}' in canonical
    assert canonical.count("marking initial (coin_slot) <- $token_") == 2
    assert "marking initial (coin_slot) <- 2 * " not in canonical
    assert round_tripped == expected


def test_template_renaming_does_not_rewrite_quoted_place_names() -> None:
    """Given a template-like place name, token_n naming changes references only."""
    # given: two templates force generated token_n names beside a quoted place name
    expected: dict[str, Any] = deepcopy(
        _corpus_document("03-cookie-vending/cookie-vending.net.json")
    )
    quoted_name = "$inserted_coin depot"
    places = cast(list[dict[str, Any]], expected["places"])
    arcs = cast(list[dict[str, Any]], expected["arcs"])
    initial_marking = cast(dict[str, list[dict[str, Any]]], expected["initialMarking"])
    for place in places:
        if place["name"] == "coin_slot":
            place["name"] = quoted_name
    for arc in arcs:
        if arc["from"] == {"place": "coin_slot"}:
            arc["from"] = {"place": quoted_name}
    coin_tokens = initial_marking.pop("coin_slot")
    expected["initialMarking"] = {
        quoted_name: coin_tokens,
        **initial_marking,
    }

    # when: canonical DSL is emitted and compiled
    canonical = emit_petrinet(expected)
    round_tripped = compile_petrinet_text(
        canonical, "cookie-vending.quoted-template-name.petrinet"
    )

    # then: only template references are renamed, never quoted identifier contents
    assert f'marking initial ("{quoted_name}") <- $token_0' in canonical
    assert '"$token_0 depot"' not in canonical
    assert round_tripped == expected


# --- probes distilled from test_router*_parser_resolver.py ---

# Card 4 probe fragment: router
_TWO_ROUTES = """\
net "source-router"
@co2_route: (sample_in) -sample-> [route_co2mon] -sample-> (co2mon_samples)
@weather_route: (sample_in) -sample-> [route_weather] -sample-> (weather_samples)
[route_co2mon] handler "route_co2mon"
[route_weather] handler "route_weather"
@co2_route predicate cel "source == \\"co2mon\\""
@weather_route predicate cel "source == \\"weather\\""
"""


def test_synthetic_two_route_lowering_keeps_arc_handle_identity_without_guards() -> (
    None
):
    """Given handled two-arc runs, predicates decorate only their consume arcs."""
    # given: each route handle owns a complete consume-then-produce declaration run
    portable = lower_petrinet_text(_TWO_ROUTES, "source-router.petrinet")

    # when: the progressive CEL predicate facts are lowered and resolved
    resolved = compile_petrinet_text(_TWO_ROUTES, "source-router.petrinet")

    # then: handles keep both ordered arc identities while each predicate selects one consume
    handles = {
        item["target"]["name"]: item["value"]["arcIds"]
        for item in portable["contributions"]
        if item["kind"] == "arc.handle"
    }
    assert handles == {
        "co2_route": [
            {"document": "source-router.petrinet", "statement": 1, "part": 1},
            {"document": "source-router.petrinet", "statement": 1, "part": 2},
        ],
        "weather_route": [
            {"document": "source-router.petrinet", "statement": 2, "part": 1},
            {"document": "source-router.petrinet", "statement": 2, "part": 2},
        ],
    }
    assert [arc.get("consume", {}).get("predicate") for arc in resolved["arcs"]] == [
        {"cel": 'source == "co2mon"'},
        None,
        {"cel": 'source == "weather"'},
        None,
    ]
    assert all("guard" not in transition for transition in resolved["transitions"])


# --- probes distilled from test_wired*_parser_resolver.py ---

_WIRED_PULSE_SOURCE_DOCUMENT: dict[str, Any] = _corpus_document(
    "10-wired-pulse/wired_pulse.source.json"
)
_WIRED_PULSE_SOURCE_ID: str = cast(str, _WIRED_PULSE_SOURCE_DOCUMENT["sourceId"])
_WIRED_PULSE_SOURCE_TEXT: str = cast(str, _WIRED_PULSE_SOURCE_DOCUMENT["text"])
_WIRED_PULSE_EXPECTED_IR: dict[str, Any] = _corpus_document(
    "10-wired-pulse/wired_pulse.contribution-ir.json"
)
_JSON_COMPOSITION_SOURCE: str = _WIRED_PULSE_SOURCE_TEXT.replace(".petrinet", ".json")

_PAIR_PORT: dict[str, tuple[str, str]] = {
    "pulse_source": ("pulse_out", "produce"),
    "pulse_sink": ("pulse_in", "consume"),
}


def _ir_schema_document() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_IR_SCHEMA_PATH.read_text(encoding="utf-8")))


def _ir_schema_accepts(instance: object) -> bool:
    validator = cast(Any, Draft202012Validator(_ir_schema_document()))
    return cast(bool, validator.is_valid(instance))


def _net(name: str, port_name: str, direction: str, color: str) -> dict[str, Any]:
    return {
        "name": name,
        "places": [
            {
                "name": port_name,
                "accepts": [color],
                "port": {"direction": direction, "type": color},
            }
        ],
        "transitions": [],
        "arcs": [],
    }


def _pair_net(which: str, direction: str, color: str) -> dict[str, Any]:
    """Adapt a corpus constituent net to one port direction/color override."""
    net = deepcopy(_corpus_document(f"10-wired-pulse/{which}.net.json"))
    place_name, arc_field = _PAIR_PORT[which]
    for place in net["places"]:
        if place["name"] == place_name:
            place["accepts"] = [color]
            place["port"] = {"direction": direction, "type": color}
    for arc in net["arcs"]:
        if arc_field == "produce":
            if arc.get(arc_field, {}).get("destination") == place_name:
                arc[arc_field]["type"] = color
        elif arc.get("from", {}).get("place") == place_name:
            arc[arc_field]["type"] = color
    return net


def _write_pair(
    root: Path,
    *,
    source_direction: str = "output",
    sink_direction: str = "input",
    source_color: str = "pulse",
    sink_color: str = "pulse",
) -> None:
    (root / "pulse_source.json").write_text(
        json.dumps(_pair_net("pulse_source", source_direction, source_color)),
        encoding="utf-8",
    )
    (root / "pulse_sink.json").write_text(
        json.dumps(_pair_net("pulse_sink", sink_direction, sink_color)),
        encoding="utf-8",
    )


def test_place_port_fact_elaborates_existing_place() -> None:
    """Given native port syntax, lowering retains the typed port fact."""
    # given: one port declaration that elaborates an existing place
    port_source = """\
net port_source
(pulse_out) -pulse-> [emit]
[emit] handler "emit"
(pulse_out) port output pulse
"""

    # when: the document is lowered without semantic resolution
    port_ir = lower_petrinet_text(port_source, "port-source.petrinet")

    # then: the port fact elaborates an existing place with one accepted color
    assert [
        (fact["kind"], fact["target"], fact["value"])
        for fact in port_ir["contributions"]
        if fact["kind"] == "place.port"
    ] == [
        (
            "place.port",
            {"type": "place", "name": "pulse_out"},
            {"direction": "output", "color": "pulse"},
        )
    ]


def _projected_facts(ir: dict[str, Any]) -> list[tuple[Any, Any, Any]]:
    return [
        (fact["kind"], fact["target"], fact["value"]) for fact in ir["contributions"]
    ]


def test_composition_ir_facts_are_literal() -> None:
    """Given the canonical composition, lowering emits exactly the committed facts."""
    # given: the committed 10-wired-pulse composition source and its committed IR
    # when: the corpus text is lowered without semantic resolution
    composition_ir = lower_petrinet_text(
        _WIRED_PULSE_SOURCE_TEXT, _WIRED_PULSE_SOURCE_ID
    )

    # then: the lowered IR is schema-valid and the ordered composition facts
    # (including their lowered byte-exact spans) match the committed IR
    assert composition_ir["documentKind"] == "composition"
    assert _ir_schema_accepts(composition_ir)
    assert _projected_facts(composition_ir) == _projected_facts(
        _WIRED_PULSE_EXPECTED_IR
    )


@pytest.mark.parametrize(
    ("source", "later_line"),
    [
        (
            """\
net conflicting_port
(pulse_out) -pulse-> [emit]
[emit] handler "emit"
(pulse_out) port output pulse
(pulse_out) port input pulse
""",
            5,
        ),
        (
            """\
composition conflicting_use
use "a.json" as source
use "b.json" as source
""",
            3,
        ),
        (
            """\
composition conflicting_wire
use "a.json" as source
use "b.json" as sink
wire source.(pulse_out) -> sink.(pulse_in)
wire sink.(pulse_in) -> source.(pulse_out)
""",
            5,
        ),
    ],
    ids=["port", "use-alias", "opposite-wire"],
)
def test_conflicting_facts_cite_later_and_first_spans(
    source: str, later_line: int
) -> None:
    """Given contradictory facts, the diagnostic relates later and first authorship."""
    # when: resolution reaches the unequal repeated fact
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "conflicting-wire-fact.petrinet")

    # then: the primary span is later and the related span is the first definition
    diagnostic = raised.value.diagnostic
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (later_line, 1)
    assert len(diagnostic.related) == 1
    assert diagnostic.related[0].span.start.column == 1
    assert diagnostic.related[0].span.start.line < later_line


def test_alias_less_use_reports_zero_width_eof() -> None:
    """Given a use without `as IDENT`, parsing reports zero-width EOF."""
    # given: a composition header followed by the prohibited alias-less inclusion
    source = """\
composition missing_alias
use "pulse_source.petrinet"
"""

    # when: the DSL parser reads the incomplete use fact
    with pytest.raises(PetrinetDslError) as raised:
        lower_petrinet_text(source, "missing-use-alias.petrinet")

    # then: the diagnostic is anchored at zero-width EOF
    assert raised.value.diagnostic.code == "PN101"
    assert raised.value.diagnostic.span.start.line == 3
    assert raised.value.diagnostic.span.start == raised.value.diagnostic.span.end


def test_header_only_composition_requires_a_use() -> None:
    """Given only a header, resolution rejects the empty composition at its source."""
    # when: compilation has neither a loader nor an origin to trigger backend validation
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text("composition empty\n", "empty-composition.petrinet")

    # then: the authored header receives a deterministic semantic diagnostic
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert "at least one use" in diagnostic.message
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (1, 1)


def test_port_color_absent_from_place_is_rejected() -> None:
    """Given a mismatched port color, a port cannot expand a place's color set."""
    # given: topology declares only pulse while the port fact claims receipt
    source = """\
net invalid_port_color
(pulse_out) -pulse-> [emit]
[emit] handler "emit"
(pulse_out) port output receipt
"""

    # when: the net is resolved and delegated to semantic validation
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(source, "invalid-port-color.petrinet")

    # then: the authored port fact is blamed and both colors remain visible
    diagnostic = raised.value.diagnostic
    assert "receipt" in diagnostic.message and "accept" in diagnostic.message.lower()
    assert (diagnostic.span.start.line, diagnostic.span.start.column) == (4, 1)


def test_imported_ir_rejects_host_object_member() -> None:
    """Given imported composition IR, host-only or untyped members are rejected."""
    # given: valid portable composition IR with one illicit resolver shortcut
    ir = lower_petrinet_text(_WIRED_PULSE_SOURCE_TEXT, _WIRED_PULSE_SOURCE_ID)
    malformed = deepcopy(ir)
    malformed["contributions"][1]["value"]["parsedNet"] = Net(
        name="bypass", places=[], transitions=[], arcs=[]
    )

    # when: the imported IR is decoded
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(malformed)

    # then: strict IR shape validation rejects the bypass before resolution
    assert raised.value.diagnostic.code == "PN200"


@pytest.mark.parametrize("mutation", ["foreign-source", "invalid-position"])
def test_imported_wire_endpoint_spans_are_closed(mutation: str) -> None:
    """Imported endpoint provenance must remain a closed, well-formed source span."""
    # given: lowered corpus composition IR with one endpoint-span mutation
    ir = lower_petrinet_text(_WIRED_PULSE_SOURCE_TEXT, _WIRED_PULSE_SOURCE_ID)
    malformed = deepcopy(ir)
    endpoint_span = malformed["contributions"][3]["value"]["from"]["span"]
    if mutation == "foreign-source":
        endpoint_span["source"] = "other.petrinet"
    else:
        endpoint_span["start"]["column"] = 0

    # when: the mutated IR is schema-checked and decoded
    if mutation == "foreign-source":
        assert _ir_schema_accepts(malformed)
    else:
        assert not _ir_schema_accepts(malformed)
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(malformed)

    # then: schema-tolerant mutations are still caught by closed IR decoding
    assert raised.value.diagnostic.code == "PN200"


@pytest.mark.parametrize(
    (
        "source_port",
        "source_direction",
        "source_color",
        "target_direction",
        "target_color",
        "endpoint_lexeme",
    ),
    [
        ('dé"part', "input", "pulse", "input", "pulse", 'source.("dé\\"part")'),
        ('dé"part', "output", "pulse", "output", "pulse", 'sink.("雪")'),
        ("other", "output", "pulse", "input", "pulse", 'source.("dé\\"part")'),
        ('dé"part', "output", "pulse", "input", "receipt", 'sink.("雪")'),
    ],
    ids=["source-direction", "target-direction", "unknown-port", "type"],
)
def test_wire_endpoint_error_spans_use_unicode_lexemes(
    source_port: str,
    source_direction: str,
    source_color: str,
    target_direction: str,
    target_color: str,
    endpoint_lexeme: str,
) -> None:
    """Direction, lookup, and type errors cite parse-derived endpoint provenance."""
    # given: a unicode composition with a custom net loader
    source = """\
composition unicode_wires
use "source.json" as source
use "sink.json" as sink
wire source.("dé\\"part") -> sink.("雪")
"""
    nets = {
        "source.json": _net("source", source_port, source_direction, source_color),
        "sink.json": _net("sink", "雪", target_direction, target_color),
    }

    # when: resolution fails on one wire endpoint
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(
            source, "unicode-wires.petrinet", net_loader=nets.__getitem__
        )

    # then: the diagnostic span is the byte-exact authored unicode lexeme
    start = source.index(endpoint_lexeme)
    end = start + len(endpoint_lexeme)
    line_start = source.rfind("\n", 0, start) + 1
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.span.as_dict() == {
        "source": "unicode-wires.petrinet",
        "start": {
            "byteOffset": len(source[:start].encode("utf-8")),
            "line": 4,
            "column": start - line_start + 1,
        },
        "end": {
            "byteOffset": len(source[:end].encode("utf-8")),
            "line": 4,
            "column": end - line_start + 1,
        },
    }


def test_relative_refs_load_from_explicit_origin(tmp_path: Path) -> None:
    """Given raw composition data, an explicit origin resolves its literal refs."""
    # given: valid constituent JSON files and literal relative references
    _write_pair(tmp_path)
    document = compile_petrinet_text(_JSON_COMPOSITION_SOURCE, "wired_pulse.petrinet")

    # when: the sole composition parser validates and retains loaded nets
    composition = cast(Any, parse_composition)(document, origin=tmp_path)
    merged = merge_composition(composition)

    # then: loading is relative, fusion removes the wired sink endpoint, and
    # JSON stays metadata-free
    assert set(document) == {"name", "nets", "wires"}
    assert set(composition.parsed_nets or {}) == {"source", "sink"}
    place_names = {place.name for place in merged.places}
    assert "source.pulse_out" in place_names
    assert "sink.pulse_in" not in place_names
    assert place_names == {"source.seed", "source.pulse_out", "sink.received"}


def test_relative_ref_without_origin_is_rejected() -> None:
    """Given in-memory relative refs, default loading never guesses the process cwd."""
    # given: a valid composition-shaped document with relative refs
    document = compile_petrinet_text(_WIRED_PULSE_SOURCE_TEXT, "wired_pulse.petrinet")

    # when/then: the parser requires origin or an explicit loader
    with pytest.raises((PetrinetDslError, NetValidationError)) as raised:
        parse_composition(document)
    assert (
        "origin" in str(raised.value).lower() or "relative" in str(raised.value).lower()
    )


@pytest.mark.parametrize(
    ("source_direction", "sink_direction", "source_color", "sink_color", "message"),
    [
        ("input", "input", "pulse", "pulse", "output"),
        ("output", "output", "pulse", "pulse", "input"),
        ("output", "input", "pulse", "receipt", "type"),
    ],
    ids=["source-direction", "target-direction", "type"],
)
def test_dsl_wire_rejects_invalid_loaded_endpoints(
    tmp_path: Path,
    source_direction: str,
    sink_direction: str,
    source_color: str,
    sink_color: str,
    message: str,
) -> None:
    """Given authored wire syntax, loaded endpoint direction and type stay strict."""
    # given: a DSL composition whose referenced JSON nets violate one wire rule
    _write_pair(
        tmp_path,
        source_direction=source_direction,
        sink_direction=sink_direction,
        source_color=source_color,
        sink_color=sink_color,
    )
    document = compile_petrinet_text(_JSON_COMPOSITION_SOURCE, "invalid-wire.petrinet")

    # when/then: semantic composition parsing rejects that exact endpoint rule
    with pytest.raises((PetrinetDslError, NetValidationError)) as raised:
        cast(Any, parse_composition)(document, origin=tmp_path)
    assert message in str(raised.value).lower()


# --- probes distilled from test_speaks*_parser_resolver.py ---

_SOURCE = """\
net speaks_window "Minimal clean-start Speaks window"

(request_in) -speak_req-> [start] -speak_token-> (in_flight)
@in_flight_clear: (in_flight) -speak_token->0 [start]
@judge_clear: (judge_requested) -judge_req->0 [start]
[start] -judge_req-> (judge_requested)

(judge_requested) -judge_req-> [finish] -utterance-> (utterance_out)
@window_close: (in_flight) -speak_token-> [finish]

[start] handler "chip_start@speaks"
[finish] handler "finish@speaks"

(request_in) port input speak_req
(utterance_out) port output utterance

(in_flight) description "Singleton token delimiting one active request"
(in_flight) annotation fusion true
[start] description "Accept a request only when all internal state is clean"
[finish] annotation role "terminal"
@window_close description "Terminally consumes the in-flight token"
@window_close annotation window "close"

marking queued (request_in) <- $demo_request
$demo_request: speak_req {"text": "Status?"}

view window position (request_in) at {"x": 0, "y": 80}
view window position [start] at {"x": 160, "y": 80}
view window position (in_flight) at {"x": 320, "y": 20}
view window position (judge_requested) at {"x": 320, "y": 140}
view window position [finish] at {"x": 500, "y": 80}
view window position (utterance_out) at {"x": 680, "y": 80}
view window route @window_close orthogonal [{"x": 400, "y": 20}, {"x": 500, "y": 20}]
extensions {}
"""

_RESERVED = "petrinet.dsl/v1"


def _document() -> dict[str, Any]:
    return _corpus_document("11-speaks-window/speaks-window.net.json")


def _portable_with_imported_metadata(
    kind: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append one schema-valid metadata fact without requiring its source syntax."""
    portable = lower_petrinet_text(
        """\
net strict_metadata
(p) -tok-> [t]
[t] handler "h"
""",
        "strict-metadata.petrinet",
    )
    values: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
        "documentation.description": (
            {"type": "place", "name": "p"},
            {"text": "A place"},
        ),
        "documentation.annotation": (
            {"type": "place", "name": "p"},
            {
                "key": "fusion",
                "value": {"type": "boolean", "value": True},
            },
        ),
        "metadata.named-marking": (
            {"type": "document"},
            {"name": "queued", "entries": []},
        ),
        "view.position": (
            {"type": "view", "name": "window"},
            {
                "subject": {"type": "place", "name": "p"},
                "position": {
                    "type": "object",
                    "entries": [
                        {"key": "x", "value": {"type": "number", "lexeme": "0"}},
                        {"key": "y", "value": {"type": "number", "lexeme": "0"}},
                    ],
                },
            },
        ),
        "view.route": (
            {"type": "arcHandle", "name": "window_close"},
            {
                "view": {"type": "view", "name": "window"},
                "points": [
                    {
                        "type": "object",
                        "entries": [
                            {"key": "x", "value": {"type": "number", "lexeme": "0"}},
                            {"key": "y", "value": {"type": "number", "lexeme": "0"}},
                        ],
                    }
                ],
            },
        ),
        "document.extensions": (
            {"type": "document"},
            {"extensions": {"type": "object", "entries": []}},
        ),
    }
    target, value = values[kind]
    prior = portable["contributions"][-1]
    ordinal = len(portable["contributions"])
    fact = {
        "id": {
            "source": portable["document"]["id"],
            "statement": ordinal,
            "part": 0,
        },
        "kind": kind,
        "ordinal": ordinal,
        "span": deepcopy(prior["span"]),
        "target": target,
        "value": value,
    }
    portable["contributions"].append(fact)
    return portable, fact


def test_documentation_annotates_net_place_transition_and_both_arc_segments() -> None:
    """Given every metadata target, descriptions and annotations elaborate it."""
    # given: a net with metadata facts on the net, a place, a transition, and one
    # of its two arc segments
    source = """\
net metadata_targets
@flow: (p) -tok-> [t]
[t] -tok-> (q)
[t] handler "h"
net description "The net"
net annotation owner {"team": "speech"}
(p) description "The input"
(p) annotation lane 1
[t] description "The step"
[t] annotation stage true
@flow description "Both arc segments"
@flow annotation trace null
"""

    # when: the source compiles
    actual = compile_petrinet_text(source, "metadata-targets.petrinet")

    # then: fact targets land on the net, place, transition, and first arc segment
    assert actual["description"] == "The net"
    assert actual["annotations"]["owner"] == {"team": "speech"}
    assert actual["annotations"][_RESERVED]["arcHandles"]["flow"]["index"] == 0
    assert actual["places"][0] == {
        "name": "p",
        "accepts": ["tok"],
        "description": "The input",
        "annotations": {"lane": 1},
    }
    assert actual["transitions"][0] == {
        "name": "t",
        "handler": "h",
        "description": "The step",
        "annotations": {"stage": True},
    }
    assert actual["arcs"][0]["description"] == "Both arc segments"
    assert actual["arcs"][0]["annotations"] == {"trace": None}
    # and: the unnamed twin arc segment stays untouched
    assert "description" not in actual["arcs"][1]
    assert "annotations" not in actual["arcs"][1]


def test_stripped_metadata_yields_identical_semantic_graph() -> None:
    """Given only metadata additions, semantic identities and colors stay unchanged."""
    # given: the source with all metadata removed but identical semantic declarations
    semantic_source = _SOURCE[: _SOURCE.index("\n(in_flight) description")] + "\n"

    # when: both forms resolve
    enriched = compile_petrinet_text(_SOURCE, "enriched-speaks.petrinet")
    plain = compile_petrinet_text(semantic_source, "plain-speaks.petrinet")

    # then: recursively removing documentation/full-document fields yields the
    # same semantic graph; an absent marking and an explicit empty marking are
    # equivalent at the engine boundary.
    stripped = deepcopy(enriched)
    plain_core = deepcopy(plain)
    for candidate in (stripped, plain_core):
        candidate.pop("description", None)
        candidate.pop("annotations", None)
        if not candidate.get("initialMarking"):
            candidate.pop("initialMarking", None)
        for collection in ("places", "transitions", "arcs"):
            for item in candidate[collection]:
                item.pop("description", None)
                item.pop("annotations", None)
    assert stripped == plain_core


def test_repeated_metadata_facts_collapse_and_conflicts_cite_first() -> None:
    """Given repeated annotation/position facts, equality collapses and inequality cites both."""
    # given: identical duplicated annotation and position facts
    equal = _SOURCE.replace(
        "(in_flight) annotation fusion true\n",
        "(in_flight) annotation fusion true\n(in_flight) annotation fusion true\n",
    ).replace(
        'view window position (request_in) at {"x": 0, "y": 80}\n',
        'view window position (request_in) at {"x": 0, "y": 80}\n'
        'view window position (request_in) at {"x": 0, "y": 80}\n',
    )

    # then: equal facts collapse into one
    assert compile_petrinet_text(equal, "equal-metadata.petrinet") == _document()

    # given: a conflicting duplicate position fact
    conflict = equal.replace(
        'view window position (request_in) at {"x": 0, "y": 80}\n'
        'view window position (request_in) at {"x": 0, "y": 80}\n',
        'view window position (request_in) at {"x": 0, "y": 80}\n'
        'view window position (request_in) at {"x": 1, "y": 80}\n',
    )

    # when: the conflicting source compiles
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(conflict, "conflicting-metadata.petrinet")

    # then: the diagnostic names the conflict and cites the first declaration
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.message == (
        "conflicting position facts for place (request_in) in view 'window'"
    )
    assert len(diagnostic.related) == 1
    assert diagnostic.related[0].message == "first position was declared here"
    assert diagnostic.related[0].span.start.line < diagnostic.span.start.line


@pytest.mark.parametrize(
    ("kind", "field", "value", "message"),
    [
        (
            "documentation.description",
            "format",
            "markdown",
            "invalid documentation description contribution",
        ),
        (
            "documentation.annotation",
            "semantic",
            True,
            "invalid documentation annotation contribution",
        ),
        (
            "metadata.named-marking",
            "initial",
            True,
            "invalid named marking contribution",
        ),
        (
            "view.position",
            "rank",
            1,
            "invalid view position contribution",
        ),
        (
            "view.route",
            "style",
            "spline",
            "invalid view route contribution",
        ),
        (
            "document.extensions",
            "objects",
            [],
            "invalid document extensions contribution",
        ),
    ],
)
def test_imported_metadata_ir_rejects_unknown_value_fields(
    kind: str, field: str, value: Any, message: str
) -> None:
    """Given imported IR, unknown fields cannot smuggle semantics past lowering."""
    # given: one schema-valid imported metadata fact with an unknown value field
    portable, fact = _portable_with_imported_metadata(kind)
    fact["value"][field] = value

    # when: the IR resolves
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(portable)

    # then: resolution rejects the closed kind at the fact's span
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == message
    assert diagnostic.span.as_dict() == fact["span"]


def test_imported_extensions_value_must_be_tagged_object() -> None:
    """Given imported extensions IR, a scalar cannot become the opaque carrier."""
    # given: an imported extensions fact whose value is a tagged scalar
    portable, fact = _portable_with_imported_metadata("document.extensions")
    fact["value"]["extensions"] = {"type": "string", "value": "not-an-object"}

    # when: the IR resolves
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(portable)

    # then: only a tagged object value is acceptable
    assert raised.value.diagnostic.code == "PN200"
    assert raised.value.diagnostic.message == "invalid document extensions contribution"
    assert raised.value.diagnostic.span.as_dict() == fact["span"]


def test_emit_preserves_plain_annotations_and_omits_v1() -> None:
    """Given unrelated annotations, emission preserves them and invents no DSL layer."""
    # given: a plain-core document with ordinary annotations and an empty marking
    document = {
        "name": "plain_metadata",
        "description": "Ordinary documentation",
        "places": [
            {
                "name": "p",
                "accepts": ["tok"],
                "annotations": {"owner": {"team": "speech"}},
            },
            {"name": "q", "accepts": ["tok"]},
        ],
        "transitions": [{"name": "t", "handler": "h"}],
        "arcs": [
            {
                "from": {"place": "p"},
                "to": {"transition": "t"},
                "consume": {"type": "tok"},
            },
            {
                "from": {"transition": "t"},
                "to": {"place": "q"},
                "produce": {"type": "tok", "destination": "q"},
            },
        ],
        "initialMarking": {},
        "annotations": {"owner": "docs"},
    }

    # when: the document emits and recompiles
    emitted = emit_petrinet(document)
    reparsed = compile_petrinet_text(emitted, "plain-metadata.petrinet")

    # then: the round trip is lossless and no reserved layer is invented
    assert reparsed == document
    assert _RESERVED not in reparsed["annotations"]
    assert "arcHandles" not in emitted
    assert "marking queued" not in emitted
    assert "view " not in emitted


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "index",
            99,
            "annotations['petrinet.dsl/v1'].arcHandles.window_close.index 99 is outside arcs[0:8]",
        ),
        (
            "index",
            0,
            "annotations['petrinet.dsl/v1'].arcHandles.window_close.fingerprint does not match arcs[0]",
        ),
    ],
    ids=["index-out-of-range", "index-first-no-search"],
)
def test_emit_validates_arc_handle_index_before_fingerprint(
    field: str, value: Any, message: str
) -> None:
    """Given stale reserved data, emission rejects its exact path without retargeting."""
    # given: a resolved document with an inconsistent arcHandle entry
    document = deepcopy(_document())
    handle = document["annotations"][_RESERVED]["arcHandles"]["window_close"]
    if field == "index":
        handle[field] = value
    else:
        handle["fingerprint"][field] = value

    # when/then: emission rejects the exact arc and path, never retargeting or searching
    pattern = "^" + message.replace("[", "\\[").replace("]", "\\]") + "$"
    with pytest.raises(ValueError, match=pattern):
        emit_petrinet(document)


def test_arc_handle_targets_named_arc_not_structural_twin() -> None:
    """Given duplicate identical arcs, metadata picks the arc the handle names."""
    # given: two structurally equal arcs, with metadata declaring only the second
    document = compile_petrinet_text(
        """\
net duplicate_arcs
@first: (p) -tok-> [t]
@second: (p) -tok-> [t]
[t] handler "h"
@second description "the second arc"
""",
        "duplicate-arcs.petrinet",
    )

    # then: the handle resolves to the named arc, not the structural twin
    assert document["annotations"][_RESERVED]["arcHandles"]["second"]["index"] == 1
    assert "description" not in document["arcs"][0]
    assert document["arcs"][1]["description"] == "the second arc"


def test_multi_segment_arc_handle_rejects_reconstructable_metadata() -> None:
    """Given a multi-segment arc handle carrying metadata, compilation rejects it."""
    # given: a two-segment arc handle that is reconstructable from its segments
    # when/then: metadata cannot attach to an ambiguous arc identity
    with pytest.raises(
        PetrinetDslError,
        match="metadata arc handle '@flow' must identify exactly one arc",
    ):
        compile_petrinet_text(
            """\
net multi_arc_metadata
@flow: (p) -tok-> [t] -tok-> (q)
[t] handler "h"
@flow description "ambiguous reconstruction"
""",
            "multi-arc-metadata.petrinet",
        )


def test_relative_view_position_roundtrips() -> None:
    """Given one authored relative position fact, payload and emission keep it."""
    # given: a minimal net with one absolute anchor and one relative fact
    source = """\
net relative_window

(seed) -pulse-> [emit] -pulse-> (out)

view window position (seed) at {"x": 3, "y": 4}
view window position (out) relative (seed) + {"x": 20, "y": -20}
"""
    # when: the source compiles
    document = compile_petrinet_text(source, "speaks_window.relative.petrinet")
    # then: the payload keeps the from-string, render-time shape
    positions = document["annotations"][_RESERVED]["views"]["window"]["positions"]
    assert positions["place:out"] == {
        "from": "place:seed",
        "delta": {"x": 20, "y": -20},
    }
    # and: canonical emission renders the declaration and recompiles equal
    emitted = emit_petrinet(document)
    assert "view window position (out) relative (seed) + " in emitted
    assert "view window position (seed) at " in emitted
    assert compile_petrinet_text(emitted, "relative-fixed-point.petrinet") == document


def test_subject_cannot_mix_absolute_and_relative_positions() -> None:
    """Given one view subject positioned absolutely and relatively, resolution conflicts."""
    # given: an authored view that positions one subject twice, differently
    source = (
        _SOURCE
        + "view window position (utterance_out) relative (request_in) + "
        + '{"x": 1, "y": 0}\n'
    )
    # when: the source compiles
    # then: the resolver names the conflict and points at the first fact
    with pytest.raises(PetrinetDslError, match="conflicting position facts"):
        compile_petrinet_text(source, "relative-conflict.petrinet")


def test_relative_position_base_must_be_declared() -> None:
    """Given a relative fact with an undeclared base, resolution rejects it."""
    # given: a relative base naming a place the net never declares
    source = """\
net relative_window

(seed) -pulse-> [emit] -pulse-> (out)

view window position (seed) at {"x": 3, "y": 4}
view window position (out) relative (ghost) + {"x": 1, "y": 0}
"""
    # when/then: the resolver rejects it like any unknown presentation target
    with pytest.raises(
        PetrinetDslError, match="relative base references unknown place 'ghost'"
    ):
        compile_petrinet_text(source, "relative-unknown-base.petrinet")


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            {"from": "place:ghost", "delta": {"x": 1, "y": 0}},
            "references unknown place 'ghost'",
        ),
        (
            {"from": "ghost", "delta": {"x": 1, "y": 0}},
            "must use from: place:<name>, "
            "place:<name>@transition:<name>, or transition:<name>",
        ),
        (
            {"from": "place:request_in", "delta": {"x": 1}},
            "delta is invalid",
        ),
        ({"from": "place:request_in"}, "is invalid"),
        (
            {
                "from": "place:request_in",
                "delta": {"x": 1, "y": 0},
                "anchor": "left",
            },
            "has unsupported field 'anchor'",
        ),
        (
            {"from": "place:request_in", "delta": {"x": float("inf"), "y": 0}},
            "delta is invalid",
        ),
    ],
)
def test_emit_validates_relative_position_payloads(
    entry: dict[str, Any], message: str
) -> None:
    """Given one malformed relative payload entry, emission rejects it by message."""
    # given: a resolved document with one relative payload entry
    document = deepcopy(_document())
    view = document["annotations"][_RESERVED]["views"]["window"]
    view["positions"]["place:utterance_out"] = entry

    # when/then: emission rejects the malformed entry by message
    with pytest.raises(ValueError, match=message):
        emit_petrinet(document)


@pytest.mark.parametrize(
    ("member", "value"), [("splines", "wavy"), ("detail", "verbose"), ("detail", 1)]
)
def test_emit_validates_view_style_payloads(member: str, value: object) -> None:
    """Given an unknown view style value, emission rejects it by path."""
    # given: a resolved document whose view carries the bad value
    document = deepcopy(_document())
    document["annotations"][_RESERVED]["views"]["window"][member] = value

    # when/then: emission names the member
    with pytest.raises(ValueError, match=rf"views\.window\.{member} is invalid"):
        emit_petrinet(document)


@pytest.mark.parametrize(
    ("subject", "entry", "message"),
    [
        ("place:ghost", {"note": "x"}, "references unknown place 'ghost'"),
        ("wire:request_in", {"note": "x"}, "must target place:, transition:"),
        ("place:request_in", {"summary": "x"}, "has unsupported field 'summary'"),
        ("place:request_in", {"highlight": True}, "highlight is invalid"),
        ("place:request_in", {}, "must be a non-empty object"),
        ("color:ghost", {"quiet": True}, "references unknown color 'ghost'"),
        ("place:request_in", {"beside": {"side": "up"}}, "beside is invalid"),
        ("place:request_in", {"beside": {}}, "needs a place annotated fusion true"),
        ("color:speak_req", {"show": []}, "show must be a non-empty list"),
        ("color:speak_req", {"show": ["a..b"]}, "show must be a non-empty list"),
        ("color:speak_req", {"show": ["id", "id"]}, "show must be a non-empty list"),
        ("color:speak_req", {"quiet": False}, "quiet must be true"),
    ],
)
def test_emit_validates_decoration_payloads(
    subject: str, entry: dict[str, Any], message: str
) -> None:
    """Given one malformed decoration entry, emission rejects it by message."""
    # given: a resolved document carrying the bad decoration
    document = deepcopy(_document())
    document["annotations"][_RESERVED]["decorations"] = {subject: entry}

    # when/then: emission rejects it by message
    with pytest.raises(ValueError, match=message):
        emit_petrinet(document)


def test_emit_writes_show_beside_quiet_for_one_color() -> None:
    """Given a color that is both quiet and shown, emission writes both facts."""
    # given: a resolved document whose color carries quiet and show
    document = deepcopy(_document())
    document["annotations"][_RESERVED]["decorations"] = {
        "color:speak_req": {"quiet": True, "show": ["id", "owner.name"]}
    }

    # when: the document emits
    emitted = emit_petrinet(document)

    # then: each fact has its own line, and the source compiles back unchanged
    assert "decorate color speak_req quiet\n" in emitted
    assert 'decorate color speak_req show "id" "owner.name"\n' in emitted
    assert compile_petrinet_text(emitted, "shown.petrinet") == document


@pytest.mark.parametrize(
    "fields",
    [[], ["a..b"], [".a"], ["a."], [""], ["id", "id"], [1]],
)
def test_imported_show_ir_rejects_invalid_field_lists(fields: list[Any]) -> None:
    """Given imported IR, a show fact needs distinct, non-empty dotted paths."""
    # given: the decorations case IR with its show fact's fields replaced
    portable = deepcopy(
        _corpus_document("19-decorations/decorations.contribution-ir.json")
    )
    fact = next(
        contribution
        for contribution in portable["contributions"]
        if contribution["kind"] == "decoration.show"
    )
    fact["value"]["fields"] = fields

    # when: the IR resolves
    with pytest.raises(PetrinetDslError) as raised:
        resolve_contribution_ir(portable)

    # then: resolution rejects the closed kind at the fact's span
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN200"
    assert diagnostic.message == "invalid show decoration contribution"
    assert diagnostic.span.as_dict() == fact["span"]


def test_show_keyword_stays_usable_as_a_name() -> None:
    """Given a place and a color named show, the keyword does not steal them."""
    # given: a net that uses show as a place name and a color name
    text = "net shown\n(show) -show-> [start]\n"

    # when: the net compiles
    document = compile_petrinet_text(text, "shown.petrinet")

    # then: both names survive
    assert document["places"] == [{"name": "show", "accepts": ["show"]}]


def test_extensions_carry_opaque_future_data_losslessly() -> None:
    """Given nested future extension data, canonical DSL preserves it losslessly."""
    # given: a resolved document carrying arbitrary nested extensions in the
    # reserved layer
    document = deepcopy(_document())
    extensions = {
        "vendor.example/layout": {
            "enabled": True,
            "layers": [1, "two", None, {"nested": 3.5}],
        }
    }
    document["annotations"][_RESERVED]["extensions"] = extensions

    # when: the document emits and recompiles
    emitted = emit_petrinet(document)
    reparsed = compile_petrinet_text(emitted, "opaque-extensions.petrinet")

    # then: extensions survive the round trip byte-for-byte
    assert reparsed == document
    assert reparsed["annotations"][_RESERVED]["extensions"] == extensions


# --- probes distilled from test_reading-hour*_parser_resolver.py ---

# EXTRA-IMPORT: from velocitron_engine import Wire
# EXTRA-IMPORT: from typing import Callable
# Adapted probes from implementations/python/tests/test_reading_hour_parser_resolver.py
# (corpus case 12-reading-hour; DSL text and net JSON derived from corpus
# .source.json / .net.json artifacts since the legacy examples/ fixtures have
# no corpus sibling for those file formats).

_READING_HOUR_DIR = "12-reading-hour-fragment"

_READING_HOUR_COMPOSITION_SOURCE = _corpus_document(
    f"{_READING_HOUR_DIR}/reading_hour.source.json"
)
_CADENCE_SOURCE = _corpus_document(f"{_READING_HOUR_DIR}/reading_cadence.source.json")
_CURATE_SOURCE = _corpus_document(f"{_READING_HOUR_DIR}/reading_pick.source.json")
_SPEAKS_SOURCE = _corpus_document(f"{_READING_HOUR_DIR}/reading_voice.source.json")

_CADENCE_NET = _corpus_document(f"{_READING_HOUR_DIR}/reading_cadence.net.json")
_CURATE_NET = _corpus_document(f"{_READING_HOUR_DIR}/reading_pick.net.json")
_SPEAKS_NET = _corpus_document(f"{_READING_HOUR_DIR}/reading_voice.net.json")

_READING_HOUR_COMPOSITION_DOC = _corpus_document(
    f"{_READING_HOUR_DIR}/reading_hour.composition.json"
)


def _write_dsl_composition_tree(tmp_path: Path) -> Path:
    """Write the corpus DSL composition and its three referenced nets to tmp_path."""
    # given: the corpus source documents for the composition and its nets
    for name, art in [
        ("reading_hour", _READING_HOUR_COMPOSITION_SOURCE),
        ("reading_cadence", _CADENCE_SOURCE),
        ("reading_pick", _CURATE_SOURCE),
        ("reading_voice", _SPEAKS_SOURCE),
    ]:
        (tmp_path / f"{name}.petrinet").write_text(
            cast(str, art["text"]), encoding="utf-8"
        )
    return tmp_path


def _write_json_composition_tree(tmp_path: Path) -> Path:
    """Write the JSON composition (legacy `.json` refs) and net documents to tmp_path."""
    # given: the corpus composition document (refs end `.petrinet`)
    composed = deepcopy(_READING_HOUR_COMPOSITION_DOC)
    for item in composed["nets"]:
        item["ref"] = item["ref"].replace(".petrinet", ".json")
    (tmp_path / "reading_hour.json").write_text(json.dumps(composed), encoding="utf-8")
    # and: the corpus net documents under their legacy reference names
    for name, art in [
        ("reading_cadence", _CADENCE_NET),
        ("reading_pick", _CURATE_NET),
        ("reading_voice", _SPEAKS_NET),
    ]:
        (tmp_path / f"{name}.json").write_text(json.dumps(art), encoding="utf-8")
    return tmp_path


def _dsl_net_loader(root: Path) -> Callable[[str], dict[str, Any]]:
    """Build a loader compiling referenced `.petrinet` files relative to root."""

    def load(ref: str) -> dict[str, Any]:
        path = root / ref
        return compile_petrinet_text(path.read_text(encoding="utf-8"), str(path))

    return load


def _arc_shape_probes(arc: Arc) -> tuple[str, str, str, str]:
    if arc.consume is not None:
        assert arc.from_place is not None and arc.to_transition is not None
        return (
            arc.from_place,
            arc.to_transition,
            arc.consume.mode,
            arc.consume.type,
        )
    assert arc.produce is not None
    assert arc.from_transition is not None and arc.to_place is not None
    return (
        arc.from_transition,
        arc.to_place,
        "produce",
        arc.produce.type,
    )


def _merged_from_dsl(tmp_path: Path) -> Net:
    # given: the composition DSL plus referenced net DSL files on disk
    root = _write_dsl_composition_tree(tmp_path)
    # when: the composition is parsed through the DSL loader
    composition = parse_composition(
        compile_petrinet_text(
            cast(str, _READING_HOUR_COMPOSITION_SOURCE["text"]),
            str(root / "reading_hour.petrinet"),
        ),
        origin=root,
        net_loader=_dsl_net_loader(root),
    )
    # then: merge yields the semantic model
    return merge_composition(composition)


def _merged_from_json(tmp_path: Path) -> Net:
    # given: the legacy JSON composition (refs `.json`) plus net JSON on disk
    root = _write_json_composition_tree(tmp_path)
    # when: the composition is parsed with the default filesystem loader
    composition = parse_composition(
        cast(
            dict[str, Any],
            json.loads((root / "reading_hour.json").read_text(encoding="utf-8")),
        ),
        origin=root,
    )
    # then: merge yields the semantic model
    return merge_composition(composition)


def test_composition_loader_resolves_refs_and_populates_parsed_nets_in_alias_order(
    tmp_path: Path,
) -> None:
    """The DSL loader resolves each reference and fills parsed_nets in alias order."""
    # given: the compiled composition document and its referenced net content
    document = compile_petrinet_text(
        cast(str, _READING_HOUR_COMPOSITION_SOURCE["text"]),
        str(_READING_HOUR_DIR + "/reading_hour.petrinet"),
    )
    assert document == _READING_HOUR_COMPOSITION_DOC
    # and: the referenced net files on disk in tmp_path
    root = _write_dsl_composition_tree(tmp_path)

    # when: the composition is parsed through the DSL net loader
    resolved = parse_composition(
        document, origin=root, net_loader=_dsl_net_loader(root)
    )

    # then: parsed_nets is populated in alias resolution order
    parsed_nets = resolved.parsed_nets
    assert parsed_nets is not None
    assert list(parsed_nets) == ["cadence", "curate", "speaks"]
    assert parsed_nets["cadence"] == parse_net(
        compile_petrinet_text(
            cast(str, _CADENCE_SOURCE["text"]),
            str(root / "reading_cadence.petrinet"),
        )
    )
    assert parsed_nets["cadence"] == parse_net(_CADENCE_NET)
    assert parsed_nets["curate"] == parse_net(_CURATE_NET)
    assert parsed_nets["speaks"] == parse_net(_SPEAKS_NET)
    # and: both wires resolve to their exact typed endpoints
    assert resolved.wires == [
        Wire(
            from_net="cadence",
            from_port="refresh_due_out",
            to_net="curate",
            to_port="refresh_due_in",
        ),
        Wire(
            from_net="curate",
            from_port="speak_request",
            to_net="speaks",
            to_port="request_in",
        ),
    ]


def test_merge_has_exact_fusions_topology_and_reexposed_output(tmp_path: Path) -> None:
    """Two wires fuse places directly while the sole unwired output stays exposed."""
    # given: the DSL-origin composition merged through its loader
    merged = _merged_from_dsl(tmp_path)

    # then: the merged place order pins the fusion decisions
    assert [place.name for place in merged.places] == [
        "cadence.tick_latch",
        "cadence.clock",
        "speaks.in_flight",
        "speaks.work",
        "speaks.utterance_out",
        "cadence.refresh_due_out",
        "curate.speak_request",
    ]
    assert [transition.name for transition in merged.transitions] == [
        "cadence.on_tick",
        "curate.curate",
        "speaks.start",
        "speaks.finish",
    ]
    assert len(merged.arcs) == 14
    assert [_arc_shape_probes(arc) for arc in merged.arcs] == [
        ("cadence.tick_latch", "cadence.on_tick", "consume", "tick_latch"),
        ("cadence.on_tick", "cadence.tick_latch", "produce", "tick_latch"),
        ("cadence.clock", "cadence.on_tick", "read", "clock"),
        ("cadence.on_tick", "cadence.refresh_due_out", "produce", "refresh_due"),
        ("cadence.refresh_due_out", "curate.curate", "consume", "refresh_due"),
        ("curate.curate", "curate.speak_request", "produce", "speak_req"),
        ("curate.speak_request", "speaks.start", "consume", "speak_req"),
        ("speaks.start", "speaks.in_flight", "produce", "speak_token"),
        ("speaks.in_flight", "speaks.start", "inhibit", "speak_token"),
        ("speaks.work", "speaks.start", "inhibit", "speak_work"),
        ("speaks.start", "speaks.work", "produce", "speak_work"),
        ("speaks.work", "speaks.finish", "consume", "speak_work"),
        ("speaks.finish", "speaks.utterance_out", "produce", "utterance"),
        ("speaks.in_flight", "speaks.finish", "consume", "speak_token"),
    ]

    # and: fused places lose their ports and carry the fusion annotation
    places = {place.name: place for place in merged.places}
    for fused_name in ["cadence.refresh_due_out", "curate.speak_request"]:
        assert places[fused_name].port is None
        assert (places[fused_name].annotations or {}).get("fusion") is True
    assert "curate.refresh_due_in" not in places
    assert "speaks.request_in" not in places
    assert places["speaks.utterance_out"].port is not None
    assert (
        places["speaks.utterance_out"].port.direction,
        places["speaks.utterance_out"].port.type,
    ) == ("output", "utterance")

    # and: the surviving timer is rewritten to fused names
    timer = merged.transitions[0].timer
    assert timer is not None
    assert (timer.clock, timer.bind) == (
        "cadence.clock",
        {"latch": "cadence.tick_latch"},
    )
    assert merged.initial_marking is not None
    assert set(merged.initial_marking) == {"cadence.clock", "cadence.tick_latch"}


def test_dsl_and_json_origins_merge_to_the_same_semantic_model(tmp_path: Path) -> None:
    """Independent authoring forms preserve ports, modes, timers, and opaque refs."""
    # given: the composition authored both in DSL and in legacy JSON
    dsl_merged = _merged_from_dsl(tmp_path)
    json_merged = _merged_from_json(tmp_path)

    # then: both origins yield the identical merged semantic model
    assert dsl_merged == json_merged
    # and: handler strings survive the merge untouched
    assert [transition.handler for transition in dsl_merged.transitions] == [
        "on_tick@cadence",
        "curate@curate",
        "start@speaks",
        "finish@speaks",
    ]
