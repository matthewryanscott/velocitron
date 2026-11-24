"""Net and composition values the merge reads and returns.

These are the engine schema types, so a merged net is the same class the
engine fires. This module does not import ``velocitron``.
"""

from __future__ import annotations

from velocitron_engine import (
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
]
