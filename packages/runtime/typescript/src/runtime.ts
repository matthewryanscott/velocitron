/**
 * Long-lived asynchronous execution for one net.
 *
 * `Runtime` owns the marking reference. It reserves consume-mode inputs,
 * runs the handler, and settles that reservation. The injected
 * `HandlerRegistry` resolves guards, predicates, and the firing policy.
 * This module does not call `Engine.fire` and does not import
 * `@velocitron/core`.
 */

import {createDefaultCelAdapter, type CelAdapter} from "@velocitron/cel";
import {
  Engine,
  HandlerRegistry,
  type FiringContext,
  type FiringReservation,
  type HandlerError,
  type Journal,
  type Marking,
  type Net,
  type Token,
  type Transition,
  type TransitionFootprint,
  type TransitionHandlerInput,
  type TransitionHandlerOutput,
} from "@velocitron/engine";

export interface Clock {
  now(): number;
  sleepUntil(when: number): Promise<void>;
}

class MonotonicClock implements Clock {
  now(): number {
    return performance.now() / 1000;
  }

  async sleepUntil(when: number): Promise<void> {
    const delaySeconds = Math.max(0, when - this.now());
    await new Promise((resolve) => setTimeout(resolve, delaySeconds * 1000));
  }
}

export type SourcePolicy = "lossless" | "batch" | "coalesce";

export class Lane {
  readonly capacity: number;

  constructor(capacity: number) {
    if (capacity < 1) throw new Error(`lane capacity must be >= 1, got ${capacity}`);
    this.capacity = capacity;
  }
}

export type ScopeResolver = (input: TransitionHandlerInput) => string | null;

export type AsyncTransitionHandler = (
  input: TransitionHandlerInput,
  ctx: RuntimeContext,
) => Promise<TransitionHandlerOutput> | TransitionHandlerOutput;

export interface HandlerSpec {
  readonly handler: AsyncTransitionHandler;
  readonly lane: string;
  readonly scope?: ScopeResolver;
  readonly blocking?: boolean;
}

export class TokenArrival {
  constructor(
    readonly place: string,
    readonly token: Token,
    readonly replace = false,
    readonly key: unknown = null,
  ) {}
}

export class TokenBatch {
  readonly placements: readonly TokenArrival[];

  constructor(placements: readonly TokenArrival[]) {
    if (placements.length === 0) {
      throw new Error("a token batch must contain at least one placement");
    }
    if (placements.some((placement) => placement.replace)) {
      throw new Error("token batches are append-only; use TokenArrival(replace=true)");
    }
    this.placements = placements;
  }
}

export type SourceItem = TokenArrival | TokenBatch;
export type SourceFactory = () => AsyncIterable<SourceItem>;

export class TokenSource {
  constructor(
    readonly name: string,
    readonly open: SourceFactory,
    readonly policy: SourcePolicy,
    readonly capacity: number,
  ) {
    if (capacity < 1) throw new Error(`source ${JSON.stringify(name)} capacity must be >= 1`);
    if (policy === "coalesce" && capacity !== 1) {
      throw new Error("coalesce sources require capacity=1");
    }
  }
}

export interface SourceHealth {
  state: "starting" | "running" | "backing_off" | "stopped";
  restarts: number;
  coalesced: number;
  lastError: string | null;
}

export interface Cancellation {
  readonly scope: string;
  readonly cancelled: number;
}

export interface RuntimeRecord {
  readonly event: "source_failed" | "suppressed";
  readonly netId: string;
  readonly firingId: string | null;
  readonly source: string | null;
  readonly detail: string;
}

export interface TraceRecord {
  readonly event: string;
  readonly netId: string;
  readonly firingId: string;
  readonly transition: string;
  readonly handler: string | null;
  readonly method: string | null;
  readonly at: string;
  readonly status: "completed" | "failed" | null;
  readonly result: boolean | null;
  readonly error: HandlerError | null;
}

export type RuntimeJournal = Journal & {
  recordRuntime?: (record: RuntimeRecord) => void;
  recordTrace?: (record: TraceRecord) => void;
};

interface ActiveFiring {
  readonly reservation: FiringReservation;
  readonly spec: HandlerSpec;
  readonly footprint: TransitionFootprint;
  readonly scope: string | null;
  readonly controller: AbortController;
}

