/**
 * The TypeScript name of the Python registration base.
 *
 * `VelocitronNet` matches `velocitron_netbase.VelocitronNet`. Constructing
 * it, `Registration`, or calling `handlerSpec` raises
 * `NetbaseUnavailableError`. The class registers generated Python nets.
 * ADR 0058 leaves a TypeScript runtime off the roadmap. The Python package
 * is `velocitron_netbase`.
 *
 * `SYNTH_HANDLER` is the synthesized-handler prefix, re-exported from
 * `@velocitron/codegen` so this seam and the generator share one spelling.
 * `net_sha256`, `net_document`, `canonical_net_json`, and `HashMismatch`
 * stay on the Python package: this module does not hash a net. It does not
 * import `@velocitron/core`.
 */

export { SYNTH_HANDLER } from "@velocitron/codegen";

export class NetbaseUnavailableError extends Error {
  constructor() {
    super(
      "TypeScript has no VelocitronNet. Register a generated net with velocitron_netbase (Python).",
    );
    this.name = "NetbaseUnavailableError";
  }
}

/** Python `VelocitronNet`. Constructing it raises. */
export class VelocitronNet {
  constructor() {
    throw new NetbaseUnavailableError();
  }
}

/** Python `Registration`. Constructing it raises. */
export class Registration {
  constructor() {
    throw new NetbaseUnavailableError();
  }
}

/** Python `handler_spec`. This package does not build a handler spec. */
export function handlerSpec(): never {
  throw new NetbaseUnavailableError();
}
