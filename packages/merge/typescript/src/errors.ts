/**
 * A composition merge rejected its inputs.
 *
 * `message` is the first issue's message, matching the implementation's
 * `NetValidationError` for the same rejection. This package does not import
 * `@velocitron/core`.
 */

import type {ReadonlyJsonObject} from "./types.js";

export interface NetValidationIssue {
  readonly code: string;
  readonly path: string;
  readonly message: string;
  readonly details?: ReadonlyJsonObject;
}

export class NetValidationError extends Error {
  readonly issues: readonly NetValidationIssue[];

  constructor(issues: readonly NetValidationIssue[]) {
    if (issues.length === 0) throw new TypeError("NetValidationError requires an issue");
    const first = issues[0];
    if (first === undefined) throw new TypeError("NetValidationError requires an issue");
    super(
      issues.length === 1
        ? first.message
        : `Net validation failed with ${issues.length} issues; first: ${first.message}`,
    );
    this.name = "NetValidationError";
    this.issues = Object.freeze(issues.map((issue) => Object.freeze({...issue})));
  }
}
