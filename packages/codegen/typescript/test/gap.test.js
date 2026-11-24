import assert from "node:assert/strict";
import test from "node:test";

import {
  REFINED_AWAY,
  SYNTH_HANDLER,
  CodegenUnavailableError,
  generateComposition,
  generateModule,
} from "../dist/index.js";

test("SYNTH_HANDLER matches the Python synthesized-handler prefix", () => {
  // then: the spelling is the one registration and the generator share
  assert.equal(SYNTH_HANDLER, "velocitron:synth:");
  assert.equal(REFINED_AWAY, "RefinedAway");
});

test("generateModule and generateComposition stay on the Python package", () => {
  // when / then: the TypeScript names fail closed
  assert.throws(() => generateModule(), CodegenUnavailableError);
  assert.throws(() => generateComposition(), CodegenUnavailableError);
});
