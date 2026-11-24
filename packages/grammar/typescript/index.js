/**
 * Parse a Velocitron `.petrinet` document.
 *
 * A checkout reads packages/grammar/VelocitronPetriNet.g4. An installed
 * package reads the copy beside this file, which tools/antlr.py keeps
 * identical to that grammar.
 *
 * parsePetrinet is a syntax parse of a net or composition document. It does
 * not lower contributions, compile CEL, resolve IR, or merge a composition.
 * Those steps stay in the language implementations. The `.play` grammar
 * lives in `packages/play`, not in this package.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { CharStreams, CommonTokenStream, ErrorListener } from "antlr4";
import VelocitronPetriNetLexer from "./dist/generated/VelocitronPetriNetLexer.js";
import VelocitronPetriNetParser from "./dist/generated/VelocitronPetriNetParser.js";

export const GRAMMAR_FILE_NAME = "VelocitronPetriNet.g4";

const SOURCE_MESSAGE = "source must be strict UTF-8 text without a BOM or bare CR";
const MISSING_NAME = "header is missing a name";
const BAD_STRING = "header name is not a JSON string";

const here = dirname(fileURLToPath(import.meta.url));

class CollectingListener extends ErrorListener {
  constructor() {
    super();
    this.errors = [];
  }

  syntaxError(_recognizer, _offendingSymbol, line, column, message) {
    this.errors.push({
      line,
      column: column + 1,
      message,
    });
  }
}

function readGrammarText() {
  const canonical = resolve(here, `../${GRAMMAR_FILE_NAME}`);
  const pythonMarker = resolve(here, "../python/pyproject.toml");
  if (existsSync(pythonMarker) && existsSync(canonical)) {
    const marker = readFileSync(pythonMarker, "utf8");
    if (marker.includes('name = "velocitron-grammar"')) {
      return readFileSync(canonical, "utf8");
    }
  }
  const packaged = resolve(here, GRAMMAR_FILE_NAME);
  if (!existsSync(packaged)) {
    throw new Error("@velocitron/grammar grammar is not installed");
  }
  return readFileSync(packaged, "utf8");
}

const grammarSource = readGrammarText();

export class PetrinetParseError extends Error {
  /**
   * @param {string} message
   * @param {number} line 1-based line
   * @param {number} column 1-based column
   */
  constructor(message, line, column) {
    super(message);
    this.name = "PetrinetParseError";
    this.line = line;
    this.column = column;
  }
}

function rejectIllegalSource(text) {
  const bareCr = text.replaceAll("\r\n", "").includes("\r");
  let surrogate = false;
  for (const character of text) {
    const code = character.codePointAt(0) ?? 0;
    if (code >= 0xd800 && code <= 0xdfff) {
      surrogate = true;
      break;
    }
  }
  if (text.startsWith("\uFEFF") || bareCr || surrogate) {
    throw new PetrinetParseError(SOURCE_MESSAGE, 1, 1);
  }
}

function decodeName(text) {
  if (typeof text !== "string" || text.length === 0) {
    throw new PetrinetParseError(MISSING_NAME, 1, 1);
  }
  if (text.startsWith('"')) {
    let decoded;
    try {
      decoded = JSON.parse(text);
    } catch {
      throw new PetrinetParseError(BAD_STRING, 1, 1);
    }
    if (typeof decoded !== "string") {
      throw new PetrinetParseError(BAD_STRING, 1, 1);
    }
    return decoded;
  }
  return text;
}

/**
 * @param {string} text
 * @param {string} [sourceName]
 * @returns {import("./index.js").PetrinetParse}
 */
export function parsePetrinet(text, sourceName = "<memory>") {
  if (typeof text !== "string") {
    throw new TypeError("petrinet source must be a string");
  }
  if (typeof sourceName !== "string") {
    throw new TypeError("source name must be a string");
  }
  rejectIllegalSource(text);
  const lexer = new VelocitronPetriNetLexer(CharStreams.fromString(text));
  const listener = new CollectingListener();
  lexer.removeErrorListeners();
  lexer.addErrorListener(listener);
  const stream = new CommonTokenStream(lexer);
  const parser = new VelocitronPetriNetParser(stream);
  parser.removeErrorListeners();
  parser.addErrorListener(listener);
  const tree = parser.document();
  stream.fill();
  if (listener.errors.length > 0) {
    const error = listener.errors[0];
    throw new PetrinetParseError(error.message, error.line, error.column);
  }
  const composition = tree.compositionHeader();
  if (composition != null) {
    return {
      kind: "composition",
      name: decodeName(composition.name()?.getText()),
      sourceName,
      tree,
    };
  }
  const header = tree.netHeader();
  return {
    kind: "net",
    name: header == null ? "unnamed" : decodeName(header.name()?.getText()),
    sourceName,
    tree,
  };
}

export function grammarText() {
  return grammarSource;
}
