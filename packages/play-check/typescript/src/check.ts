import {createDefaultCelAdapter} from "@velocitron/cel";
import {
  DepositViolationError,
  Engine,
  HandlerRegistry,
  PRIORITY_FIRING_POLICY,
  TokenInjectionError,
  domainViolation,
  type FiringRecord,
  type InjectionRecord,
  type Marking,
  type ConsumeArc,
  type Net,
  type ProduceTemplate,
  type ReadonlyJsonObject,
  type Token,
  type TokenBinding,
} from "@velocitron/engine";
import {
  isNameRef,
  type AdvanceBody,
  type AssumeGuardBody,
  type AssumePredicateBody,
  type Condition,
  type FireBody,
  type InjectBody,
  type Json,
  type JsonObject,
  type NameRef,
  type OutputClause,
  type Play,
  type PlayPath,
  type Position,
  type Step,
  type TokenExpr,
  type UpdateBody,
  type WithClause,
} from "@velocitron/play";

import {PlayCheckError} from "./errors.js";
import {loadPlayNet, type LoadPlayNetOptions} from "./load.js";
import type {
  CheckResult,
  OutputRule,
  OutputSource,
  PlayNet,
  PlayReport,
  PlayTrace,
  StepDiagnostic,
  StepFailure,
  StepResult,
} from "./model.js";

const ADVANCE_MAX_MATURING = 1000;

export interface CheckPlayOptions extends LoadPlayNetOptions {
  /** Path names to play. Omit to play every path. */
  readonly paths?: readonly string[];
}

interface ResolvedWith {
  readonly place: string;
  readonly describe: string;
  readonly subset?: ReadonlyJsonObject;
  readonly token?: Token;
  readonly index?: number;
}

interface ResolvedOutput {
  readonly tokens: readonly Token[];
  readonly merge?: ReadonlyJsonObject;
  readonly nothing: boolean;
}

interface ResolvedFire {
  readonly kind: "fire";
  readonly transition: string;
  readonly withs: readonly ResolvedWith[];
  readonly outputs: ReadonlyMap<number, ResolvedOutput>;
}

interface ResolvedInject {
  readonly kind: "inject";
  readonly place: string;
  readonly tokens: readonly Token[];
  readonly replace: boolean;
}

interface ResolvedAdvance {
  readonly kind: "advance";
  readonly place: string;
  readonly color: string;
  readonly seconds: number;
  readonly relative: boolean;
}

interface ResolvedCondition {
  readonly source: Condition;
  readonly place: string | null;
  readonly tokens: readonly Token[];
  readonly transitions: readonly string[];
}

interface ResolvedExpect {
  readonly kind: "expect";
  readonly conditions: readonly ResolvedCondition[];
}

interface ResolvedAssume {
  readonly kind: "assume";
  readonly transition: string | null;
  readonly guardRef: string | null;
  readonly predicateRef: string | null;
  readonly value: boolean;
}

type Resolved = ResolvedFire | ResolvedInject | ResolvedAdvance | ResolvedExpect | ResolvedAssume;

interface PlannedStep {
  readonly step: Step;
  readonly path: string;
  readonly resolved: Resolved;
}

class StepFailed extends Error {
  readonly failure: StepFailure;

  constructor(failure: StepFailure) {
    super(failure.diagnostic.message);
    this.name = "StepFailed";
    this.failure = failure;
  }
}

class Report implements PlayReport {
  readonly play: Play;
  readonly subject: PlayNet;
  readonly traces: readonly PlayTrace[];

  constructor(play: Play, subject: PlayNet, traces: readonly PlayTrace[]) {
    this.play = play;
    this.subject = subject;
    this.traces = traces;
  }

  get passed(): boolean {
    return this.traces.every((trace) => trace.passed);
  }

  trace(path: string): PlayTrace | null {
    return this.traces.find((item) => item.path.name === path) ?? null;
  }

  diagnostics(): readonly StepDiagnostic[] {
    const groups = new Map<string, PlayTrace[]>();
    for (const trace of this.traces) {
      if (trace.failure === null) continue;
      const key = `${trace.failure.path}:${trace.failure.diagnostic.line}:${trace.failure.diagnostic.column}`;
      const list = groups.get(key) ?? [];
      list.push(trace);
      groups.set(key, list);
    }
    const diagnostics: StepDiagnostic[] = [];
    for (const traces of groups.values()) {
      const failure = traces[0]?.failure;
      if (failure == null) continue;
      const blocked = traces
        .map((trace) => trace.path.name)
        .filter((name) => name !== failure.path);
      const details = [...failure.diagnostic.details];
      if (blocked.length > 0) details.push(`blocked paths: ${blocked.join(", ")}`);
      diagnostics.push({...failure.diagnostic, details});
    }
    return diagnostics;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function jsonData(value: JsonObject): ReadonlyJsonObject {
  return structuredClone(value) as ReadonlyJsonObject;
}

function deepEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => deepEqual(item, right[index]));
  }
  if (isRecord(left) && isRecord(right)) {
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every((key) => deepEqual(left[key], right[key]));
  }
  return false;
}

function contains(data: unknown, subset: unknown): boolean {
  if (isRecord(subset) && isRecord(data)) {
    return Object.entries(subset).every(([key, value]) => (
      Object.prototype.hasOwnProperty.call(data, key) && contains(data[key], value)
    ));
  }
  return deepEqual(data, subset);
}

function sameToken(left: Token, right: Token): boolean {
  return left.type === right.type && deepEqual(left.data, right.data);
}

function sameMultiset(left: readonly Token[], right: readonly Token[]): boolean {
  const remaining = [...right];
  for (const token of left) {
    const index = remaining.findIndex((candidate) => sameToken(candidate, token));
    if (index < 0) return false;
    remaining.splice(index, 1);
  }
  return remaining.length === 0;
}

function tokenText(token: Token): string {
  return `${token.type} ${JSON.stringify(token.data)}`;
}

function suggest(name: string, known: readonly string[]): string[] {
  return known
    .map((candidate) => ({candidate, score: levenshtein(name, candidate)}))
    .filter((item) => item.score <= Math.max(2, Math.floor(name.length / 3)))
    .sort((left, right) => left.score - right.score)
    .slice(0, 3)
    .map((item) => `did you mean ${item.candidate}?`);
}

