"""Fire and advance an already-built Velocitron net.

``Engine`` detects enablement, selects a binding, fires, and repeats in
``advance``. ``advance(outputs=)`` settles a handlerless firing from an
``OutputProvider``; ``symbolic_outputs`` is the carry rule for that seam.

Pass a ``CelAdapter``. This package does not bundle a CEL backend and does
not import ``velocitron``. Journal durability ships in ``velocitron_journal``.
Play checking ships in ``velocitron_play_check``. DSL resolution ships in
``packages/petrinet``. The net render library is
``packages/viz``.

This package is the source of truth for the firing core.
``velocitron_runtime.Engine`` subclasses it and injects the default CEL
adapter.
"""

from __future__ import annotations

from .adapter import CelAdapter
from .contract import (
    FiringContext,
    FiringPolicyHandler,
    FiringPolicyInput,
    FiringTimestamps,
    GuardHandler,
    GuardHandlerInput,
    HandlerError,
    PredicateHandler,
    PredicateHandlerInput,
    TransitionHandler,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from .engine import (
    AdvanceOutcome,
    BindingChoice,
    Conflict,
    DepositViolation,
    EnablementExplanation,
    EnablementReason,
    Engine,
    FailedAttempt,
    FiringReservation,
    OutputProvider,
    TimerMaturity,
    UnknownTransitionError,
    _BindingRejection,  # pyright: ignore[reportPrivateUsage]
    domain_violation,
    error_text,
    evaluate_produce_cel,
)
from .journal import (
    DEPOSIT_VIOLATION,
    FIRING,
    FiringRecord,
    FiringStatus,
    INJECTION,
    InjectionKind,
    InjectionRecord,
    Journal,
    NET_REVISION,
    RuntimeEvent,
    RuntimeJournal,
    RuntimeRecord,
    TRACE,
    TraceEvent,
    TraceJournal,
    TraceRecord,
)
from .outputs import carry_rule, net_fills, produce_templates, symbolic_outputs
from .registry import (
    DEFAULT_FIRING_POLICY,
    PRIORITY_FIRING_POLICY,
    HandlerNotFound,
    HandlerRegistry,
)
from .schema import (
    Arc,
    CapacityPerColorKey,
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
    "DEFAULT_FIRING_POLICY",
    "DEPOSIT_VIOLATION",
    "FIRING",
    "INJECTION",
    "NET_REVISION",
    "PRIORITY_FIRING_POLICY",
    "TRACE",
    "AdvanceOutcome",
    "Arc",
    "BindingChoice",
    "CapacityPerColorKey",
    "CelAdapter",
    "Composition",
    "Conflict",
    "ConsumePattern",
    "DeclaredInvariant",
    "DepositViolation",
    "EnablementExplanation",
    "EnablementReason",
    "Engine",
    "FailedAttempt",
    "FiringContext",
    "FiringPolicyHandler",
    "FiringPolicyInput",
    "FiringRecord",
    "FiringReservation",
    "FiringStatus",
    "FiringTimestamps",
    "GuardHandler",
    "GuardHandlerInput",
    "HandlerError",
    "HandlerNotFound",
    "HandlerRegistry",
    "InjectionKind",
    "InjectionRecord",
    "Journal",
    "Marking",
    "Net",
    "NetRef",
    "OutputProvider",
    "Place",
    "Port",
    "Predicate",
    "PredicateHandler",
    "PredicateHandlerInput",
    "ProduceTemplate",
    "ProofFacts",
    "Refinement",
    "RuntimeEvent",
    "RuntimeJournal",
    "RuntimeRecord",
    "Share",
    "Timer",
    "TimerMaturity",
    "Token",
    "TraceEvent",
    "TraceJournal",
    "TraceRecord",
    "Transition",
    "TransitionHandler",
    "TransitionHandlerInput",
    "TransitionHandlerOutput",
    "UnknownTransitionError",
    "Wire",
    "_BindingRejection",
    "carry_rule",
    "domain_violation",
    "error_text",
    "evaluate_produce_cel",
    "net_fills",
    "produce_templates",
    "symbolic_outputs",
]
