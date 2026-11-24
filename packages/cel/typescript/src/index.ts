/**
 * Compile and evaluate CEL.
 *
 * `compile` checks syntax. `evaluate` returns JSON or throws `CelError`.
 * `createDefaultCelAdapter` is the bundled `@marcbachmann/cel-js` backend.
 *
 * This package is the source of truth for the adapter.
 * Engine wiring and DSL produce-cel stay in the language implementations.
 * The CEL scan prove uses ships in `velocitron_analysis`. This package
 * does not import `@velocitron/core`.
 */

export {createDefaultCelAdapter, DefaultCelAdapter} from "./default.js";
export {
  CelCompileError,
  CelError,
  CelEvaluationError,
  normalizeCelError,
} from "./errors.js";
export type {
  CelAdapter,
  CelDiagnostic,
  CelPhase,
  CelSourceRange,
} from "./types.js";