function levenshtein(left: string, right: string): number {
  const row = Array.from({length: right.length + 1}, (_, index) => index);
  for (let i = 1; i <= left.length; i += 1) {
    let previous = row[0] ?? 0;
    row[0] = i;
    for (let j = 1; j <= right.length; j += 1) {
      const current = row[j] ?? 0;
      const cost = left[i - 1] === right[j - 1] ? 0 : 1;
      row[j] = Math.min((row[j] ?? 0) + 1, (row[j - 1] ?? 0) + 1, previous + cost);
      previous = current;
    }
  }
  return row[right.length] ?? 0;
}

function isConsumeArc(arc: Net["arcs"][number]): arc is ConsumeArc {
  return arc.consume !== undefined;
}

function produceTemplates(net: Net, transition: string): ProduceTemplate[] {
  const templates: ProduceTemplate[] = [];
  for (const arc of net.arcs) {
    if (arc.produce !== undefined && arc.from.transition === transition) templates.push(arc.produce);
  }
  return templates;
}

function netFills(template: ProduceTemplate): boolean {
  return template.data !== undefined || template.cel !== undefined;
}

function consumePlaces(net: Net, transition: string): Set<string> {
  const places = new Set<string>();
  for (const arc of net.arcs) {
    if (isConsumeArc(arc) && arc.consume.mode === "consume" && arc.to.transition === transition) {
      places.add(arc.from.place);
    }
  }
  return places;
}

function consumedOf(net: Net, transition: string, binding: TokenBinding): TokenBinding {
  const places = consumePlaces(net, transition);
  const consumed: Record<string, readonly Token[]> = Object.create(null) as Record<string, readonly Token[]>;
  for (const place of places) {
    const tokens = binding[place];
    if (tokens !== undefined && tokens.length > 0) consumed[place] = tokens;
  }
  return consumed;
}

function carryRule(
  templates: readonly ProduceTemplate[],
  consumed: TokenBinding,
): Record<string, Token[]> | null {
  const byColor = new Map<string, Token[]>();
  for (const tokens of Object.values(consumed)) {
    for (const token of tokens) {
      const list = byColor.get(token.type) ?? [];
      list.push(token);
      byColor.set(token.type, list);
    }
  }
  const carried: Record<string, Token[]> = Object.create(null) as Record<string, Token[]>;
  for (const template of templates) {
    if (netFills(template)) continue;
    const candidates = byColor.get(template.type) ?? [];
    const carriedToken = candidates.length === 1 ? candidates[0] : undefined;
    if (carriedToken === undefined) return null;
    (carried[template.destination] ??= []).push({
      type: template.type,
      data: structuredClone(carriedToken.data) as ReadonlyJsonObject,
    });
  }
  return carried;
}

function bindingPlaces(net: Net, transition: string): Set<string> {
  const places = new Set<string>();
  for (const arc of net.arcs) {
    if (
      isConsumeArc(arc)
      && (arc.consume.mode === "consume" || arc.consume.mode === "read")
      && arc.to.transition === transition
    ) {
      places.add(arc.from.place);
    }
  }
  return places;
}

function readsInstance(expression: string): boolean {
  try {
    createDefaultCelAdapter().compile(expression);
  } catch {
    return false;
  }
  return /(?<![\w.])instance\b/u.test(expression.replace(/"(?:\\.|[^"\\])*"/gu, "\"\""));
}

interface KeptRecord {
  readonly place: string;
  readonly color: string;
  readonly start: string;
}

function keptRecords(net: Net): KeptRecord[] {
  const found: KeptRecord[] = [];
  for (const place of net.places) {
    const kept = place.annotations?.kept;
    if (!isRecord(kept) || Object.keys(kept).length !== 2) continue;
    const by = kept.by;
    const start = kept.start;
    if (typeof by !== "string" || by.length === 0 || !isRecord(start)) continue;
    if (Object.keys(start).length !== 1 || typeof start.cel !== "string" || start.cel.length === 0) continue;
    const color = place.accepts.length === 1 ? place.accepts[0] : undefined;
    if (color === undefined) continue;
    found.push({place: place.name, color, start: start.cel});
  }
  return found.sort((left, right) => left.place < right.place ? -1 : left.place > right.place ? 1 : 0);
}

function emptyMarking(): Marking {
  return Object.create(null) as Marking;
}

function setPlace(marking: Marking, place: string, tokens: readonly Token[]): Marking {
  const next: Record<string, readonly Token[]> = {...marking};
  next[place] = tokens;
  return next;
}

function tokensFromMarking(raw: unknown): Marking | null {
  if (!isRecord(raw)) return null;
  const marking: Record<string, Token[]> = Object.create(null) as Record<string, Token[]>;
  for (const [place, tokens] of Object.entries(raw)) {
    if (!Array.isArray(tokens)) return null;
    const parsed: Token[] = [];
    for (const token of tokens) {
      if (!isRecord(token) || typeof token.type !== "string" || !isRecord(token.data)) return null;
      parsed.push({type: token.type, data: token.data as ReadonlyJsonObject});
    }
    marking[place] = parsed;
  }
  return marking;
}

function namedMarkings(document: PlayNet["document"]): Record<string, unknown> {
  if (document === null) return {};
  const annotations = document.annotations;
  if (!isRecord(annotations)) return {};
  const dsl = annotations["petrinet.dsl/v1"];
  if (!isRecord(dsl) || !isRecord(dsl.markings)) return {};
  return dsl.markings;
}

function startingMarking(play: Play, subject: PlayNet): Marking {
  if (play.marking === "none") return emptyMarking();
  if (play.marking === "initial") return subject.net.initialMarking ?? emptyMarking();
  const markings = namedMarkings(subject.document);
  const raw = markings[play.marking];
  const marking = tokensFromMarking(raw);
  if (marking === null) {
    const available = Object.keys(markings).sort().join(", ") || "none";
    throw new PlayCheckError(
      "SC206",
      `the net has no named marking ${play.marking} (named markings: ${available})`,
      play.position.line,
      play.position.column,
    );
  }
  return marking;
}

