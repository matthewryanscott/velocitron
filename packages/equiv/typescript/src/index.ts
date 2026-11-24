/**
 * The TypeScript name of the Python structural-equivalence check.
 *
 * `compare` and `Equivalence` match `velocitron_equiv.compare` and
 * `Equivalence`. Calling `compare`, or constructing `Equivalence`, raises
 * `EquivUnavailableError`. The check loads nets through the Python prover
 * and compares them up to renaming. This module does not compare nets. It
 * does not import `@velocitron/core`.
 */

export class EquivUnavailableError extends Error {
  constructor() {
    super(
      "TypeScript has no structural equivalence. Compare nets with velocitron_equiv (Python).",
    );
    this.name = "EquivUnavailableError";
  }
}

/** Python `Equivalence`. Constructing it raises. */
export class Equivalence {
  constructor() {
    throw new EquivUnavailableError();
  }
}

/** Python `compare`. This package does not compare nets. */
export function compare(): never {
  throw new EquivUnavailableError();
}
