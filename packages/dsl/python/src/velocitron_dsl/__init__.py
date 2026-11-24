"""Lower a Velocitron ``.petrinet`` document to contribution IR.

``lower_petrinet_text`` parses one document into portable contribution IR.
It does not resolve that IR, compile CEL, or merge a composition.
``emit_petrinet`` renders canonical ``.petrinet`` text. Resolution ships
in ``velocitron_petrinet``. Composition merge ships in ``velocitron_merge``.

This package is the source of truth for the lowerer and for canonical
emission. It does not import ``velocitron``.
"""

from __future__ import annotations

from .emit import emit_petrinet
from .diagnostics import (
    Diagnostic,
    PetrinetDslError,
    RelatedDiagnostic,
    SourcePosition,
    SourceSpan,
)
from .lower import (
    VIEW_DETAILS,
    VIEW_SPLINES,
    contains_isolated_surrogate,
    json_values_equal,
    lower_petrinet_text,
    petrinet_lexer_literals,
    untag_json_value,
    valid_capacity_key,
    valid_field_path,
)

__all__ = [
    "VIEW_DETAILS",
    "VIEW_SPLINES",
    "Diagnostic",
    "PetrinetDslError",
    "RelatedDiagnostic",
    "SourcePosition",
    "SourceSpan",
    "contains_isolated_surrogate",
    "emit_petrinet",
    "json_values_equal",
    "lower_petrinet_text",
    "petrinet_lexer_literals",
    "untag_json_value",
    "valid_capacity_key",
    "valid_field_path",
]
