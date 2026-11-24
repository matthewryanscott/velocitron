"""Source-tree tests for the .petrinet syntax parser."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from velocitron_grammar import (
    GRAMMAR_FILE_NAME,
    PetrinetParseError,
    grammar_text,
    parse_petrinet,
)

_GRAMMAR_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _GRAMMAR_ROOT / "fixtures"
_CANONICAL = _GRAMMAR_ROOT / GRAMMAR_FILE_NAME
_PACKAGED_COPY = (
    _GRAMMAR_ROOT / "python" / "src" / "velocitron_grammar" / GRAMMAR_FILE_NAME
)
_EXAMPLES = _GRAMMAR_ROOT.parents[1] / "examples" / "capability-ladder"


def _text(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_parse_petrinet_reads_a_net_document() -> None:
    # given: a net document with a header, a description, and one chain
    text = _text("net.petrinet")
    # when: the grammar package parses it
    parsed = parse_petrinet(text, source_name="net.petrinet")
    # then: the document is a net, and the result is not contribution IR
    assert parsed.kind == "net"
    assert parsed.name == "coin_deposit"
    assert parsed.source_name == "net.petrinet"
    assert type(parsed.tree).__name__ == "DocumentContext"
    assert not hasattr(parsed, "contributions")


def test_parse_petrinet_reads_a_composition_document() -> None:
    # given: a composition document with use and wire facts
    text = _text("composition.petrinet")
    # when: the grammar package parses it
    parsed = parse_petrinet(text, source_name="composition.petrinet")
    # then: the document is still a composition, with no merged net
    assert parsed.kind == "composition"
    assert parsed.name == "wired_pulse"
    assert type(parsed.tree).__name__ == "DocumentContext"
    assert not hasattr(parsed, "contributions")


def test_parse_petrinet_names_a_headerless_document_unnamed() -> None:
    # given: a net body with no net header
    text = _text("headerless.petrinet")
    # when: the grammar package parses it
    parsed = parse_petrinet(text)
    # then: the document is a net whose effective name is unnamed
    assert parsed.kind == "net"
    assert parsed.name == "unnamed"
    assert parsed.source_name == "<memory>"


def test_parse_petrinet_decodes_a_quoted_header_name() -> None:
    # given: net and composition headers whose names are JSON strings
    # when: the grammar package parses each document
    net = parse_petrinet(_text("quoted-net.petrinet"))
    composition = parse_petrinet(_text("quoted-composition.petrinet"))
    # then: the quotes are not part of the name
    assert net.kind == "net"
    assert net.name == "coin-deposit"
    assert composition.kind == "composition"
    assert composition.name == "wired-pulse"


def test_parse_petrinet_accepts_crlf_and_an_empty_net() -> None:
    # given: a net header written with CRLF, and an empty document
    crlf = "net coin_deposit\r\n(coin_slot) -> [accept_coin]\r\n"
    # when: the grammar package parses both
    parsed = parse_petrinet(crlf)
    empty = parse_petrinet("")
    # then: CRLF is a net, and empty source is an unnamed net
    assert parsed.kind == "net"
    assert parsed.name == "coin_deposit"
    assert empty.kind == "net"
    assert empty.name == "unnamed"


def test_parse_petrinet_rejects_a_syntax_error_without_a_tree() -> None:
    # given: text that is not a .petrinet document
    # when: the grammar package parses it
    with pytest.raises(PetrinetParseError) as caught:
        parse_petrinet("sentinel")
    # then: the failure is the first syntax error, at the sentinel
    assert caught.value.line == 1
    assert caught.value.column == 1
    assert str(caught.value)


def test_parse_petrinet_rejects_a_bom_and_a_bare_cr() -> None:
    # given: source text the grammar does not accept
    # when/then: each form fails before a document is returned
    for text in (
        "\ufeffnet coin_deposit\n",
        "net coin_deposit\r(a) -> [b]\n",
        "\ud800",
    ):
        with pytest.raises(PetrinetParseError, match="BOM or bare CR") as caught:
            parse_petrinet(text)
        assert caught.value.line == 1
        assert caught.value.column == 1


def test_parse_petrinet_rejects_a_non_string() -> None:
    # given: a bytes value
    # when/then: the parser requires text
    with pytest.raises(TypeError, match="must be a str"):
        parse_petrinet(b"net coin_deposit\n")  # type: ignore[arg-type]


def test_source_tree_module_reads_the_canonical_grammar(tmp_path: Path) -> None:
    # given: the package source on sys.path, ahead of any installed copy
    script = tmp_path / "read_grammar.py"
    script.write_text(
        "\n".join(
            (
                "import sys",
                "from pathlib import Path",
                "sys.path.insert(0, sys.argv[1])",
                "from velocitron_grammar import grammar_text",
                "assert grammar_text() == Path(sys.argv[2]).read_text(encoding='utf-8')",
                "print('ok')",
            )
        ),
        encoding="utf-8",
    )
    src = _GRAMMAR_ROOT / "python" / "src"
    # when: a fresh interpreter imports that source tree
    completed = subprocess.run(
        [sys.executable, str(script), str(src), str(_CANONICAL)],
        capture_output=True,
        text=True,
        check=False,
    )
    # then: grammar_text reads the canonical file beside the package
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_grammar_text_matches_the_canonical_grammar() -> None:
    # given: the canonical grammar and the copy this package ships
    canonical = _CANONICAL.read_text(encoding="utf-8")
    # when: the parser reports the grammar it was generated from
    # then: a checkout reads the canonical file, and the packaged copy matches
    assert grammar_text() == canonical
    assert _PACKAGED_COPY.read_text(encoding="utf-8") == canonical
    assert "grammar VelocitronPetriNet;" in grammar_text()


def test_parse_petrinet_reads_the_capability_ladder_examples() -> None:
    # given: a real net and a real composition from the capability ladder
    net_path = _EXAMPLES / "01-coin-deposit" / "coin-deposit.petrinet"
    composition_path = _EXAMPLES / "10-wired-pulse" / "wired_pulse.petrinet"
    # when: the grammar package parses each file
    net = parse_petrinet(
        net_path.read_text(encoding="utf-8"), source_name=net_path.name
    )
    composition = parse_petrinet(
        composition_path.read_text(encoding="utf-8"),
        source_name=composition_path.name,
    )
    # then: the documents keep their header names and kinds
    assert net.kind == "net"
    assert net.name == "coin_deposit"
    assert composition.kind == "composition"
    assert composition.name == "wired_pulse"
