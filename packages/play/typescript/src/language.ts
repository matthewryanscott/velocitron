/**
 * Lower one `.play` source to a play AST.
 *
 * The statement syntax is the ANTLR grammar `packages/play/VelocitronPlay.g4`.
 * A layout pass, outside that grammar, splits column-0 statements, indented
 * continuations, `///` prose, and `//` comments. This module reports `SC1xx`
 * only. Checking a play against a net ships in `@velocitron/play-check`.
 */

import {
  CharStreams,
  CommonTokenStream,
  Token,
} from "antlr4";
import type {
  ErrorListener,
  ParserRuleContext,
  RecognitionException,
  Recognizer,
  TerminalNode,
} from "antlr4";

import VelocitronPlayLexer from "./generated/VelocitronPlayLexer.js";
import VelocitronPlayParser, {
  ColorContext,
  ColorNotSequenceContext,
} from "./generated/VelocitronPlayParser.js";
import type {
  AdvanceBodyContext,
  AssumeBodyContext,
  ConditionContext,
  FieldPathContext,
  HeaderContext,
  JsonObjectContext,
  NameContext,
  OutputClauseContext,
  PlaceContext,
  StatementContext,
  StepContext,
  TimeValueContext,
  TokenExprContext,
  TokenListContext,
  TransitionContext,
  TruthValueContext,
  WireEndContext,
  WithClauseContext,
} from "./generated/VelocitronPlayParser.js";

export const TRUNK = "trunk";

export type WalkScope = "step" | "neighbors" | "subnet";
export type SequenceMode = "beside" | "only";
export type ActorKind = "person" | "system" | "record";
export type StepKind = "inject" | "update" | "advance" | "fire" | "expect" | "assume";
export type ConditionKind =
  | "equals"
  | "empty"
  | "count"
  | "has"
  | "enabled"
  | "not-enabled"
  | "next"
  | "quiescent";

export interface Position {
  readonly line: number;
  readonly column: number;
}

export type Json =
  | null
  | boolean
  | number
  | string
  | Json[]
  | { readonly [key: string]: Json };

export type JsonObject = { [key: string]: Json };

export interface NameRef {
  readonly name: string;
  readonly position: Position;
}

export interface TokenLiteral {
  readonly color: string | null;
  readonly data: JsonObject;
  readonly position: Position;
}

export type TokenExpr = NameRef | TokenLiteral;

export interface InjectBody {
  readonly place: NameRef;
  readonly tokens: readonly TokenExpr[];
}

export interface UpdateBody {
  readonly place: NameRef;
  readonly token: TokenExpr;
}

export interface AdvanceBody {
  readonly place: NameRef | null;
  readonly seconds: number;
  readonly relative: boolean;
}

export interface WithClause {
  readonly place: NameRef;
  readonly subset?: JsonObject;
  readonly template?: NameRef;
  readonly index?: number;
}

export interface OutputClause {
  readonly place: NameRef;
  readonly tokens: readonly TokenExpr[];
  readonly merge?: JsonObject;
  readonly nothing: boolean;
}

export interface FireBody {
  readonly transition: NameRef;
  readonly withs: readonly WithClause[];
  readonly outputs: readonly OutputClause[];
}

export interface Condition {
  readonly kind: ConditionKind;
  readonly text: string;
  readonly position: Position;
  readonly place: NameRef | null;
  readonly tokens: readonly TokenExpr[];
  readonly count: number | null;
  readonly transitions: readonly NameRef[];
}

export interface ExpectBody {
  readonly conditions: readonly Condition[];
}

export interface AssumeGuardBody {
  readonly transition: NameRef;
  readonly value: boolean;
}

export interface AssumePredicateBody {
  readonly predicate: string;
  readonly value: boolean;
  readonly position: Position;
}

export type StepBody =
  | InjectBody
  | UpdateBody
  | AdvanceBody
  | FireBody
  | ExpectBody
  | AssumeGuardBody
  | AssumePredicateBody;

export interface Step {
  readonly kind: StepKind;
  readonly body: StepBody;
  readonly statement: string;
  readonly position: Position;
  readonly label: string | null;
  readonly title: string | null;
  readonly prose: string;
}

export interface PlayPath {
  readonly name: string;
  readonly position: Position;
  readonly title: string | null;
  readonly prose: string;
  readonly fromLabel: NameRef | null;
  readonly steps: readonly Step[];
  readonly sequence: SequenceMode | null;
}

export interface ActorDecl {
  readonly name: string;
  readonly kind: ActorKind;
  readonly position: Position;
}

export interface BoxDecl {
  readonly title: string;
  readonly members: readonly string[];
  readonly position: Position;
}

export interface UseDecl {
  readonly ref: string;
  readonly alias: string;
  readonly position: Position;
}

export interface WireDecl {
  readonly fromAlias: string;
  readonly fromPlace: string;
  readonly toAlias: string;
  readonly toPlace: string;
  readonly position: Position;
}

export interface RefineDecl {
  readonly alias: string;
  readonly transition: string;
  readonly by: string;
  readonly position: Position;
}

export interface ShareDecl {
  readonly members: readonly (readonly [string, string])[];
  readonly position: Position;
}

export interface ShowDecl {
  readonly color: string;
  readonly fields: readonly string[];
  readonly position: Position;
}

