import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  CONTRIBUTION_IR_FORMAT,
  ContributionIrShapeError,
  contributionIrSchemaText,
  loadContributionIr,
  loadContributionIrText,
} from "../index.js";

const here = dirname(fileURLToPath(import.meta.url));
const packages = resolve(here, "../../..");
const fixtures = resolve(here, "../../fixtures");
const corpus = resolve(packages, "spec/conformance/petrinet");
const canonicalSchema = resolve(
  packages,
  "spec/petrinet-contribution-ir.schema.json",
);

function document(name) {
  return JSON.parse(readFileSync(join(fixtures, name), "utf8"));
}

function celStrings(value, found = []) {
  if (Array.isArray(value)) {
    for (const item of value) celStrings(item, found);
    return found;
  }
  if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      if (key === "cel" && typeof item === "string") found.push(item);
      else celStrings(item, found);
    }
  }
  return found;
}

function contributionIrFiles(directory) {
  const found = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...contributionIrFiles(path));
    else if (entry.name.endsWith(".contribution-ir.json")) found.push(path);
  }
  return found;
}

describe("contribution IR shape loader", () => {
  it("returns a detached net document", () => {
    // given: a minimal net contribution IR document
    const original = document("minimal-net.contribution-ir.json");
    // when: the shape loader validates it
    const loaded = loadContributionIr(original);
    // then: the wire document is returned unchanged and detached from the input
    assert.deepEqual(loaded, original);
    assert.notEqual(loaded, original);
    assert.equal(loaded.format, CONTRIBUTION_IR_FORMAT);
    assert.equal(loaded.version, 1);
    assert.equal(loaded.documentKind, "net");
    original.document.id = "mutated.petrinet";
    assert.equal(loaded.document.id, "example.petrinet");
  });

  it("keeps a composition unmerged", () => {
    // given: a composition contribution IR document with one header fact
    const original = document("minimal-composition.contribution-ir.json");
    // when: the shape loader validates it
    const loaded = loadContributionIr(original);
    // then: the result is still the IR document, with no merged net members
    assert.equal(loaded.documentKind, "composition");
    assert.deepEqual(Object.keys(loaded).sort(), [
      "contributions",
      "document",
      "documentKind",
      "format",
      "version",
    ]);
    assert.equal(loaded.contributions[0].kind, "document.composition-header");
  });

  it("keeps CEL text as a string", () => {
    // given: a produce-cel contribution whose CEL source is not a compiled plan
    const original = document("cel-string.contribution-ir.json");
    // when: the shape loader validates it
    const loaded = loadContributionIr(original);
    // then: the CEL source is the same string on the returned contribution
    assert.deepEqual(loaded.contributions[0].value, { cel: "token.n + 1" });
  });

  it("accepts duplicate ordinals", () => {
    // given: two contributions that share an ordinal, which the wire schema allows
    const original = document("duplicate-ordinals.contribution-ir.json");
    // when: the shape loader validates it
    const loaded = loadContributionIr(original);
    // then: both contributions are kept; ordinal contiguity is a resolver rule
    assert.deepEqual(
      loaded.contributions.map((item) => item.ordinal),
      [0, 0],
    );
  });

  it("rejects an unsupported format before the schema walk", () => {
    // given: a document whose format is not the contribution-IR identifier
    const original = document("minimal-net.contribution-ir.json");
    original.format = "velocitron.petrinet/other";
    original.contributions = "not-an-array";
    // when: the shape loader reads it
    assert.throws(
      () => loadContributionIr(original),
      (error) => {
        assert.ok(error instanceof ContributionIrShapeError);
        assert.equal(error.message, "unsupported contribution IR format or version");
        assert.deepEqual(error.issues, []);
        return true;
      },
    );
  });

  it("rejects a boolean version", () => {
    // given: a document whose version is the JSON boolean true
    const original = document("minimal-net.contribution-ir.json");
    original.version = true;
    // when/then: true is not integer version 1
    assert.throws(
      () => loadContributionIr(original),
      (error) =>
        error instanceof ContributionIrShapeError &&
        error.message === "unsupported contribution IR format or version",
    );
  });

  it("reports a schema issue under the bad contribution", () => {
    // given: a net document whose only contribution kind is not in the closed set
    const original = document("minimal-net.contribution-ir.json");
    original.contributions[0].kind = "nope";
    // when: the shape loader validates it
    assert.throws(
      () => loadContributionIr(original),
      (error) => {
        assert.ok(error instanceof ContributionIrShapeError);
        assert.equal(
          error.message,
          "contribution IR document does not match the wire schema",
        );
        assert.ok(
          error.issues.some((item) => item.instancePath.startsWith("/contributions/0")),
        );
        return true;
      },
    );
  });

  it("rejects non-objects and non-JSON text", () => {
    // given: values that are not contribution-IR objects
    // when/then: each one fails the object or JSON gate
    for (const value of [[], "net", 1, null, true]) {
      assert.throws(
        () => loadContributionIr(value),
        (error) =>
          error instanceof ContributionIrShapeError &&
          error.message === "contribution IR document must be a JSON object",
      );
    }
    const text = readFileSync(join(fixtures, "minimal-net.contribution-ir.json"), "utf8");
    assert.equal(loadContributionIrText(text).documentKind, "net");
    assert.throws(
      () => loadContributionIrText("{"),
      (error) =>
        error instanceof ContributionIrShapeError &&
        error.message === "contribution IR text is not JSON",
    );
    assert.throws(() => loadContributionIrText(1), TypeError);
  });

  it("reads the canonical schema from a checkout", () => {
    // given: the canonical contribution-IR schema in packages/spec
    // when: the loader reports the schema it will use
    // then: a checkout reads that canonical file
    assert.equal(contributionIrSchemaText(), readFileSync(canonicalSchema, "utf8"));
    assert.match(
      contributionIrSchemaText(),
      /"\$id": "https:\/\/velocitron\.dev\/spec\/petrinet-contribution-ir\.schema\.json"/,
    );
  });

  it("accepts the conformance corpus", () => {
    // given: every contribution-IR document in the petrinet conformance corpus
    const paths = contributionIrFiles(corpus);
    assert.ok(paths.length > 0);
    // when: the shape loader validates each document
    for (const path of paths) {
      const original = JSON.parse(readFileSync(path, "utf8"));
      const loaded = loadContributionIr(original);
      // then: the document round-trips, including every CEL source string
      assert.deepEqual(loaded, original);
      assert.deepEqual(celStrings(loaded), celStrings(original));
      assert.equal(loaded.format, CONTRIBUTION_IR_FORMAT);
      assert.ok(loaded.documentKind === "net" || loaded.documentKind === "composition");
    }
  });
});