function withKeptRecords(play: Play, subject: PlayNet, templates: ReadonlyMap<string, Token>, marking: Marking): Marking {
  let instance: ReadonlyJsonObject | null = null;
  if (play.instance !== null) {
    instance = isNameRef(play.instance)
      ? templates.get(play.instance.name)?.data ?? null
      : jsonData(play.instance.data);
  }
  let next = marking;
  for (const record of keptRecords(subject.net)) {
    if (readsInstance(record.start) && instance === null) continue;
    let data: ReadonlyJsonObject;
    try {
      const adapter = createDefaultCelAdapter();
      const value: unknown = adapter.evaluate(adapter.compile(record.start), {instance: instance ?? {}});
      if (!isRecord(value)) {
        throw new Error(`${JSON.stringify(value)} is not a map of its fields`);
      }
      data = value as ReadonlyJsonObject;
    } catch (error) {
      throw new PlayCheckError(
        "SC215",
        `the start of (${record.place}) cannot be built from the instance: ${
          error instanceof Error ? error.message : String(error)
        }`,
        play.position.line,
        play.position.column,
      );
    }
    const token = {type: record.color, data};
    const violation = domainViolation(subject.net, record.place, token);
    if (violation !== null) {
      throw new PlayCheckError(
        "SC215",
        `the start of (${record.place}) breaks a domain: ${violation}`,
        play.position.line,
        play.position.column,
      );
    }
    next = setPlace(next, record.place, [token]);
  }
  return next;
}

class Resolver {
  readonly #play: Play;
  readonly #subject: PlayNet;
  readonly #places: ReadonlyMap<string, Net["places"][number]>;
  readonly #transitions: ReadonlyMap<string, Net["transitions"][number]>;
  readonly #templates = new Map<string, Token>();

  constructor(play: Play, subject: PlayNet) {
    this.#play = play;
    this.#subject = subject;
    this.#places = new Map(subject.net.places.map((place) => [place.name, place]));
    this.#transitions = new Map(subject.net.transitions.map((transition) => [transition.name, transition]));
    for (const [name, literal] of play.templates) {
      if (literal.color === null) continue;
      this.#templates.set(name, {type: literal.color, data: jsonData(literal.data)});
    }
  }

  get templates(): ReadonlyMap<string, Token> {
    return this.#templates;
  }

  error(code: string, message: string, position: Position, details: readonly string[] = []): PlayCheckError {
    return new PlayCheckError(code, message, position.line, position.column, details);
  }

