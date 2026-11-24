"""Merge already-parsed nets, then validate the result as one net.

The transform lives in ``velocitron_merge``. This module parses net files
when ``parsed_nets`` is missing and closes with :func:`validate_net`,
including CEL compilation. ``velocitron_merge.merge_nets`` does not.
"""

from __future__ import annotations

from collections.abc import Sequence

from velocitron_engine import Composition, Net, Refinement, Share, Wire
from velocitron_merge import NetValidationError as MergeNetValidationError
from velocitron_merge import merge_composition as _package_merge_composition
from velocitron_merge import merge_nets as _package_merge_nets
from velocitron_merge import port_fusion_map

from .parse import NetValidationError, parse_net, validate_net

__all__ = ["merge_composition", "merge_nets", "port_fusion_map"]


def merge_nets(
    alias_to_net: dict[str, Net],
    wires: list[Wire],
    refinements: Sequence[Refinement] = (),
    shares: Sequence[Share] = (),
    name: str = "composition",
    final: Sequence[Sequence[tuple[str, str]]] | None = None,
) -> Net:
    """Merge nets under aliases, then validate the result as one net."""
    try:
        result = _package_merge_nets(
            alias_to_net,
            wires,
            refinements,
            shares,
            name=name,
            final=final,
        )
    except MergeNetValidationError as exc:
        raise NetValidationError(str(exc)) from exc
    validate_net(result)
    return result


def merge_composition(composition: Composition) -> Net:
    """Merge a composition, parsing net files when ``parsed_nets`` is absent."""
    if composition.parsed_nets is None:
        alias_to_net: dict[str, Net] = {}
        for ref in composition.nets:
            parsed = parse_net(ref.ref)
            alias_to_net[ref.alias if ref.alias is not None else parsed.name] = parsed
        return merge_nets(
            alias_to_net,
            list(composition.wires),
            composition.refinements,
            composition.shares,
            name=composition.name or "composition",
            final=composition.final,
        )
    try:
        result = _package_merge_composition(composition)
    except MergeNetValidationError as exc:
        raise NetValidationError(str(exc)) from exc
    validate_net(result)
    return result
