"""Merge already-parsed nets into one net.

``merge_nets``, ``merge_composition``, and ``port_fusion_map`` alias-qualify
places and fuse wired ports. ``merge_composition`` reads
``composition.parsed_nets`` and does not parse files. The result is not
re-validated here: structural checks and CEL compilation ship in
``velocitron_petrinet.merge_nets`` and ``merge_composition``.

This package is the source of truth for the transform. It does not import
``velocitron``. ``velocitron_petrinet`` calls it and then revalidates.
"""

from __future__ import annotations

from .errors import NetValidationError
from .merge import merge_composition, merge_nets, port_fusion_map
from .refine import find_port, validate_refinements
from .types import (
    Arc,
    Composition,
    ConsumePattern,
    DeclaredInvariant,
    Marking,
    Net,
    NetRef,
    Place,
    Port,
    Predicate,
    ProduceTemplate,
    ProofFacts,
    Refinement,
    Share,
    Timer,
    Token,
    Transition,
    Wire,
)

__all__ = [
    "Arc",
    "Composition",
    "ConsumePattern",
    "DeclaredInvariant",
    "Marking",
    "Net",
    "NetRef",
    "NetValidationError",
    "Place",
    "Port",
    "Predicate",
    "ProduceTemplate",
    "ProofFacts",
    "Refinement",
    "Share",
    "Timer",
    "Token",
    "Transition",
    "Wire",
    "find_port",
    "merge_composition",
    "merge_nets",
    "port_fusion_map",
    "validate_refinements",
]
