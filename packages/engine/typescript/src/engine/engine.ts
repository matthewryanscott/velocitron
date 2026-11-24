import type {CelAdapter} from "../adapter.js";
import type {FiringRecord, InjectionRecord, Journal} from "../journal/types.js";
import {
  DEFAULT_FIRING_POLICY,
  HandlerNotFoundError,
  PRIORITY_FIRING_POLICY,
  type FiringContext,
  type HandlerError,
  type GuardHandler,
  type OutputTokens,
  type TokenBinding,
  type TransitionHandler,
  type TransitionHandlerOutput,
  HandlerRegistry,
} from "../registry/index.js";
import type {
  Arc,
  ConsumeArc,
  Marking,
  Net,
  ProduceArc,
  ProduceTemplate,
  ReadonlyJsonObject,
  Timer,
  Token,
  Transition,
} from "../schema/types.js";
import {
  ConflictError,
  DepositViolationError,
  EngineConfigurationError,
  FailedAttemptError,
  TokenInjectionError,
  UnknownTransitionError,
} from "./errors.js";
import type {
  BatchInjectionResult,
  EngineClock,
  EngineIdFactory,
  EngineOptions,
  FireResult,
  FiringIdInput,
  FiringReservation,
  InjectOptions,
  InjectionResult,
  InjectionIdInput,
  OptionalAttemptOptions,
  RunOptions,
  SelectedBinding,
  TickOptions,
  TimerMaturity,
  TokenPlacement,
  TransitionFootprint,
} from "./types.js";

/**
 * The one failure-budget counter (ADR 0015).
 *
 * `Engine.run` makes one per call. The async runtime holds one for the life
 * of the run, from `selectionLedger`, instead of keeping a second copy.
 */
export class SelectionLedger {
  readonly #budget: number | null;
  readonly #failures = new Map<string, number>();

  constructor(budget: number | null) {
    this.#budget = budget;
  }

