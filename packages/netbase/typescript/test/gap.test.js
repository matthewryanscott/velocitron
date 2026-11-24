import assert from "node:assert/strict";
import test from "node:test";

import {
  SYNTH_HANDLER,
  NetbaseUnavailableError,
  Registration,
  VelocitronNet,
  handlerSpec,
} from "../dist/index.js";

test("SYNTH_HANDLER matches the Python synthesized-handler prefix", () => {
  // then: the spelling is the one registration and the generator share
  assert.equal(SYNTH_HANDLER, "velocitron:synth:");
});

test("VelocitronNet, Registration, and handlerSpec stay on the Python package", () => {
  // when / then: the TypeScript names fail closed
  assert.throws(() => new VelocitronNet(), NetbaseUnavailableError);
  assert.throws(() => new Registration(), NetbaseUnavailableError);
  assert.throws(() => handlerSpec(), NetbaseUnavailableError);
});
