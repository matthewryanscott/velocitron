"""Read the portable Velocitron contracts shipped by ``velocitron-spec``.

The canonical JSON Schemas, normative prose, and conformance fixtures live
at the root of ``packages/spec``. A wheel copies those files into this
module. ``schema_text``, ``prose_text``, and ``conformance_root`` read the
source tree when this file still sits beside them, and the packaged copies
otherwise.

Schema ``$id`` URLs stay on their existing ``/spec/`` paths. This package
does not compile CEL, resolve Contribution IR, or merge compositions.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, Literal, cast

NET_SCHEMA_NAME: Final = "net.schema.json"
COMPOSITION_SCHEMA_NAME: Final = "composition.schema.json"
CONTRIBUTION_IR_SCHEMA_NAME: Final = "petrinet-contribution-ir.schema.json"
SCHEMA_NAMES: Final[tuple[str, ...]] = (
    NET_SCHEMA_NAME,
    COMPOSITION_SCHEMA_NAME,
    CONTRIBUTION_IR_SCHEMA_NAME,
)
PROSE_NAMES: Final[tuple[str, ...]] = (
    "composition.md",
    "firing-semantics.md",
    "handler-contract.md",
    "net-schema.md",
    "petrinet-language.md",
    "play-language.md",
    "projection-adapter.md",
    "proofs.md",
    "properties.md",
)

# packages/spec/src/velocitron_spec/__init__.py -> packages/spec
_SOURCE_ROOT: Final = Path(__file__).resolve().parents[2]


def _read_packaged_text(source_name: str, packaged_parts: tuple[str, ...]) -> str:
    package = __package__
    if not package:
        raise FileNotFoundError(source_name)
    packaged = files(package).joinpath(*packaged_parts)
    if not packaged.is_file():
        raise FileNotFoundError(source_name)
    return packaged.read_text(encoding="utf-8")


def _read_contract_text(source_name: str, packaged_parts: tuple[str, ...]) -> str:
    source = _SOURCE_ROOT / source_name
    if source.is_file():
        return source.read_text(encoding="utf-8")
    return _read_packaged_text(source_name, packaged_parts)


SchemaName = Literal[
    "net.schema.json",
    "composition.schema.json",
    "petrinet-contribution-ir.schema.json",
]
SchemaDocument = dict[str, Any]


def schema_text(name: str) -> str:
    """Return one canonical JSON Schema as UTF-8 text."""
    if name not in SCHEMA_NAMES:
        known = ", ".join(SCHEMA_NAMES)
        raise ValueError(f"unknown schema {name!r}; expected one of {known}")
    return _read_contract_text(name, ("schemas", name))


def schema_document(name: str) -> SchemaDocument:
    """Return one packaged schema as a JSON object."""
    document = json.loads(schema_text(name))
    if not isinstance(document, dict):
        raise TypeError(f"packaged schema {name!r} must contain a JSON object")
    return cast(SchemaDocument, document)


NET_SCHEMA: Final[SchemaDocument] = schema_document(NET_SCHEMA_NAME)
COMPOSITION_SCHEMA: Final[SchemaDocument] = schema_document(COMPOSITION_SCHEMA_NAME)
CONTRIBUTION_IR_SCHEMA: Final[SchemaDocument] = schema_document(
    CONTRIBUTION_IR_SCHEMA_NAME
)


def prose_text(name: str) -> str:
    """Return one normative prose contract as UTF-8 text."""
    if name not in PROSE_NAMES:
        known = ", ".join(PROSE_NAMES)
        raise ValueError(f"unknown prose contract {name!r}; expected one of {known}")
    return _read_contract_text(name, ("prose", name))


def conformance_root() -> Path:
    """Return the conformance corpus directory."""
    source = _SOURCE_ROOT / "conformance"
    if source.is_dir():
        return source
    package = __package__
    if not package:
        raise FileNotFoundError("velocitron-spec conformance corpus is not installed")
    packaged = files(package).joinpath("conformance")
    if not packaged.is_dir():
        raise FileNotFoundError("velocitron-spec conformance corpus is not installed")
    return Path(str(packaged))