export interface Play {
  readonly name: string;
  readonly source: string;
  readonly position: Position;
  readonly title: string | null;
  readonly prose: string;
  readonly net: string | null;
  readonly marking: string;
  readonly scope: WalkScope | null;
  readonly sequence: SequenceMode | null;
  readonly instance: TokenExpr | null;
  readonly templates: ReadonlyMap<string, TokenLiteral>;
  readonly paths: readonly PlayPath[];
  readonly uses: readonly UseDecl[];
  readonly wires: readonly WireDecl[];
  readonly refines: readonly RefineDecl[];
  readonly shares: readonly ShareDecl[];
  readonly shows: readonly ShowDecl[];
  readonly actors: readonly ActorDecl[];
  readonly boxes: readonly BoxDecl[];
}

export class PlayError extends Error {
  readonly code: string;
  readonly line: number;
  readonly column: number;

  constructor(code: string, message: string, line: number, column: number) {
    super(message);
    this.name = "PlayError";
    this.code = code;
    this.line = line;
    this.column = column;
  }
}

const PLAIN_NUMBER = /^[0-9]+(?:\.[0-9]+)?$/;
const INTEGER = /^[0-9]+$/;
const DURATION =
  /^(?:(?<d>[0-9]+(?:\.[0-9]+)?)d)?(?:(?<h>[0-9]+(?:\.[0-9]+)?)h)?(?:(?<m>[0-9]+(?:\.[0-9]+)?)m)?(?:(?<s>[0-9]+(?:\.[0-9]+)?)s)?$/;

interface SyntaxError {
  readonly line: number;
  readonly column: number;
  readonly message: string;
  readonly symbol: Token | number | undefined;
}

class CollectingListener implements ErrorListener<Token | number> {
  readonly errors: SyntaxError[] = [];

  syntaxError(
    _recognizer: Recognizer<Token | number>,
    offendingSymbol: Token | number | undefined,
    line: number,
    column: number,
    message: string,
    _exception: RecognitionException | undefined,
  ): void {
    this.errors.push({
      line,
      column,
      message,
      symbol: offendingSymbol,
    });
  }
}

class Source {
  readonly text: string;
  readonly name: string;
  readonly lineStarts: number[];

  constructor(text: string, name: string) {
    this.text = text;
    this.name = name;
    this.lineStarts = [0];
    for (let index = 0; index < text.length; index += 1) {
      if (text[index] === "\n") this.lineStarts.push(index + 1);
    }
  }

  position(offset: number): Position {
    const bounded = Math.min(Math.max(offset, 0), this.text.length);
    const line = bisectRight(this.lineStarts, bounded);
    const start = this.lineStarts[line - 1] ?? 0;
    return { line, column: bounded - start + 1 };
  }

  error(code: string, message: string, offset: number): PlayError {
    const position = this.position(offset);
    return new PlayError(code, message, position.line, position.column);
  }
}

interface PathBuilder {
  name: string;
  position: Position;
  title: string | null;
  prose: string[];
  fromLabel: NameRef | null;
  steps: Step[];
  sequence: SequenceMode | null;
}

interface HeaderState {
  name: string;
  title: string | null;
  position: Position;
  net?: string;
  sequence?: SequenceMode;
  instance?: TokenExpr;
  scope?: WalkScope;
  marking?: string;
}

