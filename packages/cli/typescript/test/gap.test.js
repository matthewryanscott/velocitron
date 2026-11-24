import assert from "node:assert/strict";
import test from "node:test";

import {
  COMMANDS,
  VIZ_PROGRAM,
  CliUnavailableError,
  main,
  vizMain,
} from "../dist/index.js";

test("COMMANDS names the Python velocitron subcommands", () => {
  // then: the spelling is the dispatcher order
  assert.deepEqual(COMMANDS, [
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
  ]);
  assert.equal(VIZ_PROGRAM, "velocitron-viz");
});

test("main and vizMain stay on the Python package", () => {
  // when / then: the TypeScript names fail closed
  assert.throws(() => main(), CliUnavailableError);
  assert.throws(() => vizMain(), CliUnavailableError);
});
