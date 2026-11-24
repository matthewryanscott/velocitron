import {lowerPetrinetText} from "@velocitron/dsl";
import {parseComposition, type ParseCompositionOptions} from "./composition.js";
import {deepFreezeJson} from "./json.js";
import {resolveContributionIr} from "./resolve.js";
import type {ReadonlyJsonObject} from "./types.js";

export interface CompiledNetDocument {
  readonly documentKind: "net";
  readonly document: ReadonlyJsonObject;
}

export interface CompiledCompositionDocument {
  readonly documentKind: "composition";
  readonly document: ReadonlyJsonObject;
}

export type CompiledPetrinetDocument =
  | CompiledNetDocument
  | CompiledCompositionDocument;

/**
 * Compile one complete `.petrinet` source into resolved canonical JSON.
 *
 * Callers branch on `documentKind`. A net has already passed `parseNet`.
 * A composition with `loadRef` or `origin` has passed `parseComposition`.
 */
function normalizeSourceId(sourceId: string): string {
  if (/^(?:\/|[A-Za-z]:[\\/])/u.test(sourceId)) {
    const basename = sourceId.split(/[\\/]/u).filter(Boolean).at(-1);
    return basename ?? sourceId;
  }
  return sourceId;
}

/**
 * Compiles one source. For a composition, a `loadRef` (or `origin`) also
 * loads the referenced nets, and a wire, share or refine that does not fit
 * them is a PN202 diagnostic at the fact, as in Python.
 */
export function compilePetrinetText(
  source: string,
  sourceId: string,
  options: ParseCompositionOptions = {},
): CompiledPetrinetDocument {
  const contributionIr = lowerPetrinetText(source, normalizeSourceId(sourceId));
  const document = resolveContributionIr(contributionIr, options);
  return deepFreezeJson({
    documentKind: contributionIr.documentKind,
    document,
  }) as CompiledPetrinetDocument;
}

export type {ParseCompositionOptions};
