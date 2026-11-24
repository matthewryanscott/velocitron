import {
  createDefaultCelAdapter,
  type CelAdapter,
  type CelDiagnostic,
} from "./dist/index.js";

export function compileLiteral(): {readonly program: unknown; readonly diagnostic: CelDiagnostic["phase"]} {
  const adapter: CelAdapter = createDefaultCelAdapter();
  const program = adapter.compile("1 + 1");
  return {program, diagnostic: "compile"};
}
