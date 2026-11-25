import {createDefaultCelAdapter} from "@velocitron/cel";
import {
  PETRINET_RESOURCE_LIMITS,
  PetrinetDslError,
  PetrinetResourceError,
  pythonRepr,
  pythonStringRepr,
  validFieldPath,
  type ContributionIr,
  type Diagnostic,
  type RelatedDiagnostic,
  type SourceSpan,
} from "@velocitron/dsl";
import {parseComposition, type ParseCompositionOptions} from "./composition.js";
import {NetValidationError} from "./errors.js";
import {validateContributionIr} from "./generated/contribution-ir-validator.js";
import type {JsonValue, ReadonlyJsonObject} from "./types.js";

type AnyObject = Record<string, any>;
type IrPosition = {byteOffset: number; line: number; column: number};
type IrSpan = {source: string; start: IrPosition; end: IrPosition};
type Identity = readonly [source: string, statement: number, part: number];
type Fact<T> = {value: T; span: IrSpan};
type ArcDeclaration = {
  id: Identity;
  place: string;
  transition: string;
  isInput: boolean;
  mode: "consume" | "read" | "inhibit" | "produce";
  color: {kind: "explicit"; value: string};
  span: IrSpan;
  transitionNameSpan: IrSpan;
};
type ResolvedArc = AnyObject;

const RELATIVE_SOURCE_ID = /^(?!\/)(?![A-Za-z]:[\\/])(?![A-Za-z][A-Za-z0-9+.-]*:).+$/u;
const TIMER_BIND_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/u;
const JSON_NUMBER = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/u;

function isObject(value: unknown): value is AnyObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function keysEqual(value: AnyObject, expected: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}

function setOwn(object: AnyObject, key: string, value: unknown): void {
  Object.defineProperty(object, key, {
    configurable: true,
    enumerable: true,
    value,
    writable: true,
  });
}

function containsIsolatedSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        index += 1;
        continue;
      }
      return true;
    }
    if (unit >= 0xdc00 && unit <= 0xdfff) return true;
  }
  return false;
}

function unicodeScalarLength(value: string): number {
  let length = 0;
  for (const _character of value) length += 1;
  return length;
}

function toDiagnosticSpan(span?: AnyObject | null): SourceSpan {
  if (
    span !== null &&
    span !== undefined &&
    isObject(span.start) &&
    isObject(span.end)
  ) {
    return {
      source: String(span.source),
      start: {
        offset: span.start.byteOffset as number,
        line: span.start.line as number,
        column: span.start.column as number,
      },
      end: {
        offset: span.end.byteOffset as number,
        line: span.end.line as number,
        column: span.end.column as number,
      },
    };
  }
  const position = {offset: 0, line: 1, column: 1};
  return {source: "<ir>", start: position, end: position};
}

function resolutionError(
  code: string,
  message: string,
  span?: AnyObject | null,
  help?: string,
  related: readonly (readonly [message: string, span: IrSpan])[] = [],
): PetrinetDslError {
  const relatedDiagnostics: readonly RelatedDiagnostic[] | undefined =
    related.length === 0
      ? undefined
      : related.map(([relatedMessage, relatedSpan]) => ({
          message: relatedMessage,
          span: toDiagnosticSpan(relatedSpan),
        }));
  const diagnostic: Diagnostic = {
    code,
    message,
    span: toDiagnosticSpan(span),
    ...(help === undefined ? {} : {help}),
    ...(relatedDiagnostics === undefined ? {} : {related: relatedDiagnostics}),
  };
  return new PetrinetDslError(diagnostic);
}

function preflightContributionIr(value: unknown): void {
  if (isObject(value) && Array.isArray(value.contributions)) {
    const count = value.contributions.length;
    if (count > PETRINET_RESOURCE_LIMITS.contributions) {
      throw new PetrinetResourceError(
        "contributions",
        PETRINET_RESOURCE_LIMITS.contributions,
        count,
      );
    }
  }

  let nodes = 0;
  const active = new WeakSet<object>();
  const visit = (item: unknown, depth: number): void => {
    if (depth > PETRINET_RESOURCE_LIMITS.nestingDepth) {
      throw new PetrinetResourceError(
        "nestingDepth",
        PETRINET_RESOURCE_LIMITS.nestingDepth,
        depth,
      );
    }
    nodes += 1;
    if (nodes > PETRINET_RESOURCE_LIMITS.irNodes) {
      throw new PetrinetResourceError(
        "irNodes",
        PETRINET_RESOURCE_LIMITS.irNodes,
        nodes,
      );
    }
    if (typeof item !== "object" || item === null) return;
    if (active.has(item)) {
      throw resolutionError("PN200", "invalid Contribution IR document shape");
    }
    active.add(item);
    if (Array.isArray(item)) {
      for (const child of item) visit(child, depth + 1);
    } else {
      for (const child of Object.values(item)) visit(child, depth + 1);
    }
    active.delete(item);
  };
  visit(value, 0);
}

type PositionSubject = {
  kind: "place" | "transition" | "placeCopy";
  name: string;
  copyTransition: string;
};

function positionSubject(raw: unknown): PositionSubject | undefined {
  if (!isObject(raw)) return undefined;
  if (raw.type === "placeCopy") {
    if (
      !keysEqual(raw, ["type", "place", "transition"]) ||
      typeof raw.place !== "string" ||
      raw.place.length === 0 ||
      typeof raw.transition !== "string" ||
      raw.transition.length === 0
    ) {
      return undefined;
    }
    return {kind: "placeCopy", name: raw.place, copyTransition: raw.transition};
  }
  if (
    (raw.type !== "place" && raw.type !== "transition") ||
    !keysEqual(raw, ["type", "name"]) ||
    typeof raw.name !== "string" ||
    raw.name.length === 0
  ) {
    return undefined;
  }
  return {kind: raw.type, name: raw.name, copyTransition: ""};
}

function positionKey(subject: PositionSubject): string {
  if (subject.kind === "placeCopy") {
    return `place:${subject.name}@transition:${subject.copyTransition}`;
  }
  return `${subject.kind}:${subject.name}`;
}

function renderedPositionTarget(subject: PositionSubject): string {
  if (subject.kind === "placeCopy") return `(${subject.name})@[${subject.copyTransition}]`;
  return subject.kind === "place" ? `(${subject.name})` : `[${subject.name}]`;
}

function arcPlaceTransition(arc: AnyObject): [string, string] | undefined {
  const source = arc.from;
  const destination = arc.to;
  if (!isObject(source) || !isObject(destination)) return undefined;
  const place = "place" in source && "transition" in destination
    ? source.place
    : "transition" in source && "place" in destination
      ? destination.place
      : undefined;
  const transition = "place" in source && "transition" in destination
    ? destination.transition
    : "transition" in source && "place" in destination
      ? source.transition
      : undefined;
  if (typeof place !== "string" || typeof transition !== "string") return undefined;
  return [place, transition];
}

function siblingGroups(arcs: readonly AnyObject[], fusion: ReadonlySet<string>): string[][] {
  const inputs = new Map<string, Set<string>>();
  const firstArcs: [string, string][] = [];
  for (const arc of arcs) {
    const source = arc.from;
    const destination = arc.to;
    if (!isObject(source) || !isObject(destination)) continue;
    const place = source.place;
    const transition = destination.transition;
    if (typeof place !== "string" || typeof transition !== "string" || fusion.has(place)) {
      continue;
    }
    let seen = inputs.get(transition);
    if (seen === undefined) {
      seen = new Set();
      inputs.set(transition, seen);
    }
    if (!seen.has(place)) {
      seen.add(place);
      firstArcs.push([place, transition]);
    }
  }
  const groups = new Map<string, string[]>();
  for (const [place, transition] of firstArcs) {
    const seen = inputs.get(transition);
    if (seen !== undefined && seen.size === 1 && seen.has(place)) {
      const group = groups.get(place) ?? [];
      group.push(transition);
      groups.set(place, group);
    }
  }
  return [...groups.values()].filter((group) => group.length > 1);
}

function sharedCopyOwners(
  arcs: readonly AnyObject[],
  fusion: ReadonlySet<string>,
  besideOpen: ReadonlySet<string>,
): Map<string, ReadonlySet<string>> {
  const users = new Map<string, Set<string>>();
  for (const arc of arcs) {
    const pair = arcPlaceTransition(arc);
    if (pair === undefined || !besideOpen.has(pair[0])) continue;
    const seen = users.get(pair[0]) ?? new Set<string>();
    seen.add(pair[1]);
    users.set(pair[0], seen);
  }
  const shared = new Map<string, ReadonlySet<string>>();
  const keyOf = (place: string, transition: string): string => `${place}\0${transition}`;
  for (const group of siblingGroups(arcs, fusion)) {
    for (const place of besideOpen) {
      const used = users.get(place);
      if (used === undefined || !group.some((transition) => used.has(transition))) continue;
      let start = 0;
      while (start < group.length) {
        let end = start;
        while (end < group.length && used.has(group[end]!)) end += 1;
        const run = group.slice(start, end);
        for (let index = 0; index + 1 < run.length; index += 2) {
          const owners = new Set([run[index]!, run[index + 1]!]);
          shared.set(keyOf(place, run[index]!), owners);
          shared.set(keyOf(place, run[index + 1]!), owners);
        }
        start = end === start ? end + 1 : end;
      }
    }
  }
  return shared;
}

function sharedCopyKey(place: string, transition: string): string {
  return `${place}\0${transition}`;
}

function relativeSpan(span: IrSpan, prefix: string, target: string): IrSpan {
  const prefixScalars = unicodeScalarLength(prefix);
  const targetScalars = unicodeScalarLength(target);
  const prefixBytes = new TextEncoder().encode(prefix).byteLength;
  const targetBytes = new TextEncoder().encode(target).byteLength;
  const line = span.start.line;
  const column = span.start.column + prefixScalars;
  const byteOffset = span.start.byteOffset + prefixBytes;
  return {
    source: span.source,
    start: {byteOffset, line, column},
    end: {
      byteOffset: byteOffset + targetBytes,
      line,
      column: column + targetScalars,
    },
  };
}

function isSourceSpan(value: unknown, expectedSource: string): value is IrSpan {
  if (!isObject(value) || !keysEqual(value, ["source", "start", "end"])) return false;
  if (value.source !== expectedSource || !RELATIVE_SOURCE_ID.test(expectedSource)) return false;
  const positions: IrPosition[] = [];
  for (const rawPosition of [value.start, value.end]) {
    if (!isObject(rawPosition) || !keysEqual(rawPosition, ["byteOffset", "line", "column"])) {
      return false;
    }
    const {byteOffset, line, column} = rawPosition;
    if (
      !Number.isInteger(byteOffset) ||
      byteOffset < 0 ||
      !Number.isInteger(line) ||
      line < 1 ||
      !Number.isInteger(column) ||
      column < 1
    ) {
      return false;
    }
    positions.push({byteOffset, line, column});
  }
  const [start, end] = positions as [IrPosition, IrPosition];
  return (
    start.byteOffset <= end.byteOffset &&
    (start.line < end.line || (start.line === end.line && start.column <= end.column))
  );
}

function sourceIdentity(value: unknown, sourceMember: "source" | "document"): Identity | null {
  if (!isObject(value) || !keysEqual(value, [sourceMember, "statement", "part"])) return null;
  const source = value[sourceMember];
  const statement = value.statement;
  const part = value.part;
  if (
    typeof source !== "string" ||
    !RELATIVE_SOURCE_ID.test(source) ||
    !Number.isInteger(statement) ||
    statement < 0 ||
    !Number.isInteger(part) ||
    part < 0
  ) {
    return null;
  }
  return [source, statement, part];
}

function contributionIdentity(value: unknown): Identity | null {
  return sourceIdentity(value, "source");
}

function arcIdentity(value: unknown): Identity | null {
  return sourceIdentity(value, "document");
}

function identityKey(identity: Identity): string {
  return JSON.stringify(identity);
}

function sameIdentity(left: Identity, right: Identity): boolean {
  return left[0] === right[0] && left[1] === right[1] && left[2] === right[2];
}

function cloneJson<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => cloneJson(item)) as T;
  if (isObject(value)) {
    const result: AnyObject = {};
    for (const [key, item] of Object.entries(value)) {
      setOwn(result, key, cloneJson(item));
    }
    return result as T;
  }
  return value;
}

function untag(value: AnyObject, depth = 0): JsonValue {
  if (depth > PETRINET_RESOURCE_LIMITS.nestingDepth) {
    throw new PetrinetResourceError(
      "nestingDepth",
      PETRINET_RESOURCE_LIMITS.nestingDepth,
      depth,
    );
  }
  const kind = value.type;
  if (kind === "null") {
    if (!keysEqual(value, ["type"])) throw new Error("invalid tagged JSON");
    return null;
  }
  if (kind === "boolean") {
    if (!keysEqual(value, ["type", "value"]) || typeof value.value !== "boolean") {
      throw new Error("invalid tagged JSON");
    }
    return value.value;
  }
  if (kind === "string") {
    if (
      !keysEqual(value, ["type", "value"]) ||
      typeof value.value !== "string" ||
      containsIsolatedSurrogate(value.value)
    ) {
      throw new Error("invalid tagged JSON");
    }
    return value.value;
  }
  if (kind === "number") {
    const lexeme = value.lexeme;
    if (
      !keysEqual(value, ["type", "lexeme"]) ||
      typeof lexeme !== "string" ||
      !JSON_NUMBER.test(lexeme)
    ) {
      throw new Error("invalid tagged JSON");
    }
    const parsed = Number(lexeme);
    if (!Number.isFinite(parsed)) throw new Error("invalid tagged JSON");
    if (!/[.eE]/u.test(lexeme) && (BigInt(lexeme) > 9007199254740991n || BigInt(lexeme) < -9007199254740991n)) {
      throw new Error("invalid tagged JSON");
    }
    return Object.is(parsed, -0) ? 0 : parsed;
  }
  if (kind === "array") {
    if (!keysEqual(value, ["type", "items"]) || !Array.isArray(value.items)) {
      throw new Error("invalid tagged JSON");
    }
    return value.items.map((item: unknown) => {
      if (!isObject(item)) throw new Error("invalid tagged JSON");
      return untag(item, depth + 1);
    });
  }
  if (kind === "object") {
    if (!keysEqual(value, ["type", "entries"]) || !Array.isArray(value.entries)) {
      throw new Error("invalid tagged JSON");
    }
    const result: AnyObject = {};
    for (const rawEntry of value.entries as unknown[]) {
      if (!isObject(rawEntry) || !keysEqual(rawEntry, ["key", "value"])) {
        throw new Error("invalid tagged JSON");
      }
      const key = rawEntry.key;
      if (
        typeof key !== "string" ||
        Object.hasOwn(result, key) ||
        !isObject(rawEntry.value)
      ) {
        throw new Error("invalid tagged JSON");
      }
      setOwn(result, key, untag(rawEntry.value, depth + 1));
    }
    return result;
  }
  throw new Error("invalid tagged JSON");
}

function jsonValuesEqual(left: unknown, right: unknown): boolean {
  if (typeof left === "number" || typeof right === "number") {
    return typeof left === "number" && typeof right === "number" && left === right;
  }
  if (left === null || right === null || typeof left !== typeof right) return left === right;
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => jsonValuesEqual(item, right[index]))
    );
  }
  if (isObject(left) || isObject(right)) {
    if (!isObject(left) || !isObject(right)) return false;
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.hasOwn(right, key) && jsonValuesEqual(left[key], right[key]))
    );
  }
  return left === right;
}

function compactSortedJson(value: unknown): string {
  const normalize = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(normalize);
    if (isObject(item)) {
      const result: AnyObject = {};
      for (const key of Object.keys(item).sort()) {
        setOwn(result, key, normalize(item[key]));
      }
      return result;
    }
    return item;
  };
  return JSON.stringify(normalize(value));
}

