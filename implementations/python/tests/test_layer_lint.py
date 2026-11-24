"""The shared layer allow-list rejects cycles and illegal edges."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location("layer_lint", ROOT / "tools" / "layer_lint.py")
assert _SPEC is not None and _SPEC.loader is not None
layer_lint = importlib.util.module_from_spec(_SPEC)
sys.modules["layer_lint"] = layer_lint
_SPEC.loader.exec_module(layer_lint)


def test_the_tree_matches_the_allow_list() -> None:
    # given: the repository sources and layers.yaml
    # when:
    problems = layer_lint.lint()
    # then:
    assert problems == []


def test_a_runtime_cycle_is_reported() -> None:
    # given:
    graph = {"a": {"b"}, "b": {"a"}}
    # when:
    cycles = layer_lint.find_cycles(graph)
    # then:
    assert cycles == [("a", "b")]


def test_type_checking_import_is_not_a_runtime_edge() -> None:
    # given:
    source = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from velocitron_engine import Net\n"
    # when:
    imports = layer_lint.python_imports(source, "velocitron_viz.view", False)
    # then:
    typed = [item for item in imports if item.target == "velocitron_engine"]
    assert len(typed) == 1
    assert typed[0].type_only


def test_a_function_import_does_not_close_a_runtime_cycle() -> None:
    # given:
    source = "def load() -> None:\n    from velocitron_engine import Net\n"
    # when:
    imports = layer_lint.python_imports(source, "velocitron_cel._celpy", False)
    # then:
    assert imports[0].module_level is False


def test_a_deep_cross_layer_import_is_rejected() -> None:
    # given:
    layers = layer_lint.parse_layers((ROOT / "layers.yaml").read_text(encoding="utf-8"))
    # when:
    problems = layer_lint._edge_problems(
        layers["viz"],
        layers["engine"],
        "velocitron_engine.schema",
        public=False,
        where="schema.py:1",
    )
    # then:
    assert any("public package root" in problem for problem in problems)
    assert not any("allow list" in problem for problem in problems)


def test_umbrella_layers_are_gone() -> None:
    # given:
    layers = layer_lint.parse_layers((ROOT / "layers.yaml").read_text(encoding="utf-8"))
    # then: the allow-list has no god-node that may import every package
    assert "python-umbrella" not in layers
    assert "typescript-core" not in layers


def test_a_disallowed_edge_is_rejected() -> None:
    # given:
    layers = layer_lint.parse_layers((ROOT / "layers.yaml").read_text(encoding="utf-8"))
    # when: the engine reaches for CEL, which its allow list does not name
    problems = layer_lint._edge_problems(
        layers["engine"],
        layers["cel"],
        "velocitron_cel",
        public=True,
        where="engine.py:1",
    )
    # then:
    assert any("allow list does not permit" in problem for problem in problems)
