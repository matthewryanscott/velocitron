"""Compile a ``.petrinet`` document into canonical JSON.

``compile_petrinet_text`` lowers one source and resolves it.
``resolve_contribution_ir`` is the same close for contribution IR that is
already lowered. ``parse_net`` and ``parse_composition`` validate the
canonical JSON. CEL text is compiled here. A composition loads the nets the
caller passes in.

``merge_nets`` and ``merge_composition`` run the merge in
``velocitron_merge`` and then :func:`validate_net`. This package does not
fire a net, check a play, store a journal, or render ``.petrinet`` text.
It does not import ``velocitron``.
"""

from __future__ import annotations

from .compile import (
    compile_petrinet_sources,
    compile_petrinet_text,
    load_petrinet,
    parse_petrinet_text,
    read_petrinet_text,
)
from .parse import (
    COMPOSITION_SCHEMA,
    NET_SCHEMA,
    NetValidationError,
    parse_composition,
    parse_net,
    validate_net,
)
from .resolve import SourceInput, resolve_contribution_ir
from .validated_merge import merge_composition, merge_nets, port_fusion_map

__all__ = [
    "COMPOSITION_SCHEMA",
    "NET_SCHEMA",
    "NetValidationError",
    "SourceInput",
    "compile_petrinet_sources",
    "compile_petrinet_text",
    "load_petrinet",
    "merge_composition",
    "merge_nets",
    "parse_composition",
    "port_fusion_map",
    "parse_net",
    "parse_petrinet_text",
    "read_petrinet_text",
    "resolve_contribution_ir",
    "validate_net",
]
