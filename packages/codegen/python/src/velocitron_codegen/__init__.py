"""Generate one Python base class per Velocitron net (ADR 0058).

``generate_module`` joins a parsed ``Net`` with the contribution IR of the
same ``.petrinet`` text and emits a deterministic module: declarative
tables, abstract ``fire_<t>`` methods for handler transitions, generated
handlers for the rest, and abstract ``guard_<t>`` and ``predicate_<p>``.
``generate_composition`` emits one module per composition file, including
nested compositions, member classes, and ``RefinedAway`` mixins.

``net_document``, ``canonical_net_json``, and ``net_sha256`` are the digest
registration checks. ``velocitron_netbase`` re-exports them. Replay lives in
``velocitron_replay``. Generated modules import those packages, plus
``velocitron_engine`` for net types and ``velocitron_runtime.Engine`` when
a composition builds an engine with the default CEL adapter. This package
does not import ``velocitron``.

The ``velocitron codegen`` command lives in ``velocitron_cli``.
"""

from __future__ import annotations

from .composition_generator import (
    REFINED_AWAY,
    CompositionCodegenError,
    CompositionGenerated,
    RefinedAway,
    generate_composition,
    generate_composition_full,
)
from .generator import CodegenError, GeneratedModule, generate_module
from .hash import SYNTH_HANDLER, canonical_net_json, net_document, net_sha256

__all__ = [
    "REFINED_AWAY",
    "SYNTH_HANDLER",
    "CodegenError",
    "CompositionCodegenError",
    "CompositionGenerated",
    "GeneratedModule",
    "RefinedAway",
    "canonical_net_json",
    "generate_composition",
    "generate_composition_full",
    "generate_module",
    "net_document",
    "net_sha256",
]