function validCapacityKey(value: unknown): value is string | string[] {
  return (
    (typeof value === "string" && value.length > 0) ||
    (Array.isArray(value) &&
      value.length > 0 &&
      value.every((item) => typeof item === "string" && item.length > 0))
  );
}

function parseMarkingToken(rawToken: unknown, message: string, span: IrSpan): AnyObject {
  if (!isObject(rawToken)) throw resolutionError("PN200", message, span);
  if (keysEqual(rawToken, ["template"])) {
    const rawTemplate = rawToken.template;
    if (
      !isObject(rawTemplate) ||
      !keysEqual(rawTemplate, ["type", "name"]) ||
      rawTemplate.type !== "template" ||
      typeof rawTemplate.name !== "string" ||
      rawTemplate.name.length === 0
    ) {
      throw resolutionError("PN200", message, span);
    }
    return {template: rawTemplate.name};
  }
  if (!keysEqual(rawToken, ["color", "data"])) throw resolutionError("PN200", message, span);
  if (
    typeof rawToken.color !== "string" ||
    rawToken.color.length === 0 ||
    !isObject(rawToken.data)
  ) {
    throw resolutionError("PN200", message, span);
  }
  let data: JsonValue;
  try {
    data = untag(rawToken.data);
  } catch (error) {
    if (error instanceof PetrinetResourceError) throw error;
    throw resolutionError("PN200", message, span);
  }
  if (!isObject(data)) throw resolutionError("PN200", message, span);
  return {color: rawToken.color, data};
}

function materializeMarkingToken(options: {
  place: string;
  token: AnyObject;
  count: number;
  acceptedColors: readonly string[];
  templates: ReadonlyMap<string, JsonValue>;
  span: IrSpan;
  markingName?: string;
}): AnyObject[] {
  const {place, token, count, acceptedColors, templates, span, markingName} = options;
  let color: string;
  let data: JsonValue;
  if (typeof token.template === "string") {
    if (!templates.has(token.template)) {
      throw resolutionError("PN202", `undefined template $${token.template}`, span);
    }
    if (acceptedColors.length !== 1) {
      throw resolutionError(
        "PN202",
        `template $${token.template} color is ambiguous at (${place})`,
        span,
      );
    }
    color = acceptedColors[0] as string;
    data = templates.get(token.template) as JsonValue;
    if (!isObject(data)) {
      throw resolutionError(
        "PN202",
        `template $${token.template} data must be a JSON object`,
        span,
      );
    }
  } else {
    color = token.color as string;
    if (!acceptedColors.includes(color)) {
      const subject = markingName === undefined ? "marking" : `named marking ${pythonRepr(markingName)}`;
      throw resolutionError(
        "PN202",
        `${subject} token color ${pythonRepr(color)} is not accepted by place (${place})`,
        span,
      );
    }
    data = token.data as JsonValue;
  }
  const result: AnyObject[] = [];
  for (let index = 0; index < count; index += 1) {
    result.push({type: color, data: cloneJson(data)});
  }
  return result;
}

function invalidContributionMessage(contribution: AnyObject): string {
  switch (contribution.kind) {
    case "document.net-header": return "invalid net header contribution";
    case "document.composition-header": return "invalid composition header contribution";
    case "place.declare": return "invalid place declaration contribution";
    case "transition.declare": return "invalid transition declaration contribution";
    case "place.accepts": return "invalid place accepted-colors contribution";
    case "place.port": return "invalid place port contribution";
    case "arc.handle": return "invalid arc handle contribution";
    case "order.transition": return "invalid transition order contribution";
    case "order.arc-run": return "invalid arc-run order contribution";
    case "place.capacity-per-color-key": return "invalid place capacity contribution";
    case "arc.weight": return "invalid arc weight contribution";
    case "arc.produce-data": return "invalid arc produce-data contribution";
    case "arc.produce-cel": return "invalid arc produce-cel contribution";
    case "arc.predicate": return "invalid arc predicate contribution";
    case "arc.correlate": return "invalid arc correlate contribution";
    case "arc.declare": return "invalid arc declaration";
    case "transition.timer": return "invalid transition timer contribution";
    case "transition.timer-maturity": return "invalid transition timer maturity contribution";
    case "transition.timer-bind": return "invalid transition timer bind contribution";
    case "transition.binding-name": return "invalid transition binding name contribution";
    case "transition.priority": return "invalid transition priority contribution";
    case "transition.handler": return "invalid transition handler contribution";
    case "transition.guard": return "invalid transition guard contribution";
    case "marking.append": return "invalid initial marking contribution";
    case "template.define": return "invalid template definition contribution";
    case "documentation.description": return "invalid documentation description contribution";
    case "documentation.annotation": return "invalid documentation annotation contribution";
    case "metadata.named-marking": return "invalid named marking contribution";
    case "view.position": return "invalid view position contribution";
    case "view.route": return "invalid view route contribution";
    case "view.splines": return "invalid view splines contribution";
    case "view.detail": return "invalid view detail contribution";
    case "decoration.highlight": return "invalid highlight decoration contribution";
    case "decoration.note": return "invalid note decoration contribution";
    case "decoration.summary": return "invalid summary decoration contribution";
    case "decoration.quiet": return "invalid quiet decoration contribution";
    case "decoration.beside": return "invalid beside decoration contribution";
    case "decoration.show": return "invalid show decoration contribution";
    case "document.extensions": return "invalid document extensions contribution";
    case "domain.values": return "invalid domain contribution";
    case "proof.final": return "invalid final place contribution";
    case "proof.invariant": return "invalid invariant contribution";
    case "actor.declare": return "invalid actor declaration contribution";
    case "composition.use": return "invalid composition use";
    case "composition.wire": return "invalid composition wire";
    case "composition.share": return "invalid composition share";
    case "composition.refine": return "invalid composition refine";
    case "composition.final": return "invalid composition final";
    default: return `unsupported contribution kind ${pythonRepr(contribution.kind)}`;
  }
}

function onlyLegacyDocumentMetadataFailedSchema(
  documentIr: AnyObject,
  errors: readonly {instancePath: string}[],
): boolean {
  if (!Array.isArray(documentIr.contributions)) return false;
  const invalidIndexes = new Set<number>();
  for (const error of errors) {
    const match = /^\/contributions\/(\d+)(?:\/|$)/u.exec(error.instancePath);
    if (match === null) return false;
    invalidIndexes.add(Number(match[1]));
  }
  if (invalidIndexes.size === 0) return false;
  for (const index of invalidIndexes) {
    const contribution = documentIr.contributions[index];
    if (
      !isObject(contribution) ||
      (contribution.kind !== "documentation.description" &&
        contribution.kind !== "documentation.annotation") ||
      !isObject(contribution.target) ||
      !keysEqual(contribution.target, ["type"]) ||
      contribution.target.type !== "document"
    ) {
      return false;
    }
  }
  return true;
}

function rejectSchemaInvalidIr(documentIr: AnyObject, errors: readonly {instancePath: string}[]): never {
  if (documentIr.format !== "velocitron.petrinet/contribution-ir" || documentIr.version !== 1) {
    throw resolutionError("PN200", "unsupported Contribution IR format or version");
  }
  if (!keysEqual(documentIr, ["format", "version", "documentKind", "document", "contributions"])) {
    throw resolutionError("PN200", "invalid Contribution IR document shape");
  }
  if (!isObject(documentIr.document)) {
    throw resolutionError("PN200", "invalid Contribution IR document");
  }
  if (!Array.isArray(documentIr.contributions)) {
    throw resolutionError("PN200", "contributions must be an array");
  }
  let invalidIndex = Number.POSITIVE_INFINITY;
  for (const error of errors) {
    const match = /^\/contributions\/(\d+)(?:\/|$)/u.exec(error.instancePath);
    if (match !== null) invalidIndex = Math.min(invalidIndex, Number(match[1]));
  }
  if (!Number.isFinite(invalidIndex)) {
    throw resolutionError("PN200", "invalid Contribution IR document shape");
  }
  const contribution = documentIr.contributions[invalidIndex];
  if (!isObject(contribution)) {
    throw resolutionError("PN200", "invalid Contribution IR contribution shape");
  }
  const span = isObject(contribution.span) ? contribution.span : undefined;
  if (
    contribution.kind === "arc.declare" &&
    isObject(contribution.value) &&
    contribution.value.mode === "consume"
  ) {
    const identity = contributionIdentity(contribution.id);
    if (
      identity !== null &&
      !isSourceSpan(contribution.value.transitionNameSpan, identity[0])
    ) {
      throw resolutionError(
        "PN200",
        "consumed arc has invalid transitionNameSpan",
        span,
      );
    }
  }
  if (contribution.kind === "arc.weight" && isObject(contribution.value)) {
    const weight = contribution.value.weight;
    if (Number.isInteger(weight) && weight < 1 && isObject(contribution.target)) {
      throw resolutionError(
        "PN202",
        `arc weight must be an integer greater than or equal to 1; got ${pythonRepr(weight)} for @${String(contribution.target.name)}`,
        span,
      );
    }
  }
  if (contribution.kind === "place.capacity-per-color-key" && isObject(contribution.value) && isObject(contribution.target)) {
    const name = String(contribution.target.name);
    if (!keysEqual(contribution.value, ["key", "max"])) {
      throw resolutionError(
        "PN202",
        `capacityPerColorKey for (${name}) must contain exactly key and max`,
        span,
      );
    }
    if (!validCapacityKey(contribution.value.key)) {
      throw resolutionError(
        "PN202",
        `capacityPerColorKey key must be a non-empty string or non-empty array of non-empty strings for (${name})`,
        span,
      );
    }
    const maximum = contribution.value.max;
    if (!Number.isInteger(maximum) || maximum < 1) {
      throw resolutionError(
        "PN202",
        `capacityPerColorKey max must be an integer greater than or equal to 1; got ${pythonRepr(maximum)} for (${name})`,
        span,
      );
    }
  }
  if (
    contribution.kind === "view.route" &&
    isObject(contribution.target) &&
    typeof contribution.target.name === "string" &&
    isObject(contribution.value) &&
    isObject(contribution.value.view) &&
    typeof contribution.value.view.name === "string" &&
    Array.isArray(contribution.value.points) &&
    contribution.value.points.length === 0
  ) {
    throw resolutionError(
      "PN202",
      `view ${pythonRepr(contribution.value.view.name)} route @${contribution.target.name} requires at least one point`,
      span,
      'add at least one {"x": Number, "y": Number} point',
    );
  }
  throw resolutionError("PN200", invalidContributionMessage(contribution), span);
}

function validateEnvelope(ir: unknown): {
  documentIr: AnyObject;
  documentId: string;
  documentKind: "net" | "composition";
  contributions: AnyObject[];
} {
  preflightContributionIr(ir);
  const schemaResult = validateContributionIr(ir);
  if (!isObject(ir)) throw resolutionError("PN200", "invalid Contribution IR document shape");
  const documentIr = ir;
  if (!keysEqual(documentIr, ["format", "version", "documentKind", "document", "contributions"])) {
    if (!schemaResult.ok) rejectSchemaInvalidIr(documentIr, schemaResult.errors);
    throw resolutionError("PN200", "invalid Contribution IR document shape");
  }
  if (documentIr.format !== "velocitron.petrinet/contribution-ir" || documentIr.version !== 1) {
    throw resolutionError("PN200", "unsupported Contribution IR format or version");
  }
  const rawDocument = documentIr.document;
  if (!isObject(rawDocument)) throw resolutionError("PN200", "invalid Contribution IR document");
  const documentId = rawDocument.id;
  const documentKind = documentIr.documentKind;
  if (
    (documentKind !== "net" && documentKind !== "composition") ||
    !keysEqual(rawDocument, ["id"]) ||
    typeof documentId !== "string" ||
    !RELATIVE_SOURCE_ID.test(documentId)
  ) {
    throw resolutionError("PN200", "invalid Contribution IR document");
  }
  if (!Array.isArray(documentIr.contributions)) {
    throw resolutionError("PN200", "contributions must be an array");
  }
  const contributions = documentIr.contributions as unknown[];
  const ids = new Set<string>();
  for (let ordinal = 0; ordinal < contributions.length; ordinal += 1) {
    const rawContribution = contributions[ordinal];
    if (!isObject(rawContribution) || !keysEqual(rawContribution, ["id", "kind", "ordinal", "span", "target", "value"])) {
      throw resolutionError("PN200", "invalid Contribution IR contribution shape");
    }
    if (!Number.isInteger(rawContribution.ordinal) || rawContribution.ordinal !== ordinal) {
      throw resolutionError(
        "PN200",
        "contribution ordinals must be contiguous zero-based integers",
      );
    }
    const uniqueId = contributionIdentity(rawContribution.id);
    if (uniqueId === null) throw resolutionError("PN200", "invalid contribution identity");
    if (uniqueId[0] !== documentId) {
      throw resolutionError("PN200", "contribution identity source must match document id");
    }
    if (!isSourceSpan(rawContribution.span, uniqueId[0])) {
      throw resolutionError("PN200", "invalid contribution span");
    }
    const key = identityKey(uniqueId);
    if (ids.has(key)) throw resolutionError("PN200", "duplicate contribution identity");
    ids.add(key);
  }
  if (
    !schemaResult.ok &&
    !onlyLegacyDocumentMetadataFailedSchema(documentIr, schemaResult.errors)
  ) {
    rejectSchemaInvalidIr(documentIr, schemaResult.errors);
  }
  return {
    documentIr,
    documentId,
    documentKind,
    contributions: contributions as AnyObject[],
  };
}

