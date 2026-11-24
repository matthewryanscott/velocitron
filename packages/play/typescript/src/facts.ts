/**
 * Project a parsed play to the cross-language agreement object.
 *
 * `packages/play/python` builds the same object from the Python AST. Keep the
 * keys and the omitted-empty rules aligned with `velocitron_play.facts`.
 */

import type {
  AdvanceBody,
  AssumeGuardBody,
  AssumePredicateBody,
  Condition,
  ExpectBody,
  FireBody,
  InjectBody,
  Json,
  OutputClause,
  Play,
  PlayPath,
  Step,
  StepBody,
  TokenExpr,
  UpdateBody,
  WithClause,
} from "./language.js";
import { PlayError, isNameRef, parsePlay } from "./language.js";

export interface PlayFailure {
  readonly ok: false;
  readonly code: string;
  readonly line: number;
  readonly column: number;
}

export interface TokenFact {
  readonly template?: string;
  readonly color?: string | null;
  readonly data?: Json;
}

export interface PlayFacts {
  readonly name: string;
  readonly title: string | null;
  readonly prose: string;
  readonly line: number;
  readonly column: number;
  readonly net: string | null;
  readonly marking: string;
  readonly scope: Play["scope"];
  readonly sequence: Play["sequence"];
  readonly instance: TokenFact | null;
  readonly uses: readonly { readonly ref: string; readonly alias: string }[];
  readonly wires: readonly {
    readonly from_alias: string;
    readonly from_place: string;
    readonly to_alias: string;
    readonly to_place: string;
  }[];
  readonly refines: readonly { readonly alias: string; readonly transition: string; readonly by: string }[];
  readonly shares: readonly (readonly { readonly alias: string; readonly place: string }[])[];
  readonly shows: readonly { readonly color: string; readonly fields: readonly string[] }[];
  readonly actors: readonly { readonly name: string; readonly kind: Play["actors"][number]["kind"] }[];
  readonly boxes: readonly { readonly title: string; readonly members: readonly string[] }[];
  readonly templates: readonly { readonly name: string; readonly color: string | null; readonly data: Json }[];
  readonly paths: readonly PathFact[];
}

export interface PathFact {
  readonly name: string;
  readonly title: string | null;
  readonly prose: string;
  readonly from: { readonly name: string; readonly line: number; readonly column: number } | null;
  readonly sequence: PlayPath["sequence"];
  readonly steps: readonly StepFact[];
}

export interface StepFact {
  readonly kind: Step["kind"];
  readonly label: string | null;
  readonly title: string | null;
  readonly prose: string;
  readonly statement: string;
  readonly line: number;
  readonly column: number;
  readonly body: Json;
}

function canon(value: Json): Json {
  if (typeof value === "number") return Number.isInteger(value) ? value : value;
  if (Array.isArray(value)) return value.map((item) => canon(item));
  if (value !== null && typeof value === "object") {
    const result: { [key: string]: Json } = {};
    for (const [key, item] of Object.entries(value)) result[key] = canon(item);
    return result;
  }
  return value;
}

function tokenFact(token: TokenExpr): TokenFact {
  if (isNameRef(token)) return { template: token.name };
  return { color: token.color, data: canon(token.data) };
}

function isInject(body: StepBody): body is InjectBody {
  return "tokens" in body && "place" in body && !("transition" in body) && !("conditions" in body);
}

function isUpdate(body: StepBody): body is UpdateBody {
  return "token" in body && !("tokens" in body);
}

function isAdvance(body: StepBody): body is AdvanceBody {
  return "seconds" in body;
}

function isFire(body: StepBody): body is FireBody {
  return "transition" in body && "withs" in body;
}

function isExpect(body: StepBody): body is ExpectBody {
  return "conditions" in body;
}

function isGuard(body: StepBody): body is AssumeGuardBody {
  return "transition" in body && "value" in body && !("withs" in body);
}

function isPredicate(body: StepBody): body is AssumePredicateBody {
  return "predicate" in body;
}

function conditionFact(condition: Condition): Json {
  const fact: { [key: string]: Json } = { kind: condition.kind, text: condition.text };
  if (condition.place != null) fact.place = condition.place.name;
  if (condition.tokens.length > 0) fact.tokens = condition.tokens.map((token) => tokenFact(token) as Json);
  if (condition.count != null) fact.count = condition.count;
  if (condition.transitions.length > 0) {
    fact.transitions = condition.transitions.map((item) => item.name);
  }
  return fact;
}

