/**
 * Check a `.play` document against a net and step a walkthrough.
 *
 * `checkPlay` resolves the play, then plays every path through
 * `@velocitron/engine`. A handlerless firing is symbolic: this package
 * supplies output tokens and the engine fills `data` / `data cel`.
 * `walkthroughDocument` steps one checked path. `renderWalkthrough` prints
 * that path as Markdown.
 *
 * The `.play` grammar and AST live in `@velocitron/play`. Journal
 * durability, `records_to_play`, and the product CLI stay in the language
 * implementation. This package does not import `@velocitron/core`.
 *
 * Python is the reference for paired Graphviz graphs and PlantUML. This
 * package steps a walkthrough document and does not draw those.
 */

export {PlayCheckError} from "./errors.js";
export {checkPlay, type CheckPlayOptions} from "./check.js";
export {loadPlayNet, type LoadPlayNetOptions} from "./load.js";
export type {
  CheckResult,
  OutputRule,
  OutputSource,
  PlayNet,
  PlayReport,
  PlayTrace,
  StepDiagnostic,
  StepFailure,
  StepResult,
} from "./model.js";
export {
  markingJson,
  renderWalkthrough,
  traceJson,
  walkthroughDocument,
  type MarkingJson,
  type WalkScope,
  type WalkthroughDocument,
  type WalkthroughStep,
} from "./walkthrough.js";