  admissible(transition: string): boolean {
    if (this.#budget === null) return true;
    return (this.#failures.get(transition) ?? 0) < this.#budget;
  }

  counts(enabled: readonly string[]): Record<string, number> {
    const result = Object.create(null) as Record<string, number>;
    for (const name of enabled) result[name] = this.#failures.get(name) ?? 0;
    return result;
  }

  record(transition: string, status: FiringRecord["status"]): void {
    if (status === "failed") {
      this.#failures.set(transition, (this.#failures.get(transition) ?? 0) + 1);
    } else {
      this.#failures.clear();
    }
  }
}

interface Binding {
  readonly tokens: TokenBinding;
  readonly consumed: TokenBinding;
}

/**
 * Why the binding enumeration rejected a candidate (or the whole walk).
 *
 * The enumeration's ONE vocabulary of rejections (ADR 0027), mirrored exactly
 * by the Python engine. Candidate-level reasons annotate a yielded binding
 * that failed one of the pure, structural per-binding tests; walk-level
 * reasons close a walk that produced no candidate binding at all (`tokens` /
 * `consumed` are `undefined` there).
 *
 * The guard is deliberately NOT a rejection reason: it is possibly impure
 * (ADR 0002), so it is evaluated by the first-success consumer, which may
 * stop the enumeration early — never inside it.
 */
type BindingRejection =
  // Walk-level: a pre-binding gate failed the whole transition before any
  // candidate binding existed — the uncorrelated inhibit zero-test matched, a
  // binding arc had fewer matching tokens than its `weight`, or a timer's
  // clock place was empty (no time reference => not enabled, ADR 0018).
  | "per-arc-miss"
  // Walk-level: the cartesian product was walked to its end without one
  // surviving binding (sub-multiset, correlate-miss, correlated-inhibit,
  // timer, and — consumer-side — guard failures exhaust it).
  | "product-miss"
  // Candidate-level: the combined bound multiset would bind one token to two
  // arcs — not a valid sub-multiset of the source place (D1; shared-place
  // binding, ADR 0012).
  | "sub-multiset"
  // Candidate-level: a token bound on a correlated consume or read arc did not
  // satisfy its `correlate` against the binding (eval error or non-boolean
  // fails closed, ADR 0030).
  | "correlate-miss"
  // Candidate-level: a correlated inhibit arc's per-binding anti-join blocked
  // the binding (eval error or non-boolean fails closed, ADR 0017).
  | "correlated-inhibit"
  // Candidate-level: the timer-hold gate failed — `timer.cel` did not
  // evaluate to exact `true` for this binding, so it is unmatured (ADR 0018).
  // This is the wake-candidate consumer's success signal: the first such
  // yield is the one `timerMaturities` consumes.
  | "timer-hold";

/**
 * One candidate binding yielded by the one binding walk (ADR 0027).
 *
 * `rejected` is `null` for a Viable binding — one that passed every pure,
 * structural gate. The consumers own the remaining, possibly-impure tests:
 * the guard (first-success) and the `timer.maturity` scheduling expression
 * (first-wake). Walk-level rejections carry `undefined` `tokens`/`consumed`
 * and are the FINAL yield of an exhausted walk.
 */
interface BindingStep {
  readonly tokens?: TokenBinding;
  readonly consumed?: TokenBinding;
  readonly rejected: BindingRejection | null;
}

interface Topology {
  readonly transitions: readonly Transition[];
  readonly transitionByName: ReadonlyMap<string, Transition>;
  readonly placeByName: ReadonlyMap<string, Net["places"][number]>;
  readonly inputArcs: ReadonlyMap<string, readonly ConsumeArc[]>;
  readonly bindingArcs: ReadonlyMap<string, readonly ConsumeArc[]>;
  readonly produceArcs: ReadonlyMap<string, readonly ProduceArc[]>;
}

/**
 * Internal: a deposit broke the produce contract after the handler ran.
 *
 * A produce template's `cel` failed (an evaluation error or a non-object
 * result, ADR 0023), or a deposited token holds a value outside a declared
 * domain (ADR 0037). Never escapes `fire` — it is caught and routed through
 * the ordinary deposit-contract-violation handling (D3), carrying this
 * error's message as the violation detail.
 */
class DepositError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/**
 * Why `token` breaks one of the net's declared domains, or `null` (ADR 0037).
 * A token of a domain's color must hold one of its values at its path.
 */
export function domainViolation(net: Net, place: string, token: Token): string | null {
  for (const [key, values] of Object.entries(net.domains ?? {})) {
    const [color, ...path] = key.split(".");
    if (color !== token.type) continue;
    let current: unknown = token.data;
    for (const name of path) {
      if (
        typeof current !== "object" ||
        current === null ||
        Array.isArray(current) ||
        !Object.hasOwn(current, name)
      ) {
        return `token ${token.type} into (${place}) has no ${path.join(".")}, which domain ${key} requires`;
      }
      current = (current as Record<string, unknown>)[name];
    }
    if (!values.some((value) => value === current)) {
      return `token ${token.type} into (${place}) holds ${path.join(".")} = ${JSON.stringify(current)}, outside domain ${key}: ${values.map((value) => JSON.stringify(value)).join(", ")}`;
    }
  }
  return null;
}

const SYSTEM_CLOCK: EngineClock = Object.freeze({
  now: () => new Date().toISOString(),
});

const DEFAULT_IDS: EngineIdFactory = Object.freeze({
  firingId: ({netId, transition, attempt}: FiringIdInput) => `${netId}/${transition}/${attempt}`,
  injectionId: ({netId, place, attempt}: InjectionIdInput) => `${netId}/@inject/${place}/${attempt}`,
});

function jsonEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (typeof left !== typeof right || left === null || right === null) return false;
  if (Array.isArray(left)) {
    if (!Array.isArray(right) || left.length !== right.length) return false;
    for (let index = 0; index < left.length; index += 1) {
      if (!jsonEqual(left[index], right[index])) return false;
    }
    return true;
  }
  if (typeof left !== "object" || Array.isArray(right)) return false;
  const leftRecord = left as Readonly<Record<string, unknown>>;
  const rightRecord = right as Readonly<Record<string, unknown>>;
  const leftKeys = Object.keys(leftRecord);
  const rightKeys = Object.keys(rightRecord);
  if (leftKeys.length !== rightKeys.length) return false;
  for (const key of leftKeys) {
    if (!Object.hasOwn(rightRecord, key) || !jsonEqual(leftRecord[key], rightRecord[key])) {
      return false;
    }
  }
  return true;
}

function tokenEqual(left: Token, right: Token): boolean {
  return left.type === right.type && jsonEqual(left.data, right.data);
}

function removeEach(available: Token[], tokens: readonly Token[]): boolean {
  for (const token of tokens) {
    const index = available.findIndex((candidate) => tokenEqual(candidate, token));
    if (index < 0) return false;
    available.splice(index, 1);
  }
  return true;
}

function combinations(tokens: readonly Token[], weight: number): readonly (readonly Token[])[] {
  const result: Token[][] = [];
  const selected: Token[] = [];
  const visit = (start: number): void => {
    if (selected.length === weight) {
      result.push([...selected]);
      return;
    }
    const needed = weight - selected.length;
    for (let index = start; index <= tokens.length - needed; index += 1) {
      selected.push(tokens[index] as Token);
      visit(index + 1);
      selected.pop();
    }
  };
  visit(0);
  return result;
}

function *products<T>(groups: readonly (readonly T[])[], index = 0, selected: T[] = []): Generator<readonly T[]> {
  if (index === groups.length) {
    yield [...selected];
    return;
  }
  for (const value of groups[index] as readonly T[]) {
    selected.push(value);
    yield *products(groups, index + 1, selected);
    selected.pop();
  }
}

/**
 * Name the int and double fields a failed `cel` reads, when it reads both:
 * CEL never mixes them in arithmetic, on any backend. A whole JSON number is
 * an int here, as the default CEL adapter reads it.
 */
function numberMixNote(cel: string, scope: unknown): string | null {
  const ints: string[] = [];
  const doubles: string[] = [];
  for (const [path, value] of numberLeaves(scope, "")) {
    const escaped = path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!new RegExp(`(?<![\\w.])${escaped}(?![\\w\\[])`).test(cel)) continue;
    if (Number.isSafeInteger(value)) ints.push(`${path} is int ${value}`);
    else doubles.push(`${path} is double ${value}`);
  }
  if (ints.length === 0 || doubles.length === 0) return null;
  return `CEL does not mix int and double in arithmetic: ${[...ints, ...doubles].join(", ")}; `
    + "give them one type (a double in the token, or double(...))";
}

function *numberLeaves(value: unknown, path: string): Generator<[string, number]> {
  if (typeof value === "number") {
    yield [path, value];
  } else if (Array.isArray(value)) {
    for (const [index, item] of value.entries()) yield* numberLeaves(item, `${path}[${index}]`);
  } else if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      yield* numberLeaves(item, path === "" ? key : `${path}.${key}`);
    }
  }
}

export class Engine {
  readonly registry: HandlerRegistry;
  readonly policy: string;
  readonly journal: Journal | undefined;
  readonly depositViolation: EngineOptions["depositViolation"];
  readonly maxConsecutiveFailures: number | null;
  readonly #clock: EngineClock;
  readonly #idFactory: EngineIdFactory;
  readonly #defaultCelAdapter: CelAdapter;
  readonly #compiledByAdapter = new Map<CelAdapter, Map<string, unknown>>();
  readonly #topologyByNet = new WeakMap<Net, Topology>();

