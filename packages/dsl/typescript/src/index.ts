/**
 * Lower a Velocitron `.petrinet` document to contribution IR.
 *
 * `lowerPetrinetText` parses one document into portable contribution IR.
 * It does not resolve that IR, compile CEL, or merge a composition.
 *
 * This package is the source of truth for the lowerer.
 * Resolution ships in `@velocitron/petrinet`. Canonical emission of
 * `.petrinet` text ships in `velocitron_dsl` (`emit_petrinet`). The CLI
 * ships in `@velocitron/cli`. This package does not import a facade.
 */

export {
  PETRINET_RESOURCE_LIMITS,
  PetrinetDslError,
  PetrinetResourceError,
  renderDiagnostic,
} from "./diagnostics.js";
export type {
  Diagnostic,
  PetrinetResourceKind,
  RelatedDiagnostic,
  SourcePosition,
  SourceSpan,
} from "./diagnostics.js";
export {
  lowerPetrinetText,
  validFieldPath,
  type ContributionIr,
  type ContributionIrContribution,
  type ContributionIrIdentity,
  type ContributionIrPosition,
  type ContributionIrSpan,
} from "./lower.js";
export {default as VelocitronPetriNetLexer} from "./generated/VelocitronPetriNetLexer.js";
export {SourceMap} from "./source.js";
export {
  pythonRepr,
  pythonStringRepr,
  reprFloat,
  taggedNumberRepr,
  taggedPythonRepr,
} from "./python-repr.js";
export type {TaggedJsonValue} from "./python-repr.js";
