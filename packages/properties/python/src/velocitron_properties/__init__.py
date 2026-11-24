"""Declarative property pass for markings a system produced (ADR 0019).

:func:`check_marking` checks one marking. :func:`check_replay` reconstructs
intermediate markings from journal records and checks those too.
:func:`capacity_properties` reads ``capacityPerColorKey``.

The prover in ``velocitron_analysis`` checks markings a net can reach. This
package checks markings handed to it. It reads journal record types and
compiles CEL. It does not explore a net and it does not import
``velocitron``.

``velocitron_properties`` re-exports this seam. The TypeScript package names
the checkers and does not run them.
"""

from __future__ import annotations

from .properties import (
    AtMostN,
    EventuallyReaches,
    FiringBinding,
    Key,
    KeyCorrelation,
    MarkingInvariant,
    PlaceEmpty,
    Property,
    PropertyReport,
    PropertyViolation,
    Scope,
    capacity_properties,
    check_marking,
    check_replay,
)

__all__ = [
    "AtMostN",
    "EventuallyReaches",
    "FiringBinding",
    "Key",
    "KeyCorrelation",
    "MarkingInvariant",
    "PlaceEmpty",
    "Property",
    "PropertyReport",
    "PropertyViolation",
    "Scope",
    "capacity_properties",
    "check_marking",
    "check_replay",
]
