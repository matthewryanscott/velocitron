import {
  compilePetrinetText,
  parseNet,
  type CompiledPetrinetDocument,
} from "./dist/index.js";

export function compileLiteral(source: string): CompiledPetrinetDocument {
  const compiled = compilePetrinetText(source, "literal.petrinet");
  if (compiled.documentKind === "net") {
    parseNet(compiled.document);
  }
  return compiled;
}