interface ScopeCanceller {
  cancelScope(scope: string, current: AbortController): Cancellation;
}

class Gate {
  #set = false;
  readonly #waiters: Array<() => void> = [];

  set(): void {
    this.#set = true;
    const waiters = this.#waiters.splice(0);
    for (const waiter of waiters) waiter();
  }

  clear(): void {
    this.#set = false;
  }

  wait(): Promise<void> {
    if (this.#set) return Promise.resolve();
    return new Promise((resolve) => this.#waiters.push(resolve));
  }
}

class AsyncQueue<T> {
  readonly #items: T[] = [];
  readonly #takers: Array<(item: T) => void> = [];
  readonly #space: Array<() => void> = [];

  constructor(readonly capacity: number) {}

  get empty(): boolean {
    return this.#items.length === 0;
  }

  get full(): boolean {
    return this.#items.length >= this.capacity;
  }

  putNowait(item: T): void {
    const taker = this.#takers.shift();
    if (taker !== undefined) {
      taker(item);
      return;
    }
    if (this.full) throw new Error("queue is full");
    this.#items.push(item);
  }

  getNowait(): T {
    const item = this.#items.shift();
    if (item === undefined) throw new Error("queue is empty");
    const resume = this.#space.shift();
    if (resume !== undefined) resume();
    return item;
  }

  put(item: T): Promise<void> {
    if (!this.full) {
      this.putNowait(item);
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      this.#space.push(() => {
        this.putNowait(item);
        resolve();
      });
    });
  }

  get(signal: AbortSignal): Promise<T> {
    if (this.#items.length > 0) return Promise.resolve(this.getNowait());
    return new Promise((resolve, reject) => {
      const taker = (item: T) => {
        signal.removeEventListener("abort", onAbort);
        resolve(item);
      };
      const onAbort = () => {
        const index = this.#takers.indexOf(taker);
        if (index >= 0) this.#takers.splice(index, 1);
        reject(abortError());
      };
      this.#takers.push(taker);
      if (signal.aborted) onAbort();
      else signal.addEventListener("abort", onAbort, {once: true});
    });
  }
}

class Mailbox {
  readonly queue: AsyncQueue<SourceItem>;

  constructor(
    readonly source: TokenSource,
    readonly health: SourceHealth,
  ) {
    this.queue = new AsyncQueue(source.capacity);
  }

  async put(item: SourceItem): Promise<void> {
    if (this.source.policy === "batch" && !(item instanceof TokenBatch)) {
      throw new TypeError(`batch source ${JSON.stringify(this.source.name)} emitted a non-batch item`);
    }
    if (this.source.policy !== "coalesce") {
      await this.queue.put(item);
      return;
    }
    if (!(item instanceof TokenArrival) || item.key === null) {
      throw new TypeError(
        `coalesce source ${JSON.stringify(this.source.name)} must emit TokenArrival with a key`,
      );
    }
    if (!this.queue.full) {
      this.queue.putNowait(item);
      return;
    }
    const previous = this.queue.getNowait();
    if (previous instanceof TokenArrival && previous.key === item.key) {
      this.queue.putNowait(item);
      this.health.coalesced += 1;
      return;
    }
    this.queue.putNowait(previous);
    await this.queue.put(item);
  }
}

