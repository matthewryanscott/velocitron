/** An `SC2xx` failure raised before a path plays. `SC3xx` stays on the trace. */
export class PlayCheckError extends Error {
  readonly code: string;
  readonly line: number;
  readonly column: number;
  readonly details: readonly string[];

  constructor(
    code: string,
    message: string,
    line: number,
    column: number,
    details: readonly string[] = [],
  ) {
    super(message);
    this.name = "PlayCheckError";
    this.code = code;
    this.line = line;
    this.column = column;
    this.details = details;
  }
}
