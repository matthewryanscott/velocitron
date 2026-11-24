export const GRAMMAR_FILE_NAME: "VelocitronPetriNet.g4";

export type PetrinetDocumentKind = "net" | "composition";

export interface PetrinetParse {
  readonly kind: PetrinetDocumentKind;
  readonly name: string;
  readonly sourceName: string;
  /** ANTLR `document` rule context for this grammar. */
  readonly tree: object;
}

export class PetrinetParseError extends Error {
  readonly line: number;
  readonly column: number;
  constructor(message: string, line: number, column: number);
}

export function parsePetrinet(text: string, sourceName?: string): PetrinetParse;
export function grammarText(): string;
