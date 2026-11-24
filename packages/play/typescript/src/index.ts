/**
 * Parse a Velocitron `.play` document.
 *
 * The canonical grammar is `packages/play/VelocitronPlay.g4`. A checkout reads
 * that file. An installed package reads the copy beside this package, which
 * `tools/antlr.py` keeps identical.
 *
 * `parsePlay` lowers one play to an AST and reports `SC1xx`. It does not
 * check the play against a net, render a walkthrough, or draw a sequence
 * diagram. Those steps ship in `@velocitron/play-check`. Paired Graphviz
 * and PlantUML stay in the Python package.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { projectSource } from "./facts.js";
import type { PlayFacts, PlayFailure } from "./facts.js";

export const GRAMMAR_FILE_NAME = "VelocitronPlay.g4";

const here = dirname(fileURLToPath(import.meta.url));

function readGrammarText(): string {
  const canonical = resolve(here, `../../${GRAMMAR_FILE_NAME}`);
  const marker = resolve(here, "../../python/pyproject.toml");
  if (existsSync(marker) && existsSync(canonical)) {
    const text = readFileSync(marker, "utf8");
    if (text.includes('name = "velocitron-play"')) return readFileSync(canonical, "utf8");
  }
  const packaged = resolve(here, `../${GRAMMAR_FILE_NAME}`);
  if (!existsSync(packaged)) throw new Error("@velocitron/play grammar is not installed");
  return readFileSync(packaged, "utf8");
}

export function grammarText(): string {
  return readGrammarText();
}

export function projectPlay(text: string, sourceName?: string): PlayFacts & { ok: true } | PlayFailure {
  return projectSource(text, sourceName);
}

export { projectSource, playFacts } from "./facts.js";
export type { PathFact, PlayFacts, PlayFailure, StepFact, TokenFact } from "./facts.js";
export {
  TRUNK,
  PlayError,
  isNameRef,
  parsePlay,
} from "./language.js";
export type {
  ActorDecl,
  ActorKind,
  AdvanceBody,
  AssumeGuardBody,
  AssumePredicateBody,
  BoxDecl,
  Condition,
  ConditionKind,
  ExpectBody,
  FireBody,
  InjectBody,
  Json,
  JsonObject,
  NameRef,
  OutputClause,
  Play,
  PlayPath,
  Position,
  RefineDecl,
  SequenceMode,
  ShareDecl,
  ShowDecl,
  Step,
  StepBody,
  StepKind,
  TokenExpr,
  TokenLiteral,
  UpdateBody,
  UseDecl,
  WalkScope,
  WireDecl,
  WithClause,
} from "./language.js";
