import {
  GRAMMAR_FILE_NAME,
  grammarText,
  parsePetrinet,
  type PetrinetParse,
} from "./index.js";

export function readKind(text: string): PetrinetParse["kind"] {
  const parsed = parsePetrinet(text, "consumer.petrinet");
  return parsed.name.length >= 0 && grammarText().includes(GRAMMAR_FILE_NAME)
    ? parsed.kind
    : parsePetrinet("").kind;
}