  place(ref: NameRef): string {
    const resolved = this.#subject.placeNames.get(ref.name);
    if (resolved === undefined) {
      throw this.error(
        "SC202",
        `the net has no place (${ref.name})`,
        ref.position,
        suggest(ref.name, [...this.#subject.placeNames.keys()]),
      );
    }
    return resolved;
  }

  transition(ref: NameRef): string {
    if (!this.#transitions.has(ref.name)) {
      const refining = this.#subject.refined.get(ref.name);
      throw this.error(
        "SC203",
        `the net has no transition [${ref.name}]`,
        ref.position,
        refining === undefined
          ? suggest(ref.name, [...this.#transitions.keys()])
          : [`the composition refines [${ref.name}] by ${refining}`],
      );
    }
    return ref.name;
  }

  template(ref: NameRef): Token {
    const token = this.#templates.get(ref.name);
    if (token === undefined) throw this.error("SC204", `no template $${ref.name} is defined`, ref.position);
    return token;
  }

  tokenFor(expr: TokenExpr, place: string, colors?: readonly string[]): Token {
    const candidates = colors ?? [...(this.#places.get(place)?.accepts ?? [])];
    if (isNameRef(expr)) {
      const token = this.template(expr);
      if (!candidates.includes(token.type)) {
        throw this.error(
          "SC207",
          `(${place}) does not take color ${token.type} (it takes ${candidates.join(", ")})`,
          expr.position,
        );
      }
      return token;
    }
    if (expr.color === null && candidates.length !== 1) {
      throw this.error(
        "SC207",
        `(${place}) takes several colors (${candidates.join(", ")}); write the color before the data`,
        expr.position,
      );
    }
    const type = expr.color ?? candidates[0];
    if (type === undefined || !candidates.includes(type)) {
      throw this.error(
        "SC207",
        `(${place}) does not take color ${type ?? "?"} (it takes ${candidates.join(", ")})`,
        expr.position,
      );
    }
    return {type, data: jsonData(expr.data)};
  }

  resolve(step: Step): Resolved {
    const body = step.body;
    if (step.kind === "inject") return this.#inject(body as InjectBody, false);
    if (step.kind === "update") {
      const update = body as UpdateBody;
      const place = this.place(update.place);
      return {kind: "inject", place, tokens: [this.tokenFor(update.token, place)], replace: true};
    }
    if (step.kind === "advance") return this.#advance(body as AdvanceBody, step.position);
    if (step.kind === "fire") return this.#fire(body as FireBody);
    if (step.kind === "assume") {
      if ("predicate" in body) return this.#assumePredicate(body as AssumePredicateBody);
      return this.#assumeGuard(body as AssumeGuardBody, step.position);
    }
    const expect = body as {readonly conditions: readonly Condition[]};
    return {kind: "expect", conditions: expect.conditions.map((condition) => this.#condition(condition))};
  }

  #inject(body: InjectBody, replace: boolean): ResolvedInject {
    const place = this.place(body.place);
    return {kind: "inject", place, tokens: body.tokens.map((token) => this.tokenFor(token, place)), replace};
  }

  #advance(body: AdvanceBody, position: Position): ResolvedAdvance {
    let place: string;
    if (body.place !== null) place = this.place(body.place);
    else {
      const clocks = [...new Set(
        this.#subject.net.transitions.flatMap((transition) => transition.timer === undefined ? [] : [transition.timer.clock]),
      )].sort();
      if (clocks.length !== 1) {
        const reason = clocks.length === 0
          ? "no timer names a clock place"
          : `the timers name several clock places: ${clocks.map((clock) => `(${clock})`).join(", ")}`;
        throw this.error("SC208", `\`advance\` needs a place here: ${reason}`, position);
      }
      const clock = clocks[0];
      if (clock === undefined) throw this.error("SC208", "`advance` needs a place here", position);
      place = clock;
    }
    const accepts = [...(this.#places.get(place)?.accepts ?? [])];
    if (accepts.length !== 1) {
      throw this.error(
        "SC208",
        `\`advance\` needs a clock place of one color; (${place}) takes ${accepts.join(", ")}`,
        position,
      );
    }
    const color = accepts[0];
    if (color === undefined) throw this.error("SC208", `\`advance\` needs a clock place of one color`, position);
    return {kind: "advance", place, color, seconds: body.seconds, relative: body.relative};
  }

  #fire(body: FireBody): ResolvedFire {
    const transition = this.transition(body.transition);
    const places = bindingPlaces(this.#subject.net, transition);
    const withs = body.withs.map((clause) => this.#with(transition, places, clause));
    const templates = produceTemplates(this.#subject.net, transition);
    const outputs = new Map<number, ResolvedOutput>();
    for (const clause of body.outputs) this.#output(transition, templates, outputs, clause);
    return {kind: "fire", transition, withs, outputs};
  }

  #with(transition: string, places: ReadonlySet<string>, clause: WithClause): ResolvedWith {
    const place = this.place(clause.place);
    if (!places.has(place)) {
      throw this.error("SC209", `[${transition}] binds no token from (${place})`, clause.place.position);
    }
    if (clause.template !== undefined) {
      const token = this.template(clause.template);
      return {place, describe: `$${clause.template.name}`, token};
    }
    if (clause.index !== undefined) return {place, describe: `#${clause.index}`, index: clause.index};
    const subset = jsonData(clause.subset ?? {});
    return {place, describe: JSON.stringify(subset), subset};
  }

  #output(
    transition: string,
    templates: readonly ProduceTemplate[],
    outputs: Map<number, ResolvedOutput>,
    clause: OutputClause,
  ): void {
    const place = this.place(clause.place);
    const here = templates.flatMap((template, index) => template.destination === place ? [index] : []);
    if (here.length === 0) {
      throw this.error("SC210", `[${transition}] produces nothing into (${place})`, clause.place.position);
    }
    const fixed = here.filter((index) => netFills(templates[index] as ProduceTemplate));
    const open = here.filter((index) => !netFills(templates[index] as ProduceTemplate));
    if (clause.nothing || clause.merge !== undefined) {
      const blocked = fixed[0];
      if (blocked !== undefined && (clause.nothing || open.length === 0)) {
        throw this.#fixed(transition, templates[blocked] as ProduceTemplate, clause.place);
      }
      if (open.length !== 1) {
        throw this.error(
          "SC210",
          `[${transition}] has ${open.length} outputs into (${place}); give the tokens with their colors`,
          clause.place.position,
        );
      }
      const index = open[0];
      if (index === undefined) return;
      this.#noRepeat(outputs, index, transition, clause.place);
      outputs.set(index, clause.nothing ? {tokens: [], nothing: true} : {tokens: [], merge: jsonData(clause.merge ?? {}), nothing: false});
      return;
    }
    const byIndex = new Map<number, Token[]>();
    for (const expr of clause.tokens) {
      const colors = [...new Set(here.map((index) => (templates[index] as ProduceTemplate).type))];
      const token = this.tokenFor(expr, place, colors);
      const match = here.find((index) => (templates[index] as ProduceTemplate).type === token.type);
      if (match === undefined) continue;
      if (netFills(templates[match] as ProduceTemplate)) {
        throw this.#fixed(transition, templates[match] as ProduceTemplate, clause.place);
      }
      const list = byIndex.get(match) ?? [];
      list.push(token);
      byIndex.set(match, list);
    }
    for (const [index, tokens] of byIndex) {
      this.#noRepeat(outputs, index, transition, clause.place);
      outputs.set(index, {tokens, nothing: false});
    }
  }

  #fixed(transition: string, template: ProduceTemplate, place: NameRef): PlayCheckError {
    const how = template.cel !== undefined ? "data cel" : "data";
    return this.error(
      "SC211",
      `the net fixes the ${template.type} output of [${transition}] into (${template.destination}) with \`${how}\`; a play may not give it`,
      place.position,
    );
  }

  #noRepeat(outputs: ReadonlyMap<number, ResolvedOutput>, index: number, transition: string, place: NameRef): void {
    if (outputs.has(index)) {
      throw this.error(
        "SC210",
        `two \`->\` clauses give the same output of [${transition}] into (${place.name})`,
        place.position,
      );
    }
  }

  #condition(condition: Condition): ResolvedCondition {
    const place = condition.place === null ? null : this.place(condition.place);
    return {
      source: condition,
      place,
      tokens: place === null ? [] : condition.tokens.map((token) => this.tokenFor(token, place)),
      transitions: condition.transitions.map((transition) => this.transition(transition)),
    };
  }

  #assumeGuard(body: AssumeGuardBody, position: Position): ResolvedAssume {
    const transition = this.transition(body.transition);
    const guard = this.#transitions.get(transition)?.guard;
    if (guard === undefined) {
      throw this.error(
        "SC308",
        `[${transition}] has no \`guard\` fact, so there is nothing to assume for it`,
        position,
      );
    }
    return {kind: "assume", transition, guardRef: guard, predicateRef: null, value: body.value};
  }

  #assumePredicate(body: AssumePredicateBody): ResolvedAssume {
    const named = this.#subject.net.arcs.some((arc) => {
      const predicate = arc.consume?.predicate;
      return predicate !== undefined && "handler" in predicate && predicate.handler === body.predicate;
    });
    if (!named) {
      throw this.error(
        "SC310",
        `no consume arc names predicate handler ${JSON.stringify(body.predicate)}`,
        body.position,
      );
    }
    return {kind: "assume", transition: null, guardRef: null, predicateRef: body.predicate, value: body.value};
  }
}

function pathPlans(play: Play, resolved: ReadonlyMap<string, PlannedStep[]>): Map<string, {plan: PlannedStep[]; inherited: number}> {
  const labels = new Map<string, {owner: string; index: number}>();
  const plans = new Map<string, {plan: PlannedStep[]; inherited: number}>();
  for (const path of play.paths) {
    let prefix: PlannedStep[] = [];
    if (path.fromLabel !== null) {
      const found = labels.get(path.fromLabel.name);
      if (found === undefined) {
        const later = play.paths.some((other) => other.steps.some((step) => step.label === path.fromLabel?.name));
        throw new PlayCheckError(
          "SC205",
          `no step @${path.fromLabel.name} before path ${path.name}${
            later ? "; a path branches from the trunk or an earlier path" : ""
          }`,
          path.fromLabel.position.line,
          path.fromLabel.position.column,
        );
      }
      prefix = (plans.get(found.owner)?.plan ?? []).slice(0, found.index + 1);
    }
    const own = resolved.get(path.name) ?? [];
    plans.set(path.name, {plan: [...prefix, ...own], inherited: prefix.length});
    path.steps.forEach((step, offset) => {
      if (step.label !== null) labels.set(step.label, {owner: path.name, index: prefix.length + offset});
    });
  }
  return plans;
}

function consumeSources(net: Net): Map<string, Set<string>> {
  const sources = new Map<string, Set<string>>();
  for (const arc of net.arcs) {
    if (!isConsumeArc(arc) || arc.consume.mode !== "consume") continue;
    const set = sources.get(arc.to.transition) ?? new Set<string>();
    set.add(arc.from.place);
    sources.set(arc.to.transition, set);
  }
  return sources;
}

function removeTokens(tokens: readonly Token[], gone: readonly Token[]): Token[] {
  const remaining = [...tokens];
  for (const token of gone) {
    const index = remaining.findIndex((candidate) => sameToken(candidate, token));
    if (index >= 0) remaining.splice(index, 1);
  }
  return remaining;
}

function replayThrough(
  net: Net,
  before: Marking,
  records: readonly (FiringRecord | InjectionRecord)[],
): Marking[] {
  const sources = consumeSources(net);
  const markings: Marking[] = [];
  let marking = before;
  for (const record of records) {
    if ("firingId" in record) {
      if (record.status === "completed") {
        const consumedPlaces = sources.get(record.transition) ?? new Set<string>();
        let next: Record<string, readonly Token[]> = {...marking};
        for (const [place, tokens] of Object.entries(record.inputTokens)) {
          if (!consumedPlaces.has(place)) continue;
          next = {...next, [place]: removeTokens(next[place] ?? [], tokens)};
        }
        for (const [place, tokens] of Object.entries(record.outputTokens)) {
          next = {...next, [place]: [...(next[place] ?? []), ...tokens]};
        }
        marking = next;
      }
    } else if (record.kind === "update") {
      marking = setPlace(marking, record.place, record.tokens);
    } else {
      marking = setPlace(marking, record.place, [...(marking[record.place] ?? []), ...record.tokens]);
    }
    markings.push(marking);
  }
  return markings;
}

function traceOf(
  play: Play,
  subject: PlayNet,
  path: PlayPath,
  initial: Marking,
  steps: readonly StepResult[],
  failure: StepFailure | null,
  inherited: number,
): PlayTrace {
  const final = steps.length === 0 ? initial : (steps[steps.length - 1]?.after ?? initial);
  return {play, subject, path, initial, steps, failure, inherited, passed: failure === null, final};
}

class Player {
  readonly #play: Play;
  readonly #net: Net;
  readonly #engine: Engine;
  readonly #registry: HandlerRegistry;
  readonly #priorities: ReadonlyMap<string, number>;
  readonly #kept: ReadonlySet<string>;
  readonly #guardValues = new Map<string, boolean>();
  readonly #predicateValues = new Map<string, boolean>();
  readonly #guards = new Set<string>();
  readonly #predicates = new Set<string>();
  #handlers = 0;

