import {
  GRAMMAR_FILE_NAME,
  PlayError,
  grammarText,
  parsePlay,
  projectPlay,
  type Play,
} from "./dist/index.js";

export function readName(text: string): Play["name"] {
  try {
    const play = parsePlay(text, "consumer.play");
    return grammarText().includes(GRAMMAR_FILE_NAME) ? play.name : play.source;
  } catch (error) {
    if (error instanceof PlayError) {
      const projected = projectPlay(text);
      if (!projected.ok && projected.code === error.code) return error.code;
    }
    throw error;
  }
}