  constructor(registry: HandlerRegistry, options: EngineOptions) {
    const depositViolation = options.depositViolation ?? (
      options.journal === undefined ? "raise" : "record_then_raise"
    );
    if (!(["raise", "record_then_raise", "record_then_drop"] as const).includes(depositViolation)) {
      throw new EngineConfigurationError(`unsupported deposit violation policy ${JSON.stringify(depositViolation)}`);
    }
    if (depositViolation !== "raise" && options.journal === undefined) {
      throw new EngineConfigurationError(`${JSON.stringify(depositViolation)} requires a journal`);
    }
    const failureBudget = options.maxConsecutiveFailures ?? null;
    if (failureBudget !== null && (!Number.isInteger(failureBudget) || failureBudget < 1)) {
      throw new EngineConfigurationError("maxConsecutiveFailures must be an integer greater than or equal to 1, or null");
    }

    const policy = options.policy ?? DEFAULT_FIRING_POLICY;
    registry.resolveFiringPolicy(policy);
    this.registry = registry;
    this.policy = policy;
    this.journal = options.journal;
    this.depositViolation = depositViolation;
    this.maxConsecutiveFailures = failureBudget;
    this.#clock = options.clock ?? SYSTEM_CLOCK;
    this.#idFactory = options.idFactory ?? DEFAULT_IDS;
    const celAdapter: CelAdapter | undefined = options.celAdapter;
    if (celAdapter === undefined) {
      throw new EngineConfigurationError(
        "celAdapter is required; @velocitron/engine does not bundle a CEL backend",
      );
    }
    this.#defaultCelAdapter = celAdapter;
  }

  #topology(net: Net): Topology {
    const cached = this.#topologyByNet.get(net);
    if (cached !== undefined) return cached;

