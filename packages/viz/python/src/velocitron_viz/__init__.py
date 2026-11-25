"""Render an already-built Velocitron net as Graphviz DOT.

``net_to_dot`` draws one net. ``apply_view`` pins authored positions and
routes onto that drawing. ``fusion_layout`` is the fusion-copy placement,
including a shared copy between two neighbor transitions of one choice.
Pass a net the caller already built. This package does not parse documents,
compile CEL, merge compositions, or install a console script, and it does
not import ``velocitron``.

This package is the source of truth for the renderer. The product CLI lives
in ``velocitron_cli``. The language implementation re-exports this API and
keeps the console-script entry.
"""

from __future__ import annotations

from .canonical import render_canonical_json
from .render import (
    DETAIL_LEVELS,
    BesidePlacement,
    Detail,
    FusionLayout,
    MarkingRow,
    PairSide,
    RenderModel,
    RenderStyle,
    TokenChanges,
    TokenMark,
    TokenMarks,
    composition_overview_dot,
    composition_ports_dot,
    composition_to_dot,
    fusion_layout,
    legend_dot,
    marking_rows,
    member_label,
    net_render_model,
    net_to_dot,
    net_twin_dots,
    sibling_groups,
)
from .schema import (
    Arc,
    Composition,
    ConsumePattern,
    Marking,
    Net,
    NetRef,
    Place,
    Port,
    Predicate,
    ProduceTemplate,
    Refinement,
    Share,
    Timer,
    Token,
    Transition,
    Wire,
)
from .view import (
    BESIDE_GAP,
    DEFAULT_VIEW,
    Decoration,
    Decorations,
    ViewApplicationError,
    apply_view,
    has_view,
    read_decorations,
    resolve_positions,
    view_setting,
)

__all__ = [
    "BESIDE_GAP",
    "DEFAULT_VIEW",
    "DETAIL_LEVELS",
    "Arc",
    "BesidePlacement",
    "Composition",
    "ConsumePattern",
    "Decoration",
    "Decorations",
    "Detail",
    "FusionLayout",
    "Marking",
    "MarkingRow",
    "Net",
    "NetRef",
    "PairSide",
    "Place",
    "Port",
    "Predicate",
    "ProduceTemplate",
    "Refinement",
    "RenderModel",
    "RenderStyle",
    "Share",
    "Timer",
    "Token",
    "TokenChanges",
    "TokenMark",
    "TokenMarks",
    "Transition",
    "ViewApplicationError",
    "Wire",
    "apply_view",
    "composition_overview_dot",
    "composition_ports_dot",
    "composition_to_dot",
    "fusion_layout",
    "has_view",
    "legend_dot",
    "marking_rows",
    "member_label",
    "net_render_model",
    "net_to_dot",
    "net_twin_dots",
    "read_decorations",
    "render_canonical_json",
    "resolve_positions",
    "sibling_groups",
    "view_setting",
]
