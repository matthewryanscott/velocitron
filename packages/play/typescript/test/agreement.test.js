import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { GRAMMAR_FILE_NAME, PlayError, grammarText, parsePlay, projectPlay } from "../dist/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../../../..");
const fixtures = resolve(repo, "packages/play/fixtures");
const manifest = JSON.parse(readFileSync(resolve(fixtures, "manifest.json"), "utf8"));
const expected = JSON.parse(readFileSync(resolve(fixtures, "agreement.json"), "utf8"));

describe(".play agreement", () => {
  for (const entry of manifest) {
    it(entry.name, () => {
      // given: one shared fixture
      const text = readFileSync(resolve(repo, entry.path), "utf8");
      // when: the TypeScript lowerer projects it
      const actual = projectPlay(text);
      // then: the projection matches the Python oracle
      assert.deepEqual(actual, expected[entry.name]);
    });
  }
});

describe(".play parser", () => {
  it("reads the canonical grammar and rejects a duplicate key", () => {
    // given: the statement grammar and a repeated JSON key
    const canonical = readFileSync(resolve(repo, "packages/play", GRAMMAR_FILE_NAME), "utf8");
    // when: the package reads the grammar it was generated from
    // then: a checkout reads the canonical file, and a duplicate key is SC102
    assert.equal(grammarText(), canonical);
    assert.equal(canonical.includes("grammar VelocitronPlay;"), true);
    assert.throws(
      () => parsePlay('play s\ninject (p) <- c {"a": 1, "a": 2}\n'),
      (error) => error instanceof PlayError && error.code === "SC102" && error.message.includes("duplicate key"),
    );
  });

  it("says a kebab-case play name must be an identifier", () => {
    // when: the header names the play the way its file is named
    // then: SC101 at the dash, with the identifier to write instead
    assert.throws(
      () => parsePlay("play step-warning\n"),
      (error) => error instanceof PlayError
        && error.code === "SC101"
        && error.line === 1
        && error.column === 10
        && error.message.endsWith("a play name is an identifier (letters, digits, `_`): write `step_warning`"),
    );
  });
});
