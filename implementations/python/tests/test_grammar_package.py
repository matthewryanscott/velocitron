"""The in-repo grammar package parses the documents the implementation lowers."""

from __future__ import annotations

from pathlib import Path
import sys

from velocitron_petrinet import compile_petrinet_text

_REPO_ROOT = Path(__file__).resolve().parents[3]
_NET = (
    _REPO_ROOT
    / "examples"
    / "capability-ladder"
    / "01-coin-deposit"
    / "coin-deposit.petrinet"
)
_COMPOSITION = (
    _REPO_ROOT
    / "examples"
    / "capability-ladder"
    / "10-wired-pulse"
    / "wired_pulse.petrinet"
)


def _grammar():
    src = str(_REPO_ROOT / "packages" / "grammar" / "python" / "src")
    sys.path.insert(0, src)
    try:
        import velocitron_grammar
    finally:
        sys.path.remove(src)
    return velocitron_grammar


def test_grammar_package_kind_matches_compile() -> None:
    # given: the source-tree syntax parser and two capability-ladder documents
    parse_petrinet = _grammar().parse_petrinet
    net_text = _NET.read_text(encoding="utf-8")
    composition_text = _COMPOSITION.read_text(encoding="utf-8")
    # when: the grammar package parses them and the implementation compiles them
    net = parse_petrinet(net_text, source_name=_NET.name)
    compiled_net = compile_petrinet_text(net_text, _NET.name)
    composition = parse_petrinet(composition_text, source_name=_COMPOSITION.name)
    compiled_composition = compile_petrinet_text(composition_text, _COMPOSITION.name)
    # then: kind and header name agree, and compile still returns canonical JSON
    assert net.kind == "net"
    assert net.name == compiled_net["name"]
    assert "places" in compiled_net
    assert composition.kind == "composition"
    assert composition.name == compiled_composition["name"]
    assert "nets" in compiled_composition
    assert "contributions" not in compiled_net
