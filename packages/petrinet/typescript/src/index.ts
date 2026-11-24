/**
 * Compile a `.petrinet` document into canonical JSON.
 *
 * `compilePetrinetText` lowers one source and resolves it.
 * `resolveContributionIr` is the same close for contribution IR that is
 * already lowered. `parseNet` and `parseComposition` validate the canonical
 * JSON. CEL text is compiled here. A composition loads the nets the caller
 * passes in.
 *
 * `mergeNets` and `mergeComposition` run `@velocitron/merge`, then `parseNet`
 * revalidates the merged net, including CEL. This package does not fire a
 * net, check a play, store a journal, own the CLI, or emit `.petrinet` text.
 * Canonical `.petrinet` text emission is Python-only
 * (`velocitron_dsl.emit_petrinet`). It does not import `@velocitron/core`.
 */

export {
  compilePetrinetText,
  type CompiledCompositionDocument,
  type CompiledNetDocument,
  type CompiledPetrinetDocument,
  type ParseCompositionOptions,
} from "./compile.js";
export {
  mergeComposition,
  mergeNets,
  parseComposition,
  parseCompositionShape,
  validateRefinements,
  type CompositionLoader,
  type ParsedComposition,
} from "./composition.js";
export {
  NetValidationError,
  type NetValidationIssue,
  type NetValidationIssueCode,
} from "./errors.js";
export {
  validateContributionIr,
  type ContributionIrValidationError,
  type ContributionIrValidationResult,
} from "./generated/contribution-ir-validator.js";
export {
  JSON_SNAPSHOT_LIMITS,
  deepFreezeJson,
  snapshotJson,
} from "./json.js";
export type {JsonShapeIssue, JsonSnapshot} from "./json.js";
export {parseNet, type ParseNetOptions} from "./parse.js";
export {resolveContributionIr} from "./resolve.js";