  constructor(play: Play, subject: PlayNet, engine: Engine, registry: HandlerRegistry) {
    this.#play = play;
    this.#net = subject.net;
    this.#engine = engine;
    this.#registry = registry;
    this.#priorities = new Map(subject.net.transitions.map((transition) => [transition.name, transition.priority ?? 0]));
    this.#kept = new Set(keptRecords(subject.net).map((record) => record.place));
  }

  play(planned: PlannedStep, index: number, marking: Marking, attemptOffset = 0): StepResult {
    const resolved = planned.resolved;
    if (resolved.kind === "inject") return this.#inject(planned, resolved, index, marking);
    if (resolved.kind === "advance") return this.#advance(planned, resolved, index, marking);
    if (resolved.kind === "fire") return this.#fire(planned, resolved, index, marking, attemptOffset);
    if (resolved.kind === "assume") return this.#assume(planned, resolved, index, marking);
    return this.#expect(planned, resolved, index, marking);
  }

  assume(planned: PlannedStep, resolved: ResolvedAssume, index: number, marking: Marking): StepResult {
    return this.#assume(planned, resolved, index, marking);
  }

  #fail(
    planned: PlannedStep,
    index: number,
    before: Marking,
    code: string,
    message: string,
    details: readonly string[] = [],
    extra: {readonly checks?: readonly CheckResult[]; readonly enabled?: readonly string[]} = {},
  ): StepFailed {
    return new StepFailed({
      step: planned.step,
      path: planned.path,
      index,
      before,
      diagnostic: {
        code,
        message,
        line: planned.step.position.line,
        column: planned.step.position.column,
        details,
      },
      checks: extra.checks ?? [],
      enabled: extra.enabled ?? [],
    });
  }