    const transitionByName = new Map(net.transitions.map((transition) => [transition.name, transition]));
    const placeByName = new Map(net.places.map((place) => [place.name, place]));
    const inputArcs = new Map<string, ConsumeArc[]>();
    const bindingArcs = new Map<string, ConsumeArc[]>();
    const produceArcs = new Map<string, ProduceArc[]>();
    for (const arc of net.arcs) {
      if (arc.consume !== undefined) {
        const transition = arc.to.transition;
        const inputs = inputArcs.get(transition);
        if (inputs === undefined) inputArcs.set(transition, [arc]);
        else inputs.push(arc);
        if (arc.consume.mode === "consume" || arc.consume.mode === "read") {
          const bindings = bindingArcs.get(transition);
          if (bindings === undefined) bindingArcs.set(transition, [arc]);
          else bindings.push(arc);
        }
      } else {
        const transition = arc.from.transition;
        const outputs = produceArcs.get(transition);
        if (outputs === undefined) produceArcs.set(transition, [arc]);
        else outputs.push(arc);
      }
    }
    const topology: Topology = {
      transitions: net.transitions,
      transitionByName,
      placeByName,
      inputArcs,
      bindingArcs,
      produceArcs,
    };
    this.#topologyByNet.set(net, topology);
    return topology;
  }

  #requireTransition(net: Net, name: string): Transition {
    const transition = this.#topology(net).transitionByName.get(name);
    if (transition === undefined) throw new UnknownTransitionError(net.name, name);
    return transition;
  }

  #programs(adapter: CelAdapter): Map<string, unknown> {
    let programs = this.#compiledByAdapter.get(adapter);
    if (programs === undefined) {
      programs = new Map();
      this.#compiledByAdapter.set(adapter, programs);
    }
    return programs;
  }

  #evaluate(source: string, context: ReadonlyJsonObject): unknown {
    const adapter = this.#defaultCelAdapter;
    const programs = this.#programs(adapter);
    let program = programs.get(source);
    if (program === undefined) {
      program = adapter.compile(source);
      programs.set(source, program);
    }
    return adapter.evaluate(program, context);
  }

  #context(net: Net, transition: string, attempt: number): FiringContext {
    return {
      firingId: this.#idFactory.firingId({netId: net.name, transition, attempt}),
      netId: net.name,
      attempt,
      timestamps: {fired_at: this.#clock.now()},
    };
  }

  #predicateMatches(net: Net, arc: ConsumeArc, token: Token, context: FiringContext): boolean {
    if (token.type !== arc.consume.type) return false;
    const predicate = arc.consume.predicate;
    if (predicate === undefined) return true;
    if (predicate.cel !== undefined) {
      try {
        return this.#evaluate(predicate.cel, token.data) === true;
      } catch {
        return false;
      }
    }
    try {
      return this.registry.resolvePredicate(predicate.handler)({token, firingContext: context}) === true;
    } catch {
      return false;
    }
  }

  #inhibitsAllow(net: Net, transition: string, marking: Marking, context: FiringContext): boolean {
    for (const arc of this.#topology(net).inputArcs.get(transition) ?? []) {
      if (arc.consume.mode !== "inhibit" || arc.consume.correlate !== undefined) continue;
      const place = arc.from.place;
      if ((marking[place] ?? []).some((token) => this.#predicateMatches(net, arc, token, context))) {
        return false;
      }
    }
    return true;
  }

  /**
   * The `binding` a transition's CEL sees: bound-token data keyed by place
   * name, or by the transition's `bindingNames` when it declares them
   * (ADR 0032). Two names for one place see the same list.
   */
  #bindingDataOf(net: Net, transition: string, binding: TokenBinding): ReadonlyJsonObject {
    const data = Object.create(null) as Record<string, readonly ReadonlyJsonObject[]>;
    const names = this.#topology(net).transitionByName.get(transition)?.bindingNames;
    if (names === undefined) {
      for (const [place, tokens] of Object.entries(binding)) {
        data[place] = tokens.map((token) => token.data);
      }
      return data;
    }
    for (const [key, place] of Object.entries(names)) {
      const tokens = binding[place];
      if (tokens !== undefined) data[key] = tokens.map((token) => token.data);
    }
    return data;
  }

  /**
   * Every correlated consume/read arc's bound tokens satisfy its `correlate`
   * against the whole candidate binding (ADR 0030). Arcs in declaration
   * order, each arc's tokens in bound order; each token is evaluated over
   * `{token, binding}`, where `binding` is the complete candidate (this arc's
   * own tokens included). Only exact `true` passes; an eval error or a
   * non-boolean fails closed and rejects the binding.
   */
  #bindingCorrelatesHold(
    net: Net,
    transition: string,
    selection: readonly (readonly Token[])[],
    arcs: readonly ConsumeArc[],
    binding: TokenBinding,
  ): boolean {
    let bindingData: ReadonlyJsonObject | undefined;
    for (let index = 0; index < arcs.length; index += 1) {
      const correlate = (arcs[index] as ConsumeArc).consume.correlate;
      if (correlate === undefined) continue;
      bindingData ??= this.#bindingDataOf(net, transition, binding);
      for (const token of selection[index] as readonly Token[]) {
        try {
          const result = this.#evaluate(correlate.cel, {token: token.data, binding: bindingData});
          if (result !== true) return false;
        } catch {
          return false;
        }
      }
    }
    return true;
  }

  #correlatedInhibitsAllow(
    net: Net,
    transition: string,
    marking: Marking,
    binding: TokenBinding,
    context: FiringContext,
  ): boolean {
    let bindingData: ReadonlyJsonObject | undefined;
    for (const arc of this.#topology(net).inputArcs.get(transition) ?? []) {
      const correlate = arc.consume.correlate;
      if (arc.consume.mode !== "inhibit" || correlate === undefined) continue;
      bindingData ??= this.#bindingDataOf(net, transition, binding);
      for (const token of marking[arc.from.place] ?? []) {
        if (!this.#predicateMatches(net, arc, token, context)) continue;
        try {
          const result = this.#evaluate(correlate.cel, {token: token.data, binding: bindingData});
          if (result !== false) return false;
        } catch {
          return false;
        }
      }
    }
    return true;
  }

  #timerHolds(
    net: Net,
    timer: Timer,
    clockData: ReadonlyJsonObject,
    binding: TokenBinding,
  ): boolean {
    const environment = Object.create(null) as Record<string, ReadonlyJsonObject>;
    environment.clock = clockData;
    for (const [variable, place] of Object.entries(timer.bind ?? {})) {
      const token = binding[place]?.[0];
      if (token === undefined) return false;
      environment[variable] = token.data;
    }
    try {
      return this.#evaluate(timer.cel, environment) === true;
    } catch {
      return false;
    }
  }

  #arcCandidates(
    net: Net,
    arc: ConsumeArc,
    marking: Marking,
    context: FiringContext,
  ): readonly (readonly Token[])[] | null {
    const matching = (marking[arc.from.place] ?? []).filter(
      (token) => this.#predicateMatches(net, arc, token, context),
    );
    if (matching.length < arc.consume.weight) return null;
    return combinations(matching, arc.consume.weight);
  }

  #bindingFromSelection(
    selection: readonly (readonly Token[])[],
    arcs: readonly ConsumeArc[],
    consumeOnly: boolean,
  ): TokenBinding {
    const binding = Object.create(null) as Record<string, Token[]>;
    for (let index = 0; index < arcs.length; index += 1) {
      const arc = arcs[index] as ConsumeArc;
      if (consumeOnly && arc.consume.mode !== "consume") continue;
      const place = arc.from.place;
      (binding[place] ??= []).push(...(selection[index] as readonly Token[]));
    }
    return binding;
  }

  #isSubmultiset(binding: TokenBinding, marking: Marking): boolean {
    for (const [place, tokens] of Object.entries(binding)) {
      if (!removeEach([...(marking[place] ?? [])], tokens)) return false;
    }
    return true;
  }

  /**
   * THE one binding enumeration: yield each candidate binding and, with it,
   * why it was rejected.
   *
   * The single internal walk (ADR 0027) under both binding consumers —
   * `timerMaturities` used to re-enumerate the product on its own.
   * Deterministic order per spec/firing-semantics.md (a, D2); the pure gates
   * run in evaluation order:
   *
   * 1. Walk-level gates (no binding exists to annotate): the timer's clock
   *    token, the uncorrelated inhibit zero-test, then each binding arc's
   *    weight-satisfiability. The first failure closes the walk with a final
   *    `per-arc-miss` yield.
   * 2. The cartesian product of per-arc lexicographic `weight`-combinations
   *    (consume- and read-mode arcs in declaration order), each binding
   *    annotated in order: sub-multiset validity (D1), the consume/read
   *    correlate join (ADR 0030), the correlated-inhibit anti-join (ADR
   *    0017), the timer-hold gate (ADR 0018) — a failing
   *    binding is yielded with its rejection and the walk advances.
   * 3. A binding passing every pure gate is yielded viable (`rejected` is
   *    `null`). The consumers attach the remaining tests — the possibly
   *    impure first: the guard (first-success consumer, ADR 0002) and the
   *    `timer.maturity` scheduling expression (first-wake consumer).
   * 4. A walk whose product never produced a viable binding closes with a
   *    final `product-miss` yield.
   *
   * Consumers stop early (lazy): the first-success consumer returns at its
   * first accepted binding, abandoning the walk; the first-wake consumer
   * returns at the first `timer-hold` rejection.
   *
   * References: spec/firing-semantics.md (a, D1, D2, D9); ADR 0002; ADR 0012;
   * ADR 0017; ADR 0018; ADR 0027; ADR 0030.
   */
  *#candidateBindings(
    net: Net,
    transition: string,
    marking: Marking,
    context: FiringContext,
  ): Generator<BindingStep> {
    // Defensive lookup: mirrored from the Python walk — the walk does not own
    // the name-taking boundary (D10 puts the unknown-name raise at the public
    // entry points), so an absent name degrades to a no-timer walk.
    const timer = this.#topology(net).transitionByName.get(transition)?.timer;
    let clockData: ReadonlyJsonObject | undefined;
    if (timer !== undefined) {
      clockData = marking[timer.clock]?.[0]?.data;
      if (clockData === undefined) {
        yield {rejected: "per-arc-miss"};
        return;
      }
    }

    // Uncorrelated inhibit arcs gate enablement BEFORE any binding work.
    if (!this.#inhibitsAllow(net, transition, marking, context)) {
      yield {rejected: "per-arc-miss"};
      return;
    }

    const arcs = this.#topology(net).bindingArcs.get(transition) ?? [];
    const candidates: (readonly (readonly Token[])[])[] = [];
    for (const arc of arcs) {
      const choices = this.#arcCandidates(net, arc, marking, context);
      if (choices === null) {
        yield {rejected: "per-arc-miss"};
        return;
      }
      candidates.push(choices);
    }

    for (const selection of products(candidates)) {
      const binding = this.#bindingFromSelection(selection, arcs, false);
      const consumed = this.#bindingFromSelection(selection, arcs, true);
      if (!this.#isSubmultiset(binding, marking)) {
        yield {tokens: binding, consumed, rejected: "sub-multiset"};
        continue;
      }
      // Correlated consume/read arcs (the join, ADR 0030) test their bound
      // tokens against the whole assembled binding. Pure CEL, so it runs
      // before the correlated inhibits, the timer, and the guard.
      if (!this.#bindingCorrelatesHold(net, transition, selection, arcs, binding)) {
        yield {tokens: binding, consumed, rejected: "correlate-miss"};
        continue;
      }
      if (!this.#correlatedInhibitsAllow(net, transition, marking, binding, context)) {
        yield {tokens: binding, consumed, rejected: "correlated-inhibit"};
        continue;
      }
      if (
        timer !== undefined &&
        clockData !== undefined &&
        !this.#timerHolds(net, timer, clockData, binding)
      ) {
        yield {tokens: binding, consumed, rejected: "timer-hold"};
        continue;
      }
      // Viable: every pure gate passed. The consumer evaluates the remaining,
      // possibly-impure tests (guard; timer.maturity).
      yield {tokens: binding, consumed, rejected: null};
    }
    // No combination satisfied the pure-gate constraints.
    yield {rejected: "product-miss"};
  }

  #selectBinding(
    net: Net,
    transition: Transition,
    marking: Marking,
    context: FiringContext,
  ): Binding | null {
    // FIRST-SUCCESS consumer of `#candidateBindings` (ADR 0027): resolve the
    // guard once — an unresolved guard ref means the transition is not enabled
    // regardless of any binding — then consume the enumeration until the first
    // viable binding the guard accepts.
    let guard: GuardHandler | undefined;
    if (transition.guard !== undefined) {
      try {
        guard = this.registry.resolveGuard(transition.guard);
      } catch (error) {
        if (error instanceof HandlerNotFoundError) return null;
        throw error;
      }
    }
    for (const step of this.#candidateBindings(net, transition.name, marking, context)) {
      if (step.rejected !== null) continue;
      const tokens = step.tokens as TokenBinding;
      if (guard !== undefined) {
        try {
          if (guard({
            transitionId: transition.name,
            inputTokens: tokens,
            firingContext: context,
          }) !== true) {
            continue;
          }
        } catch {
          // An impure guard that raises degrades to not-enabled, symmetric
          // with a predicate handler's runtime error and an unresolved guard
          // ref. Never a runtime crash. (ADR 0002; D9.)
          return null;
        }
      }
      return {tokens, consumed: step.consumed as TokenBinding};
    }
    // Walk-level miss (`per-arc-miss`, `product-miss`) — not enabled.
    return null;
  }

  selectBinding(
    net: Net,
    transition: string,
    marking: Marking,
    options: OptionalAttemptOptions = {},
  ): SelectedBinding {
    const declared = this.#requireTransition(net, transition);
    const context = this.#context(net, transition, options.attempt ?? 0);
    return this.#selectBinding(net, declared, marking, context)?.tokens ?? null;
  }

  enabledTransitions(
    net: Net,
    marking: Marking,
    options: OptionalAttemptOptions = {},
  ): readonly string[] {
    const enabled: string[] = [];
    const attempt = options.attempt ?? 0;
    for (const transition of this.#topology(net).transitions) {
      const context = this.#context(net, transition.name, attempt);
      if (this.#selectBinding(net, transition, marking, context) !== null) {
        enabled.push(transition.name);
      }
    }
    return enabled;
  }

  #record(
    context: FiringContext,
    net: Net,
    transition: string,
    attempt: number,
    status: FiringRecord["status"],
    inputTokens: TokenBinding,
    outputTokens: OutputTokens,
    error: HandlerError | null,
    metadata: ReadonlyJsonObject,
  ): FiringRecord {
    return {
      firingId: context.firingId,
      netId: net.name,
      transition,
      attempt,
      status,
      inputTokens,
      outputTokens,
      error,
      metadata,
      timestamps: context.timestamps,
    };
  }

  #failed(
    context: FiringContext,
    net: Net,
    transition: string,
    attempt: number,
    error: HandlerError | null,
    metadata: ReadonlyJsonObject = {},
  ): FiringRecord {
    const record = this.#record(context, net, transition, attempt, "failed", {}, {}, error, metadata);
    this.journal?.recordFiring(record);
    return record;
  }

  #templates(net: Net, transition: string): readonly ProduceTemplate[] {
    return (this.#topology(net).produceArcs.get(transition) ?? []).map((arc) => arc.produce);
  }

  #hasDepositViolation(outputTokens: OutputTokens, templates: readonly ProduceTemplate[]): boolean {
    for (const [destination, tokens] of Object.entries(outputTokens)) {
      for (const token of tokens) {
        if (!templates.some((template) => (
          template.destination === destination && template.type === token.type
        ))) {
          return true;
        }
      }
    }
    return false;
  }

  #depositedTokens(
    net: Net,
    transition: string,
    outputTokens: OutputTokens,
    templates: readonly ProduceTemplate[],
    bindingTokens: TokenBinding,
  ): OutputTokens {
    const deposited = Object.create(null) as Record<string, Token[]>;
    for (const [destination, tokens] of Object.entries(outputTokens)) {
      if (tokens.length > 0) deposited[destination] = [...tokens];
    }
    // ADR 0023: the environment for computed fallbacks is the same
    // bound-token-data map correlate uses (ADR 0032 keys); built once, lazily.
    let bindingData: ReadonlyJsonObject | undefined;
    for (const template of templates) {
      const handlerTokens = outputTokens[template.destination] ?? [];
      if (handlerTokens.some((token) => token.type === template.type)) continue;
      if (template.data !== undefined) {
        (deposited[template.destination] ??= []).push({type: template.type, data: template.data});
      } else if (template.cel !== undefined) {
        bindingData ??= this.#bindingDataOf(net, transition, bindingTokens);
        let result: unknown;
        try {
          result = this.#evaluate(template.cel, {binding: bindingData});
        } catch (error) {
          const note = numberMixNote(template.cel, {binding: bindingData});
          throw new DepositError(
            `produce cel into ${JSON.stringify(template.destination)} failed to evaluate: ${
              error instanceof Error ? error.message : String(error)
            }${note === null ? "" : `; ${note}`}`,
          );
        }
        if (typeof result !== "object" || result === null || Array.isArray(result)) {
          throw new DepositError(
            `produce cel into ${JSON.stringify(template.destination)} must yield a JSON object, got ${
              result === null ? "null" : Array.isArray(result) ? "array" : typeof result
            }`,
          );
        }
        (deposited[template.destination] ??= []).push({
          type: template.type,
          data: result as ReadonlyJsonObject,
        });
      }
    }
    if (net.domains !== undefined) {
      for (const [destination, tokens] of Object.entries(deposited)) {
        for (const token of tokens) {
          const violation = domainViolation(net, destination, token);
          if (violation !== null) throw new DepositError(violation);
        }
      }
    }
    return deposited;
  }

  #commit(marking: Marking, consumed: TokenBinding, deposited: OutputTokens): Marking {
    const touched = new Set([...Object.keys(consumed), ...Object.keys(deposited)]);
    if (touched.size === 0) return marking;
    const next = Object.assign(
      Object.create(null) as Record<string, readonly Token[]>,
      marking,
    );
    for (const place of touched) {
      const tokens = [...(marking[place] ?? [])];
      removeEach(tokens, consumed[place] ?? []);
      tokens.push(...(deposited[place] ?? []));
      next[place] = tokens;
    }
    return next;
  }

  #depositViolationResult(
    context: FiringContext,
    net: Net,
    transition: string,
    attempt: number,
    metadata: ReadonlyJsonObject,
    marking: Marking,
    detail?: string,
  ): FireResult {
    const error = new DepositViolationError(transition, detail);
    const record = this.#record(
      context,
      net,
      transition,
      attempt,
      "failed",
      {},
      {},
      {type: "DepositViolation", message: error.message},
      metadata,
    );
    if (this.depositViolation === "raise") throw error;
    this.journal?.recordDepositViolation(record);
    if (this.depositViolation === "record_then_raise") throw error;
    return {marking, record};
  }

  /**
   * Fire one transition. A failure returns the marking unchanged with its
   * record; with `strict` it throws `FailedAttemptError` instead (after the
   * journal got the record), its `cause` the exception the handler output
   * carried, as a strict `run` does.
   */
  fire(
    net: Net,
    marking: Marking,
    transition: string,
    options: {readonly attempt: number; readonly strict?: boolean},
  ): FireResult {
    const result = this.#fire(net, marking, transition, options);
    if (options.strict === true && result.record.status !== "completed") {
      const cause = result.cause === undefined ? undefined : {cause: result.cause};
      throw new FailedAttemptError(net.name, result.record, result.marking, cause);
    }
    return {marking: result.marking, record: result.record};
  }

  /** `fire`, plus the exception a failed handler output carries: in-process only, never journaled. */
  #fire(
    net: Net,
    marking: Marking,
    transition: string,
    options: {readonly attempt: number},
  ): FireResult & {readonly cause?: unknown} {
    const declared = this.#requireTransition(net, transition);
    const context = this.#context(net, transition, options.attempt);
    const binding = this.#selectBinding(net, declared, marking, context);
    if (binding === null) {
      return {
        marking,
        record: this.#failed(context, net, transition, options.attempt, {
          type: "NotEnabled",
          message: `transition ${JSON.stringify(transition)} is not enabled`,
        }),
      };
    }
    if (declared.handler === undefined) {
      return {
        marking,
        record: this.#failed(context, net, transition, options.attempt, {
          type: "HandlerNotFound",
          message: `transition ${JSON.stringify(transition)} has no handler`,
        }),
      };
    }

    let handler: TransitionHandler;
    try {
      handler = this.registry.resolveTransition(declared.handler);
    } catch (error) {
      if (!(error instanceof HandlerNotFoundError)) throw error;
      return {
        marking,
        record: this.#failed(context, net, transition, options.attempt, {
          type: "HandlerNotFound",
          message: `handler ${JSON.stringify(declared.handler)} is not registered`,
        }),
      };
    }

    const output: TransitionHandlerOutput = handler({
      transitionId: transition,
      inputTokens: binding.tokens,
      firingContext: context,
    });
    const metadata = output.metadata ?? {};
    if (output.status === "failed") {
      return {
        marking,
        record: this.#failed(context, net, transition, options.attempt, output.error, metadata),
        cause: output.exception,
      };
    }

    const outputTokens = output.outputTokens ?? {};
    const templates = this.#templates(net, transition);
    if (this.#hasDepositViolation(outputTokens, templates)) {
      return this.#depositViolationResult(
        context,
        net,
        transition,
        options.attempt,
        metadata,
        marking,
      );
    }
    let deposited: OutputTokens;
    try {
      deposited = this.#depositedTokens(net, transition, outputTokens, templates, binding.tokens);
    } catch (error) {
      if (!(error instanceof DepositError)) throw error;
      return this.#depositViolationResult(
        context,
        net,
        transition,
        options.attempt,
        metadata,
        marking,
        error.message,
      );
    }
    const next = this.#commit(marking, binding.consumed, deposited);
    const record = this.#record(
      context,
      net,
      transition,
      options.attempt,
      "completed",
      binding.tokens,
      deposited,
      null,
      metadata,
    );
    this.journal?.recordFiring(record);
    return {marking: next, record};
  }

  validate(net: Net): void {
    for (const transition of net.transitions) {
      if (transition.handler !== undefined) this.registry.resolveTransition(transition.handler);
      if (transition.guard !== undefined) this.registry.resolveGuard(transition.guard);
    }
    for (const arc of net.arcs) {
      if (arc.consume?.predicate?.handler !== undefined) {
        this.registry.resolvePredicate(arc.consume.predicate.handler);
      }
    }
  }

  #validateInjection(net: Net, place: string, token: Token): void {
    const declared = this.#topology(net).placeByName.get(place);
    if (declared === undefined) {
      throw new TokenInjectionError(net.name, place, `net ${JSON.stringify(net.name)} has no place named ${JSON.stringify(place)}`);
    }
    if (!declared.accepts.includes(token.type)) {
      throw new TokenInjectionError(
        net.name,
        place,
        `place ${JSON.stringify(place)} does not accept token type ${JSON.stringify(token.type)}`,
      );
    }
    const violation = domainViolation(net, place, token);
    if (violation !== null) throw new TokenInjectionError(net.name, place, violation);
  }

  inject(
    net: Net,
    marking: Marking,
    place: string,
    token: Token,
    options: InjectOptions,
  ): InjectionResult {
    this.#validateInjection(net, place, token);
    const existing = marking[place] ?? [];
    const replace = options.replace ?? false;
    const next = Object.assign(
      Object.create(null) as Record<string, readonly Token[]>,
      marking,
    );
    next[place] = replace ? [token] : [...existing, token];
    const record: InjectionRecord = {
      injectionId: this.#idFactory.injectionId({netId: net.name, place, attempt: options.attempt}),
      netId: net.name,
      place,
      attempt: options.attempt,
      kind: replace ? "update" : "inject",
      tokens: [token],
      replaced: replace ? existing : [],
      timestamps: {fired_at: this.#clock.now()},
    };
    this.journal?.recordInjection(record);
    return {marking: next, record};
  }

  injectMany(
    net: Net,
    marking: Marking,
    placements: readonly TokenPlacement[],
    options: {readonly attempt: number},
  ): BatchInjectionResult {
    for (const placement of placements) {
      this.#validateInjection(net, placement.place, placement.token);
    }
    const additions = new Map<string, Token[]>();
    for (const placement of placements) {
      const tokens = additions.get(placement.place);
      if (tokens === undefined) additions.set(placement.place, [placement.token]);
      else tokens.push(placement.token);
    }
    const next: Record<string, readonly Token[]> = placements.length === 0
      ? marking
      : Object.assign(
          Object.create(null) as Record<string, readonly Token[]>,
          marking,
        );
    for (const [place, tokens] of additions) {
      next[place] = [...(marking[place] ?? []), ...tokens];
    }
    const records: InjectionRecord[] = [];
    for (const placement of placements) {
      const record: InjectionRecord = {
        injectionId: this.#idFactory.injectionId({
          netId: net.name,
          place: placement.place,
          attempt: options.attempt,
        }),
        netId: net.name,
        place: placement.place,
        attempt: options.attempt,
        kind: "inject",
        tokens: [placement.token],
        replaced: [],
        timestamps: {fired_at: this.#clock.now()},
      };
      this.journal?.recordInjection(record);
      records.push(record);
    }
    return {marking: next, records};
  }

  timerMaturities(net: Net, marking: Marking): readonly TimerMaturity[] {
    const maturities: TimerMaturity[] = [];
    for (const transition of net.transitions) {
      const timer = transition.timer;
      if (timer === undefined || timer.maturity === undefined) continue;
      const clockData = marking[timer.clock]?.[0]?.data;
      if (clockData === undefined) continue;
      const context = this.#context(net, transition.name, 0);
      // FIRST-WAKE consumer of `#candidateBindings` (ADR 0027): consume the
      // enumeration until its first `timer-hold` rejection — the first
      // structurally valid binding whose `timer.cel` does not hold (the
      // timer-predicate failure). That binding's `timer.maturity` expression
      // declares the next future clock timestamp worth injecting; the walk
      // stops there, lazily.
      for (const step of this.#candidateBindings(net, transition.name, marking, context)) {
        if (step.rejected !== "timer-hold") continue;
        const at = this.#timerMaturity(timer, clockData, step.tokens as TokenBinding);
        if (at !== undefined) {
          maturities.push({transition: transition.name, clock: timer.clock, at});
        }
        break; // first timer-predicate failure ends this transition's walk
      }
    }
    return maturities;
  }

  #timerMaturity(
    timer: Timer,
    clockData: ReadonlyJsonObject,
    binding: TokenBinding,
  ): number | undefined {
    // `timer.cel` remains the only timer enablement authority. This companion
    // expression only identifies the next future clock timestamp worth
    // injecting for a structurally viable candidate binding.
    const environment = Object.create(null) as Record<string, ReadonlyJsonObject>;
    environment.clock = clockData;
    for (const [variable, place] of Object.entries(timer.bind ?? {})) {
      const token = binding[place]?.[0];
      if (token === undefined) return undefined;
      environment[variable] = token.data;
    }
    try {
      const raw = this.#evaluate(timer.maturity as string, environment);
      const current = Number(clockData.now);
      const at = typeof raw === "number" ? raw : Number.NaN;
      // A maturity at or behind the clock is not a future wake candidate, so
      // it is excluded silently — like a ready timer (whose cel already holds)
      // is skipped upstream. Reaching here means the cel did NOT hold.
      if (Number.isFinite(current) && Number.isFinite(at) && at > current) {
        return at;
      }
    } catch {
      // An unschedulable maturity is advisory and never changes enablement.
    }
    return undefined;
  }

  tick(
    net: Net,
    marking: Marking,
    place: string,
    token: Token,
    options: TickOptions = {},
  ): Marking {
    const injected = this.inject(net, marking, place, token, {
      attempt: options.attempt ?? 0,
      replace: true,
    });
    return this.run(net, injected.marking, {maxSteps: options.maxSteps});
  }

  run(net: Net, marking: Marking, options: RunOptions = {}): Marking {
    const maxSteps = options.maxSteps ?? 1_000;
    const priorities = new Map(net.transitions.map((transition) => [
      transition.name,
      transition.priority ?? 0,
    ]));
    const ledger = this.selectionLedger();
    let current = marking;
    for (let step = 0; step < maxSteps; step += 1) {
      const enabled = this.enabledTransitions(net, current, {attempt: step})
        .filter((name) => ledger.admissible(name));
      if (enabled.length === 0) break;
      if (options.strict === true) this.#refuseConflict(net, enabled, priorities, current);
      const priorityInput = Object.create(null) as Record<string, number>;
      for (const name of enabled) priorityInput[name] = priorities.get(name) ?? 0;
      const choice = this.registry.resolveFiringPolicy(this.policy)({
        marking: current,
        enabledTransitions: enabled,
        priorities: priorityInput,
        consecutiveFailures: ledger.counts(enabled),
      });
      if (choice === null) break;
      const result = this.#fire(net, current, choice, {attempt: step});
      current = result.marking;
      ledger.record(choice, result.record.status);
      if (options.strict === true && result.record.status !== "completed") {
        const cause = result.cause === undefined ? undefined : {cause: result.cause};
        throw new FailedAttemptError(net.name, result.record, current, cause);
      }
    }
    return current;
  }

  /** A strict run's conflict check: under the priority policy, only the top priority contends. */
  #refuseConflict(
    net: Net,
    enabled: readonly string[],
    priorities: ReadonlyMap<string, number>,
    marking: Marking,
  ): void {
    let contenders = enabled;
    if (this.policy === PRIORITY_FIRING_POLICY) {
      const top = Math.max(...enabled.map((name) => priorities.get(name) ?? 0));
      contenders = enabled.filter((name) => (priorities.get(name) ?? 0) === top);
    }
    if (contenders.length > 1) throw new ConflictError(net.name, contenders, marking);
  }

  /**
   * A fresh failure ledger bound to this engine's budget.
   *
   * `run` makes one per call. The async runtime keeps one for the admission
   * loop so exhaustion and reset stay the engine's rule.
   */
  selectionLedger(): SelectionLedger {
    return new SelectionLedger(this.maxConsecutiveFailures);
  }

  /**
   * Places this transition consumes, reads, or writes, in arc declaration order.
   *
   * The async runtime classifies footprints from this table instead of
   * re-walking arcs. Inhibit arcs are omitted.
   */
  transitionFootprint(net: Net, transition: string): TransitionFootprint {
    const topology = this.#topology(net);
    const consume = new Set<string>();
    const read = new Set<string>();
    const write = new Set<string>();
    for (const arc of topology.inputArcs.get(transition) ?? []) {
      if (arc.consume.mode === "consume") consume.add(arc.from.place);
      else if (arc.consume.mode === "read") read.add(arc.from.place);
    }
    for (const arc of topology.produceArcs.get(transition) ?? []) {
      write.add(arc.produce.destination);
    }
    return {consume, read, write};
  }

  /**
   * Reserve one enabled firing without calling its transition handler.
   *
   * `null` means the transition was not enabled. The reservation owns the
   * consume-mode tokens. No firing record is written until `settle`.
   */
  reserve(
    net: Net,
    marking: Marking,
    transition: string,
    options: {readonly attempt: number},
  ): FiringReservation | null {
    const declared = this.#requireTransition(net, transition);
    const context = this.#context(net, transition, options.attempt);
    const binding = this.#selectBinding(net, declared, marking, context);
    if (binding === null) return null;
    return {
      net,
      originalMarking: marking,
      reservedMarking: this.#commit(marking, binding.consumed, {}),
      transition,
      attempt: options.attempt,
      context,
      inputTokens: binding.tokens,
      consumedTokens: binding.consumed,
    };
  }

  /**
   * Commit or roll back a firing reserved by `reserve`.
   *
   * A failed output restores the consumed tokens. A deposit-contract violation
   * follows the engine's configured mode. `fire` is unchanged: it still calls
   * the synchronous handler itself.
   */
  settle(
    marking: Marking,
    reservation: FiringReservation,
    output: TransitionHandlerOutput,
  ): FireResult {
    const metadata = output.metadata ?? {};
    if (output.status === "failed") {
      const record = this.#record(
        reservation.context,
        reservation.net,
        reservation.transition,
        reservation.attempt,
        "failed",
        reservation.inputTokens,
        {},
        output.error,
        metadata,
      );
      this.journal?.recordFiring(record);
      return {marking: this.#restoreReservation(marking, reservation), record};
    }

    const templates = this.#templates(reservation.net, reservation.transition);
    const outputTokens = output.outputTokens ?? {};
    if (this.#hasDepositViolation(outputTokens, templates)) {
      return this.#settleViolation(marking, reservation, metadata);
    }
    let deposited: OutputTokens;
    try {
      deposited = this.#depositedTokens(
        reservation.net,
        reservation.transition,
        outputTokens,
        templates,
        reservation.inputTokens,
      );
    } catch (error) {
      if (!(error instanceof DepositError)) throw error;
      return this.#settleViolation(marking, reservation, metadata, error.message);
    }
    const committed = this.#commit(marking, {}, deposited);
    const record = this.#record(
      reservation.context,
      reservation.net,
      reservation.transition,
      reservation.attempt,
      "completed",
      reservation.inputTokens,
      deposited,
      null,
      metadata,
    );
    this.journal?.recordFiring(record);
    return {marking: committed, record};
  }

  #restoreReservation(marking: Marking, reservation: FiringReservation): Marking {
    const places = Object.keys(reservation.consumedTokens);
    if (places.length === 0) return marking;
    const next = Object.assign(Object.create(null) as Record<string, readonly Token[]>, marking);
    for (const place of places) {
      next[place] = reservation.originalMarking[place] ?? [];
    }
    return next;
  }

  #settleViolation(
    marking: Marking,
    reservation: FiringReservation,
    metadata: ReadonlyJsonObject,
    detail?: string,
  ): FireResult {
    const message = detail ?? (
      `transition ${JSON.stringify(reservation.transition)} produced tokens that violate its produce contract`
    );
    if (this.depositViolation === "raise") throw new DepositViolationError(reservation.transition, message);
    const record = this.#record(
      reservation.context,
      reservation.net,
      reservation.transition,
      reservation.attempt,
      "failed",
      reservation.inputTokens,
      {},
      {type: "DepositViolation", message},
      metadata,
    );
    this.journal?.recordDepositViolation(record);
    if (this.depositViolation === "record_then_raise") {
      throw new DepositViolationError(reservation.transition, message);
    }
    return {marking: this.#restoreReservation(marking, reservation), record};
  }
}
