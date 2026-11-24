import type {FiringRecord} from "../journal/types.js";
import type {Marking} from "../schema/types.js";

export class EngineConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class UnknownTransitionError extends Error {
  readonly net: string;
  readonly transition: string;

  constructor(net: string, transition: string) {
    super(`net ${JSON.stringify(net)} has no transition named ${JSON.stringify(transition)}`);
    this.name = new.target.name;
    this.net = net;
    this.transition = transition;
  }
}

export class DepositViolationError extends Error {
  readonly transition: string;

  constructor(transition: string, detail?: string) {
    super(detail ?? `transition ${JSON.stringify(transition)} produced tokens that violate its produce contract`);
    this.name = new.target.name;
    this.transition = transition;
  }
}

export class TokenInjectionError extends Error {
  readonly net: string;
  readonly place: string;

  constructor(net: string, place: string, message: string) {
    super(`token injection: ${message}`);
    this.name = new.target.name;
    this.net = net;
    this.place = place;
  }
}

/**
 * A strict `run` found two or more transitions enabled at once, which the
 * firing policy would pick among (under the priority policy, two or more at
 * the top declared priority). Nothing fired at that marking, its `marking`.
 */
export class ConflictError extends Error {
  readonly net: string;
  readonly transitions: readonly string[];
  readonly marking: Marking;

  constructor(net: string, transitions: readonly string[], marking: Marking) {
    super(`${net}: ${transitions.map((name) => `[${name}]`).join(", ")} are enabled at once`);
    this.name = new.target.name;
    this.net = net;
    this.transitions = [...transitions];
    this.marking = marking;
  }
}

/**
 * A strict `run` or `fire` stopped at a failed attempt instead of retrying it. The
 * record went to the journal as usual; the marking is unchanged by it, and
 * `marking` is where the run stopped. Its `cause` is the exception the failed
 * handler output carried, if any.
 */
export class FailedAttemptError extends Error {
  readonly net: string;
  readonly record: FiringRecord;
  readonly marking: Marking;

  constructor(net: string, record: FiringRecord, marking: Marking, options?: ErrorOptions) {
    const detail = record.error === null
      ? "no error given"
      : `${record.error.type}: ${record.error.message}`;
    super(`${net}: [${record.transition}] failed: ${detail}`, options);
    this.name = new.target.name;
    this.net = net;
    this.record = record;
    this.marking = marking;
  }
}
