/**
 * Run a net asynchronously and evaluate intended waits.
 *
 * `Runtime` reserves consume-mode inputs, runs the handler, and settles
 * the reservation. Pass a `HandlerRegistry` for guards, predicates, and
 * the firing policy. This package does not call `Engine.fire`.
 *
 * `intendedWaits` reads a transition's `wait` annotation. The engine
 * ignores that annotation.
 *
 * `Engine` is `@velocitron/engine`'s `Engine` with `celAdapter` defaulting to
 * `createDefaultCelAdapter()`. Pass `celAdapter` to select a backend. The
 * firing core stays in `@velocitron/engine` and still requires one.
 *
 * Journal storage stays in `@velocitron/journal`. This package does not
 * import `@velocitron/core`.
 */

export {Engine, type EngineOptions} from "./default-engine.js";
export {
  Lane,
  Runtime,
  RuntimeContext,
  TokenArrival,
  TokenBatch,
  TokenSource,
} from "./runtime.js";
export type {
  AsyncTransitionHandler,
  Cancellation,
  Clock,
  HandlerSpec,
  RuntimeJournal,
  RuntimeOptions,
  RuntimeRecord,
  ScopeResolver,
  SourceFactory,
  SourceHealth,
  SourceItem,
  SourcePolicy,
  TraceRecord,
} from "./runtime.js";
export {WAIT_KEY, holds, intendedWaits, waitProblems} from "./waits.js";
export type {Wait} from "./waits.js";
