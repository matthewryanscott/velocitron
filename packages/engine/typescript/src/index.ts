/**
 * Fire and advance an already-built Velocitron net.
 *
 * `Engine` detects enablement, selects a binding, fires, and repeats in
 * `run`. Pass a `CelAdapter`. This package does not bundle a CEL backend and
 * does not import the umbrella implementation. Python `advance(outputs=)` symbolic
 * advance stays in `velocitron-engine`; this runtime has `fire`, `run`, and
 * `tick`. `reserve` / `settle` are the async-runtime seam; the run loop
 * that uses them ships in `@velocitron/runtime`. Journal durability ships
 * in `@velocitron/journal`. DSL resolution ships in `@velocitron/petrinet`.
 * The net render library is `@velocitron/viz`.
 *
 * This package is the source of truth for the firing core.
 * `@velocitron/runtime`'s `Engine` subclasses it and injects the default
 * CEL adapter.
 */

export type {CelAdapter} from "./adapter.js";
export {
  ConflictError,
  DepositViolationError,
  Engine,
  EngineConfigurationError,
  FailedAttemptError,
  SelectionLedger,
  TokenInjectionError,
  UnknownTransitionError,
  domainViolation,
} from "./engine/index.js";
export type {
  AttemptOptions,
  BatchInjectionResult,
  DepositViolationPolicy,
  EngineClock,
  EngineIdFactory,
  EngineOptions,
  FireResult,
  FiringIdInput,
  InjectOptions,
  InjectionIdInput,
  InjectionResult,
  OptionalAttemptOptions,
  RunOptions,
  SelectedBinding,
  FiringReservation,
  TickOptions,
  TimerMaturity,
  TokenPlacement,
  TransitionFootprint,
} from "./engine/types.js";
export type {
  FiringRecord,
  FiringStatus,
  InjectionKind,
  InjectionRecord,
  Journal,
  JournalRecord,
  SequencedJournalRecord,
} from "./journal/types.js";
export {
  DEFAULT_FIRING_POLICY,
  PRIORITY_FIRING_POLICY,
  HandlerConflictError,
  HandlerNotFoundError,
  HandlerRegistry,
  HandlerRegistryError,
  InvalidHandlerRegistrationError,
} from "./registry/index.js";
export type {
  FiringContext,
  FiringPolicyHandler,
  FiringPolicyInput,
  FiringTimestamps,
  GuardHandler,
  HandlerError,
  HandlerKind,
  OutputTokens,
  PredicateHandler,
  PredicateHandlerInput,
  TokenBinding,
  TransitionHandler,
  TransitionHandlerInput,
  TransitionHandlerOutput,
} from "./registry/types.js";
export type * from "./schema/types.js";