function withFact(clause: WithClause): Json {
  const fact: { [key: string]: Json } = { place: clause.place.name };
  if (clause.template != null) fact.template = clause.template.name;
  else if (clause.index != null) fact.index = clause.index;
  else if (clause.subset != null) fact.subset = canon(clause.subset);
  return fact;
}

function outputFact(clause: OutputClause): Json {
  const fact: { [key: string]: Json } = { place: clause.place.name };
  if (clause.nothing) fact.nothing = true;
  else if (clause.merge != null) fact.merge = canon(clause.merge);
  else fact.tokens = clause.tokens.map((token) => tokenFact(token) as Json);
  return fact;
}

function bodyFact(body: StepBody): Json {
  if (isInject(body)) {
    return { place: body.place.name, tokens: body.tokens.map((token) => tokenFact(token) as Json) };
  }
  if (isUpdate(body)) return { place: body.place.name, token: tokenFact(body.token) as Json };
  if (isAdvance(body)) {
    return {
      place: body.place == null ? null : body.place.name,
      seconds: canon(body.seconds),
      relative: body.relative,
    };
  }
  if (isFire(body)) {
    return {
      transition: body.transition.name,
      with: body.withs.map((clause) => withFact(clause)),
      output: body.outputs.map((clause) => outputFact(clause)),
    };
  }
  if (isExpect(body)) return { conditions: body.conditions.map((condition) => conditionFact(condition)) };
  if (isGuard(body)) return { assume: "guard", transition: body.transition.name, value: body.value };
  if (isPredicate(body)) return { assume: "predicate", predicate: body.predicate, value: body.value };
  throw new Error("unknown step body");
}

function stepFact(step: Step): StepFact {
  return {
    kind: step.kind,
    label: step.label,
    title: step.title,
    prose: step.prose,
    statement: step.statement,
    line: step.position.line,
    column: step.position.column,
    body: bodyFact(step.body),
  };
}

function pathFact(path: PlayPath): PathFact {
  return {
    name: path.name,
    title: path.title,
    prose: path.prose,
    from:
      path.fromLabel == null
        ? null
        : {
            name: path.fromLabel.name,
            line: path.fromLabel.position.line,
            column: path.fromLabel.position.column,
          },
    sequence: path.sequence,
    steps: path.steps.map((step) => stepFact(step)),
  };
}

export function playFacts(play: Play): PlayFacts {
  return {
    name: play.name,
    title: play.title,
    prose: play.prose,
    line: play.position.line,
    column: play.position.column,
    net: play.net,
    marking: play.marking,
    scope: play.scope,
    sequence: play.sequence,
    instance: play.instance == null ? null : tokenFact(play.instance),
    uses: play.uses.map((use) => ({ ref: use.ref, alias: use.alias })),
    wires: play.wires.map((wire) => ({
      from_alias: wire.fromAlias,
      from_place: wire.fromPlace,
      to_alias: wire.toAlias,
      to_place: wire.toPlace,
    })),
    refines: play.refines.map((refine) => ({
      alias: refine.alias,
      transition: refine.transition,
      by: refine.by,
    })),
    shares: play.shares.map((share) =>
      share.members.map(([alias, place]) => ({ alias, place })),
    ),
    shows: play.shows.map((show) => ({ color: show.color, fields: show.fields })),
    actors: play.actors.map((actor) => ({ name: actor.name, kind: actor.kind })),
    boxes: play.boxes.map((box) => ({ title: box.title, members: box.members })),
    templates: [...play.templates.entries()].map(([name, literal]) => ({
      name,
      color: literal.color,
      data: canon(literal.data),
    })),
    paths: play.paths.map((path) => pathFact(path)),
  };
}

export function projectSource(text: string, sourceName = "<memory>"): PlayFacts & { ok: true } | PlayFailure {
  try {
    return { ok: true, ...playFacts(parsePlay(text, sourceName)) };
  } catch (error) {
    if (error instanceof PlayError) {
      return { ok: false, code: error.code, line: error.line, column: error.column };
    }
    throw error;
  }
}
