import {
  PetrinetDslError,
  lowerPetrinetText,
  type ContributionIr,
  type Diagnostic,
} from "./dist/index.js";

export function lowerLiteral(source: string): ContributionIr {
  try {
    return lowerPetrinetText(source, "literal.petrinet");
  } catch (error) {
    if (error instanceof PetrinetDslError) {
      const diagnostic: Diagnostic = error.diagnostic;
      throw new Error(diagnostic.code);
    }
    throw error;
  }
}