function resolveCompositionContributions(
  contributions: AnyObject[],
  options: ParseCompositionOptions,
): ReadonlyJsonObject {
  let header: Fact<string> | undefined;
  const uses = new Map<string, Fact<string>>();
  const orderedUses: AnyObject[] = [];
  const wires: AnyObject[] = [];
  const wireSpans = new Map<string, IrSpan>();
  const wireEndpointSpans: [IrSpan, IrSpan][] = [];
  const refinements: AnyObject[] = [];
  const refineFacts = new Map<string, Fact<string>>();
  const refineTransitionSpans = new Map<string, IrSpan>();
  const shares: AnyObject[] = [];
  const shareLabels = new Set<string>();
  const shareSpans: IrSpan[] = [];
  const final: AnyObject[][] = [];
  const finalKeys = new Set<string>();
  const finalSpans: IrSpan[] = [];

  for (const contribution of contributions) {
    const {kind, target, value} = contribution;
    const span = contribution.span as IrSpan;
    const identity = contributionIdentity(contribution.id);
    if (
      !isObject(target) ||
      !isObject(value) ||
      !isObject(span) ||
      identity === null ||
      identity[2] !== 0
    ) {
      throw resolutionError("PN200", "invalid composition contribution", span);
    }
    if (identity[1] !== contribution.ordinal) {
      throw resolutionError("PN200", "invalid composition statement order", span);
    }
    if (header === undefined && kind !== "document.composition-header") {
      throw resolutionError("PN200", "composition header must be first", span);
    }
    if (!keysEqual(target, ["type"]) || target.type !== "document") {
      throw resolutionError("PN200", "invalid composition target", span);
    }

    if (kind === "document.composition-header") {
      const namespace = value.namespace;
      if (
        header !== undefined ||
        !keysEqual(value, ["namespace"]) ||
        typeof namespace !== "string" ||
        namespace.length === 0 ||
        containsIsolatedSurrogate(namespace)
      ) {
        throw resolutionError("PN200", "invalid composition header contribution", span);
      }
      header = {value: namespace, span};
      continue;
    }

    if (kind === "composition.use") {
      const {ref, alias} = value;
      if (
        !keysEqual(value, ["ref", "alias"]) ||
        typeof ref !== "string" ||
        ref.length === 0 ||
        typeof alias !== "string" ||
        alias.length === 0 ||
        !TIMER_BIND_IDENTIFIER.test(alias) ||
        containsIsolatedSurrogate(ref)
      ) {
        throw resolutionError("PN200", "invalid composition use", span);
      }
      const existing = uses.get(alias);
      if (existing !== undefined) {
        if (existing.value !== ref) {
          throw resolutionError(
            "PN202",
            `conflicting use facts for alias ${alias}`,
            span,
            "use each alias for exactly one referenced net",
            [[`first use of alias ${alias} was declared here`, existing.span]],
          );
        }
        continue;
      }
      uses.set(alias, {value: ref, span});
      orderedUses.push({ref, alias});
      continue;
    }

    if (kind === "composition.wire") {
      const rawFrom = value.from;
      const rawTo = value.to;
      if (!keysEqual(value, ["from", "to"]) || !isObject(rawFrom) || !isObject(rawTo)) {
        throw resolutionError("PN200", "invalid composition wire", span);
      }
      const endpointValues: [string, string][] = [];
      const endpointSpans: IrSpan[] = [];
      for (const endpoint of [rawFrom, rawTo]) {
        const {alias, place, span: endpointSpan} = endpoint;
        if (
          !keysEqual(endpoint, ["alias", "place", "span"]) ||
          typeof alias !== "string" ||
          alias.length === 0 ||
          typeof place !== "string" ||
          place.length === 0 ||
          !isSourceSpan(endpointSpan, identity[0])
        ) {
          throw resolutionError("PN200", "invalid composition wire", span);
        }
        if (!uses.has(alias)) {
          throw resolutionError(
            "PN202",
            `wire references unknown alias ${alias}`,
            endpointSpan,
            "declare the alias with use before wiring it",
          );
        }
        endpointValues.push([alias, place]);
        endpointSpans.push(endpointSpan as IrSpan);
      }
      const [source, destination] = endpointValues as [[string, string], [string, string]];
      const key = JSON.stringify([source, destination]);
      if (wireSpans.has(key)) continue;
      const reverse = JSON.stringify([destination, source]);
      const reverseSpan = wireSpans.get(reverse);
      if (reverseSpan !== undefined) {
        throw resolutionError(
          "PN202",
          "conflicting wire facts reverse the same endpoints",
          span,
          "remove the reversed wire; wires run output to input",
          [["first wire between these endpoints was declared here", reverseSpan]],
        );
      }
      wireSpans.set(key, span);
      wireEndpointSpans.push(endpointSpans as [IrSpan, IrSpan]);
      wires.push({
        from: {net: source[0], port: source[1]},
        to: {net: destination[0], port: destination[1]},
      });
      continue;
    }

    if (kind === "composition.share") {
      const rawPlaces = value.places;
      if (!keysEqual(value, ["places"]) || !Array.isArray(rawPlaces) || rawPlaces.length < 2) {
        throw resolutionError("PN200", "invalid composition share", span);
      }
      const members: [string, string][] = [];
      for (const member of rawPlaces as unknown[]) {
        if (!isObject(member)) {
          throw resolutionError("PN200", "invalid composition share", span);
        }
        const {alias, place, span: memberSpan} = member;
        if (
          !keysEqual(member, ["alias", "place", "span"]) ||
          typeof alias !== "string" ||
          alias.length === 0 ||
          typeof place !== "string" ||
          place.length === 0 ||
          !isSourceSpan(memberSpan, identity[0])
        ) {
          throw resolutionError("PN200", "invalid composition share", span);
        }
        if (!uses.has(alias)) {
          throw resolutionError(
            "PN202",
            `share references unknown alias ${alias}`,
            memberSpan,
            "declare the alias with use before sharing its place",
          );
        }
        members.push([alias, place]);
      }
      const label = `share ${members.map(([alias, place]) => `${alias}.(${place})`).join(" ~ ")}`;
      if (shareLabels.has(label)) continue;
      shareLabels.add(label);
      shareSpans.push(span);
      shares.push({places: members.map(([alias, place]) => ({net: alias, place}))});
      continue;
    }

    if (kind === "composition.refine") {
      const refined = value.transition;
      const refining = value.by;
      if (!keysEqual(value, ["transition", "by"]) || !isObject(refined) || !isObject(refining)) {
        throw resolutionError("PN200", "invalid composition refine", span);
      }
      const {alias, name, span: transitionSpan} = refined;
      const {alias: by, span: bySpan} = refining;
      if (
        !keysEqual(refined, ["alias", "name", "span"]) ||
        !keysEqual(refining, ["alias", "span"]) ||
        typeof alias !== "string" ||
        alias.length === 0 ||
        typeof name !== "string" ||
        name.length === 0 ||
        typeof by !== "string" ||
        by.length === 0 ||
        !isSourceSpan(transitionSpan, identity[0]) ||
        !isSourceSpan(bySpan, identity[0])
      ) {
        throw resolutionError("PN200", "invalid composition refine", span);
      }
      for (const [refineAlias, aliasSpan] of [[alias, transitionSpan], [by, bySpan]] as const) {
        if (!uses.has(refineAlias)) {
          throw resolutionError(
            "PN202",
            `refine references unknown alias ${refineAlias}`,
            aliasSpan,
            "declare the alias with use before refining with it",
          );
        }
      }
      if (by === alias) {
        throw resolutionError(
          "PN202",
          `refine ${alias}.[${name}] by ${by}: a net cannot refine its own transition`,
          bySpan,
          "refine with the alias of another net",
        );
      }
      const key = JSON.stringify([alias, name]);
      const existing = refineFacts.get(key);
      if (existing !== undefined) {
        if (existing.value === by) continue;
        throw resolutionError(
          "PN202",
          `conflicting refine facts for ${alias}.[${name}]`,
          span,
          "refine each transition by exactly one net",
          [[`first refine of ${alias}.[${name}] was declared here`, existing.span]],
        );
      }
      refineFacts.set(key, {value: by, span});
      refineTransitionSpans.set(key, transitionSpan as IrSpan);
      refinements.push({net: alias, transition: name, by});
      continue;
    }

    if (kind === "composition.final") {
      const rawMarkings = value.markings;
      if (!keysEqual(value, ["markings"]) || !Array.isArray(rawMarkings) || rawMarkings.length === 0) {
        throw resolutionError("PN200", "invalid composition final", span);
      }
      for (const rawMarking of rawMarkings as unknown[]) {
        if (!Array.isArray(rawMarking) || rawMarking.length === 0) {
          throw resolutionError("PN200", "invalid composition final", span);
        }
        const members: [string, string][] = [];
        for (const member of rawMarking as unknown[]) {
          if (!isObject(member)) {
            throw resolutionError("PN200", "invalid composition final", span);
          }
          const {alias, place, span: memberSpan} = member;
          if (
            !keysEqual(member, ["alias", "place", "span"]) ||
            typeof alias !== "string" ||
            alias.length === 0 ||
            typeof place !== "string" ||
            place.length === 0 ||
            !isSourceSpan(memberSpan, identity[0])
          ) {
            throw resolutionError("PN200", "invalid composition final", span);
          }
          if (!uses.has(alias)) {
            throw resolutionError(
              "PN202",
              `final references unknown alias ${alias}`,
              memberSpan,
              "declare the alias with use before naming its place",
            );
          }
          members.push([alias, place]);
        }
        const label = `final ${members.map(([alias, place]) => `${alias}.(${place})`).join(" + ")}`;
        const keys = members.map((member) => JSON.stringify(member));
        if (new Set(keys).size !== keys.length) {
          throw resolutionError(
            "PN202",
            `${label}: names a place more than once`,
            span,
            "name each place of a final marking once",
          );
        }
        const key = JSON.stringify([...keys].sort());
        if (finalKeys.has(key)) continue;
        finalKeys.add(key);
        finalSpans.push(span);
        final.push(members.map(([alias, place]) => ({net: alias, place})));
      }
      continue;
    }

    throw resolutionError("PN200", `unsupported contribution kind ${pythonRepr(kind)}`, span);
  }

  if (header === undefined) throw resolutionError("PN200", "missing composition header");
  if (orderedUses.length === 0) {
    throw resolutionError(
      "PN202",
      "composition requires at least one use fact",
      header.span,
      'add `use "path" as alias` after the composition header',
    );
  }
  const result = {
    name: header.value,
    nets: orderedUses,
    wires,
    ...(shares.length === 0 ? {} : {shares}),
    ...(refinements.length === 0 ? {} : {refinements}),
    ...(final.length === 0 ? {} : {final}),
  };
  if (options.loadRef === undefined && options.origin === undefined) return result;
  try {
    parseComposition(result, options);
  } catch (error: unknown) {
    if (!(error instanceof NetValidationError)) throw error;
    throw compositionFitError(error.issues[0]!, {
      headerSpan: header.span,
      wires,
      wireEndpointSpans,
      shareSpans,
      finalSpans,
      refineFacts,
      refineTransitionSpans,
    });
  }
  return result;
}

const REFINE_HELP: readonly (readonly [string, string])[] = [
  ["has no transition", "refine a transition the net declares"],
  ["may only consume, read and produce", "refine a transition without inhibit arcs or a timer"],
  ["is not wired", "wire the place to a port of the refining net"],
  ["wired to it carry", "wire the place to a port that carries the arc's color"],
  ["is a composition", "refine by the alias of a net, not of a composition"],
];

/** The composition parser's first issue, as a PN202 at the fact, as in Python. */
function compositionFitError(
  issue: {code: string; path: string; message: string},
  facts: {
    headerSpan: IrSpan;
    wires: AnyObject[];
    wireEndpointSpans: [IrSpan, IrSpan][];
    shareSpans: IrSpan[];
    finalSpans: IrSpan[];
    refineFacts: Map<string, Fact<string>>;
    refineTransitionSpans: Map<string, IrSpan>;
  },
): PetrinetDslError {
  const wire = /^\/wires\/(\d+)(?:\/(from|to)\/port)?$/u.exec(issue.path);
  if (wire !== null) {
    const index = Number(wire[1]);
    const {from, to} = facts.wires[index] as {from: AnyObject; to: AnyObject};
    const [fromSpan, toSpan] = facts.wireEndpointSpans[index]!;
    const role = wire[2];
    const endpoint = role === "from" ? from : to;
    const written = `${endpoint.net}.(${endpoint.port})`;
    if (issue.code === "composition.port_undeclared") {
      return resolutionError(
        "PN202",
        `wire references unknown port ${written}`,
        role === "from" ? fromSpan : toSpan,
        "wire only declared port places",
      );
    }
    if (issue.code === "composition.port_direction") {
      return role === "from"
        ? resolutionError(
            "PN202",
            `wire source endpoint ${written} is an input port; a wire must run from an output port to an input port`,
            fromSpan,
            "reverse the wire so it runs from output to input",
          )
        : resolutionError(
            "PN202",
            `wire target ${written} must be an input port`,
            toSpan,
            "wire into an input port",
          );
    }
    const types = /^wired ports carry different types: (".*") -> (".*")$/u.exec(issue.message);
    if (issue.code === "composition.wire.type_mismatch" && types !== null) {
      return resolutionError(
        "PN202",
        `wire port colors differ: ${from.net}.(${from.port}) carries ${pythonStringRepr(JSON.parse(types[1]!))} but ${to.net}.(${to.port}) carries ${pythonStringRepr(JSON.parse(types[2]!))}`,
        toSpan,
        "connect ports that declare the same color",
      );
    }
  }
  const share = /^\/shares\/(\d+)$/u.exec(issue.path);
  if (share !== null && issue.message.startsWith("share ")) {
    return resolutionError(
      "PN202",
      issue.message,
      facts.shareSpans[Number(share[1])]!,
      "share places that exist and accept the same colors",
    );
  }
  const final = /^\/final\/(\d+)$/u.exec(issue.path);
  if (final !== null && issue.message.startsWith("final ")) {
    return resolutionError(
      "PN202",
      issue.message,
      facts.finalSpans[Number(final[1])]!,
      "name places that the composed nets declare",
    );
  }
  const refine = /^refine ([A-Za-z_][A-Za-z0-9_.]*)\.\[(.*?)\] by [A-Za-z_][A-Za-z0-9_]*: /u.exec(
    issue.message,
  );
  if (refine !== null) {
    // A path into a nested composition is reported under the flattened
    // alias: (lifecycle, gate.x) is (lifecycle.gate, x).
    const span = [...facts.refineTransitionSpans].find(([key]) => {
      const [alias, name] = JSON.parse(key) as [string, string];
      return `${alias}.${name}` === `${refine[1]}.${refine[2]}`;
    })?.[1];
    const reason = issue.message.slice(refine[0].length);
    return resolutionError(
      "PN202",
      issue.message,
      span ?? facts.headerSpan,
      REFINE_HELP.find(([phrase]) => reason.includes(phrase))?.[1],
    );
  }
  return resolutionError(
    "PN500",
    `composition reference loading failed: ${issue.message}`,
    facts.headerSpan,
  );
}

let celAdapter: ReturnType<typeof createDefaultCelAdapter> | undefined;
function isValidCel(source: string): boolean {
  try {
    (celAdapter ??= createDefaultCelAdapter()).compile(source);
    return true;
  } catch {
    return false;
  }
}

