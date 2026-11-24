"""Leaf and composition generation run without the umbrella."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_codegen import (
    SYNTH_HANDLER,
    CodegenError,
    CompositionCodegenError,
    canonical_net_json,
    generate_composition,
    generate_module,
    net_document,
    net_sha256,
)
from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import compile_petrinet_text, parse_net

_LEAF = """
net two "Two transitions, one actor each"

[keep] handler "keep@two"
[drop] handler "drop@two"

(a) -> [keep] -> (b)
(b) -> [drop] -> (c)

[keep] actor "us"
[drop] actor "them"
"""

_SOURCE = """
net source "One-shot source"

(seed) -task-> [emit] -task-> (sent)
[emit] handler "emit@source"
(sent) port output task
"""

_SINK = """
net sink "Sink"

(inbox) -task-> [take] -task-> (done)
[take] handler "take@sink"
(inbox) port input task
"""

_COMPOSITION = """
composition pulse

use "source.petrinet" as source
use "sink.petrinet" as sink
wire source.(sent) -> sink.(inbox)
"""


def _module(text: str, name: str = "two.petrinet", *, actor: str | None = None):
    lowered = lower_petrinet_text(text, name)
    net = parse_net(compile_petrinet_text(text, name))
    return generate_module(
        net,
        source=name,
        source_name=name,
        text=text,
        contributions=lowered["contributions"],
        actor=actor,
    )


def test_a_leaf_module_names_its_class_and_handlers() -> None:
    # given: a two-transition net
    # when: the module is generated for one actor
    module = _module(_LEAF, actor="us")
    # then: the kept handler is abstract and the other actor's method is gone
    assert module.net_name == "two"
    assert "class TwoNet" in module.text
    assert "def fire_keep" in module.text
    assert "def fire_drop" not in module.text
    assert module.sha256 == net_sha256(
        parse_net(compile_petrinet_text(_LEAF, "two.petrinet"))
    )
    assert len(module.sha256) == 64


def test_generation_is_deterministic() -> None:
    # given: the same leaf
    # when: it is generated twice
    first = _module(_LEAF)
    second = _module(_LEAF)
    # then: the bytes match
    assert first.text == second.text


def test_a_keyword_place_name_fails_generation() -> None:
    # given: a place whose name is not a method suffix
    text = 'net bad "keyword"\n\n(class) -> [go] -> (out)\n'
    # when / then: generation collects the failure
    with pytest.raises(CodegenError):
        _module(text, "bad.petrinet")


def test_net_document_round_trips_through_parse_net() -> None:
    # given: a parsed leaf
    net = parse_net(compile_petrinet_text(_LEAF, "two.petrinet"))
    # when: the canonical document is parsed again
    again = parse_net(net_document(net))
    # then: the digest is stable
    assert canonical_net_json(net) == canonical_net_json(again)
    assert net_sha256(net) == net_sha256(again)


def test_a_composition_emits_one_module_per_file(tmp_path: Path) -> None:
    # given: two leaves and a wire
    (tmp_path / "source.petrinet").write_text(_SOURCE, encoding="utf-8")
    (tmp_path / "sink.petrinet").write_text(_SINK, encoding="utf-8")
    composition = tmp_path / "pulse.petrinet"
    composition.write_text(_COMPOSITION, encoding="utf-8")
    # when: the composition is generated
    modules = generate_composition(str(composition))
    # then: the composition class names both members
    assert "pulse" in modules
    text = modules["pulse"]
    assert "class PulseComposition" in text
    assert "SourceNet" in text
    assert "SinkNet" in text
    assert "from source_net import" in text
    assert "from sink_net import" in text


def test_a_shared_handler_ref_fails_the_composition(tmp_path: Path) -> None:
    # given: two members that declare the same handler ref
    shared = """
net {name} "{name}"

(a) -> [send] -> (b)
[send] handler "shared@x"
"""
    (tmp_path / "one.petrinet").write_text(shared.format(name="one"), encoding="utf-8")
    (tmp_path / "two.petrinet").write_text(shared.format(name="two"), encoding="utf-8")
    composition = tmp_path / "both.petrinet"
    composition.write_text(
        """
composition both

use "one.petrinet" as one
use "two.petrinet" as two
""",
        encoding="utf-8",
    )
    # when / then: generation names the shared ref
    with pytest.raises(CompositionCodegenError, match="shared@x"):
        generate_composition(str(composition))


def test_a_synthesized_handler_spelling_fails_the_composition(tmp_path: Path) -> None:
    # given: a declared ref that uses the synthesized prefix
    (tmp_path / "only.petrinet").write_text(
        f"""
net only "only"

(a) -> [send] -> (b)
[send] handler "{SYNTH_HANDLER}only.send"
""",
        encoding="utf-8",
    )
    composition = tmp_path / "wrap.petrinet"
    composition.write_text(
        """
composition wrap

use "only.petrinet" as only
""",
        encoding="utf-8",
    )
    # when / then: the prefix is rejected
    with pytest.raises(CompositionCodegenError, match="synthesized"):
        generate_composition(str(composition))
