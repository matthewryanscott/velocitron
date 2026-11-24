import type {CelAdapter} from "../adapter.js";
import type {FiringRecord, InjectionRecord, Journal} from "../journal/types.js";
import type {FiringContext, TokenBinding} from "../registry/types.js";
import type {Marking, Net, Token} from "../schema/types.js";

export type DepositViolationPolicy = "raise" | "record_then_raise" | "record_then_drop";

export interface EngineClock {
  now(): string;
}

export interface FiringIdInput {
  readonly netId: string;
  readonly transition: string;
  readonly attempt: number;
}

export interface InjectionIdInput {
  readonly netId: string;
  readonly place: string;
  readonly attempt: number;
}

export interface EngineIdFactory {
  firingId(input: FiringIdInput): string;
  injectionId(input: InjectionIdInput): string;
}

export interface EngineOptions {
  readonly celAdapter: CelAdapter;
  readonly policy?: string;
  readonly journal?: Journal;
  readonly depositViolation?: DepositViolationPolicy;
  readonly maxConsecutiveFailures?: number | null;
  readonly clock?: EngineClock;
  readonly idFactory?: EngineIdFactory;
}

export interface AttemptOptions {
  readonly attempt: number;
}

export interface OptionalAttemptOptions {
  readonly attempt?: number;
}

export interface InjectOptions extends AttemptOptions {
  readonly replace?: boolean;
}

export interface RunOptions {
  readonly maxSteps?: number;
  /**
   * Raise `ConflictError` when the policy would pick among two or more
   * enabled transitions, and `FailedAttemptError` on a failed attempt.
   */
  readonly strict?: boolean;
}

export interface TickOptions extends OptionalAttemptOptions, RunOptions {}

export interface FireResult {
  readonly marking: Marking;
  readonly record: FiringRecord;
}

export interface InjectionResult {
  readonly marking: Marking;
  readonly record: InjectionRecord;
}

export interface BatchInjectionResult {
  readonly marking: Marking;
  readonly records: readonly InjectionRecord[];
}

export interface TokenPlacement {
  readonly place: string;
  readonly token: Token;
}

/** One reserved firing. `reservedMarking` has already consumed the consume-mode tokens. */
export interface FiringReservation {
  readonly net: Net;
  readonly originalMarking: Marking;
  readonly reservedMarking: Marking;
  readonly transition: string;
  readonly attempt: number;
  readonly context: FiringContext;
  readonly inputTokens: TokenBinding;
  readonly consumedTokens: TokenBinding;
}

/** Places a transition consumes, reads, or writes. Inhibit arcs are none of these. */
export interface TransitionFootprint {
  readonly consume: ReadonlySet<string>;
  readonly read: ReadonlySet<string>;
  readonly write: ReadonlySet<string>;
}

export interface TimerMaturity {
  readonly transition: string;
  readonly clock: string;
  readonly at: number;
}

export type SelectedBinding = TokenBinding | null;