/** Resolve closed v1 Contribution IR into canonical net or composition JSON. */
export function resolveContributionIr(
  ir: ContributionIr | unknown,
  options: ParseCompositionOptions = {},
): ReadonlyJsonObject {
  const {documentKind, contributions} = validateEnvelope(ir);
  if (documentKind === "composition") {
    return resolveCompositionContributions(contributions, options);
  }

  let header: AnyObject | undefined;
  const placeAppearances: string[] = [];
  const declaredPlaces = new Set<string>();
  const transitions: string[] = [];
  const accepts = new Map<string, string[]>();
  const declaredAccepts = new Map<string, Fact<string[]>>();
  const ports = new Map<string, Fact<AnyObject>>();
  const handlers = new Map<string, Fact<string>>();
  const guards = new Map<string, Fact<string>>();
  const transitionSpans = new Map<string, IrSpan>();
  let arcs: ResolvedArc[] = [];
  const arcDeclarations: ArcDeclaration[] = [];
  const arcIndexes = new Map<string, number>();
  const arcObjects = new Map<string, ResolvedArc>();
  const arcHandles = new Map<string, Identity[]>();
  const arcHandleSpans = new Map<string, IrSpan>();
  const arcHandleIds = new Map<string, Identity>();
  const claimedHandleArcIds = new Set<string>();
  const arcData = new Map<string, Fact<JsonValue>>();
  const arcCels = new Map<string, Fact<string>>();
  const arcPredicates = new Map<string, Fact<AnyObject>>();
  const arcCorrelates = new Map<string, Fact<string>>();
  const capacities = new Map<string, Fact<AnyObject>>();
  const timers = new Map<string, {clock: string; cel: string; span: IrSpan}>();
  const timerBinds = new Map<string, Map<string, Fact<string>>>();
  const timerMaturities = new Map<string, Fact<string>>();
  const bindingNames = new Map<string, Map<string, Fact<string>>>();
  const priorities = new Map<string, Fact<number>>();
  const arcWeights = new Map<string, Fact<number>>();
  const transitionOrders = new Map<string, number>();
  const transitionOrderRanks = new Map<number, Fact<string>>();
  const handleOrders = new Map<string, number>();
  const templates = new Map<string, JsonValue>();
  const templateSpans = new Map<string, IrSpan>();
  const markings: {place: string; token: AnyObject; count: number; span: IrSpan}[] = [];
  const descriptions = new Map<string, Fact<string>>();
  const annotations = new Map<string, Map<string, Fact<JsonValue>>>();
  const namedMarkings = new Map<string, {place: string; token: AnyObject; count: number; span: IrSpan}[]>();
  const positions = new Map<string, Map<string, Fact<AnyObject> & {subject: PositionSubject}>>();
  const relativeBases: {viewName: string; base: PositionSubject; span: IrSpan}[] = [];
  const routes = new Map<string, Fact<AnyObject[]>>();
  const viewStyles = new Map<string, Fact<string>>();
  const decorations = new Map<string, Map<string, Fact<JsonValue>>>();
  let extensions: Fact<ReadonlyJsonObject> | undefined;
  const domains = new Map<string, Fact<JsonValue[]>>();
  const finalMarkings = new Map<string, Fact<string[]>>();
  const invariants: Fact<AnyObject>[] = [];
  const actors = new Map<string, Fact<string>>();

  const metadataKey = (type: string, name: string): string => JSON.stringify([type, name]);
  const viewSubjectKey = (view: string, type: string): string => JSON.stringify([view, type]);
  const routeKey = (view: string, handle: string): string => JSON.stringify([view, handle]);
  const pushPlaceAppearance = (name: string): void => {
    if (!placeAppearances.includes(name)) placeAppearances.push(name);
  };
  const pushTransition = (name: string, span: IrSpan): void => {
    if (!transitions.includes(name)) {
      transitions.push(name);
      transitionSpans.set(name, span);
    }
  };

  for (const contribution of contributions) {
    const {kind} = contribution;
    const target = contribution.target as AnyObject;
    const value = contribution.value as AnyObject;
    const span = contribution.span as IrSpan;
    if (!isObject(target) || !isObject(value) || !isObject(span)) {
      throw resolutionError("PN200", "invalid Contribution IR member");
    }

    if (kind === "document.net-header") {
      if (
        header !== undefined ||
        !keysEqual(target, ["type"]) ||
        target.type !== "document" ||
        Object.keys(value).some((key) => key !== "name" && key !== "description") ||
        typeof value.name !== "string"
      ) {
        throw resolutionError("PN200", "invalid net header contribution", span);
      }
      header = value;
      continue;
    }

    if (kind === "place.declare") {
      const name = target.name;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "place" ||
        typeof name !== "string" ||
        name.length === 0 ||
        Object.keys(value).length !== 0
      ) {
        throw resolutionError("PN200", "invalid place declaration contribution", span);
      }
      declaredPlaces.add(name);
      pushPlaceAppearance(name);
      continue;
    }

    if (kind === "transition.declare") {
      const name = target.name;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        Object.keys(value).length !== 0
      ) {
        throw resolutionError("PN200", "invalid transition declaration contribution", span);
      }
      pushTransition(name, span);
      continue;
    }

    if (kind === "place.accepts") {
      const name = target.name;
      const rawColors = value.colors;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "place" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["colors"]) ||
        !Array.isArray(rawColors) ||
        rawColors.length === 0 ||
        rawColors.some((color) => typeof color !== "string" || color.length === 0) ||
        new Set(rawColors).size !== rawColors.length
      ) {
        throw resolutionError("PN200", "invalid place accepted-colors contribution", span);
      }
      const colors = rawColors as string[];
      pushPlaceAppearance(name);
      const existing = declaredAccepts.get(name);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing.value, colors)) {
          throw resolutionError(
            "PN202",
            `conflicting accepted-color facts for place (${name})`,
            span,
            "remove one declaration or make both accepted-color lists identical",
            [["first accepted-color declaration was here", existing.span]],
          );
        }
        continue;
      }
      declaredAccepts.set(name, {value: colors, span});
      continue;
    }

    if (kind === "place.port") {
      const name = target.name;
      const {direction, color} = value;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "place" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["direction", "color"]) ||
        (direction !== "input" && direction !== "output") ||
        typeof color !== "string" ||
        color.length === 0
      ) {
        throw resolutionError("PN200", "invalid place port contribution", span);
      }
      const port = {direction, type: color};
      const existing = ports.get(name);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing.value, port)) {
          throw resolutionError(
            "PN202",
            `conflicting port facts for place (${name})`,
            span,
            "remove one declaration or make both port values identical",
            [["first port was declared here", existing.span]],
          );
        }
        continue;
      }
      ports.set(name, {value: port, span});
      continue;
    }

    if (kind === "arc.handle") {
      const name = target.name;
      const rawArcIds = value.arcIds;
      const contributionId = contributionIdentity(contribution.id);
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        !keysEqual(value, ["arcIds"]) ||
        !Array.isArray(rawArcIds) ||
        rawArcIds.length < 1 ||
        contributionId === null ||
        contributionId[2] !== 0
      ) {
        throw resolutionError("PN200", "invalid arc handle contribution", span);
      }
      const resolvedIds: Identity[] = [];
      for (const rawArcId of rawArcIds) {
        const arcId = arcIdentity(rawArcId);
        if (
          arcId === null ||
          arcId[0] !== contributionId[0] ||
          claimedHandleArcIds.has(identityKey(arcId))
        ) {
          throw resolutionError("PN200", "invalid arc handle contribution", span);
        }
        resolvedIds.push(arcId);
      }
      for (const id of resolvedIds) claimedHandleArcIds.add(identityKey(id));
      const existing = arcHandles.get(name);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing, resolvedIds)) {
          throw resolutionError(
            "PN202",
            `conflicting declarations for arc handle @${name}`,
            span,
            undefined,
            [["first declaration was here", arcHandleSpans.get(name) as IrSpan]],
          );
        }
        continue;
      }
      arcHandles.set(name, resolvedIds);
      arcHandleIds.set(name, contributionId);
      arcHandleSpans.set(name, span);
      continue;
    }

    if (kind === "order.transition") {
      const name = target.name;
      const rank = value.rank;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        !Number.isInteger(rank) ||
        rank < 1 ||
        transitionOrders.has(name)
      ) {
        throw resolutionError("PN200", "invalid transition order contribution", span);
      }
      const existing = transitionOrderRanks.get(rank);
      if (existing !== undefined) {
        throw resolutionError(
          "PN202",
          `transition order position ${rank} is assigned more than once`,
          span,
          "assign each explicitly ordered transition a unique positive position",
          [[`[${existing.value}] first assigned position ${rank}`, existing.span]],
        );
      }
      transitionOrders.set(name, rank);
      transitionOrderRanks.set(rank, {value: name, span});
      continue;
    }

    if (kind === "order.arc-run") {
      const name = target.name;
      const rank = value.rank;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        !Number.isInteger(rank) ||
        rank < 1 ||
        handleOrders.has(name)
      ) {
        throw resolutionError("PN200", "invalid arc-run order contribution", span);
      }
      handleOrders.set(name, rank);
      continue;
    }

    if (kind === "place.capacity-per-color-key") {
      const name = target.name;
      if (!keysEqual(target, ["type", "name"]) || target.type !== "place" || typeof name !== "string") {
        throw resolutionError("PN200", "invalid place capacity contribution", span);
      }
      if (!keysEqual(value, ["key", "max"])) {
        throw resolutionError(
          "PN202",
          `capacityPerColorKey for (${name}) must contain exactly key and max`,
          span,
        );
      }
      if (!validCapacityKey(value.key)) {
        throw resolutionError(
          "PN202",
          `capacityPerColorKey key must be a non-empty string or non-empty array of non-empty strings for (${name})`,
          span,
        );
      }
      if (!Number.isInteger(value.max) || value.max < 1) {
        throw resolutionError(
          "PN202",
          `capacityPerColorKey max must be an integer greater than or equal to 1; got ${pythonRepr(value.max)} for (${name})`,
          span,
        );
      }
      const capacity = {key: value.key, max: value.max};
      const existing = capacities.get(name);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing.value, capacity)) {
          throw resolutionError(
            "PN202",
            `conflicting capacityPerColorKey facts for (${name})`,
            span,
            undefined,
            [["first declaration was here", existing.span]],
          );
        }
        continue;
      }
      capacities.set(name, {value: capacity, span});
      continue;
    }

    if (kind === "arc.weight") {
      const name = target.name;
      const weight = value.weight;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        !keysEqual(value, ["weight"])
      ) {
        throw resolutionError("PN200", "invalid arc weight contribution", span);
      }
      if (!Number.isInteger(weight) || weight < 1) {
        throw resolutionError(
          "PN202",
          `arc weight must be an integer greater than or equal to 1; got ${pythonRepr(weight)} for @${name}`,
          span,
        );
      }
      const existing = arcWeights.get(name);
      if (existing !== undefined) {
        if (existing.value !== weight) {
          throw resolutionError(
            "PN202",
            `conflicting weight facts for arc @${name}`,
            span,
            undefined,
            [["first declaration was here", existing.span]],
          );
        }
        continue;
      }
      arcWeights.set(name, {value: weight, span});
      continue;
    }

    if (kind === "arc.produce-data") {
      const name = target.name;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        !keysEqual(value, ["data"]) ||
        !isObject(value.data)
      ) {
        throw resolutionError("PN200", "invalid arc produce-data contribution", span);
      }
      let data: JsonValue;
      try {
        data = untag(value.data);
      } catch (error) {
        if (error instanceof PetrinetResourceError) throw error;
        throw resolutionError("PN200", "invalid tagged JSON arc data value", span);
      }
      const existing = arcData.get(name);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing.value, data)) {
          throw resolutionError(
            "PN202",
            `conflicting data facts for arc @${name}`,
            span,
            "remove one declaration or make both arc data values identical",
            [[`first value ${compactSortedJson(existing.value)} was declared here`, existing.span]],
          );
        }
        continue;
      }
      arcData.set(name, {value: data, span});
      continue;
    }

    if (kind === "arc.produce-cel") {
      const name = target.name;
      const cel = value.cel;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        !keysEqual(value, ["cel"]) ||
        typeof cel !== "string" ||
        cel.length === 0
      ) {
        throw resolutionError("PN200", "invalid arc produce-cel contribution", span);
      }
      const existing = arcCels.get(name);
      if (existing !== undefined) {
        if (existing.value !== cel) {
          throw resolutionError(
            "PN202",
            `conflicting data cel facts for arc @${name}`,
            span,
            undefined,
            [["first declaration was here", existing.span]],
          );
        }
        continue;
      }
      arcCels.set(name, {value: cel, span});
      continue;
    }

    if (kind === "arc.predicate") {
      const name = target.name;
      const predicateKind = value.kind;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        (predicateKind !== "cel" && predicateKind !== "handler") ||
        !keysEqual(value, ["kind", predicateKind]) ||
        typeof value[predicateKind] !== "string" ||
        value[predicateKind].length === 0
      ) {
        throw resolutionError("PN200", "invalid arc predicate contribution", span);
      }
      const predicate = {[predicateKind]: value[predicateKind]};
      const existing = arcPredicates.get(name);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing.value, predicate)) {
          throw resolutionError(
            "PN202",
            `conflicting predicate facts for arc @${name}`,
            span,
            "remove one declaration or make both predicate values identical",
            [["first predicate was declared here", existing.span]],
          );
        }
        continue;
      }
      arcPredicates.set(name, {value: predicate, span});
      continue;
    }

    if (kind === "arc.correlate") {
      const name = target.name;
      const cel = value.cel;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof name !== "string" ||
        !keysEqual(value, ["cel"]) ||
        typeof cel !== "string" ||
        cel.length === 0
      ) {
        throw resolutionError("PN200", "invalid arc correlate contribution", span);
      }
      const existing = arcCorrelates.get(name);
      if (existing !== undefined) {
        if (existing.value !== cel) {
          throw resolutionError(
            "PN202",
            `conflicting correlate facts for arc @${name}`,
            span,
            "remove one declaration or make both CEL expressions identical",
            [["first correlate was declared here", existing.span]],
          );
        }
        continue;
      }
      arcCorrelates.set(name, {value: cel, span});
      continue;
    }

    if (kind === "arc.declare") {
      const rawColor = value.color;
      const rawSource = value.from;
      const rawDestination = value.to;
      const mode = value.mode;
      const id = arcIdentity(target.id);
      const contributionId = contributionIdentity(contribution.id);
      if (
        !keysEqual(target, ["type", "id"]) ||
        target.type !== "arc" ||
        id === null ||
        contributionId === null ||
        !sameIdentity(id, contributionId) ||
        !isObject(rawColor) ||
        !isObject(rawSource) ||
        !isObject(rawDestination) ||
        !["consume", "read", "inhibit", "produce"].includes(mode)
      ) {
        throw resolutionError("PN200", "invalid arc declaration", span);
      }
      if (
        !keysEqual(rawColor, ["kind", "value"]) ||
        rawColor.kind !== "explicit" ||
        typeof rawColor.value !== "string" ||
        rawColor.value.length === 0
      ) {
        throw resolutionError("PN200", "invalid arc declaration", span);
      }
      let place: unknown;
      let transition: unknown;
      let transitionNameSpan: IrSpan;
      const isInput =
        rawSource.type === "place" &&
        rawDestination.type === "transition" &&
        ["consume", "read", "inhibit"].includes(mode);
      if (isInput) {
        const expected = ["from", "to", "color", "mode"];
        if (mode === "consume") expected.push("transitionNameSpan");
        if (!keysEqual(value, expected)) {
          throw resolutionError("PN200", "invalid consumed arc declaration", span);
        }
        place = rawSource.name;
        transition = rawDestination.name;
        transitionNameSpan = value.transitionNameSpan ?? span;
        if (mode === "consume" && !isSourceSpan(transitionNameSpan, contributionId[0])) {
          throw resolutionError("PN200", "consumed arc has invalid transitionNameSpan", span);
        }
      } else if (
        rawSource.type === "transition" &&
        rawDestination.type === "place" &&
        mode === "produce"
      ) {
        if (!keysEqual(value, ["from", "to", "color", "mode"])) {
          throw resolutionError("PN200", "invalid produced arc declaration", span);
        }
        place = rawDestination.name;
        transition = rawSource.name;
        transitionNameSpan = span;
      } else {
        throw resolutionError("PN200", "invalid Coin Deposit arc direction", span);
      }
      if (typeof place !== "string" || typeof transition !== "string") {
        throw resolutionError("PN200", "arc endpoint names must be strings", span);
      }
      pushPlaceAppearance(place);
      pushTransition(transition, transitionNameSpan);
      arcDeclarations.push({
        id,
        place,
        transition,
        isInput,
        mode,
        color: rawColor as {kind: "explicit"; value: string},
        span,
        transitionNameSpan,
      });
      continue;
    }

    if (kind === "transition.timer") {
      const name = target.name;
      const rawClock = value.clock;
      const cel = value.cel;
      if (
        !isObject(rawClock) ||
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["clock", "cel"]) ||
        !keysEqual(rawClock, ["type", "name"]) ||
        rawClock.type !== "place" ||
        typeof rawClock.name !== "string" ||
        rawClock.name.length === 0 ||
        typeof cel !== "string" ||
        cel.length === 0
      ) {
        throw resolutionError("PN200", "invalid transition timer contribution", span);
      }
      const existing = timers.get(name);
      if (existing !== undefined) {
        if (existing.clock !== rawClock.name) {
          throw resolutionError(
            "PN202",
            `conflicting timer clock facts for transition [${name}]`,
            span,
            "remove one declaration or make both timer clock values identical",
            [["first timer clock was declared here", existing.span]],
          );
        }
        if (existing.cel !== cel) {
          throw resolutionError(
            "PN202",
            `conflicting timer CEL facts for transition [${name}]`,
            span,
            "remove one declaration or make both timer CEL values identical",
            [["first timer CEL was declared here", existing.span]],
          );
        }
        continue;
      }
      timers.set(name, {clock: rawClock.name, cel, span});
      continue;
    }

    if (kind === "transition.timer-maturity") {
      const name = target.name;
      const maturity = value.maturity;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["maturity"]) ||
        typeof maturity !== "string" ||
        maturity.length === 0
      ) {
        throw resolutionError("PN200", "invalid transition timer maturity contribution", span);
      }
      const existing = timerMaturities.get(name);
      if (existing !== undefined && existing.value !== maturity) {
        throw resolutionError(
          "PN202",
          `conflicting timer maturity CEL facts for transition [${name}]`,
          span,
          "remove one declaration or make both timer maturity CEL values identical",
          [["first timer maturity CEL was declared here", existing.span]],
        );
      }
      if (existing === undefined) timerMaturities.set(name, {value: maturity, span});
      continue;
    }

    if (kind === "transition.timer-bind") {
      const name = target.name;
      const bindName = value.name;
      const rawPlace = value.place;
      if (
        !isObject(rawPlace) ||
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["name", "place"]) ||
        typeof bindName !== "string" ||
        !TIMER_BIND_IDENTIFIER.test(bindName) ||
        !keysEqual(rawPlace, ["type", "name"]) ||
        rawPlace.type !== "place" ||
        typeof rawPlace.name !== "string" ||
        rawPlace.name.length === 0
      ) {
        throw resolutionError("PN200", "invalid transition timer bind contribution", span);
      }
      let binds = timerBinds.get(name);
      if (binds === undefined) {
        binds = new Map();
        timerBinds.set(name, binds);
      }
      const existing = binds.get(bindName);
      if (existing !== undefined) {
        if (existing.value !== rawPlace.name) {
          throw resolutionError(
            "PN202",
            `conflicting timer bind facts for ${pythonRepr(bindName)} on transition [${name}]`,
            span,
            "remove one declaration or make both timer bind values identical",
            [["first timer bind was declared here", existing.span]],
          );
        }
        continue;
      }
      binds.set(bindName, {value: rawPlace.name, span});
      continue;
    }

    if (kind === "transition.binding-name") {
      const name = target.name;
      const key = value.name;
      const rawPlace = value.place;
      if (
        !isObject(rawPlace) ||
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["name", "place"]) ||
        typeof key !== "string" ||
        key.length === 0 ||
        !keysEqual(rawPlace, ["type", "name"]) ||
        rawPlace.type !== "place" ||
        typeof rawPlace.name !== "string" ||
        rawPlace.name.length === 0
      ) {
        throw resolutionError("PN200", "invalid transition binding name contribution", span);
      }
      let keys = bindingNames.get(name);
      if (keys === undefined) {
        keys = new Map();
        bindingNames.set(name, keys);
      }
      const existing = keys.get(key);
      if (existing !== undefined) {
        if (existing.value !== rawPlace.name) {
          throw resolutionError(
            "PN202",
            `conflicting binding name facts for ${pythonRepr(key)} on transition [${name}]`,
            span,
            "remove one declaration or make both binding name values identical",
            [["first binding name was declared here", existing.span]],
          );
        }
        continue;
      }
      keys.set(key, {value: rawPlace.name, span});
      continue;
    }

    if (kind === "transition.priority") {
      const name = target.name;
      const priority = value.priority;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["priority"]) ||
        !Number.isInteger(priority) ||
        priority < 0
      ) {
        throw resolutionError("PN200", "invalid transition priority contribution", span);
      }
      const existing = priorities.get(name);
      if (existing !== undefined) {
        if (existing.value !== priority) {
          throw resolutionError(
            "PN202",
            `conflicting priority facts for transition [${name}]`,
            span,
            "remove one declaration or make both priority values identical",
            [["first priority was declared here", existing.span]],
          );
        }
        continue;
      }
      priorities.set(name, {value: priority, span});
      continue;
    }

    if (kind === "transition.handler") {
      const name = target.name;
      const handler = value.handler;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["handler"]) ||
        typeof handler !== "string"
      ) {
        throw resolutionError("PN200", "invalid transition handler contribution", span);
      }
      const existing = handlers.get(name);
      if (existing !== undefined) {
        if (existing.value !== handler) {
          throw resolutionError(
            "PN202",
            `conflicting handler facts for transition [${name}]`,
            span,
            "remove one declaration or make both handler values identical",
            [["first handler was declared here", existing.span]],
          );
        }
        continue;
      }
      handlers.set(name, {value: handler, span});
      continue;
    }

    if (kind === "transition.guard") {
      const name = target.name;
      const guard = value.guard;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "transition" ||
        typeof name !== "string" ||
        name.length === 0 ||
        !keysEqual(value, ["guard"]) ||
        typeof guard !== "string" ||
        guard.length === 0
      ) {
        throw resolutionError("PN200", "invalid transition guard contribution", span);
      }
      const existing = guards.get(name);
      if (existing !== undefined) {
        if (existing.value !== guard) {
          throw resolutionError(
            "PN204",
            `conflicting guard facts for transition [${name}]`,
            span,
            "remove one declaration or make both guard values identical",
            [["first guard was declared here", existing.span]],
          );
        }
        continue;
      }
      guards.set(name, {value: guard, span});
      continue;
    }

    if (kind === "marking.append") {
      const place = target.name;
      const count = value.count;
      const message = "invalid initial marking contribution";
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "place" ||
        typeof place !== "string" ||
        place.length === 0 ||
        !keysEqual(value, ["count", "token"]) ||
        !Number.isInteger(count) ||
        count < 1
      ) {
        throw resolutionError("PN200", message, span);
      }
      markings.push({place, token: parseMarkingToken(value.token, message, span), count, span});
      continue;
    }

    if (kind === "template.define") {
      const name = target.name;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "template" ||
        typeof name !== "string" ||
        !isObject(value.value)
      ) {
        throw resolutionError("PN200", "invalid template definition contribution", span);
      }
      let resolvedTemplate: JsonValue;
      try {
        resolvedTemplate = untag(value.value);
      } catch (error) {
        if (error instanceof PetrinetResourceError) throw error;
        throw resolutionError("PN200", "invalid tagged JSON template value", span);
      }
      if (templates.has(name)) {
        if (!jsonValuesEqual(templates.get(name), resolvedTemplate)) {
          throw resolutionError(
            "PN202",
            `conflicting definitions for template $${name}`,
            span,
            undefined,
            [["first definition was here", templateSpans.get(name) as IrSpan]],
          );
        }
        continue;
      }
      templates.set(name, resolvedTemplate);
      templateSpans.set(name, span);
      continue;
    }

    if (kind === "documentation.description") {
      const targetType = target.type;
      const targetName = target.name ?? "";
      const text = value.text;
      if (
        (!["document", "place", "transition", "arcHandle"].includes(targetType)) ||
        (targetType === "document" &&
          !(
            keysEqual(target, ["type"]) ||
            (keysEqual(target, ["type", "kind"]) && target.kind === "net")
          )) ||
        (targetType !== "document" && (!keysEqual(target, ["type", "name"]) || typeof targetName !== "string")) ||
        !keysEqual(value, ["text"]) ||
        typeof text !== "string"
      ) {
        throw resolutionError("PN200", "invalid documentation description contribution", span);
      }
      const key = metadataKey(targetType, targetName);
      const existing = descriptions.get(key);
      if (existing !== undefined && existing.value !== text) {
        const renderedTarget =
          targetType === "place" ? `(${targetName})` :
          targetType === "transition" ? `[${targetName}]` :
          targetType === "arcHandle" ? `@${targetName}` : "net";
        throw resolutionError(
          "PN202",
          `conflicting description facts for ${targetType} ${renderedTarget}`,
          span,
          undefined,
          [["first description was declared here", existing.span]],
        );
      }
      if (existing === undefined) descriptions.set(key, {value: text, span});
      continue;
    }

    if (kind === "documentation.annotation") {
      const targetType = target.type;
      const targetName = target.name ?? "";
      const annotationKey = value.key;
      if (
        !["document", "place", "transition", "arcHandle"].includes(targetType) ||
        (targetType === "document" &&
          !(
            keysEqual(target, ["type"]) ||
            (keysEqual(target, ["type", "kind"]) && target.kind === "net")
          )) ||
        (targetType !== "document" && (!keysEqual(target, ["type", "name"]) || typeof targetName !== "string")) ||
        !keysEqual(value, ["key", "value"]) ||
        typeof annotationKey !== "string" ||
        annotationKey.length === 0 ||
        !isObject(value.value)
      ) {
        throw resolutionError("PN200", "invalid documentation annotation contribution", span);
      }
      if (annotationKey === "petrinet.dsl/v1") {
        throw resolutionError(
          "PN202",
          "annotation key 'petrinet.dsl/v1' is reserved for compiler-owned metadata",
          span,
          "use extensions for opaque full-document data",
        );
      }
      let annotationValue: JsonValue;
      try {
        annotationValue = untag(value.value);
      } catch (error) {
        if (error instanceof PetrinetResourceError) throw error;
        throw resolutionError("PN200", "invalid documentation annotation contribution", span);
      }
      const identity = metadataKey(targetType, targetName);
      let facts = annotations.get(identity);
      if (facts === undefined) {
        facts = new Map();
        annotations.set(identity, facts);
      }
      const existing = facts.get(annotationKey);
      if (existing !== undefined && !jsonValuesEqual(existing.value, annotationValue)) {
        const renderedTarget =
          targetType === "place" ? `place (${targetName})` :
          targetType === "transition" ? `transition [${targetName}]` :
          targetType === "arcHandle" ? `arc @${targetName}` : "net";
        throw resolutionError(
          "PN202",
          `conflicting annotation ${annotationKey} facts for ${renderedTarget}`,
          span,
          "remove one declaration or make both annotation values identical",
          [["first annotation value was declared here", existing.span]],
        );
      }
      if (existing === undefined) facts.set(annotationKey, {value: annotationValue, span});
      continue;
    }

    if (kind === "metadata.named-marking") {
      const name = value.name;
      const rawEntries = value.entries;
      if (
        !keysEqual(target, ["type"]) ||
        target.type !== "document" ||
        !keysEqual(value, ["name", "entries"]) ||
        typeof name !== "string" ||
        name.length === 0 ||
        !Array.isArray(rawEntries)
      ) {
        throw resolutionError("PN200", "invalid named marking contribution", span);
      }
      if (name === "initial") {
        throw resolutionError(
          "PN202",
          "'initial' is reserved and cannot name a non-initial marking",
          span,
          "use the unquoted initial marking keyword or choose another name",
        );
      }
      const parsedEntries: {place: string; token: AnyObject; count: number; span: IrSpan}[] = [];
      for (const rawEntry of rawEntries) {
        if (!isObject(rawEntry) || !isObject(rawEntry.place)) {
          throw resolutionError("PN200", "invalid named marking contribution", span);
        }
        const place = rawEntry.place.name;
        const count = rawEntry.count;
        if (
          !keysEqual(rawEntry, ["place", "count", "token"]) ||
          !keysEqual(rawEntry.place, ["type", "name"]) ||
          rawEntry.place.type !== "place" ||
          typeof place !== "string" ||
          place.length === 0 ||
          !Number.isInteger(count) ||
          count < 1
        ) {
          throw resolutionError("PN200", "invalid named marking contribution", span);
        }
        parsedEntries.push({
          place,
          token: parseMarkingToken(rawEntry.token, "invalid named marking contribution", span),
          count,
          span,
        });
      }
      const entries = namedMarkings.get(name) ?? [];
      entries.push(...parsedEntries);
      namedMarkings.set(name, entries);
      continue;
    }

    if (kind === "view.position") {
      const viewName = target.name;
      const parsedSubject = positionSubject(value.subject);
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "view" ||
        typeof viewName !== "string" ||
        viewName.length === 0 ||
        !keysEqual(value, ["subject", "position"]) ||
        parsedSubject === undefined ||
        !isObject(value.position)
      ) {
        throw resolutionError("PN200", "invalid view position contribution", span);
      }
      let position: AnyObject;
      if (keysEqual(value.position, ["from", "delta"])) {
        const parsedBase = positionSubject(value.position.from);
        if (parsedBase === undefined) {
          throw resolutionError("PN200", "invalid view position contribution", span);
        }
        let decodedDelta: JsonValue;
        try {
          decodedDelta = untag(value.position.delta);
        } catch (error) {
          if (error instanceof PetrinetResourceError) throw error;
          throw resolutionError("PN200", "invalid view position contribution", span);
        }
        const decodedDeltaAny = decodedDelta as AnyObject;
        if (
          !keysEqual(decodedDeltaAny, ["x", "y"]) ||
          typeof decodedDeltaAny.x !== "number" ||
          typeof decodedDeltaAny.y !== "number"
        ) {
          throw resolutionError("PN200", "invalid view position contribution", span);
        }
        position = {
          from: positionKey(parsedBase),
          delta: {x: decodedDeltaAny.x, y: decodedDeltaAny.y},
        };
        relativeBases.push({viewName, base: parsedBase, span});
      } else {
        let decodedPosition: JsonValue;
        try {
          decodedPosition = untag(value.position);
        } catch (error) {
          if (error instanceof PetrinetResourceError) throw error;
          throw resolutionError("PN200", "invalid view position contribution", span);
        }
        const decodedAny = decodedPosition as AnyObject;
        if (
          !keysEqual(decodedAny, ["x", "y"]) ||
          typeof decodedAny.x !== "number" ||
          typeof decodedAny.y !== "number"
        ) {
          throw resolutionError("PN200", "invalid view position contribution", span);
        }
        position = {x: decodedAny.x, y: decodedAny.y};
      }
      const subjectKey = positionKey(parsedSubject);
      const key = viewSubjectKey(viewName, parsedSubject.kind);
      let viewPositions = positions.get(key);
      if (viewPositions === undefined) {
        viewPositions = new Map();
        positions.set(key, viewPositions);
      }
      const existing = viewPositions.get(subjectKey);
      if (existing !== undefined && !jsonValuesEqual(existing.value, position)) {
        const noun = parsedSubject.kind === "placeCopy" ? "copy " : `${parsedSubject.kind} `;
        throw resolutionError(
          "PN202",
          `conflicting position facts for ${noun}${renderedPositionTarget(parsedSubject)} in view ${pythonRepr(viewName)}`,
          span,
          "remove one declaration or make both positions identical",
          [["first position was declared here", existing.span]],
        );
      }
      if (existing === undefined) {
        viewPositions.set(subjectKey, {value: position, span, subject: parsedSubject});
      }
      continue;
    }

    if (kind === "view.route") {
      const handle = target.name;
      const view = value.view;
      const rawPoints = value.points;
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "arcHandle" ||
        typeof handle !== "string" ||
        !keysEqual(value, ["view", "points"]) ||
        !isObject(view) ||
        !keysEqual(view, ["type", "name"]) ||
        view.type !== "view" ||
        typeof view.name !== "string" ||
        !Array.isArray(rawPoints)
      ) {
        throw resolutionError("PN200", "invalid view route contribution", span);
      }
      if (rawPoints.length === 0) {
        throw resolutionError(
          "PN202",
          `view ${pythonRepr(view.name)} route @${handle} requires at least one point`,
          span,
          'add at least one {"x": Number, "y": Number} point',
        );
      }
      const points: AnyObject[] = [];
      try {
        for (const rawPoint of rawPoints) {
          if (!isObject(rawPoint)) throw new Error("invalid point");
          const decodedPoint = untag(rawPoint);
          if (!isObject(decodedPoint)) throw new Error("invalid point");
          const point = decodedPoint as AnyObject;
          if (
            !keysEqual(point, ["x", "y"]) ||
            typeof point.x !== "number" ||
            typeof point.y !== "number"
          ) {
            throw new Error("invalid point");
          }
          points.push(point);
        }
      } catch (error) {
        if (error instanceof PetrinetResourceError) throw error;
        throw resolutionError("PN200", "invalid view route contribution", span);
      }
      const key = routeKey(view.name, handle);
      const existing = routes.get(key);
      if (existing !== undefined && !jsonValuesEqual(existing.value, points)) {
        throw resolutionError(
          "PN202",
          `conflicting route facts for arc @${handle} in view ${pythonRepr(view.name)}`,
          span,
          undefined,
          [["first route was declared here", existing.span]],
        );
      }
      if (existing === undefined) routes.set(key, {value: points, span});
      continue;
    }

    if (kind === "view.splines" || kind === "view.detail") {
      const member = kind.slice("view.".length);
      const viewName = target.name;
      const styleValue = value[member];
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "view" ||
        typeof viewName !== "string" ||
        viewName.length === 0 ||
        !keysEqual(value, [member]) ||
        typeof styleValue !== "string"
      ) {
        throw resolutionError("PN200", `invalid view ${member} contribution`, span);
      }
      const key = JSON.stringify([viewName, member]);
      const existing = viewStyles.get(key);
      if (existing !== undefined && existing.value !== styleValue) {
        throw resolutionError(
          "PN202",
          `conflicting ${member} facts for view ${pythonRepr(viewName)}`,
          span,
          "remove one declaration or make both values identical",
          [[`first ${member} value was declared here`, existing.span]],
        );
      }
      if (existing === undefined) viewStyles.set(key, {value: styleValue, span});
      continue;
    }

    if (
      kind === "decoration.highlight" ||
      kind === "decoration.note" ||
      kind === "decoration.summary" ||
      kind === "decoration.quiet" ||
      kind === "decoration.beside" ||
      kind === "decoration.show"
    ) {
      const member = kind.slice("decoration.".length);
      const targetType = target.type;
      const targetName = target.name;
      const allowedTypes = member === "quiet" || member === "show"
        ? ["color"]
        : member === "beside"
          ? ["place"]
          : member === "summary"
            ? ["transition", "arcHandle"]
            : ["place", "transition", "arcHandle"];
      let validValue: boolean;
      let decorationValue: JsonValue;
      if (member === "highlight") {
        validValue =
          Object.keys(value).every((key) => key === "label") &&
          (value.label === undefined || typeof value.label === "string");
        decorationValue = value.label === undefined ? {} : {label: value.label as string};
      } else if (member === "beside") {
        validValue =
          Object.keys(value).every((key) => key === "side") &&
          (value.side === undefined || value.side === "left" || value.side === "right");
        decorationValue = value.side === undefined ? {} : {side: value.side as string};
      } else if (member === "quiet") {
        validValue = Object.keys(value).length === 0;
        decorationValue = true;
      } else if (member === "show") {
        const fields = value.fields;
        validValue =
          keysEqual(value, ["fields"]) &&
          Array.isArray(fields) &&
          fields.length > 0 &&
          fields.every(validFieldPath) &&
          new Set(fields).size === fields.length;
        decorationValue = validValue ? [...(fields as string[])] : null;
      } else {
        validValue = keysEqual(value, ["text"]) && typeof value.text === "string";
        decorationValue = value.text as string;
      }
      if (
        !keysEqual(target, ["type", "name"]) ||
        typeof targetType !== "string" ||
        !allowedTypes.includes(targetType) ||
        typeof targetName !== "string" ||
        targetName.length === 0 ||
        !validValue
      ) {
        throw resolutionError("PN200", invalidContributionMessage(contribution), span);
      }
      const subjectKind = targetType === "arcHandle" ? "arc" : targetType;
      const subject = `${subjectKind}:${targetName}`;
      let facts = decorations.get(subject);
      if (facts === undefined) {
        facts = new Map();
        decorations.set(subject, facts);
      }
      const existing = facts.get(member);
      if (existing !== undefined && !jsonValuesEqual(existing.value, decorationValue)) {
        const renderedTarget = subjectKind === "place"
          ? `(${targetName})`
          : subjectKind === "transition"
            ? `[${targetName}]`
            : subjectKind === "arc"
              ? `@${targetName}`
              : `color ${targetName}`;
        throw resolutionError(
          "PN202",
          `conflicting ${member} decorations for ${renderedTarget}`,
          span,
          "remove one declaration or make both decorations identical",
          [[`first ${member} decoration was declared here`, existing.span]],
        );
      }
      if (existing === undefined) facts.set(member, {value: decorationValue, span});
      continue;
    }

    if (kind === "document.extensions") {
      if (
        !keysEqual(target, ["type"]) ||
        target.type !== "document" ||
        !keysEqual(value, ["extensions"]) ||
        !isObject(value.extensions)
      ) {
        throw resolutionError("PN200", "invalid document extensions contribution", span);
      }
      let decodedValue: JsonValue;
      try {
        decodedValue = untag(value.extensions);
      } catch (error) {
        if (error instanceof PetrinetResourceError) throw error;
        throw resolutionError("PN200", "invalid document extensions contribution", span);
      }
      if (!isObject(decodedValue)) {
        throw resolutionError("PN200", "invalid document extensions contribution", span);
      }
      const decoded = decodedValue as ReadonlyJsonObject;
      if (extensions !== undefined && !jsonValuesEqual(extensions.value, decoded)) {
        throw resolutionError(
          "PN202",
          "conflicting document extensions facts",
          span,
          undefined,
          [["first extensions were declared here", extensions.span]],
        );
      }
      if (extensions === undefined) extensions = {value: decoded, span};
      continue;
    }

    if (kind === "domain.values") {
      const color = target.name;
      const path = value.path;
      let domainValues: JsonValue[] = [];
      try {
        domainValues = Array.isArray(value.values)
          ? value.values.map((item: unknown) => untag(item as AnyObject))
          : [];
      } catch (error) {
        if (error instanceof PetrinetResourceError) throw error;
        throw resolutionError("PN200", "invalid domain contribution", span);
      }
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "color" ||
        typeof color !== "string" ||
        color.length === 0 ||
        !keysEqual(value, ["path", "values"]) ||
        !validFieldPath(path) ||
        domainValues.length === 0 ||
        domainValues.some((item) => item === null || typeof item === "object") ||
        domainValues.some((item, index) =>
          domainValues.slice(0, index).some((other) => jsonValuesEqual(item, other)),
        )
      ) {
        throw resolutionError("PN200", "invalid domain contribution", span);
      }
      const key = `${color}.${path}`;
      const existing = domains.get(key);
      if (existing !== undefined) {
        if (!jsonValuesEqual(existing.value, domainValues)) {
          throw resolutionError(
            "PN202",
            `conflicting domain facts for ${key}`,
            span,
            "remove one declaration or make both value lists identical",
            [["first domain was declared here", existing.span]],
          );
        }
        continue;
      }
      domains.set(key, {value: domainValues, span});
      continue;
    }

    if (kind === "proof.final") {
      const name = target.name;
      const others: unknown = value.with ?? [];
      if (
        !keysEqual(target, ["type", "name"]) ||
        target.type !== "place" ||
        typeof name !== "string" ||
        name.length === 0 ||
        Object.keys(value).some((key) => key !== "with") ||
        !Array.isArray(others) ||
        (value.with !== undefined && others.length === 0) ||
        !others.every((other) => typeof other === "string" && other.length > 0)
      ) {
        throw resolutionError("PN200", "invalid final place contribution", span);
      }
      const marking = [name, ...(others as string[])];
      if (new Set(marking).size !== marking.length) {
        throw resolutionError("PN200", "invalid final place contribution", span);
      }
      const key = JSON.stringify([...marking].sort());
      if (!finalMarkings.has(key)) finalMarkings.set(key, {value: marking, span});
      continue;
    }

    if (kind === "proof.invariant") {
      const terms: unknown[] = Array.isArray(value.terms) ? value.terms : [];
      const constant: unknown = value.constant;
      const invariantName: unknown = value.name;
      const validTerm = (term: unknown): boolean =>
        isObject(term) &&
        keysEqual(term, ["place", "weight"]) &&
        typeof term.place === "string" &&
        term.place.length > 0 &&
        Number.isSafeInteger(term.weight) &&
        term.weight >= 1;
      if (
        !keysEqual(target, ["type", "kind"]) ||
        target.type !== "document" ||
        target.kind !== "net" ||
        Object.keys(value).some((member) => !["terms", "name", "constant"].includes(member)) ||
        terms.length === 0 ||
        !terms.every(validTerm) ||
        new Set(terms.map((term) => (term as AnyObject).place)).size !== terms.length ||
        (constant !== undefined && (!Number.isSafeInteger(constant) || (constant as number) < 0)) ||
        (invariantName !== undefined &&
          (typeof invariantName !== "string" || invariantName.length === 0))
      ) {
        throw resolutionError("PN200", "invalid invariant contribution", span);
      }
      const invariant: AnyObject = {
        weights: Object.fromEntries(
          terms.map((term) => [(term as AnyObject).place, (term as AnyObject).weight]),
        ),
      };
      if (constant !== undefined) invariant.constant = constant;
      if (invariantName !== undefined) {
        const first = invariants.find((fact) => fact.value.name === invariantName);
        if (first !== undefined) {
          throw resolutionError(
            "PN202",
            `two invariants are named ${pythonRepr(invariantName)}`,
            span,
            "give each invariant its own name",
            [["first invariant was declared here", first.span]],
          );
        }
        invariant.name = invariantName;
      }
      invariants.push({value: invariant, span});
      continue;
    }

    if (kind === "actor.declare") {
      const actorName: unknown = value.name;
      const actorKind: unknown = value.kind;
      if (
        !keysEqual(target, ["type", "kind"]) ||
        target.type !== "document" ||
        target.kind !== "net" ||
        !keysEqual(value, ["name", "kind"]) ||
        typeof actorName !== "string" ||
        actorName.length === 0 ||
        (actorKind !== "person" && actorKind !== "system" && actorKind !== "record")
      ) {
        throw resolutionError("PN200", "invalid actor declaration contribution", span);
      }
      const existingActor = actors.get(actorName);
      if (existingActor !== undefined) {
        if (existingActor.value !== actorKind) {
          throw resolutionError(
            "PN202",
            `conflicting actor declarations for ${pythonRepr(actorName)}`,
            span,
            "declare each actor once, as a person or as a system",
            [["first declaration was here", existingActor.span]],
          );
        }
        continue;
      }
      actors.set(actorName, {value: actorKind, span});
      continue;
    }

    throw resolutionError("PN200", `unsupported contribution kind ${pythonRepr(kind)}`, span);
  }

  const places = [...placeAppearances];
  for (const place of placeAppearances) {
    const declaration = declaredAccepts.get(place);
    if (declaration !== undefined) accepts.set(place, [...declaration.value]);
  }

  for (const declaration of arcDeclarations) {
    const {id, place, transition, isInput, mode, span, color} = declaration;
    const resolvedColor = color.value;
    let accepted = accepts.get(place);
    if (accepted === undefined) {
      accepted = [];
      accepts.set(place, accepted);
    }
    const declared = declaredAccepts.get(place);
    if (declared !== undefined && !declared.value.includes(resolvedColor)) {
      throw resolutionError(
        "PN202",
        `arc color ${pythonRepr(resolvedColor)} conflicts with accepted colors declared for (${place})`,
        span,
        "add the arc color to the place declaration or change the arc color",
        [["accepted colors were declared here", declared.span]],
      );
    }
    if (!accepted.includes(resolvedColor)) accepted.push(resolvedColor);
    const arc: ResolvedArc = {
      from: isInput ? {place} : {transition},
      to: isInput ? {transition} : {place},
    };
    if (isInput) {
      const consume: AnyObject = {type: resolvedColor};
      if (mode !== "consume") consume.mode = mode;
      arc.consume = consume;
    } else {
      arc.produce = {destination: place, type: resolvedColor};
    }
    const key = identityKey(id);
    if (arcIndexes.has(key)) throw resolutionError("PN200", "duplicate arc identity", span);
    arcIndexes.set(key, arcs.length);
    arcs.push(arc);
    arcObjects.set(key, arc);
  }

  for (const place of declaredPlaces) {
    if (!accepts.has(place)) accepts.set(place, ["token"]);
  }

  for (const [handle, resolvedIds] of arcHandles) {
    const handleId = arcHandleIds.get(handle) as Identity;
    let declarationCount = 0;
    for (const key of arcIndexes.keys()) {
      const id = JSON.parse(key) as Identity;
      if (id[0] === handleId[0] && id[1] === handleId[1]) declarationCount += 1;
    }
    const expectedIds: Identity[] = [];
    for (let part = 1; part <= declarationCount; part += 1) {
      expectedIds.push([handleId[0], handleId[1], part]);
    }
    if (!jsonValuesEqual(resolvedIds, expectedIds)) {
      throw resolutionError("PN200", "invalid arc handle contribution", arcHandleSpans.get(handle));
    }
    if (resolvedIds.some((id) => !arcIndexes.has(identityKey(id)))) {
      throw resolutionError(
        "PN202",
        `handle @${handle} refers to an unknown arc`,
        arcHandleSpans.get(handle),
      );
    }
  }

  for (const [place, fact] of capacities) {
    if (!accepts.has(place)) {
      throw resolutionError("PN202", `capacity refers to unknown place (${place})`, fact.span);
    }
  }

  for (const [place, fact] of ports) {
    const accepted = accepts.get(place);
    if (accepted === undefined) {
      throw resolutionError("PN202", `port refers to unknown place (${place})`, fact.span);
    }
    if (!accepted.includes(fact.value.type)) {
      throw resolutionError(
        "PN202",
        `port color ${pythonRepr(fact.value.type)} is not accepted by place (${place})`,
        fact.span,
        "declare a port color already accepted by the place",
      );
    }
  }

  for (const [handle, fact] of arcWeights) {
    const ids = arcHandles.get(handle);
    if (ids === undefined) {
      throw resolutionError("PN202", `weight refers to unknown arc handle @${handle}`, fact.span);
    }
    const inputIndexes = ids
      .map((id) => arcIndexes.get(identityKey(id)) as number)
      .filter((index) => Object.hasOwn(arcs[index] as AnyObject, "consume"));
    if (inputIndexes.length === 0) {
      throw resolutionError("PN202", `arc weight is not allowed on produce arc @${handle}`, fact.span);
    }
    if (inputIndexes.length !== 1) {
      throw resolutionError(
        "PN202",
        `arc handle @${handle} must identify exactly one input arc for weight`,
        fact.span,
      );
    }
    const consume = (arcs[inputIndexes[0] as number] as AnyObject).consume as AnyObject;
    if (consume.mode === "inhibit" && fact.value > 1) {
      throw resolutionError(
        "PN202",
        `arc weight greater than 1 is not allowed on inhibit arc @${handle}`,
        fact.span,
      );
    }
    if (fact.value > 1) consume.weight = fact.value;
  }

  for (const [handle, fact] of arcData) {
    const ids = arcHandles.get(handle);
    if (ids === undefined) {
      throw resolutionError("PN202", `data refers to unknown arc handle @${handle}`, fact.span);
    }
    const produceIndexes = ids
      .map((id) => arcIndexes.get(identityKey(id)) as number)
      .filter((index) => Object.hasOwn(arcs[index] as AnyObject, "produce"));
    if (produceIndexes.length !== 1) {
      throw resolutionError(
        "PN202",
        `arc handle @${handle} must identify exactly one produce arc`,
        fact.span,
      );
    }
    (arcs[produceIndexes[0] as number] as AnyObject).produce.data = fact.value;
  }

  for (const [handle, fact] of arcCels) {
    const literal = arcData.get(handle);
    if (literal !== undefined) {
      throw resolutionError(
        "PN202",
        `arc @${handle} declares both data and data cel; they are mutually exclusive`,
        fact.span,
        undefined,
        [["literal data was declared here", literal.span]],
      );
    }
    const ids = arcHandles.get(handle);
    if (ids === undefined) {
      throw resolutionError("PN202", `data cel refers to unknown arc handle @${handle}`, fact.span);
    }
    const produceIndexes = ids
      .map((id) => arcIndexes.get(identityKey(id)) as number)
      .filter((index) => Object.hasOwn(arcs[index] as AnyObject, "produce"));
    if (produceIndexes.length !== 1) {
      throw resolutionError(
        "PN202",
        `arc handle @${handle} must identify exactly one produce arc`,
        fact.span,
      );
    }
    if (!isValidCel(fact.value)) {
      throw resolutionError(
        "PN203",
        `invalid CEL data expression for arc @${handle}`,
        fact.span,
        "fix the CEL expression syntax",
      );
    }
    (arcs[produceIndexes[0] as number] as AnyObject).produce.cel = fact.value;
  }

  for (const [handle, fact] of arcPredicates) {
    const ids = arcHandles.get(handle);
    if (ids === undefined) {
      throw resolutionError("PN202", `predicate refers to unknown arc handle @${handle}`, fact.span);
    }
    const consumeIndexes = ids
      .map((id) => arcIndexes.get(identityKey(id)) as number)
      .filter((index) => Object.hasOwn(arcs[index] as AnyObject, "consume"));
    if (consumeIndexes.length !== 1) {
      throw resolutionError(
        "PN202",
        `arc handle @${handle} must identify exactly one consume arc`,
        fact.span,
      );
    }
    if (typeof fact.value.cel === "string" && !isValidCel(fact.value.cel)) {
      throw resolutionError(
        "PN203",
        `invalid CEL predicate for arc @${handle}`,
        fact.span,
        "fix the CEL expression syntax",
      );
    }
    (arcs[consumeIndexes[0] as number] as AnyObject).consume.predicate = fact.value;
  }

  for (const [handle, fact] of arcCorrelates) {
    const ids = arcHandles.get(handle);
    if (ids === undefined) {
      throw resolutionError("PN202", `correlate refers to unknown arc handle @${handle}`, fact.span);
    }
    const inputIndexes = ids
      .map((id) => arcIndexes.get(identityKey(id)) as number)
      .filter((index) => (arcs[index] as AnyObject).consume !== undefined);
    if (inputIndexes.length !== 1) {
      const target = inputIndexes.length === 0 ? "no input arc" : "several input arcs";
      throw resolutionError(
        "PN202",
        `correlate must target exactly one input arc (->, ->?, ->0); @${handle} names ${target}`,
        fact.span,
        "move correlate to a named input arc",
        [[`arc @${handle} was declared here`, arcHandleSpans.get(handle) as IrSpan]],
      );
    }
    if (!isValidCel(fact.value)) {
      throw resolutionError(
        "PN203",
        `invalid CEL correlate for arc @${handle}`,
        fact.span,
        "fix the CEL expression syntax",
      );
    }
    (arcs[inputIndexes[0] as number] as AnyObject).consume.correlate = {cel: fact.value};
  }

  for (const [transition, fact] of guards) {
    if (!transitions.includes(transition)) {
      throw resolutionError("PN202", `guard refers to unknown transition [${transition}]`, fact.span);
    }
  }
  for (const [transition, fact] of timers) {
    if (!transitions.includes(transition)) {
      throw resolutionError("PN202", `timer refers to unknown transition [${transition}]`, fact.span);
    }
  }
  for (const [transition, fact] of timerMaturities) {
    if (!transitions.includes(transition)) {
      throw resolutionError(
        "PN202",
        `timer maturity refers to unknown transition [${transition}]`,
        fact.span,
      );
    }
    if (!timers.has(transition)) {
      throw resolutionError(
        "PN201",
        `transition [${transition}] has timer maturity but no timer fact`,
        fact.span,
        `add \`[${transition}] timer clock (...) cel "..."\``,
      );
    }
  }
  for (const [transition, binds] of timerBinds) {
    const firstSpan = binds.values().next().value?.span as IrSpan;
    if (!transitions.includes(transition)) {
      throw resolutionError("PN202", `timer bind refers to unknown transition [${transition}]`, firstSpan);
    }
    if (!timers.has(transition)) {
      throw resolutionError(
        "PN201",
        `transition [${transition}] has timer binds but no timer fact`,
        firstSpan,
        `add \`[${transition}] timer clock (...) cel "..."\``,
      );
    }
  }
  for (const [transition, keys] of bindingNames) {
    if (!transitions.includes(transition)) {
      throw resolutionError(
        "PN202",
        `binding name refers to unknown transition [${transition}]`,
        keys.values().next().value?.span as IrSpan,
      );
    }
  }
  for (const [transition, fact] of priorities) {
    if (!transitions.includes(transition)) {
      throw resolutionError("PN202", `priority refers to unknown transition [${transition}]`, fact.span);
    }
  }
  for (const [transition, fact] of handlers) {
    if (!transitions.includes(transition)) {
      throw resolutionError(
        "PN202",
        `handler refers to unknown transition [${transition}]`,
        fact.span,
      );
    }
  }

  const validateMetadataTarget = (
    targetType: string,
    targetName: string,
    span: IrSpan,
    noun: "description" | "annotation",
  ): void => {
    if (targetType === "place" && !accepts.has(targetName)) {
      throw resolutionError(
        "PN202",
        `${noun} references unknown place ${pythonRepr(targetName)}; metadata facts cannot declare semantic objects`,
        span,
        `declare the place in topology before ${noun === "description" ? "describing" : "annotating"} it`,
      );
    }
    if (targetType === "transition" && !transitions.includes(targetName)) {
      throw resolutionError(
        "PN202",
        `${noun} references unknown transition ${pythonRepr(targetName)}; metadata facts cannot declare semantic objects`,
        span,
        `declare the transition in topology before ${noun === "description" ? "describing" : "annotating"} it`,
      );
    }
    if (targetType === "arcHandle" && !arcHandles.has(targetName)) {
      throw resolutionError(
        "PN202",
        `${noun} references unknown arc handle @${targetName}`,
        span,
        `declare and name the arc before ${noun === "description" ? "describing" : "annotating"} it`,
      );
    }
  };
  for (const [key, fact] of descriptions) {
    const [type, name] = JSON.parse(key) as [string, string];
    validateMetadataTarget(type, name, fact.span, "description");
  }
  for (const [key, facts] of annotations) {
    const [type, name] = JSON.parse(key) as [string, string];
    const fact = facts.values().next().value as Fact<JsonValue>;
    validateMetadataTarget(type, name, fact.span, "annotation");
  }

  const incident = new Set<string>();
  for (const arc of arcs) {
    const pair = arcPlaceTransition(arc);
    if (pair !== undefined) incident.add(`${pair[0]}\0${pair[1]}`);
  }
  const quotedName = (name: string): string =>
    TIMER_BIND_IDENTIFIER.test(name) ? name : JSON.stringify(name);
  const copySpan = (
    span: IrSpan,
    viewName: string,
    place: string,
    transition: string,
    subject: boolean,
  ): IrSpan => {
    if (!subject) return span;
    return relativeSpan(
      span,
      `view ${quotedName(viewName)} position `,
      `(${quotedName(place)})@[${quotedName(transition)}]`,
    );
  };
  const requireCopy = (
    place: string,
    transition: string,
    span: IrSpan,
    viewName: string,
    subject: boolean,
  ): void => {
    const errorSpan = copySpan(span, viewName, place, transition, subject);
    if (!accepts.has(place) || !transitions.includes(transition)) {
      throw resolutionError(
        "PN202",
        `view ${pythonRepr(viewName)} references unknown copy (${place})@[${transition}]; presentation facts cannot declare semantic objects`,
        errorSpan,
        "declare the place and the transition in topology before positioning the copy",
      );
    }
    const fusion = annotations.get(metadataKey("place", place))?.get("fusion");
    if (fusion?.value !== true) {
      throw resolutionError(
        "PN202",
        `copy target (${place})@[${transition}] needs a fusion place; (${place}) is drawn once, so it has no copies`,
        errorSpan,
        `annotate it with \`(${place}) annotation fusion true\`, or position the place`,
      );
    }
    if (!incident.has(`${place}\0${transition}`)) {
      throw resolutionError(
        "PN202",
        `transition [${transition}] has no arc to place (${place}), so (${place})@[${transition}] is not a copy`,
        errorSpan,
        `draw an arc between [${transition}] and (${place}), or remove the copy target`,
      );
    }
  };

  for (const [key, viewPositions] of positions) {
    const [viewName, subjectType] = JSON.parse(key) as [string, string];
    for (const fact of viewPositions.values()) {
      const subject = fact.subject;
      if (subject.kind === "placeCopy") {
        requireCopy(subject.name, subject.copyTransition, fact.span, viewName, true);
        continue;
      }
      const known = subjectType === "place" ? accepts.has(subject.name) : transitions.includes(subject.name);
      if (!known) {
        const renderedViewName = quotedName(viewName);
        const renderedSubjectName = quotedName(subject.name);
        throw resolutionError(
          "PN202",
          `view ${pythonRepr(viewName)} references unknown ${subjectType} ${pythonRepr(subject.name)}; presentation facts cannot declare semantic objects`,
          relativeSpan(
            fact.span,
            `view ${renderedViewName} position `,
            `${subjectType === "place" ? "(" : "["}${renderedSubjectName}${subjectType === "place" ? ")" : "]"}`,
          ),
          `declare the ${subjectType} in topology before positioning it`,
        );
      }
    }
  }
  for (const base of relativeBases) {
    if (base.base.kind === "placeCopy") {
      requireCopy(base.base.name, base.base.copyTransition, base.span, base.viewName, false);
      continue;
    }
    const baseKnown = base.base.kind === "place"
      ? accepts.has(base.base.name)
      : transitions.includes(base.base.name);
    if (!baseKnown) {
      const renderedBaseName = quotedName(base.base.name);
      throw resolutionError(
        "PN202",
        `view ${pythonRepr(base.viewName)} relative base references unknown ${base.base.kind} ${pythonRepr(renderedBaseName)}; presentation facts cannot declare semantic objects`,
        base.span,
        `declare the ${base.base.kind} in topology before using it as a relative base`,
      );
    }
  }
  for (const base of relativeBases) {
    if (base.base.kind !== "place") continue;
    const placePositions = positions.get(viewSubjectKey(base.viewName, "place"));
    if (placePositions === undefined || !placePositions.has(`place:${base.base.name}`)) {
      throw resolutionError(
        "PN202",
        `view ${pythonRepr(base.viewName)} relative base (${base.base.name}) is the place entry's point, but view ${pythonRepr(base.viewName)} has no position for (${base.base.name})`,
        base.span,
        `position (${base.base.name}) in this view before offsetting from it`,
      );
    }
  }
  for (const [key, fact] of routes) {
    const [viewName, handle] = JSON.parse(key) as [string, string];
    if (!arcHandles.has(handle)) {
      throw resolutionError(
        "PN202",
        `view ${pythonRepr(viewName)} route references unknown arc handle @${handle}`,
        fact.span,
        "declare and name the routed arc before routing it",
      );
    }
  }

  const knownColors = new Set([...accepts.values()].flat());
  for (const [subject, facts] of decorations) {
    const separator = subject.indexOf(":");
    const subjectKind = subject.slice(0, separator);
    const subjectName = subject.slice(separator + 1);
    const known = subjectKind === "place"
      ? accepts.has(subjectName)
      : subjectKind === "transition"
        ? transitions.includes(subjectName)
        : subjectKind === "arc"
          ? arcHandles.has(subjectName)
          : knownColors.has(subjectName);
    if (!known) {
      const noun = subjectKind === "arc" ? "arc handle" : subjectKind;
      throw resolutionError(
        "PN202",
        `decoration references unknown ${noun} ${pythonRepr(subjectName)}; presentation facts cannot declare semantic objects`,
        (facts.values().next().value as Fact<JsonValue>).span,
        `declare the ${noun} before decorating it`,
      );
    }
    const besideFact = facts.get("beside");
    const fusion = annotations.get(metadataKey("place", subjectName))?.get("fusion");
    if (besideFact !== undefined && fusion?.value !== true) {
      throw resolutionError(
        "PN202",
        `beside decoration needs a fusion place; (${subjectName}) is drawn once, so it has no local copies to place`,
        besideFact.span,
        `annotate it with \`(${subjectName}) annotation fusion true\`, or remove the beside decoration`,
      );
    }
  }
  const fusionPlaces = new Set<string>();
  for (const [key, facts] of annotations) {
    const [type, name] = JSON.parse(key) as [string, string];
    if (type === "place" && facts.get("fusion")?.value === true) fusionPlaces.add(name);
  }
  const besideOpen = new Set<string>();
  for (const [subject, facts] of decorations) {
    if (!subject.startsWith("place:")) continue;
    const beside = facts.get("beside");
    if (
      beside !== undefined &&
      isObject(beside.value) &&
      !Object.hasOwn(beside.value, "side")
    ) {
      besideOpen.add(subject.slice("place:".length));
    }
  }
  const sharedOwners = sharedCopyOwners(arcs, fusionPlaces, besideOpen);
  const sharedGroups = new Map<string, {position: AnyObject; span: IrSpan; transition: string}[]>();
  for (const [key, viewPositions] of positions) {
    const [viewName, subjectType] = JSON.parse(key) as [string, string];
    if (subjectType !== "placeCopy") continue;
    for (const fact of viewPositions.values()) {
      const place = fact.subject.name;
      const transition = fact.subject.copyTransition;
      const owners = sharedOwners.get(sharedCopyKey(place, transition));
      if (owners === undefined) continue;
      const groupKey = JSON.stringify([viewName, place, [...owners].sort()]);
      const group = sharedGroups.get(groupKey) ?? [];
      group.push({position: fact.value, span: fact.span, transition});
      sharedGroups.set(groupKey, group);
    }
  }
  for (const [groupKey, entries] of sharedGroups) {
    if (entries.length < 2) continue;
    const [viewName, place] = JSON.parse(groupKey) as [string, string, string[]];
    entries.sort((left, right) => left.span.start.byteOffset - right.span.start.byteOffset);
    const first = entries[0]!;
    for (const entry of entries.slice(1)) {
      if (jsonValuesEqual(entry.position, first.position)) continue;
      throw resolutionError(
        "PN202",
        `conflicting position facts for shared copy (${place})@[${first.transition}] and (${place})@[${entry.transition}] in view ${pythonRepr(viewName)}`,
        entry.span,
        "remove one declaration or make both positions identical",
        [["first position was declared here", first.span]],
      );
    }
  }
  for (const [key, fact] of domains) {
    const color = key.slice(0, key.indexOf("."));
    if (!knownColors.has(color)) {
      throw resolutionError(
        "PN202",
        `domain refers to unknown color ${pythonRepr(color)}; no place accepts it`,
        fact.span,
        "name a color that a place accepts",
      );
    }
  }
  for (const {value: marking, span: factSpan} of finalMarkings.values()) {
    for (const place of marking) {
      if (!accepts.has(place)) {
        throw resolutionError("PN202", `final refers to unknown place (${place})`, factSpan);
      }
    }
  }
  for (const fact of invariants) {
    for (const place of Object.keys(fact.value.weights as AnyObject)) {
      if (!accepts.has(place)) {
        throw resolutionError("PN202", `invariant refers to unknown place (${place})`, fact.span);
      }
    }
  }

  if (header === undefined) header = {name: "unnamed"};
  if (transitionOrders.size > 0) {
    if (
      transitionOrders.size !== transitions.length ||
      transitions.some((name) => !transitionOrders.has(name)) ||
      new Set(transitionOrders.values()).size !== transitions.length ||
      [...transitionOrders.values()].some((rank) => rank < 1 || rank > transitions.length)
    ) {
      throw resolutionError("PN202", "transition order must rank every transition exactly once");
    }
    transitions.sort((left, right) => (transitionOrders.get(left) as number) - (transitionOrders.get(right) as number));
  }
  if (handleOrders.size > 0) {
    if (
      handleOrders.size !== arcHandles.size ||
      [...arcHandles.keys()].some((name) => !handleOrders.has(name)) ||
      new Set(handleOrders.values()).size !== arcHandles.size ||
      [...handleOrders.values()].some((rank) => rank < 1 || rank > arcHandles.size)
    ) {
      throw resolutionError("PN202", "arc-run order must rank every handle exactly once");
    }
    const covered = new Set([...arcHandles.values()].flat().map(identityKey));
    if ([...arcIndexes.keys()].some((id) => !covered.has(id)) || covered.size !== arcIndexes.size) {
      throw resolutionError("PN202", "arc-run order cannot omit arcs from an unhandled chain");
    }
    const orderedArcs: ResolvedArc[] = [];
    const orderedHandles = [...handleOrders.keys()].sort(
      (left, right) => (handleOrders.get(left) as number) - (handleOrders.get(right) as number),
    );
    for (const handle of orderedHandles) {
      for (const id of arcHandles.get(handle) as Identity[]) {
        const index = arcIndexes.get(identityKey(id));
        if (index === undefined) {
          throw resolutionError("PN202", `handle @${handle} refers to an unknown arc`);
        }
        orderedArcs.push(arcs[index] as ResolvedArc);
      }
    }
    arcs = orderedArcs;
  }

  let materializedTokenCount = 0;
  const reserveMaterializedTokens = (count: number): void => {
    const actual = materializedTokenCount + count;
    if (actual > PETRINET_RESOURCE_LIMITS.materializedTokens) {
      throw new PetrinetResourceError(
        "materializedTokens",
        PETRINET_RESOURCE_LIMITS.materializedTokens,
        actual,
      );
    }
    materializedTokenCount = actual;
  };

  const initialMarking: AnyObject = {};
  for (const fact of markings) {
    const accepted = accepts.get(fact.place);
    if (accepted === undefined) {
      throw resolutionError("PN202", `marking refers to unknown place (${fact.place})`, fact.span);
    }
    reserveMaterializedTokens(fact.count);
    let existing = Object.hasOwn(initialMarking, fact.place)
      ? initialMarking[fact.place] as AnyObject[]
      : undefined;
    if (existing === undefined) {
      existing = [];
      setOwn(initialMarking, fact.place, existing);
    }
    existing.push(...materializeMarkingToken({
      place: fact.place,
      token: fact.token,
      count: fact.count,
      acceptedColors: accepted,
      templates,
      span: fact.span,
    }));
  }

  const resolvedNamedMarkings: AnyObject = {};
  for (const [markingName, entries] of namedMarkings) {
    const resolvedMarking: AnyObject = {};
    for (const fact of entries) {
      const accepted = accepts.get(fact.place);
      if (accepted === undefined) {
        throw resolutionError(
          "PN202",
          `named marking ${pythonRepr(markingName)} references unknown place ${pythonRepr(fact.place)}; marking facts cannot declare semantic objects`,
          fact.span,
          "declare the place in topology before marking it",
        );
      }
      reserveMaterializedTokens(fact.count);
      let existing = Object.hasOwn(resolvedMarking, fact.place)
        ? resolvedMarking[fact.place] as AnyObject[]
        : undefined;
      if (existing === undefined) {
        existing = [];
        setOwn(resolvedMarking, fact.place, existing);
      }
      existing.push(...materializeMarkingToken({
        place: fact.place,
        token: fact.token,
        count: fact.count,
        acceptedColors: accepted,
        templates,
        span: fact.span,
        markingName,
      }));
    }
    setOwn(resolvedNamedMarkings, markingName, resolvedMarking);
  }

  const resolvedPlaces: AnyObject[] = [];
  for (const place of places) {
    const resolvedPlace: AnyObject = {name: place, accepts: accepts.get(place)};
    const capacity = capacities.get(place);
    if (capacity !== undefined) resolvedPlace.capacityPerColorKey = capacity.value;
    const port = ports.get(place);
    if (port !== undefined) resolvedPlace.port = port.value;
    const description = descriptions.get(metadataKey("place", place));
    if (description !== undefined) resolvedPlace.description = description.value;
    const annotationFacts = annotations.get(metadataKey("place", place));
    if (annotationFacts !== undefined && annotationFacts.size > 0) {
      resolvedPlace.annotations = Object.fromEntries(
        [...annotationFacts].map(([key, fact]) => [key, fact.value]),
      );
    }
    resolvedPlaces.push(resolvedPlace);
  }

  const resolvedTransitions: AnyObject[] = [];
  for (const transition of transitions) {
    const resolvedTransition: AnyObject = {name: transition};
    const handler = handlers.get(transition);
    if (handler !== undefined) resolvedTransition.handler = handler.value;
    const guard = guards.get(transition);
    if (guard !== undefined) resolvedTransition.guard = guard.value;
    const timerFact = timers.get(transition);
    if (timerFact !== undefined) {
      const timer: AnyObject = {clock: timerFact.clock, cel: timerFact.cel};
      const binds = timerBinds.get(transition);
      if (binds !== undefined && binds.size > 0) {
        timer.bind = Object.fromEntries(
          [...binds.keys()].sort().map((name) => [name, (binds.get(name) as Fact<string>).value]),
        );
      }
      const maturity = timerMaturities.get(transition);
      if (maturity !== undefined) timer.maturity = maturity.value;
      resolvedTransition.timer = timer;
    }
    const keys = bindingNames.get(transition);
    if (keys !== undefined) {
      resolvedTransition.bindingNames = Object.fromEntries(
        [...keys.keys()].sort().map((key) => [key, (keys.get(key) as Fact<string>).value]),
      );
    }
    const priority = priorities.get(transition);
    if (priority !== undefined && priority.value !== 0) resolvedTransition.priority = priority.value;
    const description = descriptions.get(metadataKey("transition", transition));
    if (description !== undefined) resolvedTransition.description = description.value;
    const annotationFacts = annotations.get(metadataKey("transition", transition));
    if (annotationFacts !== undefined && annotationFacts.size > 0) {
      resolvedTransition.annotations = Object.fromEntries(
        [...annotationFacts].map(([key, fact]) => [key, fact.value]),
      );
    }
    resolvedTransitions.push(resolvedTransition);
  }

  const currentArcIndexes = new Map<ResolvedArc, number>();
  arcs.forEach((arc, index) => currentArcIndexes.set(arc, index));
  for (const [handle, ids] of arcHandles) {
    const description = descriptions.get(metadataKey("arcHandle", handle));
    const annotationFacts = annotations.get(metadataKey("arcHandle", handle));
    if (description === undefined && (annotationFacts === undefined || annotationFacts.size === 0)) continue;
    for (const id of ids) {
      const arc = arcObjects.get(identityKey(id)) as ResolvedArc;
      const position = currentArcIndexes.get(arc) as number;
      if (description !== undefined) arcs[position]!.description = description.value;
      if (annotationFacts !== undefined && annotationFacts.size > 0) {
        arcs[position]!.annotations = Object.fromEntries(
          [...annotationFacts].map(([key, fact]) => [key, fact.value]),
        );
      }
    }
  }

  const result: AnyObject = {
    name: header.name,
    places: resolvedPlaces,
    transitions: resolvedTransitions,
    arcs,
  };
  if (
    markings.length > 0 ||
    (namedMarkings.size === 0 && positions.size === 0 && routes.size === 0 && viewStyles.size === 0 && decorations.size === 0 && extensions === undefined)
  ) {
    result.initialMarking = initialMarking;
  }

  const headerDescription = header.description;
  const metadataDescription = descriptions.get(metadataKey("document", ""));
  if (metadataDescription !== undefined) {
    if (headerDescription !== undefined && headerDescription !== metadataDescription.value) {
      throw resolutionError(
        "PN202",
        "conflicting description facts for net",
        metadataDescription.span,
      );
    }
    result.description = metadataDescription.value;
  } else if (headerDescription !== undefined) {
    result.description = headerDescription;
  }

  const documentAnnotations = annotations.get(metadataKey("document", ""));
  if (documentAnnotations !== undefined && documentAnnotations.size > 0) {
    result.annotations = Object.fromEntries(
      [...documentAnnotations].map(([key, fact]) => [key, fact.value]),
    );
  }
  if (actors.size > 0) {
    const actorsFact = documentAnnotations?.get("actors");
    if (actorsFact !== undefined) {
      throw resolutionError(
        "PN202",
        "conflicting annotation actors facts for net",
        actorsFact.span,
        "declare actors with `person` and `system` lines only",
        [["first actor was declared here", [...actors.values()][0]!.span]],
      );
    }
    result.annotations = {
      ...(result.annotations as AnyObject | undefined),
      actors: [...actors].map(([name, fact]) => ({name, kind: fact.value})),
    };
  }
  if (domains.size > 0) {
    result.domains = Object.fromEntries([...domains].map(([key, fact]) => [key, fact.value]));
  }
  if (finalMarkings.size > 0 || invariants.length > 0) {
    result.proofs = {
      ...(finalMarkings.size > 0
        ? {
            final: [...finalMarkings.values()].map(({value: marking}) =>
              marking.length === 1 ? marking[0]! : marking,
            ),
          }
        : {}),
      ...(invariants.length > 0 ? {invariants: invariants.map((fact) => fact.value)} : {}),
    };
  }

  const metadataHandles = new Set<string>();
  for (const key of [...descriptions.keys(), ...annotations.keys()]) {
    const [type, name] = JSON.parse(key) as [string, string];
    if (type === "arcHandle") metadataHandles.add(name);
  }
  for (const key of routes.keys()) {
    const [, handle] = JSON.parse(key) as [string, string];
    metadataHandles.add(handle);
  }
  for (const subject of decorations.keys()) {
    if (subject.startsWith("arc:")) metadataHandles.add(subject.slice("arc:".length));
  }

  const views: AnyObject = {};
  for (const [key, viewPositions] of positions) {
    const [viewName] = JSON.parse(key) as [string, string];
    let view = Object.hasOwn(views, viewName) ? views[viewName] as AnyObject : undefined;
    if (view === undefined) {
      view = {positions: {}, routes: {}};
      setOwn(views, viewName, view);
    }
    for (const [subject, fact] of viewPositions) {
      setOwn(view.positions, subject, fact.value);
    }
  }
  for (const [key, fact] of routes) {
    const [viewName, handle] = JSON.parse(key) as [string, string];
    let view = Object.hasOwn(views, viewName) ? views[viewName] as AnyObject : undefined;
    if (view === undefined) {
      view = {positions: {}, routes: {}};
      setOwn(views, viewName, view);
    }
    setOwn(view.routes, handle, {style: "orthogonal", points: fact.value});
  }
  for (const [key, fact] of viewStyles) {
    const [viewName, member] = JSON.parse(key) as [string, string];
    let view = Object.hasOwn(views, viewName) ? views[viewName] as AnyObject : undefined;
    if (view === undefined) {
      view = {positions: {}, routes: {}};
      setOwn(views, viewName, view);
    }
    setOwn(view, member, fact.value);
  }

  if (
    Object.keys(resolvedNamedMarkings).length > 0 ||
    Object.keys(views).length > 0 ||
    decorations.size > 0 ||
    extensions !== undefined ||
    metadataHandles.size > 0
  ) {
    const payloadHandles: AnyObject = {};
    for (const handle of [...metadataHandles].sort()) {
      const ids = arcHandles.get(handle) as Identity[];
      if (ids.length !== 1) {
        throw resolutionError(
          "PN202",
          `metadata arc handle '@${handle}' must identify exactly one arc`,
          arcHandleSpans.get(handle),
        );
      }
      const arcObject = arcObjects.get(identityKey(ids[0] as Identity)) as ResolvedArc;
      const currentIndex = currentArcIndexes.get(arcObject) as number;
      const resolvedArc = arcs[currentIndex] as AnyObject;
      const fingerprint = resolvedArc.consume !== undefined
        ? {
            from: cloneJson(resolvedArc.from),
            to: cloneJson(resolvedArc.to),
            type: resolvedArc.consume.type,
            mode: resolvedArc.consume.mode ?? "consume",
          }
        : {
            from: cloneJson(resolvedArc.from),
            to: cloneJson(resolvedArc.to),
            type: resolvedArc.produce.type,
            mode: "produce",
          };
      setOwn(payloadHandles, handle, {index: currentIndex, fingerprint});
    }
    const payload: AnyObject = {
      arcHandles: payloadHandles,
      markings: resolvedNamedMarkings,
      views,
      extensions: extensions?.value ?? {},
    };
    if (decorations.size > 0) {
      const payloadDecorations: AnyObject = {};
      for (const [subject, facts] of decorations) {
        const entry: AnyObject = {};
        for (const [member, fact] of facts) setOwn(entry, member, fact.value);
        setOwn(payloadDecorations, subject, entry);
      }
      payload.decorations = payloadDecorations;
    }
    (result.annotations ??= {})["petrinet.dsl/v1"] = payload;
  }

  for (const [transition, timer] of timers) {
    if (!accepts.has(timer.clock)) {
      throw resolutionError(
        "PN201",
        `timer clock place (${timer.clock}) for transition [${transition}] is not declared`,
        timer.span,
        "declare the clock place in topology before using it in a timer",
      );
    }
    const binds = timerBinds.get(transition);
    if (binds !== undefined) {
      const bindingSources = new Set<string>();
      for (const arc of arcs) {
        if (
          arc.to?.transition === transition &&
          arc.consume !== undefined &&
          arc.consume.mode !== "inhibit"
        ) {
          bindingSources.add(arc.from.place);
        }
      }
      for (const [bindName, bind] of binds) {
        if (bindName === "clock") {
          throw resolutionError(
            "PN202",
            `timer bind name 'clock' is reserved on transition [${transition}]`,
            bind.span,
            "choose a bind name other than 'clock'",
          );
        }
        if (!bindingSources.has(bind.value)) {
          throw resolutionError(
            "PN202",
            `timer bind ${pythonRepr(bindName)} on transition [${transition}] names place (${bind.value}), but that place does not feed [${transition}] through a consume or read arc`,
            bind.span,
            "bind the variable to a consume or read input place",
          );
        }
      }
    }
    const maturity = timerMaturities.get(transition);
    if (
      !isValidCel(timer.cel) ||
      (maturity !== undefined && !isValidCel(maturity.value))
    ) {
      throw resolutionError(
        "PN203",
        `invalid CEL timer for transition [${transition}]`,
        timer.span,
        "fix the CEL expression syntax",
      );
    }
  }
  for (const [transition, keys] of bindingNames) {
    const bindingSources = new Set<string>();
    for (const arc of arcs) {
      if (
        arc.to?.transition === transition &&
        arc.consume !== undefined &&
        arc.consume.mode !== "inhibit"
      ) {
        bindingSources.add(arc.from.place);
      }
    }
    const named = new Set([...keys.values()].map((fact) => fact.value));
    if (
      named.size !== bindingSources.size ||
      [...named].some((place) => !bindingSources.has(place))
    ) {
      throw resolutionError(
        "PN202",
        `binding names on transition [${transition}] must name exactly the places it consumes or reads`,
        keys.values().next().value?.span as IrSpan,
        "give each consume or read input place one bind fact",
      );
    }
  }

  return result as ReadonlyJsonObject;
}
