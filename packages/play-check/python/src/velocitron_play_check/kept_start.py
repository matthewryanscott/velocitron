"""Kept-record starts a play builds before its first step.

``velocitron_analysis`` owns prove and validate. A play needs the same start
value (ADR 0051). This module reads the annotation shape, sees whether the
expression names ``instance``, and evaluates it. It does not import
``velocitron``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from velocitron_cel import CelEvalError, get_default_adapter, load_celpy
from velocitron_engine import Net

INSTANCE = "instance"
"""The one name a start expression may read: the instance token's data."""

_parser: Any = None


@dataclass(frozen=True)
class KeptRecord:
    """One kept place: its color, who keeps it, and its start expression."""

    place: str
    color: str
    by: str
    start: str

    @property
    def reads_instance(self) -> bool:
        """Whether the start reads the instance, so it needs one to be built."""
        return _reads_instance(self.start)


class KeptStartError(ValueError):
    """A start expression that cannot be built into a record."""


def _shape(value: Any) -> tuple[str, str] | None:
    """``(by, start)`` of a well-formed ``kept`` annotation, else ``None``."""
    if not isinstance(value, Mapping):
        return None
    fields = cast(Mapping[str, Any], value)
    by, start = fields.get("by"), fields.get("start")
    if set(fields) != {"by", "start"} or not isinstance(by, str) or not by:
        return None
    if not isinstance(start, Mapping):
        return None
    start_fields = cast(Mapping[str, Any], start)
    cel = start_fields.get("cel")
    if set(start_fields) != {"cel"} or not isinstance(cel, str) or not cel:
        return None
    return by, cel


def kept_records(net: Net) -> dict[str, KeptRecord]:
    """The well-formed kept places of ``net``, by place name."""
    found: dict[str, KeptRecord] = {}
    for place in net.places:
        shape = _shape((place.annotations or {}).get("kept"))
        if shape is not None and len(place.accepts) == 1:
            found[place.name] = KeptRecord(place.name, place.accepts[0], *shape)
    return found


def build_start(
    record: KeptRecord, instance: Mapping[str, Any] | None
) -> dict[str, Any]:
    """The record's start value, built against the instance token's data.

    Raises :class:`KeptStartError` when the expression cannot be evaluated
    or does not give a map.
    """
    if instance is None and record.reads_instance:
        raise KeptStartError(
            f"the start of ({record.place}) reads `instance`, and no instance is given"
        )
    adapter = get_default_adapter()
    try:
        value = adapter.eval(
            adapter.compile(record.start), {INSTANCE: dict(instance or {})}
        )
    except (CelEvalError, KeyError, TypeError, ValueError, RuntimeError) as error:
        raise KeptStartError(
            f"the start of ({record.place}) cannot be built from the instance "
            f"{_json_text(instance)}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise KeptStartError(
            f"the start of ({record.place}) gives {value!r}, not a map of its fields"
        )
    return cast(dict[str, Any], value)


def _json_text(data: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(data or {}), sort_keys=True, ensure_ascii=False)


def _cel_parser() -> Any:
    global _parser
    if _parser is None:
        _parser = load_celpy().celparser.CELParser()
    return _parser


def _reads_instance(expression: str) -> bool:
    """Whether a CEL expression names the identifier ``instance``.

    An expression celpy cannot parse does not count: the prover's scanner
    treats that shape as opaque and finds no reference.
    """
    try:
        tree = _cel_parser().parse(expression)
    except Exception:
        return False
    for node in tree.iter_subtrees():
        if getattr(node, "data", None) != "ident":
            continue
        children = list(node.children)
        if children and str(children[0]) == INSTANCE:
            return True
    return False
