import assert from "node:assert/strict";
import test from "node:test";

import {EquivUnavailableError, Equivalence, compare} from "../dist/index.js";

test("the equivalence names stay on the Python package", () => {
  // when / then: the TypeScript names fail closed
  assert.throws(() => compare(), EquivUnavailableError);
  assert.throws(() => new Equivalence(), EquivUnavailableError);
});
