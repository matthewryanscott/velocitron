/**
 * The TypeScript name of the Python CLI seam.
 *
 * `main` matches `velocitron_cli.main` (`velocitron`). `vizMain` matches
 * `velocitron_cli.viz_main` (`velocitron-viz`). Calling either one raises
 * `CliUnavailableError`. The dispatcher is argparse in the Python package.
 * This package does not parse arguments or import `@velocitron/core`.
 *
 * `COMMANDS` is the `velocitron` subcommand list. `VIZ_PROGRAM` is the
 * drawing program name.
 */

/** Subcommands of the `velocitron` console script, in dispatcher order. */
export const COMMANDS = [
  "validate",
  "to-json",
  "to-petrinet",
  "explain",
  "skill",
  "check",
  "prove",
  "codegen",
  "equiv",
  "play",
] as const;

export type Command = (typeof COMMANDS)[number];

/** The drawing console script. */
export const VIZ_PROGRAM = "velocitron-viz";

export class CliUnavailableError extends Error {
  constructor() {
    super(
      "The Velocitron CLI is the Python package velocitron_cli. TypeScript does not dispatch console commands.",
    );
    this.name = "CliUnavailableError";
  }
}

/** Python `main`. This package does not parse argv. */
export function main(): never {
  throw new CliUnavailableError();
}

/** Python `viz_main`. This package does not draw. */
export function vizMain(): never {
  throw new CliUnavailableError();
}
