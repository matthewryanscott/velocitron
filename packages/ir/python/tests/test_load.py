"""Source-tree tests for the contribution-IR shape loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from velocitron_ir import (
    CONTRIBUTION_IR_FORMAT,
    ContributionIrShapeError,
    contribution_ir_schema_text,
    load_contribution_ir,
    load_contribution_ir_text,
)

_PACKAGES = Path(__file__).resolve().parents[3]
_FIXTURES = _PACKAGES / "ir" / "fixtures"
_CORPUS = _PACKAGES / "spec" / "conformance" / "petrinet"
_CANONICAL_SCHEMA = _PACKAGES / "spec" / "petrinet-contribution-ir.schema.json"


def _document(name: str) -> dict[str, object]:
    loaded = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _cel_strings(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "cel" and isinstance(item, str):
                found.append(item)
            else:
                found.extend(_cel_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_cel_strings(item))
    return found


def test_load_contribution_ir_returns_a_detached_net_document() -> None:
    # given: a minimal net contribution IR document
    document = _document("minimal-net.contribution-ir.json")
    # when: the shape loader validates it
    loaded = load_contribution_ir(document)
    # then: the wire document is returned unchanged and detached from the input
    assert loaded == document
    assert loaded is not document
    assert loaded["format"] == CONTRIBUTION_IR_FORMAT
    assert loaded["version"] == 1
    assert loaded["documentKind"] == "net"
    document["document"] = {"id": "mutated.petrinet"}
    assert loaded["document"]["id"] == "example.petrinet"


def test_load_contribution_ir_keeps_a_composition_unmerged() -> None:
    # given: a composition contribution IR document with one header fact
    document = _document("minimal-composition.contribution-ir.json")
    # when: the shape loader validates it
    loaded = load_contribution_ir(document)
    # then: the result is still the IR document, with no merged net members
    assert loaded["documentKind"] == "composition"
    assert set(loaded) == {
        "contributions",
        "document",
        "documentKind",
        "format",
        "version",
    }
    assert loaded["contributions"][0]["kind"] == "document.composition-header"


def test_load_contribution_ir_keeps_cel_text_as_a_string() -> None:
    # given: a produce-cel contribution whose CEL source is not a compiled plan
    document = _document("cel-string.contribution-ir.json")
    # when: the shape loader validates it
    loaded = load_contribution_ir(document)
    # then: the CEL source is the same string on the returned contribution
    assert loaded["contributions"][0]["value"] == {"cel": "token.n + 1"}


def test_load_contribution_ir_accepts_duplicate_ordinals() -> None:
    # given: two contributions that share an ordinal, which the wire schema allows
    document = _document("duplicate-ordinals.contribution-ir.json")
    # when: the shape loader validates it
    loaded = load_contribution_ir(document)
    # then: both contributions are kept; ordinal contiguity is a resolver rule
    assert [item["ordinal"] for item in loaded["contributions"]] == [0, 0]


def test_load_contribution_ir_rejects_an_unsupported_format_before_schema() -> None:
    # given: a document whose format is not the contribution-IR identifier
    document = _document("minimal-net.contribution-ir.json")
    document["format"] = "velocitron.petrinet/other"
    document["contributions"] = "not-an-array"
    # when: the shape loader reads it
    with pytest.raises(ContributionIrShapeError) as caught:
        load_contribution_ir(document)
    # then: the format gate fails before the schema reports the contributions member
    assert str(caught.value) == "unsupported contribution IR format or version"
    assert caught.value.issues == ()


def test_load_contribution_ir_rejects_a_boolean_version() -> None:
    # given: a document whose version is the JSON boolean true
    document = _document("minimal-net.contribution-ir.json")
    document["version"] = True
    # when/then: true is not integer version 1
    with pytest.raises(
        ContributionIrShapeError, match="unsupported contribution IR format"
    ):
        load_contribution_ir(document)


def test_load_contribution_ir_reports_schema_issue_pointers() -> None:
    # given: a net document whose only contribution kind is not in the closed set
    document = _document("minimal-net.contribution-ir.json")
    contributions = document["contributions"]
    assert isinstance(contributions, list)
    contribution = contributions[0]
    assert isinstance(contribution, dict)
    contribution["kind"] = "nope"
    # when: the shape loader validates it
    with pytest.raises(ContributionIrShapeError) as caught:
        load_contribution_ir(document)
    # then: the failure is a schema mismatch and names the kind pointer
    assert (
        str(caught.value) == "contribution IR document does not match the wire schema"
    )
    assert any(
        issue.instance_path == "/contributions/0/kind" for issue in caught.value.issues
    )


def test_load_contribution_ir_rejects_non_objects() -> None:
    # given: JSON values that are not objects
    # when/then: each one fails the object gate
    for value in ([], "net", 1, None, True):
        with pytest.raises(ContributionIrShapeError, match="must be a JSON object"):
            load_contribution_ir(value)


def test_load_contribution_ir_text_parses_json() -> None:
    # given: the minimal net fixture as text
    text = (_FIXTURES / "minimal-net.contribution-ir.json").read_text(encoding="utf-8")
    # when: the text loader parses and validates it
    loaded = load_contribution_ir_text(text)
    # then: the document kind is net, and non-JSON text fails closed
    assert loaded["documentKind"] == "net"
    with pytest.raises(ContributionIrShapeError, match="not JSON"):
        load_contribution_ir_text("{")
    with pytest.raises(TypeError, match="must be a str"):
        load_contribution_ir_text(b"{}")


def test_schema_text_matches_the_canonical_spec_schema() -> None:
    # given: the canonical contribution-IR schema in packages/spec
    # when: the loader reports the schema it will use
    # then: a checkout reads that canonical file
    assert contribution_ir_schema_text() == _CANONICAL_SCHEMA.read_text(
        encoding="utf-8"
    )
    assert (
        '"$id": "https://velocitron.dev/spec/petrinet-contribution-ir.schema.json"'
        in (contribution_ir_schema_text())
    )


def test_load_contribution_ir_accepts_the_conformance_corpus() -> None:
    # given: every contribution-IR document in the petrinet conformance corpus
    paths = sorted(_CORPUS.rglob("*.contribution-ir.json"))
    assert paths
    # when: the shape loader validates each document
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        loaded = load_contribution_ir(document)
        # then: the document round-trips, including every CEL source string
        assert loaded == document
        assert _cel_strings(loaded) == _cel_strings(document)
        assert loaded["format"] == CONTRIBUTION_IR_FORMAT
        assert loaded["documentKind"] in {"net", "composition"}