function bisectRight(starts: number[], offset: number): number {
  let lo = 0;
  let hi = starts.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((starts[mid] ?? 0) <= offset) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function asSeconds(value: number): number {
  if (!Number.isFinite(value)) throw new Error("non-finite time");
  return Number.isInteger(value) ? value : value;
}

function durationSeconds(text: string): number {
  const match = DURATION.exec(text);
  const groups = match?.groups;
  if (match == null || groups == null || !Object.values(groups).some((part) => part != null)) {
    throw new Error("invalid duration");
  }
  const units: Record<string, number> = { d: 86400, h: 3600, m: 60, s: 1 };
  let total = 0;
  for (const [unit, scale] of Object.entries(units)) {
    const part = groups[unit];
    if (part != null) total += Number(part) * scale;
  }
  return asSeconds(total);
}

function collapsed(text: string, start: number, stop: number): string {
  return text.slice(start, stop).split(/\s+/).filter((part) => part.length > 0).join(" ");
}

function proseText(line: string): string {
  const body = line.slice(3);
  return body.startsWith(" ") ? body.slice(1) : body;
}

function isToken(symbol: Token | number | undefined): symbol is Token {
  return typeof symbol === "object" && symbol != null;
}

function symbolStart(symbol: Token | number | undefined): number | null {
  if (!isToken(symbol) || symbol.start < 0) return null;
  return symbol.start;
}

function nodeStart(node: ParserRuleContext | TerminalNode): number {
  if ("symbol" in node && node.symbol != null && node.symbol.start >= 0) {
    return node.symbol.start;
  }
  if (!("symbol" in node) && node.start != null && node.start.start >= 0) {
    return node.start.start;
  }
  throw new Error("missing token start");
}

function chunkOffset(chunk: string, line: number, column: number): number {
  let offset = 0;
  let current = 1;
  while (current < line) {
    const newline = chunk.indexOf("\n", offset);
    if (newline < 0) return chunk.length;
    offset = newline + 1;
    current += 1;
  }
  return Math.min(chunk.length, offset + column);
}

type LayoutItem = ["prose" | "blank" | "statement", number, number];

function statements(source: Source): LayoutItem[] {
  const text = source.text;
  const items: LayoutItem[] = [];
  let current: [number, number] | null = null;
  let blankAfter: [number, number] | null = null;
  for (const lineStart of source.lineStarts) {
    if (lineStart >= text.length && lineStart > 0) break;
    const newline = text.indexOf("\n", lineStart);
    const lineEnd = newline < 0 ? text.length : newline;
    const line = text.slice(lineStart, lineEnd);
    if (line.trim().length === 0) {
      if (current == null) items.push(["blank", lineStart, lineEnd]);
      else if (blankAfter == null) blankAfter = [lineStart, lineEnd];
      continue;
    }
    const first = line[0];
    if (first === " " || first === "\t") {
      if (current != null) {
        current[1] = lineEnd;
        blankAfter = null;
        continue;
      }
      throw source.error("SC101", "a statement must start at column 0", lineStart);
    }
    if (current != null) {
      items.push(["statement", current[0], current[1]]);
      current = null;
      if (blankAfter != null) {
        items.push(["blank", blankAfter[0], blankAfter[1]]);
        blankAfter = null;
      }
    }
    if (line.startsWith("///")) items.push(["prose", lineStart, lineEnd]);
    else if (line.startsWith("//")) continue;
    else current = [lineStart, lineEnd];
  }
  if (current != null) items.push(["statement", current[0], current[1]]);
  return items;
}

function channelTokens(chunk: string): Token[] {
  const lexer = new VelocitronPlayLexer(CharStreams.fromString(chunk));
  lexer.removeErrorListeners();
  const stream = new CommonTokenStream(lexer);
  stream.fill();
  return stream.tokens.filter(
    (token): token is Token =>
      token.channel === Token.DEFAULT_CHANNEL && token.type !== Token.EOF,
  );
}

function badAdvanceOffset(chunk: string): number | null {
  const tokens = channelTokens(chunk);
  const first = tokens[0];
  if (first == null || first.type !== VelocitronPlayParser.ADVANCE) return null;
  let index = 1;
  const open = tokens[index];
  if (open != null && open.type === VelocitronPlayParser.LPAREN) {
    index += 1;
    while (index < tokens.length && tokens[index]?.type !== VelocitronPlayParser.RPAREN) {
      index += 1;
    }
    if (index >= tokens.length) return null;
    index += 1;
  }
  if (tokens[index]?.type === VelocitronPlayParser.PLUS) index += 1;
  if (index >= tokens.length) return tokens[tokens.length - 1]?.start ?? 0;
  const token = tokens[index];
  if (token == null) return null;
  if (token.type === VelocitronPlayParser.DURATION) return null;
  if (token.type === VelocitronPlayParser.NUMBER && PLAIN_NUMBER.test(token.text ?? "")) {
    return null;
  }
  return token.start;
}

const PLAY_HEADER_NAME = /^play[ \t]+([^\s"]\S*)/;

/**
 * The offset of the first character a header's play name may not hold, and
 * the identifier to write instead; null for any other statement. Play files
 * are kebab-case, so `play step-warning` is the likely slip.
 */
function badPlayName(chunk: string): [number, string] | null {
  const match = PLAY_HEADER_NAME.exec(chunk);
  if (match == null) return null;
  const name = (match[1] ?? "").split("//", 1)[0] ?? "";
  if (name.length === 0) return null;
  const bad = /[^A-Za-z0-9_]/.exec(name);
  let index: number;
  if (bad != null) index = bad.index;
  else if (/^[0-9]/.test(name)) index = 0;
  else return null;
  let suggestion = name.replace(/[^A-Za-z0-9_]/g, "_");
  if (/^[0-9]/.test(suggestion)) suggestion = `_${suggestion}`;
  return [match[0].length - (match[1] ?? "").length + index, suggestion];
}

function isJsonObject(value: Json): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function parseJson(text: string): Json {
  let index = 0;
  function fail(message: string): never {
    throw new Error(message);
  }
  const skip = (): void => {
    while (index < text.length && " \t\r\n".includes(text[index] ?? "")) index += 1;
  };
  const parseString = (): string => {
    if (text[index] !== '"') fail("Expecting string");
    index += 1;
    let out = "";
    while (index < text.length) {
      const character = text[index] ?? "";
      if (character === '"') {
        index += 1;
        return out;
      }
      if (character === "\\") {
        index += 1;
        const escaped = text[index] ?? "";
        index += 1;
        if (escaped === '"' || escaped === "\\" || escaped === "/") out += escaped;
        else if (escaped === "b") out += "\b";
        else if (escaped === "f") out += "\f";
        else if (escaped === "n") out += "\n";
        else if (escaped === "r") out += "\r";
        else if (escaped === "t") out += "\t";
        else if (escaped === "u") {
          const hex = text.slice(index, index + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("Invalid \\u escape");
          out += String.fromCharCode(Number.parseInt(hex, 16));
          index += 4;
        } else fail(`Invalid \\escape: ${escaped}`);
        continue;
      }
      if (character < " ") fail("Invalid control character");
      out += character;
      index += 1;
    }
    fail("Unterminated string");
  };
  const parseNumber = (): number => {
    const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(text.slice(index));
    if (match == null) fail("Expecting number");
    const literal = match[0] ?? "";
    index += literal.length;
    const value = Number(literal);
    if (!Number.isFinite(value)) {
      fail(`non-finite number ${value > 0 ? "Infinity" : "-Infinity"}`);
    }
    return value;
  };
  const parseValue = (): Json => {
    skip();
    const character = text[index];
    if (character === '"') return parseString();
    if (character === "{") return parseObject();
    if (character === "[") return parseArray();
    if (text.startsWith("true", index)) {
      index += 4;
      return true;
    }
    if (text.startsWith("false", index)) {
      index += 5;
      return false;
    }
    if (text.startsWith("null", index)) {
      index += 4;
      return null;
    }
    if (character === "-" || (character != null && character >= "0" && character <= "9")) {
      return parseNumber();
    }
    fail("Expecting value");
  };
  const parseObject = (): JsonObject => {
    index += 1;
    const result: JsonObject = {};
    skip();
    if (text[index] === "}") {
      index += 1;
      return result;
    }
    while (index < text.length) {
      skip();
      const key = parseString();
      skip();
      if (text[index] !== ":") fail("Expecting ':' delimiter");
      index += 1;
      const value = parseValue();
      if (Object.hasOwn(result, key)) fail(`duplicate key ${JSON.stringify(key)}`);
      result[key] = value;
      skip();
      if (text[index] === ",") {
        index += 1;
        continue;
      }
      if (text[index] === "}") {
        index += 1;
        return result;
      }
      fail("Expecting ',' delimiter");
    }
    fail("Unterminated object");
  };
  const parseArray = (): Json[] => {
    index += 1;
    const result: Json[] = [];
    skip();
    if (text[index] === "]") {
      index += 1;
      return result;
    }
    while (index < text.length) {
      result.push(parseValue());
      skip();
      if (text[index] === ",") {
        index += 1;
        continue;
      }
      if (text[index] === "]") {
        index += 1;
        return result;
      }
      fail("Expecting ',' delimiter");
    }
    fail("Unterminated array");
  };
  skip();
  const value = parseValue();
  skip();
  if (index !== text.length) fail("Extra data");
  return value;
}

function isTemplate(token: TokenExpr): token is NameRef {
  return "name" in token;
}

class Statement {
  readonly source: Source;
  readonly base: number;
  readonly chunk: string;
  readonly tree: StatementContext;

  constructor(source: Source, start: number, end: number) {
    this.source = source;
    this.base = start;
    this.chunk = source.text.slice(start, end);
    const listener = new CollectingListener();
    const lexer = new VelocitronPlayLexer(CharStreams.fromString(this.chunk));
    lexer.removeErrorListeners();
    lexer.addErrorListener(listener);
    const stream = new CommonTokenStream(lexer);
    const parser = new VelocitronPlayParser(stream);
    parser.removeErrorListeners();
    parser.addErrorListener(listener);
    const tree = parser.statement();
    const failure = listener.errors[0];
    if (failure != null) {
      const advance = badAdvanceOffset(this.chunk);
      if (advance != null) {
        throw this.error("SC103", "expected seconds or a duration such as `90m`", advance);
      }
      const named = badPlayName(this.chunk);
      if (named != null) {
        throw this.error(
          "SC101",
          `a play name is an identifier (letters, digits, \`_\`): write \`${named[1]}\``,
          named[0],
        );
      }
      const offset = symbolStart(failure.symbol) ?? chunkOffset(this.chunk, failure.line, failure.column);
      throw this.error("SC101", failure.message, offset);
    }
    this.tree = tree;
  }

  error(code: string, message: string, chunkOffsetValue: number): PlayError {
    return this.source.error(code, message, this.base + chunkOffsetValue);
  }

  position(chunkOffsetValue: number): Position {
    return this.source.position(this.base + chunkOffsetValue);
  }

  string(node: TerminalNode | null, what: string): string {
    if (node == null) throw this.error("SC101", `${what} must be a string`, 0);
    const offset = nodeStart(node);
    let value: unknown;
    try {
      value = JSON.parse(node.getText());
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw this.error("SC102", `invalid JSON in ${what}: ${message}`, offset);
    }
    if (typeof value !== "string") throw this.error("SC101", `${what} must be a string`, offset);
    return value;
  }

  jsonObject(ctx: JsonObjectContext | null, what: string): JsonObject {
    if (ctx?.start == null || ctx.stop == null) {
      throw this.error("SC102", `invalid JSON in ${what}: missing object`, 0);
    }
    const offset = ctx.start.start;
    const raw = this.chunk.slice(offset, ctx.stop.stop + 1);
    let value: Json;
    try {
      value = parseJson(raw);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw this.error("SC102", `invalid JSON in ${what}: ${message}`, offset);
    }
    if (!isJsonObject(value)) throw this.error("SC102", `${what} must be a JSON object`, offset);
    return value;
  }

  tight(ctx: ParserRuleContext | null): string {
    if (ctx?.start == null || ctx.stop == null) {
      throw this.error("SC101", "a name cannot contain whitespace", 0);
    }
    const raw = this.chunk.slice(ctx.start.start, ctx.stop.stop + 1);
    if ([...raw].some((character) => /\s/.test(character)) || raw.includes("//")) {
      throw this.error("SC101", "a name cannot contain whitespace", ctx.start.start);
    }
    return raw;
  }

  single(ctx: ParserRuleContext | null): string {
    if (ctx == null) throw this.error("SC101", "expected a name", 0);
    return ctx.getText();
  }

  nameText(ctx: NameContext | FieldPathContext | null, what: string): string {
    if (ctx == null) throw this.error("SC101", `expected ${what}`, 0);
    const quoted = ctx.STRING();
    if (quoted != null) return this.string(quoted, what);
    return this.tight(ctx.qualifiedName());
  }

  nameRef(ctx: NameContext | null, what: string): NameRef {
    if (ctx?.start == null) throw this.error("SC101", `expected ${what}`, 0);
    return { name: this.nameText(ctx, what), position: this.position(ctx.start.start) };
  }

  place(ctx: PlaceContext | null): NameRef {
    const qualified = ctx?.qualifiedName() ?? null;
    if (qualified?.start == null) throw this.error("SC101", "expected a place", 0);
    return { name: this.tight(qualified), position: this.position(qualified.start.start) };
  }

  transition(ctx: TransitionContext | null): NameRef {
    const qualified = ctx?.qualifiedName() ?? null;
    if (qualified?.start == null) throw this.error("SC101", "expected a transition", 0);
    return { name: this.tight(qualified), position: this.position(qualified.start.start) };
  }

  color(ctx: ColorContext | ColorNotSequenceContext | null, what: string): string {
    if (ctx == null) throw this.error("SC101", `expected ${what}`, 0);
    const quoted = ctx.STRING();
    if (quoted != null) return this.string(quoted, what);
    if (ctx instanceof ColorNotSequenceContext) return this.single(ctx.singleNameNotSequence());
    return this.single(ctx.singleName());
  }

  field(ctx: FieldPathContext | null): string {
    if (ctx == null) throw this.error("SC101", "expected a field name", 0);
    let path: string;
    let offset: number;
    const quoted = ctx.STRING();
    if (quoted != null) {
      path = this.string(quoted, "a field name");
      offset = nodeStart(quoted);
    } else {
      path = this.tight(ctx.qualifiedName());
      offset = ctx.start?.start ?? 0;
    }
    if (path.length === 0 || path.split(".").some((key) => key.length === 0)) {
      throw this.error("SC101", `invalid field path ${JSON.stringify(path)}`, offset);
    }
    return path;
  }

  integer(node: TerminalNode | null, what: string): number {
    if (node == null) throw this.error("SC101", `expected ${what}`, 0);
    const text = node.getText();
    if (!INTEGER.test(text)) throw this.error("SC101", `expected ${what}`, nodeStart(node));
    return Number(text);
  }

  time(ctx: TimeValueContext | null): number {
    if (ctx == null || ctx.singleName() != null) {
      throw this.error(
        "SC103",
        "expected seconds or a duration such as `90m`",
        ctx?.start?.start ?? 0,
      );
    }
    const number = ctx.NUMBER();
    if (number != null) {
      const text = number.getText();
      if (!PLAIN_NUMBER.test(text)) {
        throw this.error("SC103", "expected seconds or a duration such as `90m`", nodeStart(number));
      }
      return asSeconds(Number(text));
    }
    try {
      return durationSeconds(ctx.DURATION()?.getText() ?? "");
    } catch {
      throw this.error(
        "SC103",
        "expected seconds or a duration such as `90m`",
        ctx.start?.start ?? 0,
      );
    }
  }

  token(ctx: TokenExprContext | null, what: string): TokenExpr {
    if (ctx?.start == null) throw this.error("SC101", `expected ${what}`, 0);
    const position = this.position(ctx.start.start);
    if (ctx.DOLLAR() != null) return { name: this.single(ctx.singleName()), position };
    const data = this.jsonObject(ctx.jsonObject(), what);
    if (ctx.color() == null) return { color: null, data, position };
    return { color: this.color(ctx.color(), "a color"), data, position };
  }

  tokens(ctx: TokenListContext | null, what: string): TokenExpr[] {
    if (ctx == null) return [];
    return ctx.tokenExpr_list().map((token) => this.token(token, what));
  }

  wireEnd(ctx: WireEndContext | null): [string, string] {
    if (ctx == null) throw this.error("SC101", "expected a wire end", 0);
    return [this.single(ctx.singleName()), this.place(ctx.place()).name];
  }

  condition(ctx: ConditionContext | null): Condition {
    if (ctx?.start == null || ctx.stop == null) throw this.error("SC101", "expected a condition", 0);
    const position = this.position(ctx.start.start);
    const text = collapsed(this.chunk, ctx.start.start, ctx.stop.stop + 1);
    if (ctx.EQ() != null) {
      return {
        kind: "equals",
        text,
        position,
        place: this.place(ctx.place()),
        tokens: this.tokens(ctx.tokenList(), "token data"),
        count: null,
        transitions: [],
      };
    }
    if (ctx.EMPTY() != null) {
      return {
        kind: "empty",
        text,
        position,
        place: this.place(ctx.place()),
        tokens: [],
        count: null,
        transitions: [],
      };
    }
    if (ctx.COUNT() != null) {
      return {
        kind: "count",
        text,
        position,
        place: this.place(ctx.place()),
        tokens: [],
        count: this.integer(ctx.NUMBER(), "a token count"),
        transitions: [],
      };
    }
    if (ctx.HAS() != null) {
      return {
        kind: "has",
        text,
        position,
        place: this.place(ctx.place()),
        tokens: [this.token(ctx.tokenExpr(), "token data")],
        count: null,
        transitions: [],
      };
    }
    const transitions = ctx.transition_list().map((item) => this.transition(item));
    let kind: ConditionKind = "quiescent";
    if (ctx.NOT() != null) kind = "not-enabled";
    else if (ctx.ENABLED() != null) kind = "enabled";
    else if (ctx.NEXT() != null) kind = "next";
    return { kind, text, position, place: null, tokens: [], count: null, transitions };
  }

  withClause(ctx: WithClauseContext | null): WithClause {
    const place = this.place(ctx?.place() ?? null);
    if (ctx != null && ctx.DOLLAR() != null) {
      const name = ctx.singleName();
      return {
        place,
        template: {
          name: this.single(name),
          position: this.position(name?.start?.start ?? 0),
        },
      };
    }
    if (ctx != null && ctx.HASH() != null) {
      return { place, index: this.integer(ctx.NUMBER(), "a token index") };
    }
    return { place, subset: this.jsonObject(ctx?.jsonObject() ?? null, "a subset") };
  }

  output(ctx: OutputClauseContext | null): OutputClause {
    const place = this.place(ctx?.place() ?? null);
    if (ctx != null && ctx.NOTHING() != null) return { place, tokens: [], nothing: true };
    if (ctx != null && ctx.PLUS() != null) {
      return {
        place,
        tokens: [],
        merge: this.jsonObject(ctx.jsonObject(), "the merged fields"),
        nothing: false,
      };
    }
    return { place, tokens: this.tokens(ctx?.tokenList() ?? null, "token data"), nothing: false };
  }

  truth(ctx: TruthValueContext | null): boolean {
    const word = ctx?.getText() ?? "";
    if (word === "true" || word === "false") return word === "true";
    throw this.error("SC101", "expected `true` or `false`", ctx?.start?.start ?? 0);
  }

  step(ctx: StepContext | null): Step {
    if (ctx == null) throw this.error("SC101", "expected a play statement", 0);
    const bodyCtx = ctx.stepBody();
    const labelCtx = ctx.label();
    const label = labelCtx == null ? null : this.single(labelCtx.singleName());
    let title: string | null = null;
    let bodyEnd = this.chunk.length;
    const titleNode = ctx.STRING();
    if (titleNode != null) {
      title = this.string(titleNode, "the step title");
      bodyEnd = nodeStart(titleNode);
    }
    const bodyStart = bodyCtx?.start?.start ?? 0;
    let kind: StepKind;
    let body: StepBody;
    const inject = bodyCtx?.injectBody() ?? null;
    const update = bodyCtx?.updateBody() ?? null;
    const advance = bodyCtx?.advanceBody() ?? null;
    const fire = bodyCtx?.fireBody() ?? null;
    const expect = bodyCtx?.expectBody() ?? null;
    if (inject != null) {
      body = { place: this.place(inject.place()), tokens: this.tokens(inject.tokenList(), "token data") };
      kind = "inject";
    } else if (update != null) {
      body = { place: this.place(update.place()), token: this.token(update.tokenExpr(), "token data") };
      kind = "update";
    } else if (advance != null) {
      body = this.advance(advance);
      kind = "advance";
    } else if (fire != null) {
      body = {
        transition: this.transition(fire.transition()),
        withs: fire.withClause_list().map((item) => this.withClause(item)),
        outputs: fire.outputClause_list().map((item) => this.output(item)),
      };
      kind = "fire";
    } else if (expect != null) {
      body = { conditions: expect.condition_list().map((item) => this.condition(item)) };
      kind = "expect";
    } else {
      body = this.assume(bodyCtx?.assumeBody() ?? null, bodyStart);
      kind = "assume";
    }
    return {
      kind,
      body,
      statement: collapsed(this.chunk, bodyStart, bodyEnd),
      position: this.position(0),
      label,
      title,
      prose: "",
    };
  }

  private advance(ctx: AdvanceBodyContext): AdvanceBody {
    return {
      place: ctx.place() == null ? null : this.place(ctx.place()),
      seconds: this.time(ctx.timeValue()),
      relative: ctx.PLUS() != null,
    };
  }

  private assume(ctx: AssumeBodyContext | null, bodyStart: number): AssumeGuardBody | AssumePredicateBody {
    if (ctx == null) throw this.error("SC101", "expected an assume statement", bodyStart);
    if (ctx.PREDICATE() != null) {
      const quoted = ctx.STRING();
      return {
        predicate: this.string(quoted, "a predicate handler ref"),
        value: this.truth(ctx.truthValue()),
        position: this.position(quoted == null ? bodyStart : nodeStart(quoted)),
      };
    }
    return { transition: this.transition(ctx.transition()), value: this.truth(ctx.truthValue()) };
  }
}

function withProse(step: Step, prose: string): Step {
  return { ...step, prose };
}

function present<T>(value: T | null | undefined): value is T {
  return value != null;
}

/**
 * Parse `.play` source text. Throws {@link PlayError} for `SC1xx`.
 *
 * `sourceName` names the file in diagnostics. The statement syntax is
 * `VelocitronPlay.g4`; this function also applies the line discipline and
 * the `SC104` / `SC105` rules.
 */
export function parsePlay(text: string, sourceName = "<memory>"): Play {
  const source = new Source(text, sourceName);
  let header: HeaderState | null = null;
  const headerProse: string[] = [];
  const uses: UseDecl[] = [];
  const wires: WireDecl[] = [];
  const refines: RefineDecl[] = [];
  const shares: ShareDecl[] = [];
  const shows: ShowDecl[] = [];
  const actors: ActorDecl[] = [];
  const boxes: BoxDecl[] = [];
  const templates = new Map<string, TokenLiteral>();
  const paths: PathBuilder[] = [];
  const labels = new Map<string, Position>();
  const pending: string[][] = [];
  let blockOpen = false;
  let afterHeaderLine = false;

  const takePending = (): string => {
    const textValue = pending.map((block) => block.join("\n")).join("\n\n");
    pending.length = 0;
    return textValue;
  };
  const scopeProse = (): string[] => {
    const last = paths[paths.length - 1];
    if (last == null || last.name === TRUNK) return headerProse;
    return last.prose;
  };
  const attachSettingProse = (): void => {
    if (pending.length > 0) scopeProse().push(takePending());
  };

  for (const [kind, start, end] of statements(source)) {
    if (kind === "blank") {
      blockOpen = false;
      afterHeaderLine = false;
      continue;
    }
    const lineText = source.text.slice(start, end);
    if (kind === "prose") {
      if (afterHeaderLine) {
        const blocks = scopeProse();
        const prose = proseText(lineText);
        if (blockOpen) {
          const last = blocks.length - 1;
          blocks[last] = `${blocks[last] ?? ""}\n${prose}`;
        } else blocks.push(prose);
        blockOpen = true;
        continue;
      }
      if (!blockOpen) pending.push([]);
      pending[pending.length - 1]?.push(proseText(lineText));
      blockOpen = true;
      continue;
    }
    blockOpen = false;
    afterHeaderLine = false;
    const parsed = new Statement(source, start, end);
    const tree = parsed.tree;
    if (header == null) {
      const headerCtx: HeaderContext | null = tree.header();
      if (headerCtx == null) {
        throw source.error("SC104", 'a play starts with `play NAME ["title"]`', start);
      }
      const title = headerCtx.STRING() == null ? null : parsed.string(headerCtx.STRING(), "the title");
      header = {
        name: parsed.single(headerCtx.singleName()),
        title,
        position: source.position(start),
      };
      const taken = takePending();
      if (taken) headerProse.push(taken);
      paths.push({
        name: TRUNK,
        position: header.position,
        title: null,
        prose: [],
        fromLabel: null,
        steps: [],
        sequence: null,
      });
      afterHeaderLine = true;
      continue;
    }
    if (present(tree.header())) {
      throw source.error("SC104", "a source holds one `play` header", start);
    }
    const sequence = tree.sequenceShow();
    if (present(sequence)) {
      const mode: SequenceMode = sequence.ONLY() != null ? "only" : "beside";
      const last = paths[paths.length - 1];
      if (last == null) throw source.error("SC104", "a play starts with `play NAME`", start);
      const branch = last.name === TRUNK ? null : last;
      const currentSequence = branch == null ? header.sequence : branch.sequence;
      if (currentSequence != null) {
        const scopeName = branch == null ? "the play" : `path ${branch.name}`;
        throw source.error("SC104", `${scopeName} names its sequence view twice`, start);
      }
      if (branch != null) branch.sequence = mode;
      else header.sequence = mode;
      attachSettingProse();
      continue;
    }
    const box = tree.boxSetting();
    if (present(box)) {
      const names = box.name_list();
      const title = parsed.nameText(names[0] ?? null, "the box title");
      const members = names.slice(1).map((name) => parsed.nameText(name, "a lifeline name"));
      const boxed = new Set(boxes.flatMap((declared) => declared.members));
      for (const member of members) {
        if (boxed.has(member) || members.filter((item) => item === member).length > 1) {
          throw source.error("SC105", `lifeline ${member} is in two boxes`, start);
        }
      }
      boxes.push({ title, members, position: source.position(start) });
      attachSettingProse();
      continue;
    }
    const actor = tree.actorSetting();
    if (present(actor)) {
      const kindCtx = actor.actorKind();
      if (kindCtx == null) throw source.error("SC101", "expected an actor kind", start);
      const actorKind: ActorKind =
        kindCtx.PERSON() != null ? "person" : kindCtx.SYSTEM() != null ? "system" : "record";
      const actorName = parsed.nameText(actor.name(), "an actor name");
      if (!actorName) throw source.error("SC101", "an actor name must not be empty", start);
      if (actors.some((declared) => declared.name === actorName)) {
        throw source.error("SC105", `actor ${actorName} is declared twice`, start);
      }
      actors.push({ name: actorName, kind: actorKind, position: source.position(start) });
      attachSettingProse();
      continue;
    }
    const net = tree.netSetting();
    if (present(net)) {
      if (header.net != null) throw source.error("SC104", "the play names its net twice", start);
      header.net = parsed.string(net.STRING(), "the net file");
      attachSettingProse();
      continue;
    }
    const use = tree.useSetting();
    if (present(use)) {
      const alias = parsed.single(use.singleName());
      if (uses.some((declared) => declared.alias === alias)) {
        throw source.error("SC105", `alias ${alias} is used twice`, start);
      }
      uses.push({
        ref: parsed.string(use.STRING(), "the net file"),
        alias,
        position: source.position(start),
      });
      attachSettingProse();
      continue;
    }
    const wire = tree.wireSetting();
    if (present(wire)) {
      const ends = wire.wireEnd_list();
      const [fromAlias, fromPlace] = parsed.wireEnd(ends[0] ?? null);
      const [toAlias, toPlace] = parsed.wireEnd(ends[1] ?? null);
      wires.push({ fromAlias, fromPlace, toAlias, toPlace, position: source.position(start) });
      attachSettingProse();
      continue;
    }
    const share = tree.shareSetting();
    if (present(share)) {
      shares.push({
        members: share.wireEnd_list().map((end) => parsed.wireEnd(end)),
        position: source.position(start),
      });
      attachSettingProse();
      continue;
    }
    const refine = tree.refineSetting();
    if (present(refine)) {
      const aliases = refine.singleName_list();
      refines.push({
        alias: parsed.single(aliases[0] ?? null),
        transition: parsed.transition(refine.transition()).name,
        by: parsed.single(aliases[1] ?? null),
        position: source.position(start),
      });
      attachSettingProse();
      continue;
    }
    const instance = tree.instanceSetting();
    if (present(instance)) {
      if (header.instance != null) {
        throw source.error("SC104", "the play names its instance twice", start);
      }
      header.instance = parsed.token(instance.tokenExpr(), "token data");
      attachSettingProse();
      continue;
    }
    const scopeCtx = tree.scopeSetting();
    if (present(scopeCtx)) {
      if (header.scope != null) throw source.error("SC104", "the play names its scope twice", start);
      header.scope =
        scopeCtx.STEP() != null ? "step" : scopeCtx.NEIGHBORS() != null ? "neighbors" : "subnet";
      attachSettingProse();
      continue;
    }
    const show = tree.colorShow();
    if (present(show)) {
      const color = parsed.color(show.colorNotSequence(), "a color");
      if (shows.some((declared) => declared.color === color)) {
        throw source.error("SC104", `the play shows color ${color} twice`, start);
      }
      const fields = show.fieldPath_list().map((fieldPath) => parsed.field(fieldPath));
      if (new Set(fields).size !== fields.length) {
        throw source.error("SC101", `\`show ${color}\` repeats a field`, start);
      }
      shows.push({ color, fields, position: source.position(start) });
      attachSettingProse();
      continue;
    }
    const marking = tree.markingSetting();
    if (present(marking)) {
      if (header.marking != null) {
        throw source.error("SC104", "the play names its marking twice", start);
      }
      header.marking = parsed.nameText(marking.name(), "`initial`, `none` or a marking name");
      attachSettingProse();
      continue;
    }
    const template = tree.templateDecl();
    if (present(template)) {
      const name = parsed.single(template.singleName());
      if (templates.has(name)) throw source.error("SC105", `template $${name} is defined twice`, start);
      const colorCtx = template.color();
      templates.set(name, {
        color: parsed.color(colorCtx, "a color"),
        data: parsed.jsonObject(template.jsonObject(), "template data"),
        position: parsed.position(colorCtx?.start?.start ?? 0),
      });
      attachSettingProse();
      continue;
    }
    const pathCtx = tree.pathDecl();
    if (present(pathCtx)) {
      const names = pathCtx.singleName_list();
      const name = parsed.single(names[0] ?? null);
      if (name === TRUNK || paths.some((path) => path.name === name)) {
        throw source.error(
          "SC105",
          `path name ${name} is already taken${name === TRUNK ? " (the first path is the trunk)" : ""}`,
          parsed.base + nodeStart(names[0] ?? pathCtx),
        );
      }
      const title = pathCtx.STRING() == null ? null : parsed.string(pathCtx.STRING(), "the title");
      const labelAt = pathCtx.AT();
      const fromLabel: NameRef = {
        name: parsed.single(names[1] ?? null),
        position: parsed.position(labelAt == null ? 0 : nodeStart(labelAt)),
      };
      const builder: PathBuilder = {
        name,
        position: source.position(start),
        title,
        prose: [],
        fromLabel,
        steps: [],
        sequence: null,
      };
      const prose = takePending();
      if (prose) builder.prose.push(prose);
      paths.push(builder);
      afterHeaderLine = true;
      continue;
    }
    const stepCtx = tree.step();
    if (stepCtx == null) throw source.error("SC101", "expected a play statement", start);
    let step = parsed.step(stepCtx);
    if (step.label != null) {
      if (labels.has(step.label)) {
        throw source.error("SC105", `label @${step.label} is used twice`, start);
      }
      labels.set(step.label, step.position);
    }
    const prose = takePending();
    if (prose) step = withProse(step, prose);
    const current = paths[paths.length - 1];
    if (current == null) throw source.error("SC104", "a play starts with `play NAME`", start);
    current.steps.push(step);
  }

  if (header == null) throw source.error("SC104", "a play starts with `play NAME`", 0);
  if (pending.length > 0) {
    const trailing = takePending();
    const scope = paths[paths.length - 1];
    if (scope == null) throw source.error("SC104", "a play starts with `play NAME`", 0);
    const last = scope.steps[scope.steps.length - 1];
    if (last != null) {
      scope.steps[scope.steps.length - 1] = withProse(
        last,
        last.prose ? `${last.prose}\n\n${trailing}` : trailing,
      );
    } else scopeProse().push(trailing);
  }
  return {
    name: header.name,
    source: sourceName,
    position: header.position,
    title: header.title,
    prose: headerProse.join("\n\n"),
    net: header.net ?? null,
    marking: header.marking ?? "initial",
    scope: header.scope ?? null,
    sequence: header.sequence ?? null,
    instance: header.instance ?? null,
    templates,
    paths: paths.map((path) => ({
      name: path.name,
      position: path.position,
      title: path.title,
      prose: path.prose.join("\n\n"),
      fromLabel: path.fromLabel,
      steps: path.steps,
      sequence: path.sequence,
    })),
    uses,
    wires,
    refines,
    shares,
    shows,
    actors,
    boxes,
  };
}

export function isNameRef(token: TokenExpr): token is NameRef {
  return isTemplate(token);
}