function abortError(): Error {
  const error = new Error("This operation was aborted");
  error.name = "AbortError";
  return error;
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function raceAbort<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(abortError());
    signal.addEventListener("abort", onAbort, {once: true});
    promise.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

function isPromise(value: unknown): value is Promise<TransitionHandlerOutput> {
  return typeof value === "object" && value !== null && "then" in value
    && typeof (value as {then?: unknown}).then === "function";
}

function overlaps(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  for (const item of left) {
    if (right.has(item)) return true;
  }
  return false;
}

function footprintsConflict(left: TransitionFootprint, right: TransitionFootprint): boolean {
  return overlaps(left.consume, right.consume)
    || overlaps(left.consume, right.write)
    || overlaps(left.write, right.consume)
    || overlaps(left.write, right.read)
    || overlaps(left.write, right.write)
    || overlaps(right.write, left.read);
}

function writeFootprint(place: string): TransitionFootprint {
  return {consume: new Set(), read: new Set(), write: new Set([place])};
}

function failedOutput(
  errorType: string,
  message: string,
  metadata: Readonly<Record<string, string | null>>,
): TransitionHandlerOutput {
  return {
    status: "failed",
    outputTokens: {},
    error: {type: errorType, message},
    metadata: {runtime: metadata},
  };
}

export class RuntimeContext {
  constructor(
    readonly scope: string | null,
    private readonly runtime: ScopeCanceller,
    private readonly controller: AbortController,
  ) {}

  /** Cancel every other active firing in `scope` and report the count. */
  cancel(scope: string): Cancellation {
    return this.runtime.cancelScope(scope, this.controller);
  }
}

export interface RuntimeOptions {
  readonly net: Net;
  readonly handlers: Readonly<Record<string, HandlerSpec>>;
  readonly lanes: Readonly<Record<string, Lane | number>>;
  readonly sources?: readonly TokenSource[];
  readonly clock?: Clock;
  readonly journal?: RuntimeJournal;
  readonly registry?: HandlerRegistry;
  readonly marking?: Marking;
  readonly policy?: string;
  readonly maxConsecutiveFailures?: number | null;
  readonly celAdapter?: CelAdapter;
  readonly sourceBackoff?: number;
}

/**
 * Own a net's long-lived asynchronous execution.
 *
 * `handlers` is keyed by transition handler reference. Every transition
 * needs a `HandlerSpec`. `lanes` bounds how many of those handlers run at
 * once. The registry is not where async handlers are registered, and this
 * class does not call `Engine.fire`.
 */
export class Runtime implements ScopeCanceller {
  readonly net: Net;
  readonly handlers: Readonly<Record<string, HandlerSpec>>;
  readonly lanes: ReadonlyMap<string, Lane>;
  readonly sources: readonly TokenSource[];
  readonly clock: Clock;
  readonly journal: RuntimeJournal | undefined;
  readonly registry: HandlerRegistry;
  readonly engine: Engine;
  readonly policy: string;
  readonly sourceBackoff: number;
  readonly sourceHealth: Readonly<Record<string, SourceHealth>>;
  marking: Marking;

  readonly #stop = new AbortController();
  readonly #changed = new Gate();
  readonly #timerChanged = new Gate();
  readonly #tasks = new Set<Promise<void>>();
  readonly #active = new Set<ActiveFiring>();
  readonly #laneInUse = new Map<string, number>();
  readonly #blocked = new Set<string>();
  readonly #mailboxes = new Map<string, Mailbox>();
  readonly #ledger: ReturnType<Engine["selectionLedger"]>;
  #started = false;
  #stopping = false;
  #attempt = 0;
  #injectionAttempt = 0;

  constructor(options: RuntimeOptions) {
    const sourceBackoff = options.sourceBackoff ?? 0.1;
    if (sourceBackoff <= 0) throw new Error("sourceBackoff must be > 0");
    this.net = options.net;
    this.handlers = options.handlers;
    this.lanes = new Map(Object.entries(options.lanes).map(([name, lane]) => [
      name,
      lane instanceof Lane ? lane : new Lane(lane),
    ]));
    this.sources = options.sources ?? [];
    this.clock = options.clock ?? new MonotonicClock();
    this.journal = options.journal;
    this.registry = options.registry ?? new HandlerRegistry();
    this.policy = options.policy ?? "first-found";
    this.sourceBackoff = sourceBackoff;
    const celAdapter = options.celAdapter ?? createDefaultCelAdapter();
    this.engine = new Engine(this.registry, {
      policy: this.policy,
      journal: this.journal,
      depositViolation: this.journal === undefined ? "raise" : "record_then_drop",
      celAdapter,
      maxConsecutiveFailures: options.maxConsecutiveFailures,
    });
    this.marking = options.marking ?? options.net.initialMarking ?? {};
    this.#ledger = this.engine.selectionLedger();
    this.sourceHealth = Object.fromEntries(this.sources.map((source) => [
      source.name,
      {state: "starting", restarts: 0, coalesced: 0, lastError: null} satisfies SourceHealth,
    ]));

    const handlerless = this.net.transitions
      .filter((transition) => transition.handler === undefined)
      .map((transition) => transition.name);
    if (handlerless.length > 0) {
      throw new Error(
        `Runtime requires handlers; transitions without handlers: ${JSON.stringify(handlerless)}`,
      );
    }
    const transitionRefs = new Set(
      this.net.transitions.map((transition) => transition.handler).filter((handler) => handler !== undefined),
    );
    const handlerRefs = new Set(Object.keys(this.handlers));
    const missing = [...transitionRefs].filter((name) => !handlerRefs.has(name)).sort();
    const extra = [...handlerRefs].filter((name) => !transitionRefs.has(name)).sort();
    if (missing.length > 0 || extra.length > 0) {
      throw new Error(
        "handler specs must match the net's handler refs exactly; "
        + `missing=${JSON.stringify(missing)}, extra=${JSON.stringify(extra)}`,
      );
    }
    const unknownLanes = [...new Set(
      Object.values(this.handlers).map((spec) => spec.lane).filter((lane) => !this.lanes.has(lane)),
    )].sort();
    if (unknownLanes.length > 0) {
      throw new Error(`handler specs reference unknown lanes: ${JSON.stringify(unknownLanes)}`);
    }
    const names = this.sources.map((source) => source.name);
    if (new Set(names).size !== names.length) throw new Error("token-source names must be unique");
    const missingMaturity = this.net.transitions
      .filter((transition) => transition.timer !== undefined && transition.timer.maturity === undefined)
      .map((transition) => transition.name)
      .sort();
    if (missingMaturity.length > 0) {
      throw new Error(
        `Runtime requires timer.maturity for every native timer: ${JSON.stringify(missingMaturity)}`,
      );
    }
    for (const name of this.lanes.keys()) this.#laneInUse.set(name, 0);
  }

  async start(): Promise<void> {
    if (this.#started) throw new Error("Runtime is already started");
    this.#started = true;
    this.#bootstrapTimerClocks();
    this.#admit();
    for (const source of this.sources) {
      const mailbox = new Mailbox(source, this.sourceHealth[source.name]);
      this.#mailboxes.set(source.name, mailbox);
      this.#track(this.#superviseSource(source, mailbox));
      this.#track(this.#dispatchSource(mailbox));
    }
    if (this.#timerClockPlaces().length > 0) this.#track(this.#runTimers());
  }

  /** Advance until `stop`, or until the caller stops waiting on this promise. */
  async advance(): Promise<void> {
    await this.start();
    try {
      await new Promise<void>((resolve) => {
        if (this.#stopping) resolve();
        else this.#stop.signal.addEventListener("abort", () => resolve(), {once: true});
      });
    } finally {
      await this.stop();
    }
  }

  async stop(): Promise<void> {
    if (this.#stopping) return;
    this.#stopping = true;
    this.#stop.abort();
    for (const active of this.#active) active.controller.abort();
    await Promise.allSettled(this.#tasks);
    for (const health of Object.values(this.sourceHealth)) health.state = "stopped";
    this.#signal();
  }

  async inject(arrival: TokenArrival): Promise<void> {
    this.#requireStarted();
    await this.#applyArrival(arrival);
  }

  async injectBatch(batch: TokenBatch): Promise<void> {
    this.#requireStarted();
    await this.#applyArrival(batch);
  }

  async waitIdle(): Promise<void> {
    this.#requireStarted();
    await new Promise((resolve) => setTimeout(resolve, 0));
    while (this.#active.size > 0 || this.#mailboxesBusy()) {
      this.#changed.clear();
      if (this.#active.size === 0 && !this.#mailboxesBusy()) return;
      await this.#changed.wait();
    }
  }

  cancelScope(scope: string, current: AbortController): Cancellation {
    const targets = [...this.#active].filter((active) => (
      active.scope === scope && active.controller !== current && !active.controller.signal.aborted
    ));
    for (const active of targets) active.controller.abort();
    this.#signal();
    return {scope, cancelled: targets.length};
  }

  #requireStarted(): void {
    if (!this.#started || this.#stopping) throw new Error("Runtime is not running");
  }

  #track(task: Promise<void>): void {
    this.#tasks.add(task);
    void task.finally(() => this.#tasks.delete(task));
  }

  #signal(): void {
    this.#changed.set();
    this.#timerChanged.set();
  }

  #mailboxesBusy(): boolean {
    for (const mailbox of this.#mailboxes.values()) {
      if (!mailbox.queue.empty) return true;
    }
    return false;
  }

  #timerClockPlaces(): readonly string[] {
    return [...new Set(
      this.net.transitions.flatMap((transition) => (
        transition.timer === undefined ? [] : [transition.timer.clock]
      )),
    )].sort();
  }

  #bootstrapTimerClocks(): void {
    const places = new Map(this.net.places.map((place) => [place.name, place]));
    const now = this.clock.now();
    for (const clockPlace of this.#timerClockPlaces()) {
      if ((this.marking[clockPlace] ?? []).length > 0) continue;
      const place = places.get(clockPlace);
      if (place === undefined || place.accepts.length === 0) {
        throw new Error(`timer clock place ${JSON.stringify(clockPlace)} accepts no token type`);
      }
      this.#injectNow(new TokenArrival(clockPlace, {type: place.accepts[0], data: {now}}));
    }
  }

  async #runTimers(): Promise<void> {
    while (!this.#stopping) {
      this.#timerChanged.clear();
      const maturities = this.engine.timerMaturities(this.net, this.marking);
      const now = this.clock.now();
      const duePlaces = [...new Set(
        maturities.filter((item) => item.at <= now).map((item) => item.clock),
      )].sort();
      if (duePlaces.length > 0) {
        await this.#advanceTimerClocks(duePlaces, now);
        continue;
      }
      const future = maturities.map((item) => item.at);
      const nextWake = future.length === 0 ? null : Math.min(...future);
      if (this.#stopping) return;
      await this.#waitForTimerChange(nextWake);
    }
  }

  async #advanceTimerClocks(places: readonly string[], now: number): Promise<void> {
    while (places.some((place) => this.#writeConflicts(place))) {
      this.#changed.clear();
      await raceAbort(this.#changed.wait(), this.#stop.signal);
    }
    const changed = new Set<string>();
    for (const place of places) {
      const existing = this.marking[place] ?? [];
      if (existing.length === 0) continue;
      const token = existing[0];
      this.#injectNow(new TokenArrival(
        place,
        {type: token.type, data: {...token.data, now}},
        true,
      ));
      changed.add(place);
    }
    if (changed.size > 0) {
      this.#unblockFor(changed);
      this.#admit();
      this.#signal();
    }
  }

  async #waitForTimerChange(when: number | null): Promise<void> {
    if (when === null) {
      await raceAbort(this.#timerChanged.wait(), this.#stop.signal);
      return;
    }
    const sleeper = this.clock.sleepUntil(when);
    const changed = this.#timerChanged.wait();
    try {
      await raceAbort(Promise.race([sleeper, changed]), this.#stop.signal);
    } catch (error) {
      if (!isAbort(error)) throw error;
    }
  }

  async #superviseSource(source: TokenSource, mailbox: Mailbox): Promise<void> {
    const health = this.sourceHealth[source.name];
    while (!this.#stopping) {
      try {
        health.state = "running";
        for await (const item of source.open()) {
          if (this.#stopping) return;
          await raceAbort(mailbox.put(item), this.#stop.signal);
          this.#signal();
        }
        return;
      } catch (error) {
        if (isAbort(error) || this.#stopping) return;
        health.state = "backing_off";
        health.restarts += 1;
        health.lastError = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
        this.#recordRuntime("source_failed", {source: source.name, detail: health.lastError});
        try {
          await raceAbort(delay(this.sourceBackoff, this.#stop.signal), this.#stop.signal);
        } catch (sleepError) {
          if (isAbort(sleepError) || this.#stopping) return;
          throw sleepError;
        }
      }
    }
  }

  async #dispatchSource(mailbox: Mailbox): Promise<void> {
    while (!this.#stopping) {
      let item: SourceItem;
      try {
        item = await mailbox.queue.get(this.#stop.signal);
      } catch (error) {
        if (isAbort(error) || this.#stopping) return;
        throw error;
      }
      try {
        await this.#applyArrival(item);
      } finally {
        this.#signal();
      }
    }
  }

  async #applyArrival(item: SourceItem): Promise<void> {
    const places = item instanceof TokenArrival
      ? [item.place]
      : item.placements.map((arrival) => arrival.place);
    while (places.some((place) => this.#writeConflicts(place))) {
      this.#changed.clear();
      await raceAbort(this.#changed.wait(), this.#stop.signal);
    }
    if (item instanceof TokenArrival) this.#injectNow(item);
    else {
      const injected = this.engine.injectMany(
        this.net,
        this.marking,
        item.placements.map((arrival) => ({place: arrival.place, token: arrival.token})),
        {attempt: this.#nextInjectionAttempt()},
      );
      this.marking = injected.marking;
    }
    this.#unblockFor(new Set(places));
    this.#admit();
    this.#signal();
  }

  #unblockFor(changedPlaces: ReadonlySet<string>): void {
    for (const transition of this.net.transitions) {
      if (!this.#blocked.has(transition.name)) continue;
      const footprint = this.engine.transitionFootprint(this.net, transition.name);
      if (overlaps(changedPlaces, footprint.consume) || overlaps(changedPlaces, footprint.read)) {
        this.#blocked.delete(transition.name);
      }
    }
  }

  #injectNow(arrival: TokenArrival): void {
    const injected = this.engine.inject(this.net, this.marking, arrival.place, arrival.token, {
      attempt: this.#nextInjectionAttempt(),
      replace: arrival.replace,
    });
    this.marking = injected.marking;
  }

  #nextInjectionAttempt(): number {
    const attempt = this.#injectionAttempt;
    this.#injectionAttempt += 1;
    return attempt;
  }

  #nextAttempt(): number {
    const attempt = this.#attempt;
    this.#attempt += 1;
    return attempt;
  }

  #writeConflicts(place: string): boolean {
    const arrival = writeFootprint(place);
    for (const active of this.#active) {
      if (footprintsConflict(arrival, active.footprint)) return true;
    }
    return false;
  }

  #admit(): void {
    while (!this.#stopping) {
      const enabled = new Set(this.engine.enabledTransitions(this.net, this.marking, {
        attempt: this.#attempt,
      }));
      const candidates: Transition[] = [];
      for (const transition of this.net.transitions) {
        if (!enabled.has(transition.name) || this.#blocked.has(transition.name)) continue;
        const handlerRef = transition.handler;
        if (handlerRef === undefined) continue;
        const spec = this.handlers[handlerRef];
        const footprint = this.engine.transitionFootprint(this.net, transition.name);
        if ((this.#laneInUse.get(spec.lane) ?? 0) >= (this.lanes.get(spec.lane)?.capacity ?? 0)) continue;
        let conflict = false;
        for (const active of this.#active) {
          if (footprintsConflict(footprint, active.footprint)) {
            conflict = true;
            break;
          }
        }
        if (conflict || !this.#ledger.admissible(transition.name)) continue;
        candidates.push(transition);
      }
      if (candidates.length === 0) return;
      const names = candidates.map((transition) => transition.name);
      const priorities = Object.create(null) as Record<string, number>;
      for (const transition of candidates) priorities[transition.name] = transition.priority ?? 0;
      const choice = this.registry.resolveFiringPolicy(this.policy)({
        marking: this.marking,
        enabledTransitions: names,
        priorities,
        consecutiveFailures: this.#ledger.counts(names),
      });
      if (choice === null) return;
      const transition = candidates.find((item) => item.name === choice);
      if (transition === undefined) return;
      const reservation = this.engine.reserve(this.net, this.marking, transition.name, {
        attempt: this.#nextAttempt(),
      });
      if (reservation === null) continue;
      const handlerRef = transition.handler;
      if (handlerRef === undefined) continue;
      this.#recordTrace("tokens_reserved", reservation.context, transition.name, handlerRef);
      this.marking = reservation.reservedMarking;
      this.#signal();
      const spec = this.handlers[handlerRef];
      const footprint = this.engine.transitionFootprint(this.net, transition.name);
      const input: TransitionHandlerInput = {
        transitionId: transition.name,
        inputTokens: reservation.inputTokens,
        firingContext: reservation.context,
      };
      const scope = spec.scope === undefined ? null : spec.scope(input);
      this.#laneInUse.set(spec.lane, (this.#laneInUse.get(spec.lane) ?? 0) + 1);
      const controller = new AbortController();
      const active: ActiveFiring = {reservation, spec, footprint, scope, controller};
      this.#active.add(active);
      this.#track(this.#execute(active, input, handlerRef));
    }
  }

  async #execute(active: ActiveFiring, input: TransitionHandlerInput, handlerRef: string): Promise<void> {
    const ctx = new RuntimeContext(active.scope, this, active.controller);
    const method = active.spec.handler.name || null;
    this.#recordTrace(
      "handler_started",
      active.reservation.context,
      active.reservation.transition,
      handlerRef,
      method,
    );
    let output: TransitionHandlerOutput;
    try {
      output = await this.#invoke(active, input, ctx);
    } catch (error) {
      if (isAbort(error)) {
        output = failedOutput("Cancelled", "runtime cancellation before handler completion", {
          scope: active.scope,
        });
      } else {
        const raised = error instanceof Error ? error : new Error(String(error));
        const handlerError = {type: raised.name, message: raised.message};
        this.#recordTrace(
          "handler_raised",
          active.reservation.context,
          active.reservation.transition,
          handlerRef,
          method,
          undefined,
          handlerError,
        );
        output = failedOutput(raised.name, raised.message, {});
      }
    }
    this.#recordTrace(
      "handler_returned",
      active.reservation.context,
      active.reservation.transition,
      handlerRef,
      method,
      output.status,
      output.status === "failed" ? output.error : null,
    );
    try {
      const settled = this.engine.settle(this.marking, active.reservation, output);
      this.marking = settled.marking;
      this.#ledger.record(active.reservation.transition, settled.record.status);
      if (settled.record.status === "failed") this.#blocked.add(active.reservation.transition);
      else this.#unblockFor(new Set(Object.keys(settled.record.outputTokens)));
    } finally {
      this.#active.delete(active);
      this.#laneInUse.set(active.spec.lane, (this.#laneInUse.get(active.spec.lane) ?? 1) - 1);
      this.#admit();
      this.#signal();
    }
  }

  async #invoke(
    active: ActiveFiring,
    input: TransitionHandlerInput,
    ctx: RuntimeContext,
  ): Promise<TransitionHandlerOutput> {
    if (active.spec.blocking !== true) {
      const result = active.spec.handler(input, ctx);
      if (!isPromise(result)) {
        throw new TypeError("non-blocking Runtime handlers must return an awaitable");
      }
      return await raceAbort(result, active.controller.signal);
    }
    let suppress = false;
    const worker = new Promise<TransitionHandlerOutput>((resolve, reject) => {
      setTimeout(() => {
        try {
          const result = active.spec.handler(input, ctx);
          if (isPromise(result)) {
            reject(new TypeError(
              "blocking Runtime handlers must return a completed output, not an awaitable",
            ));
            return;
          }
          resolve(result);
        } catch (error) {
          reject(error);
        }
      }, 0);
    });
    worker.then(
      () => {
        if (suppress) this.#recordLateWorker(active.reservation, "completed after cancellation; result suppressed");
      },
      (error: unknown) => {
        if (!suppress) return;
        const detail = isAbort(error)
          ? "cancelled after Runtime suppression"
          : `failed after cancellation: ${error instanceof Error ? `${error.name}: ${error.message}` : String(error)}`;
        this.#recordLateWorker(active.reservation, detail);
      },
    );
    try {
      return await raceAbort(worker, active.controller.signal);
    } catch (error) {
      if (isAbort(error)) suppress = true;
      throw error;
    }
  }

  #recordLateWorker(reservation: FiringReservation, detail: string): void {
    this.#recordRuntime("suppressed", {
      firingId: reservation.context.firingId,
      detail,
    });
  }

  #recordRuntime(
    event: "source_failed" | "suppressed",
    fields: {readonly firingId?: string; readonly source?: string; readonly detail: string},
  ): void {
    if (this.journal === undefined) return;
    if (this.journal.recordRuntime === undefined) {
      throw new TypeError("Runtime requires a journal with recordRuntime() lifecycle support");
    }
    this.journal.recordRuntime({
      event,
      netId: this.net.name,
      firingId: fields.firingId ?? null,
      source: fields.source ?? null,
      detail: fields.detail,
    });
  }

  #recordTrace(
    event: string,
    ctx: FiringContext,
    transition: string,
    handler: string | null,
    method?: string | null,
    status?: "completed" | "failed",
    error?: HandlerError | null,
  ): void {
    if (this.journal?.recordTrace === undefined) return;
    this.journal.recordTrace({
      event,
      netId: this.net.name,
      firingId: ctx.firingId,
      transition,
      handler,
      method: method ?? null,
      at: new Date().toISOString(),
      status: status ?? null,
      result: null,
      error: error ?? null,
    });
  }
}

function delay(seconds: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, seconds * 1000);
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    signal.addEventListener("abort", onAbort, {once: true});
  });
}
