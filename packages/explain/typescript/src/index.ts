/**
 * The TypeScript name of the Python net explanation.
 *
 * `explainNet` matches `velocitron_explain.explain_net`. Calling it raises
 * `ExplainUnavailableError`. The renderer quotes a validated net and, given
 * a marking, asks the Python engine's enablement explanation. This module
 * does not render prose. It does not import `@velocitron/core`.
 */

export class ExplainUnavailableError extends Error {
  constructor() {
    super(
      "TypeScript has no net explanation. Render prose with velocitron_explain (Python).",
    );
    this.name = "ExplainUnavailableError";
  }
}

/** Python `explain_net`. This package does not render a net. */
export function explainNet(): never {
  throw new ExplainUnavailableError();
}
