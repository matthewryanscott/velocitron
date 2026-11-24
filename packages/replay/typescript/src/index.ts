/**
 * The TypeScript name of the Python tape-replay driver.
 *
 * `ReplayCursor`, `ReplayBase`, and `replayRun` match
 * `velocitron_replay.ReplayCursor`, `ReplayBase`, and `replay_run`.
 * Constructing them, or calling `replayRun`, raises
 * `ReplayUnavailableError`. The driver subclasses `VelocitronNet` and calls
 * `Engine.fire`. ADR 0058 leaves a TypeScript runtime off the roadmap. The
 * Python package is `velocitron_replay`.
 *
 * `ReplayOrderError`, `ReplayNetMismatch`, `Divergence`, and `ReplayResult`
 * are the same gap: this module does not walk a tape. It does not import
 * `@velocitron/core`.
 */

export class ReplayUnavailableError extends Error {
  constructor() {
    super(
      "TypeScript has no tape replay. Replay a journal with velocitron_replay (Python).",
    );
    this.name = "ReplayUnavailableError";
  }
}

/** Python `ReplayCursor`. Constructing it raises. */
export class ReplayCursor {
  constructor() {
    throw new ReplayUnavailableError();
  }
}

/** Python `ReplayBase`. Constructing it raises. */
export class ReplayBase {
  constructor() {
    throw new ReplayUnavailableError();
  }
}

/** Python `ReplayOrderError`. Constructing it raises. */
export class ReplayOrderError {
  constructor() {
    throw new ReplayUnavailableError();
  }
}

/** Python `ReplayNetMismatch`. Constructing it raises. */
export class ReplayNetMismatch {
  constructor() {
    throw new ReplayUnavailableError();
  }
}

/** Python `Divergence`. Constructing it raises. */
export class Divergence {
  constructor() {
    throw new ReplayUnavailableError();
  }
}

/** Python `ReplayResult`. Constructing it raises. */
export class ReplayResult {
  constructor() {
    throw new ReplayUnavailableError();
  }
}

/** Python `replay_run`. This package does not drive `Engine.fire`. */
export function replayRun(): never {
  throw new ReplayUnavailableError();
}
