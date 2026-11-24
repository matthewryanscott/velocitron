"""The in-repo contribution-IR shape package still feeds the resolver."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

from velocitron_petrinet import resolve_contribution_ir

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CADENCE = (
    _REPO_ROOT
    / "packages"
    / "spec"
    / "conformance"
    / "petrinet"
    / "12-reading-hour-fragment"
    / "reading_cadence.contribution-ir.json"
)
_CEL = "clock.now >= latch.fired_at + latch.cadence_s"


def _load_ir_package() -> ModuleType:
    loader_path = (
        _REPO_ROOT
        / "packages"
        / "ir"
        / "python"
        / "src"
        / "velocitron_ir"
        / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("velocitron_ir_source", loader_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves string annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def test_shape_package_output_still_resolves_to_a_net() -> None:
    # given: the source-tree shape loader and a conformance contribution-IR net
    module = _load_ir_package()
    load = getattr(module, "load_contribution_ir")
    document = json.loads(_CADENCE.read_text(encoding="utf-8"))
    # when: the shape loader validates it and the implementation resolver decodes it
    loaded = load(document)
    resolved = resolve_contribution_ir(loaded)
    # then: CEL text is unchanged on the IR, and resolution still yields the net
    assert _CEL in _cel_strings(loaded)
    assert isinstance(resolved, dict)
    assert "places" in resolved
    assert resolved.get("format") != "velocitron.petrinet/contribution-ir"
