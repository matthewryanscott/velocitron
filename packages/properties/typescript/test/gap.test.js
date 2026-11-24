import assert from "node:assert/strict";
import test from "node:test";

import {
  PropertiesUnavailableError,
  capacityProperties,
  checkMarking,
  checkReplay,
} from "../dist/index.js";

test("the property-pass names stay on the Python package", () => {
  // when / then: the TypeScript names fail closed
  assert.throws(() => checkMarking(), PropertiesUnavailableError);
  assert.throws(() => checkReplay(), PropertiesUnavailableError);
  assert.throws(() => capacityProperties(), PropertiesUnavailableError);
});
