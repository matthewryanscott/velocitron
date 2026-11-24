/**
 * The TypeScript name of the Python declarative property pass.
 *
 * `checkMarking`, `checkReplay`, and `capacityProperties` match
 * `velocitron_properties.check_marking`, `check_replay`, and
 * `capacity_properties`. Calling them raises `PropertiesUnavailableError`.
 * The pass reconstructs markings from journal records and evaluates CEL.
 * Those stay in Python. This module does not check a marking. It does not
 * import `@velocitron/core`.
 */

export class PropertiesUnavailableError extends Error {
  constructor() {
    super(
      "TypeScript has no property pass. Check a marking with velocitron_properties (Python).",
    );
    this.name = "PropertiesUnavailableError";
  }
}

/** Python `check_marking`. This package does not check a marking. */
export function checkMarking(): never {
  throw new PropertiesUnavailableError();
}

/** Python `check_replay`. This package does not walk a journal. */
export function checkReplay(): never {
  throw new PropertiesUnavailableError();
}

/** Python `capacity_properties`. This package does not read a net. */
export function capacityProperties(): never {
  throw new PropertiesUnavailableError();
}
