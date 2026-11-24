"""Kept records: records this system keeps, present from the start.

A place annotated ``kept`` (``(condition) kept by "circulation desk" starts as cel
"{'isbn': instance.isbn, 'damaged': false}"``) holds one
record that the net's own steps read and rewrite. It is there before the
first step, with the value its start expression gives, and nobody outside
the net writes it. ``velocitron prove`` builds the start against the check's
instance token and never lets the environment write the place; a play
builds it from the story's ``instance`` token (ADR 0051).

This module reads the annotation, checks it (``velocitron validate``), and
builds a start value. The engine ignores the annotation.

References: spec/proofs.md ("Kept records"); ADR 0047; ADR 0051.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from velocitron_cel import CelEvalError, get_default_adapter
from velocitron_engine import Net, Share

from . import celscan
from .celscan import Lit, MapLit

INSTANCE = "instance"
"""The one name a start expression may read: the instance token's data."""


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
        return any(
            ref.root == INSTANCE for ref in celscan.refs(celscan.parse(self.start))
        )

    def annotation(self) -> dict[str, Any]:
        return {"by": self.by, "start": {"cel": self.start}}


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
    (it reads a field the instance does not have, or needs an instance and
    none is given) or does not give a map.
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


def _record_columns(net: Net) -> set[str]:
    actors = (net.annotations or {}).get("actors")
    names: set[str] = set()
    for entry in cast(list[Any], actors if isinstance(actors, list) else []):
        if isinstance(entry, Mapping):
            fields = cast(Mapping[str, Any], entry)
            if fields.get("kind") == "record" and isinstance(fields.get("name"), str):
                names.add(cast(str, fields["name"]))
    return names


def kept_problems(net: Net) -> list[tuple[str, str]]:
    """What is wrong with the kept places of an authored net, as
    ``(place, message)`` pairs in place order.

    Run it on a net as written, not on a merged net: the merge marks every
    fused place ``fusion``.
    """
    from .analysis import NetModel

    problems: list[tuple[str, str]] = []
    records = _record_columns(net)
    initial = net.initial_marking
    model: NetModel | None = None
    for place in net.places:
        if "kept" not in (place.annotations or {}):
            continue
        name = place.name
        annotations = place.annotations or {}
        shape = _shape(annotations["kept"])
        if shape is None:
            problems.append(
                (
                    name,
                    f"({name}) has a malformed kept annotation; it is "
                    '{"by": NAME, "start": {"cel": "…"}}',
                )
            )
            continue
        if len(place.accepts) != 1:
            problems.append(
                (
                    name,
                    f"({name}) is a kept record and takes {len(place.accepts)} colors "
                    f"({', '.join(place.accepts)}); a kept record has one color",
                )
            )
            continue
        if annotations.get("fusion"):
            problems.append(
                (
                    name,
                    f"({name}) is a kept record, so the outside world does not supply "
                    "it; remove `annotation fusion true`",
                )
            )
        if place.port is not None:
            problems.append(
                (
                    name,
                    f"({name}) is a kept record and cannot be a port; use `share` to "
                    "use it in another net",
                )
            )
        lives = annotations.get("lives")
        if isinstance(lives, str) and lives in records:
            problems.append(
                (
                    name,
                    f'({name}) is a kept record, but it lives in the record column "'
                    f'{lives}", which the outside world keeps (ADR 0047)',
                )
            )
        if initial is not None and initial.get(name):
            problems.append(
                (
                    name,
                    f"({name}) is a kept record; its start comes from `starts as`, "
                    "not from the initial marking",
                )
            )
        record = KeptRecord(name, place.accepts[0], *shape)
        if model is None:
            model = NetModel(net)
        problems += [(name, text) for text in _start_problems(net, model, record)]
    return problems


def _start_problems(net: Net, model: Any, record: KeptRecord) -> list[str]:
    """Why the start expression does not fit the record's color."""
    name = record.place
    try:
        get_default_adapter().compile(record.start)
    except Exception as error:  # noqa: BLE001 - every backend raises its own type
        return [f"the start of ({name}) is not valid CEL: {error}"]
    tree = celscan.parse(record.start)
    roots = sorted({ref.root for ref in celscan.refs(tree)} - {INSTANCE})
    if roots:
        return [
            f"the start of ({name}) may read only `instance`, not "
            + ", ".join(f"`{root}`" for root in roots)
        ]
    if not isinstance(tree, MapLit) or not all(
        isinstance(key, Lit) and isinstance(key.value, str) for key, _ in tree.entries
    ):
        return [
            f"the start of ({name}) is a map of the record's fields, such as "
            "{'erroring': false}"
        ]
    values: dict[str, Any] = {}
    for key, value in tree.entries:
        assert isinstance(key, Lit)
        values[cast(str, key.value)] = value
    problems: list[str] = []
    for key, allowed in sorted((net.domains or {}).items()):
        color, _, rest = key.partition(".")
        if color != record.color or "." in rest:
            continue
        if rest not in values:
            problems.append(
                f"the start of ({name}) sets no '{rest}', which domain {key} requires"
            )
            continue
        given = values[rest]
        if isinstance(given, Lit) and not any(
            type(given.value) is type(option) and given.value == option
            for option in allowed
        ):
            problems.append(
                f"the start of ({name}) sets '{rest}' to {given.value!r}, outside "
                f"domain {key}"
            )
    read = sorted({path[0] for path in model.tested(name, record.color)})
    for field_name in read:
        if field_name not in values:
            problems.append(
                f"the start of ({name}) sets no '{field_name}', which the net reads "
                f"from ({name})"
            )
    return problems


def share_problems(
    nets: Mapping[str, Net], shares: Sequence[Share]
) -> list[tuple[Share, str]]:
    """Shares that join a kept place with a place that is not kept the same way."""
    problems: list[tuple[Share, str]] = []
    for share in shares:
        kept: dict[tuple[str, str], dict[str, Any] | None] = {}
        for alias, place in share.members:
            found = kept_records(nets[alias]).get(place)
            kept[(alias, place)] = found.annotation() if found is not None else None
        values = list(kept.values())
        if all(value is None for value in values):
            continue
        first = next(member for member, value in kept.items() if value is not None)
        for member, value in kept.items():
            if value != kept[first]:
                problems.append(
                    (
                        share,
                        f"the share joins the kept record {first[0]}.({first[1]}) "
                        f"with {member[0]}.({member[1]}), which "
                        + (
                            "is not kept"
                            if value is None
                            else "is kept by another actor or from another start"
                        )
                        + "; every member of a shared kept record is kept the same way",
                    )
                )
                break
    return problems


__all__ = [
    "INSTANCE",
    "KeptRecord",
    "KeptStartError",
    "build_start",
    "kept_problems",
    "kept_records",
    "share_problems",
]
