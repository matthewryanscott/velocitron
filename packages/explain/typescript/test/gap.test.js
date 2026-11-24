import assert from "node:assert/strict";
import test from "node:test";

import {ExplainUnavailableError, explainNet} from "../dist/index.js";

test("the explanation name stays on the Python package", () => {
  // when / then: the TypeScript name fails closed
  assert.throws(() => explainNet(), ExplainUnavailableError);
});
