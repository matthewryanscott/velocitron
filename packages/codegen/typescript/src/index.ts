/**
 * The TypeScript name of the Python codegen seam.
 *
 * `generateModule` and `generateComposition` match `generate_module` and
 * `generate_composition`. Calling either one raises
 * `CodegenUnavailableError`. The emitter writes Python that subclasses
 * `velocitron.netbase.VelocitronNet`, and ADR 0058 leaves TypeScript
 * codegen off the roadmap. The Python package is `velocitron_codegen`.
 *
 * `SYNTH_HANDLER` is the synthesized-handler prefix. `REFINED_AWAY` is the
 * exception name a composition mixin raises. This package does not import
 * `@velocitron/core`.
 */

export const SYNTH_HANDLER = "velocitron:synth:";

/** The exception a generated `Refined<T>` mixin raises. */
export const REFINED_AWAY = "RefinedAway";

export class CodegenUnavailableError extends Error {
  constructor() {
    super(
      "TypeScript codegen is not implemented. Generate Python modules with velocitron_codegen (the velocitron codegen command).",
    );
    this.name = "CodegenUnavailableError";
  }
}

/** Python `generate_module`. This package does not emit a module. */
export function generateModule(): never {
  throw new CodegenUnavailableError();
}

/** Python `generate_composition`. This package does not emit a module. */
export function generateComposition(): never {
  throw new CodegenUnavailableError();
}
