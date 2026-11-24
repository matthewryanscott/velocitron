"""Contract tests for canonical and packaged JSON Schema resources."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from velocitron_spec import (
    COMPOSITION_SCHEMA,
    COMPOSITION_SCHEMA_NAME,
    CONTRIBUTION_IR_SCHEMA,
    CONTRIBUTION_IR_SCHEMA_NAME,
    NET_SCHEMA,
    NET_SCHEMA_NAME,
    SchemaDocument,
    SchemaName,
    schema_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_CASES: tuple[tuple[SchemaName, Path, SchemaDocument], ...] = (
    (NET_SCHEMA_NAME, _REPO_ROOT / "packages" / "spec" / "net.schema.json", NET_SCHEMA),
    (
        COMPOSITION_SCHEMA_NAME,
        _REPO_ROOT / "packages" / "spec" / "composition.schema.json",
        COMPOSITION_SCHEMA,
    ),
    (
        CONTRIBUTION_IR_SCHEMA_NAME,
        _REPO_ROOT / "packages" / "spec" / "petrinet-contribution-ir.schema.json",
        CONTRIBUTION_IR_SCHEMA,
    ),
)


@pytest.mark.parametrize(("name", "canonical_path", "loaded_schema"), _SCHEMA_CASES)
def test_given_a_canonical_schema_then_it_is_valid_draft_2020_12(
    name: SchemaName, canonical_path: Path, loaded_schema: dict[str, Any]
) -> None:
    # given: the standalone canonical JSON document
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    # when/then: it is a valid schema and is the document loaded by the package
    Draft202012Validator.check_schema(canonical)
    assert canonical == loaded_schema, name


def test_given_packaged_schemas_then_the_generator_reports_in_sync() -> None:
    # given: the repo-root generator that mirrors packages/spec/*.schema.json into the package
    generator = _REPO_ROOT / "tools" / "generate-schemas-python.py"
    # when: its --check gate runs against the shipped files
    completed = subprocess.run(
        [sys.executable, str(generator), "--check"],
        capture_output=True,
        text=True,
    )
    # then: every packaged copy is an exact sync, not a second schema definition
    assert completed.returncode == 0, f"{completed.stdout}\n{completed.stderr}"
    assert "Packaged Python schemas are current." in completed.stdout


@pytest.mark.parametrize(("name", "canonical_path", "loaded_schema"), _SCHEMA_CASES)
def test_given_only_package_resources_then_each_schema_is_available(
    name: SchemaName, canonical_path: Path, loaded_schema: dict[str, Any]
) -> None:
    del canonical_path
    # given: the spec package text the umbrella loads
    # when/then: that text is the schema object, with no second copy in velocitron
    assert json.loads(schema_text(name)) == loaded_schema


def _load_spec_package() -> ModuleType:
    loader_path = (
        _REPO_ROOT / "packages" / "spec" / "src" / "velocitron_spec" / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("velocitron_spec_source", loader_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_given_the_spec_package_loader_then_it_reads_canonical_contracts() -> None:
    # given: the in-repo velocitron-spec loader, without installing the distribution
    module = _load_spec_package()
    schema_text = cast(Callable[[str], str], getattr(module, "schema_text"))
    prose_text = cast(Callable[[str], str], getattr(module, "prose_text"))
    conformance_root = cast(Callable[[], Path], getattr(module, "conformance_root"))
    # when: it reads the schemas, one prose contract, and the conformance root
    loaded = {name: schema_text(name) for name, _path, _schema in _SCHEMA_CASES}
    firing = prose_text("firing-semantics.md")
    corpus = conformance_root()
    # then: those reads are the canonical package files, and unknown names fail
    for name, canonical_path, _schema in _SCHEMA_CASES:
        assert loaded[name] == canonical_path.read_text(encoding="utf-8")
    assert firing == (
        _REPO_ROOT / "packages" / "spec" / "firing-semantics.md"
    ).read_text(encoding="utf-8")
    assert (corpus / "petrinet" / "manifest.json").is_file()
    assert (corpus / "play").is_dir()
    with pytest.raises(ValueError, match="unknown schema"):
        schema_text("missing.schema.json")
