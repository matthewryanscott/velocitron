/**
 * Merge already-parsed nets into one net.
 *
 * `mergeNets`, `mergeComposition`, and `portFusionMap` alias-qualify places
 * and fuse wired ports. `mergeComposition` takes the nets the caller already
 * resolved; it does not read files. The result is not re-validated here:
 * structural checks and CEL compilation ship in `@velocitron/petrinet`
 * (`mergeNets` / `mergeComposition`).
 *
 * This package is the source of truth for the transform. It does not import
 * `@velocitron/core`. `@velocitron/petrinet` calls it and then revalidates.
 */

export {NetValidationError, type NetValidationIssue} from "./errors.js";
export {
  findPort,
  mergeComposition,
  mergeNets,
  portFusionMap,
  validateRefinements,
} from "./composition-merge.js";
export type {
  Arc,
  CompositionDocument,
  CompositionPlaceEndpoint,
  CompositionPortEndpoint,
  CompositionRefinement,
  CompositionShare,
  CompositionWire,
  ConsumePattern,
  DeclaredInvariant,
  JsonValue,
  Marking,
  Net,
  Place,
  Port,
  ProduceTemplate,
  ProofFacts,
  ReadonlyJsonObject,
  Timer,
  Token,
  Transition,
} from "./types.js";
