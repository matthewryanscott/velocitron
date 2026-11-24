import assert from "node:assert/strict";
import test from "node:test";

import {
  Divergence,
  ReplayBase,
  ReplayCursor,
  ReplayNetMismatch,
  ReplayOrderError,
  ReplayResult,
  ReplayUnavailableError,
  replayRun,
} from "../dist/index.js";

test("the tape-replay names stay on the Python package", () => {
  // when / then: the TypeScript names fail closed
  assert.throws(() => new ReplayCursor(), ReplayUnavailableError);
  assert.throws(() => new ReplayBase(), ReplayUnavailableError);
  assert.throws(() => new ReplayOrderError(), ReplayUnavailableError);
  assert.throws(() => new ReplayNetMismatch(), ReplayUnavailableError);
  assert.throws(() => new Divergence(), ReplayUnavailableError);
  assert.throws(() => new ReplayResult(), ReplayUnavailableError);
  assert.throws(() => replayRun(), ReplayUnavailableError);
});
