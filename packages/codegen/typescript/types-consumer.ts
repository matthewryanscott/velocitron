import {
  REFINED_AWAY,
  SYNTH_HANDLER,
  generateComposition,
  generateModule,
  type CodegenUnavailableError,
} from "./dist/index.js";

export function prefix(): string {
  return SYNTH_HANDLER;
}

export function refined(): string {
  return REFINED_AWAY;
}

export function unavailable(): CodegenUnavailableError {
  try {
    generateModule();
  } catch (error) {
    return error as CodegenUnavailableError;
  }
}

export function compositionUnavailable(): CodegenUnavailableError {
  try {
    generateComposition();
  } catch (error) {
    return error as CodegenUnavailableError;
  }
}
