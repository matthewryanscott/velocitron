"""Load a Velocitron contribution-IR document as a wire shape.

The canonical schema is ``packages/spec/petrinet-contribution-ir.schema.json``.
A checkout reads that file. A wheel reads the copy this package ships, which
``tools/generate-schemas-python.py`` keeps identical.

This module validates format, version, and the wire schema. It leaves CEL
source strings as strings. Contribution resolution ships in
``packages/petrinet``. Composition merge ships in ``packages/merge``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path
from typing import Any, Final, Literal, TypedDict, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

CONTRIBUTION_IR_FORMAT: Final = "velocitron.petrinet/contribution-ir"
CONTRIBUTION_IR_VERSION: Final = 1
CONTRIBUTION_IR_SCHEMA_NAME: Final = "petrinet-contribution-ir.schema.json"

_UNSUPPORTED: Final = "unsupported contribution IR format or version"
_NOT_OBJECT: Final = "contribution IR document must be a JSON object"
_NOT_JSON: Final = "contribution IR text is not JSON"
_SCHEMA_MISMATCH: Final = "contribution IR document does not match the wire schema"
_DOCUMENT_KEYS: Final = frozenset(
    {"format", "version", "documentKind", "document", "contributions"}
)


class ContributionIrPosition(TypedDict):
    """UTF-8 source coordinates on the contribution-IR wire."""

    byteOffset: int
    line: int
    column: int


class ContributionIrSpan(TypedDict):
    """A half-open source span carried on the wire."""

    source: str
    start: ContributionIrPosition
    end: ContributionIrPosition


class ContributionIrIdentity(TypedDict):
    """Source-derived contribution identity. Not a runtime UUID."""

    source: str
    statement: int
    part: int


class ContributionIrDocument(TypedDict):
    """The document identity member of a contribution-IR root."""

    id: str


class ContributionIrContribution(TypedDict):
    """One closed contribution envelope. ``value`` keeps CEL text as a string."""

    id: ContributionIrIdentity
    ordinal: int
    span: ContributionIrSpan
    kind: str
    target: dict[str, Any]
    value: dict[str, Any]


class ContributionIr(TypedDict):
    """A contribution-IR document that has passed the wire-shape gate.

    ``format`` is ``velocitron.petrinet/contribution-ir`` and ``version`` is
    ``1``. ``documentKind`` is ``net`` or ``composition``.
    """

    format: Literal["velocitron.petrinet/contribution-ir"]
    version: Literal[1]
    documentKind: Literal["net", "composition"]
    document: ContributionIrDocument
    contributions: list[ContributionIrContribution]


@dataclass(frozen=True, slots=True)
class ContributionIrShapeIssue:
    """One JSON Schema failure, with a JSON Pointer instance path."""

    instance_path: str
    message: str


class ContributionIrShapeError(ValueError):
    """The value is not a supported contribution-IR wire document."""

    issues: tuple[ContributionIrShapeIssue, ...]

    def __init__(
        self,
        message: str,
        issues: tuple[ContributionIrShapeIssue, ...] = (),
    ) -> None:
        super().__init__(message)
        self.issues = issues


def _checkout_schema() -> Path | None:
    # packages/ir/python/src/velocitron_ir/__init__.py -> packages/ir/python
    project_root = Path(__file__).resolve().parents[2]
    marker = project_root / "pyproject.toml"
    canonical = project_root.parent.parent / "spec" / CONTRIBUTION_IR_SCHEMA_NAME
    if project_root.name != "python" or project_root.parent.name != "ir":
        return None
    if not marker.is_file() or not canonical.is_file():
        return None
    for line in marker.read_text(encoding="utf-8").splitlines():
        if line.strip() == 'name = "velocitron-ir"':
            return canonical
    return None


def _read_schema_text() -> str:
    checkout = _checkout_schema()
    if checkout is not None:
        return checkout.read_text(encoding="utf-8")
    packaged = files("velocitron_ir").joinpath("schemas", CONTRIBUTION_IR_SCHEMA_NAME)
    if not packaged.is_file():
        raise FileNotFoundError("velocitron-ir contribution IR schema is not installed")
    return packaged.read_text(encoding="utf-8")


def _load_schema() -> tuple[str, dict[str, Any]]:
    text = _read_schema_text()
    document = json.loads(text)
    if not isinstance(document, dict):
        raise TypeError("contribution IR schema must be a JSON object")
    schema = cast(dict[str, Any], document)
    Draft202012Validator.check_schema(schema)
    return text, schema


_SCHEMA_TEXT, _SCHEMA = _load_schema()
_VALIDATOR = Draft202012Validator(deepcopy(_SCHEMA))


def contribution_ir_schema_text() -> str:
    """Return the contribution-IR JSON Schema as UTF-8 text."""
    return _SCHEMA_TEXT


def contribution_ir_schema() -> dict[str, Any]:
    """Return a detached copy of the contribution-IR JSON Schema."""
    return deepcopy(_SCHEMA)


def _json_pointer(path: Iterable[object]) -> str:
    tokens: list[str] = []
    for part in path:
        text = str(part).replace("~", "~0").replace("/", "~1")
        tokens.append(text)
    if not tokens:
        return ""
    return "/" + "/".join(tokens)


def _flatten_errors(errors: Iterable[ValidationError]) -> list[ValidationError]:
    flat: list[ValidationError] = []
    for error in errors:
        flat.append(error)
        flat.extend(_flatten_errors(error.context))
    return flat


def _schema_issues(
    errors: Iterable[ValidationError],
) -> tuple[ContributionIrShapeIssue, ...]:
    issues = [
        ContributionIrShapeIssue(_json_pointer(error.absolute_path), error.message)
        for error in _flatten_errors(errors)
    ]
    issues.sort(key=lambda issue: (issue.instance_path, issue.message))
    return tuple(issues)


def _require_supported_format(document: Mapping[str, Any]) -> None:
    format_id = document.get("format")
    version = document.get("version")
    if (
        format_id != CONTRIBUTION_IR_FORMAT
        or type(version) is not int
        or version != CONTRIBUTION_IR_VERSION
    ):
        raise ContributionIrShapeError(_UNSUPPORTED)


def load_contribution_ir(document: object) -> ContributionIr:
    """Validate one parsed contribution-IR value and return a detached copy.

    An unsupported ``format`` or ``version`` fails before the schema walk.
    The schema then checks the closed wire shape. Cross-contribution identity
    and ordinal rules belong to resolution, which this function does not run.
    """
    if not isinstance(document, dict):
        raise ContributionIrShapeError(_NOT_OBJECT)
    raw = cast(dict[str, Any], document)
    _require_supported_format(raw)
    errors = list(_VALIDATOR.iter_errors(raw))  # pyright: ignore[reportUnknownMemberType]
    if errors:
        raise ContributionIrShapeError(_SCHEMA_MISMATCH, _schema_issues(errors))
    if frozenset(raw) != _DOCUMENT_KEYS:
        raise ContributionIrShapeError(_SCHEMA_MISMATCH)
    loaded = cast(ContributionIr, deepcopy(raw))
    return loaded


def load_contribution_ir_text(text: object) -> ContributionIr:
    """Parse contribution-IR JSON text and validate its wire shape."""
    if not isinstance(text, str):
        raise TypeError("contribution IR text must be a str")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContributionIrShapeError(_NOT_JSON) from exc
    return load_contribution_ir(value)


__all__ = [
    "CONTRIBUTION_IR_FORMAT",
    "CONTRIBUTION_IR_SCHEMA_NAME",
    "CONTRIBUTION_IR_VERSION",
    "ContributionIr",
    "ContributionIrContribution",
    "ContributionIrDocument",
    "ContributionIrIdentity",
    "ContributionIrPosition",
    "ContributionIrShapeError",
    "ContributionIrShapeIssue",
    "ContributionIrSpan",
    "contribution_ir_schema",
    "contribution_ir_schema_text",
    "load_contribution_ir",
    "load_contribution_ir_text",
]
