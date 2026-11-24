import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { COMPOSITION_SCHEMA, NET_SCHEMA } from "../dist/generated/schemas.js";
import { validateComposition, validateNet } from "../dist/generated/validators.js";

const here = dirname(fileURLToPath(import.meta.url));
const spec = resolve(here, "../../../spec");
const netSchema = JSON.parse(readFileSync(resolve(spec, "net.schema.json"), "utf8"));
const compositionSchema = JSON.parse(
  readFileSync(resolve(spec, "composition.schema.json"), "utf8"),
);
const validatorSource = readFileSync(resolve(here, "../src/generated/validators.ts"), "utf8");

describe("generated canonical schemas", () => {
  it("matches both root schema documents exactly", () => {
    // given: the spec documents and the generated copies
    // then: the generated documents are those schemas
    assert.deepEqual(NET_SCHEMA, netSchema);
    assert.deepEqual(COMPOSITION_SCHEMA, compositionSchema);
  });

  it("contains standalone browser-safe validators", () => {
    // then: the generated source is a standalone validator
    assert.match(validatorSource, /export const validateNet/);
    assert.match(validatorSource, /export const validateComposition/);
    assert.doesNotMatch(validatorSource, /\brequire\s*\(/u);
    assert.doesNotMatch(validatorSource, /\b(?:new\s+)?Function\s*\(/u);
    assert.doesNotMatch(validatorSource, /\bnode:/u);
    assert.doesNotMatch(validatorSource, /from\s+["'](?:node:)?(?:fs|path|module)["']/u);
  });

  it("validates without compiling schemas at import time", () => {
    // when: the standalone validators run
    // then: they accept an empty net and reject an empty composition
    assert.equal(validateNet({ arcs: [], name: "empty", places: [], transitions: [] }), true);
    assert.equal(validateNet({ arcs: [], name: "", places: [], transitions: [] }), false);
    assert.equal(validateComposition({ nets: [{ ref: "net.json" }], wires: [] }), true);
    assert.equal(validateComposition({ nets: [], wires: [] }), false);
  });
});