  #result(
    planned: PlannedStep,
    index: number,
    before: Marking,
    after: Marking,
    fields: Partial<Omit<StepResult, "step" | "path" | "index" | "before" | "after">> = {},
  ): StepResult {
    const records = fields.records ?? [];
    return {
      step: planned.step,
      path: planned.path,
      index,
      before,
      after,
      records,
      markings: fields.markings ?? replayThrough(this.#net, before, records),
      binding: fields.binding ?? {},
      consumed: fields.consumed ?? {},
      read: fields.read ?? {},
      produced: fields.produced ?? {},
      replaced: fields.replaced ?? {},
      outputs: fields.outputs ?? [],
      checks: fields.checks ?? [],
    };
  }

  #assume(planned: PlannedStep, resolved: ResolvedAssume, index: number, marking: Marking): StepResult {
    if (resolved.guardRef !== null) this.#setGuard(resolved.guardRef, resolved.value);
    if (resolved.predicateRef !== null) this.#setPredicate(resolved.predicateRef, resolved.value);
    return this.#result(planned, index, marking, marking);
  }

  #setGuard(name: string, value: boolean): void {
    this.#guardValues.set(name, value);
    if (this.#guards.has(name)) return;
    this.#registry.registerGuard(name, () => this.#guardValues.get(name) === true);
    this.#guards.add(name);
  }

  #setPredicate(name: string, value: boolean): void {
    this.#predicateValues.set(name, value);
    if (this.#predicates.has(name)) return;
    this.#registry.registerPredicate(name, () => this.#predicateValues.get(name) === true);
    this.#predicates.add(name);
  }

  #inject(planned: PlannedStep, resolved: ResolvedInject, index: number, marking: Marking): StepResult {
    const held = marking[resolved.place] ?? [];
    if (!resolved.replace && this.#kept.has(resolved.place) && (held.length > 0 || resolved.tokens.length > 1)) {
      throw this.#fail(
        planned,
        index,
        marking,
        "SC305",
        held.length > 0
          ? `the injection is rejected: (${resolved.place}) is a kept record and already holds its record; change it with \`update\``
          : `the injection is rejected: (${resolved.place}) is a kept record and holds one record`,
      );
    }
    try {
      if (resolved.replace) {
        const token = resolved.tokens[0];
        if (token === undefined) {
          throw this.#fail(planned, index, marking, "SC305", "the injection is rejected: update needs a token");
        }
        const result = this.#engine.inject(this.#net, marking, resolved.place, token, {attempt: index, replace: true});
        return this.#result(planned, index, marking, result.marking, {
          records: [result.record],
          produced: {[resolved.place]: [token]},
          replaced: result.record.replaced.length > 0 ? {[resolved.place]: result.record.replaced} : {},
        });
      }
      const result = this.#engine.injectMany(
        this.#net,
        marking,
        resolved.tokens.map((token) => ({place: resolved.place, token})),
        {attempt: index},
      );
      return this.#result(planned, index, marking, result.marking, {
        records: result.records,
        produced: {[resolved.place]: resolved.tokens},
      });
    } catch (error) {
      if (error instanceof StepFailed) throw error;
      if (error instanceof TokenInjectionError || error instanceof Error) {
        throw this.#fail(planned, index, marking, "SC305", `the injection is rejected: ${error.message}`);
      }
      throw error;
    }
  }

  #advance(planned: PlannedStep, resolved: ResolvedAdvance, index: number, marking: Marking): StepResult {
    const current = marking[resolved.place] ?? [];
    const token = current[0];
    let value = resolved.seconds;
    if (resolved.relative) {
      const now = token?.data.now;
      if (typeof now !== "number") {
        const found = token === undefined ? `(${resolved.place}) is empty` : `its token is ${tokenText(token)}`;
        throw this.#fail(
          planned,
          index,
          marking,
          "SC306",
          `\`${planned.step.statement}\` adds to the clock's \`now\`, but ${found}`,
        );
      }
      value = now + resolved.seconds;
    }
    const data: Record<string, Json> = {...(token?.data ?? {}), now: value};
    const nextToken: Token = {type: token?.type ?? resolved.color, data: data as ReadonlyJsonObject};
    const injected = this.#engine.inject(this.#net, marking, resolved.place, nextToken, {attempt: index, replace: true});
    const replaced = injected.record.replaced;
    if (replaced.length === 0 && current.length === 0) {
      return this.#result(planned, index, marking, injected.marking, {
        records: [injected.record],
        produced: {[resolved.place]: [nextToken]},
      });
    }
    const records: (FiringRecord | InjectionRecord)[] = [injected.record];
    let after = injected.marking;
    const failed = new Set<string>();
    let fired = 0;
    const timed = new Set(
      this.#net.transitions
        .filter((transition) => transition.timer?.clock === resolved.place)
        .map((transition) => transition.name),
    );
    while (true) {
      const candidates = this.#engine.enabledTransitions(this.#net, after, {attempt: index + fired}).filter((name) => (
        timed.has(name) && !failed.has(name) && this.#outputsDetermined(name, after, index + fired)
      ));
      if (candidates.length === 0) break;
      const choice = this.#registry.resolveFiringPolicy(PRIORITY_FIRING_POLICY)({
        marking: after,
        enabledTransitions: candidates,
        priorities: Object.fromEntries(candidates.map((name) => [name, this.#priorities.get(name) ?? 0])),
        consecutiveFailures: Object.fromEntries(candidates.map((name) => [name, 0])),
      });
      if (choice === null) break;
      fired += 1;
      if (fired >= ADVANCE_MAX_MATURING) {
        throw this.#fail(
          planned,
          index,
          after,
          "SC315",
          `the advance's maturation did not quiesce: it hit the cap of ${ADVANCE_MAX_MATURING} matured firings, so the play is unbounded`,
        );
      }
      const synthetic = this.#syntheticFire(choice, planned.path);
      const syntheticFire = synthetic.resolved;
      if (syntheticFire.kind !== "fire") continue;
      try {
        const matured = this.#fire(synthetic, syntheticFire, index, after, fired);
        after = matured.after;
        const stamped = matured.records.map((record) => stamp(record, injected.record.injectionId));
        records.push(...stamped);
        const last = stamped[stamped.length - 1];
        if (last !== undefined && "status" in last && last.status === "failed") failed.add(choice);
      } catch (error) {
        if (!(error instanceof StepFailed) && !(error instanceof DepositViolationError)) throw error;
        failed.add(choice);
      }
    }
    return this.#result(planned, index, marking, after, {
      records,
      produced: {[resolved.place]: [nextToken]},
      replaced: replaced.length > 0 ? {[resolved.place]: replaced} : {},
    });
  }

  #syntheticFire(transition: string, path: string): PlannedStep {
    const step: Step = {
      kind: "fire",
      body: {transition: {name: transition, position: {line: 0, column: 0}}, withs: [], outputs: []},
      statement: `fire [${transition}]`,
      position: {line: 0, column: 0},
      label: null,
      title: null,
      prose: "",
    };
    return {
      step,
      path,
      resolved: {kind: "fire", transition, withs: [], outputs: new Map()},
    };
  }

  #outputsDetermined(transition: string, marking: Marking, attempt: number): boolean {
    const templates = produceTemplates(this.#net, transition);
    if (templates.every((template) => netFills(template))) return true;
    // A handler writes the outputs the net does not fill; carrying would guess.
    if (this.#net.transitions.some((t) => t.name === transition && t.handler !== undefined)) {
      return false;
    }
    const binding = this.#engine.selectBinding(this.#net, transition, marking, {attempt});
    if (binding === null) return false;
    return carryRule(templates, consumedOf(this.#net, transition, binding)) !== null;
  }

  #fire(
    planned: PlannedStep,
    resolved: ResolvedFire,
    index: number,
    marking: Marking,
    attemptOffset: number,
  ): StepResult {
    const attempt = index + attemptOffset;
    let binding: TokenBinding | null;
    try {
      binding = this.#engine.selectBinding(this.#net, resolved.transition, marking, {attempt});
    } catch (error) {
      throw this.#fail(
        planned,
        index,
        marking,
        "SC301",
        `[${resolved.transition}] is not enabled`,
        [error instanceof Error ? error.message : String(error)],
      );
    }
    const enabled = this.#engine.enabledTransitions(this.#net, marking, {attempt});
    const enabledLine = `enabled now: ${enabled.length === 0 ? "nothing" : enabled.map((name) => `[${name}]`).join(", ")}`;
    if (binding === null) {
      throw this.#fail(
        planned,
        index,
        marking,
        "SC301",
        `[${resolved.transition}] is not enabled`,
        [enabledLine],
        {enabled},
      );
    }
    if (resolved.withs.length > 0 && !this.#bindingMatches(binding, resolved.withs, marking)) {
      const wanted = resolved.withs.map((clause) => `with (${clause.place}) ${clause.describe}`).join(", ");
      throw this.#fail(
        planned,
        index,
        marking,
        "SC302",
        `no enabled binding of [${resolved.transition}] matches ${wanted}`,
        [
          "the engine selected one binding; this checker does not search the other enabled bindings",
          enabledLine,
        ],
        {enabled},
      );
    }
    const templates = produceTemplates(this.#net, resolved.transition);
    const consumed = consumedOf(this.#net, resolved.transition, binding);
    const carried = carryRule(templates, consumed);
    const outputTokens: Record<string, Token[]> = Object.create(null) as Record<string, Token[]>;
    const sources: OutputSource[] = [];
    const byColor = new Map<string, Token[]>();
    for (const tokens of Object.values(consumed)) {
      for (const token of tokens) {
        const list = byColor.get(token.type) ?? [];
        list.push(token);
        byColor.set(token.type, list);
      }
    }
    templates.forEach((template, templateIndex) => {
      if (netFills(template)) {
        sources.push({place: template.destination, color: template.type, rule: "net"});
        return;
      }
      const output = resolved.outputs.get(templateIndex);
      const carry = byColor.get(template.type) ?? [];
      if (output?.nothing) {
        sources.push({place: template.destination, color: template.type, rule: "nothing"});
        return;
      }
      if (output !== undefined && output.tokens.length > 0) {
        (outputTokens[template.destination] ??= []).push(...output.tokens.map((token) => ({
          type: token.type,
          data: structuredClone(token.data) as ReadonlyJsonObject,
        })));
        sources.push({place: template.destination, color: template.type, rule: "play"});
        return;
      }
      const carriedToken = carry.length === 1 ? carry[0] : undefined;
      if (carriedToken === undefined || carried === null) {
        const colors = [...byColor.keys()].sort();
        throw this.#fail(
          planned,
          index,
          marking,
          "SC303",
          `the ${template.type} output of [${resolved.transition}] into (${template.destination}) is not determined`,
          [
            `the net gives this output no data or data cel, the step states no token, and the carry rule needs exactly one consumed ${template.type} token (found ${carry.length}; consumed colors: ${colors.join(", ") || "none"})`,
          ],
        );
      }
      const data = structuredClone(carriedToken.data) as Record<string, Json>;
      let rule: OutputRule = "carry";
      if (output?.merge !== undefined) {
        Object.assign(data, structuredClone(output.merge));
        rule = "merge";
      }
      (outputTokens[template.destination] ??= []).push({type: template.type, data: data as ReadonlyJsonObject});
      sources.push({place: template.destination, color: template.type, rule});
    });
    const handlerName = `play-check:${resolved.transition}:${attempt}:${this.#handlers}`;
    this.#handlers += 1;
    this.#registry.registerTransition(handlerName, () => ({
      status: "completed",
      outputTokens,
      error: null,
      metadata: {},
    }));
    const net = withHandler(this.#net, resolved.transition, handlerName);
    try {
      const fired = this.#engine.fire(net, marking, resolved.transition, {attempt});
      if (fired.record.status !== "completed") {
        const code = fired.record.error?.type === "DepositViolation" ? "SC304" : "SC301";
        throw this.#fail(
          planned,
          index,
          marking,
          code,
          code === "SC304"
            ? `the engine rejects the deposit of [${resolved.transition}]: ${fired.record.error?.message ?? "deposit violation"}`
            : `[${resolved.transition}] is not enabled`,
          [enabledLine],
          {enabled},
        );
      }
      const read = difference(binding, consumed);
      return this.#result(planned, index, marking, fired.marking, {
        records: [fired.record],
        binding,
        consumed,
        read,
        produced: fired.record.outputTokens,
        outputs: sources,
      });
    } catch (error) {
      if (error instanceof StepFailed) throw error;
      if (error instanceof DepositViolationError) {
        throw this.#fail(
          planned,
          index,
          marking,
          "SC304",
          `the engine rejects the deposit of [${resolved.transition}]: ${error.message}`,
        );
      }
      throw error;
    }
  }

  #bindingMatches(binding: TokenBinding, withs: readonly ResolvedWith[], marking: Marking): boolean {
    return withs.every((clause) => {
      const bound = binding[clause.place] ?? [];
      if (clause.index !== undefined) {
        const chosen = (marking[clause.place] ?? [])[clause.index];
        return chosen !== undefined && bound.some((token) => sameToken(token, chosen));
      }
      if (clause.token !== undefined) return bound.some((token) => sameToken(token, clause.token as Token));
      return bound.some((token) => contains(token.data, clause.subset ?? {}));
    });
  }

  #expect(planned: PlannedStep, resolved: ResolvedExpect, index: number, marking: Marking): StepResult {
    let enabled: readonly string[] | undefined;
    const enabledNow = (): readonly string[] => {
      enabled ??= this.#engine.enabledTransitions(this.#net, marking, {attempt: index});
      return enabled;
    };
    const checks = resolved.conditions.map((condition) => this.#evaluate(condition, marking, enabledNow));
    const failed = checks.filter((check) => !check.ok);
    if (failed.length > 0) {
      throw this.#fail(
        planned,
        index,
        marking,
        "SC307",
        `expected ${failed.map((check) => `\`${check.text}\``).join("; ")} ${failed.length === 1 ? "does not hold" : "do not hold"}`,
        failed.map((check) => `${check.text}: ${check.detail}`),
        {checks},
      );
    }
    return this.#result(planned, index, marking, marking, {checks});
  }

  #evaluate(
    condition: ResolvedCondition,
    marking: Marking,
    enabledNow: () => readonly string[],
  ): CheckResult {
    const kind = condition.source.kind;
    const text = condition.source.text;
    if (condition.place !== null) {
      const tokens = [...(marking[condition.place] ?? [])];
      const holds = tokens.length === 0
        ? `(${condition.place}) is empty`
        : `(${condition.place}) holds ${tokens.map((token) => tokenText(token)).join(", ")}`;
      if (kind === "equals") return {text, ok: sameMultiset(tokens, condition.tokens), detail: holds, kind};
      if (kind === "empty") return {text, ok: tokens.length === 0, detail: holds, kind};
      if (kind === "count") {
        return {text, ok: tokens.length === condition.source.count, detail: `(${condition.place}) holds ${tokens.length}`, kind};
      }
      const wanted = condition.tokens[0];
      const ok = wanted !== undefined && tokens.some((token) => token.type === wanted.type && contains(token.data, wanted.data));
      return {text, ok, detail: holds, kind};
    }
    const enabled = enabledNow();
    const enabledText = `enabled now: ${enabled.length === 0 ? "nothing" : enabled.map((name) => `[${name}]`).join(", ")}`;
    if (kind === "enabled") {
      const missing = condition.transitions.filter((name) => !enabled.includes(name));
      return {text, ok: missing.length === 0, detail: enabledText, kind};
    }
    if (kind === "not-enabled") {
      return {text, ok: !condition.transitions.some((name) => enabled.includes(name)), detail: enabledText, kind};
    }
    if (kind === "quiescent") return {text, ok: enabled.length === 0, detail: enabledText, kind};
    let choice: string | null = null;
    let priority = Number.NEGATIVE_INFINITY;
    for (const name of enabled) {
      const candidate = this.#priorities.get(name) ?? 0;
      if (choice === null || candidate > priority) {
        choice = name;
        priority = candidate;
      }
    }
    const wanted = condition.transitions[0];
    const among = enabled.map((name) => `[${name}]`).join(", ");
    const detail = choice === null ? "nothing is enabled" : `the priority policy picks [${choice}] of ${among}`;
    return {text, ok: choice === wanted, detail, kind};
  }
}

function withHandler(net: Net, transition: string, handler: string): Net {
  return {
    ...net,
    transitions: net.transitions.map((item) => item.name === transition ? {...item, handler} : item),
  };
}

function difference(whole: TokenBinding, part: TokenBinding): Record<string, Token[]> {
  const result: Record<string, Token[]> = {};
  for (const [place, tokens] of Object.entries(whole)) {
    const remaining = removeTokens(tokens, part[place] ?? []);
    if (remaining.length > 0) result[place] = remaining;
  }
  return result;
}

function stamp(record: FiringRecord | InjectionRecord, injectionId: string): FiringRecord | InjectionRecord {
  if (!("firingId" in record)) return record;
  return {...record, metadata: {...record.metadata, maturedBy: injectionId}};
}

function playPath(
  play: Play,
  subject: PlayNet,
  path: PlayPath,
  plan: readonly PlannedStep[],
  inherited: number,
  initial: Marking,
): PlayTrace {
  const registry = new HandlerRegistry();
  const engine = new Engine(registry, {celAdapter: createDefaultCelAdapter()});
  const player = new Player(play, subject, engine, registry);
  let marking = initial;
  const results: StepResult[] = [];
  for (const [index, planned] of plan.entries()) {
    if (index < inherited && planned.resolved.kind === "assume") {
      player.assume(planned, planned.resolved, index, marking);
      continue;
    }
    try {
      const result = player.play(planned, index, marking);
      results.push(result);
      marking = result.after;
    } catch (error) {
      if (error instanceof StepFailed) {
        return traceOf(play, subject, path, initial, results, error.failure, inherited);
      }
      throw error;
    }
  }
  return traceOf(play, subject, path, initial, results, null, inherited);
}

/**
 * Resolve `play` and play each path through `@velocitron/engine`.
 *
 * `SC2xx` is thrown. A step that fails (`SC3xx`) ends that path's trace.
 * Symbolic firing registers a handler that returns the play's outputs, or
 * the carry rule, and lets the engine fill `data` / `data cel` templates.
 * `with` matches the one binding `selectBinding` returns.
 */
export function checkPlay(play: Play, options: CheckPlayOptions = {}): PlayReport {
  const subject = loadPlayNet(play, options);
  const colors = new Set(subject.net.places.flatMap((place) => [...place.accepts]));
  for (const show of play.shows) {
    if (!colors.has(show.color)) {
      const known = [...colors].sort().join(", ");
      throw new PlayCheckError(
        "SC214",
        `\`show\` names color ${show.color}, which no place takes (colors: ${known})`,
        show.position.line,
        show.position.column,
      );
    }
  }
  const resolver = new Resolver(play, subject);
  const resolved = new Map<string, PlannedStep[]>();
  for (const path of play.paths) {
    resolved.set(path.name, path.steps.map((step) => ({
      step,
      path: path.name,
      resolved: resolver.resolve(step),
    })));
  }
  const initial = withKeptRecords(play, subject, resolver.templates, startingMarking(play, subject));
  const plans = pathPlans(play, resolved);
  const selected = options.paths ?? play.paths.map((path) => path.name);
  for (const name of selected) {
    if (!play.paths.some((path) => path.name === name)) {
      throw new PlayCheckError(
        "SC213",
        `the play has no path ${name} (paths: ${play.paths.map((path) => path.name).join(", ")})`,
        play.position.line,
        play.position.column,
      );
    }
  }
  const traces = selected.map((name) => {
    const path = play.paths.find((item) => item.name === name);
    const plan = plans.get(name);
    if (path === undefined || plan === undefined) {
      throw new PlayCheckError("SC213", `the play has no path ${name}`, play.position.line, play.position.column);
    }
    return playPath(play, subject, path, plan.plan, plan.inherited, initial);
  });
  return new Report(play, subject, traces);
}
