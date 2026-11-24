import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  GRAMMAR_FILE_NAME,
  PetrinetParseError,
  grammarText,
  parsePetrinet,
} from "../index.js";

const here = dirname(fileURLToPath(import.meta.url));
const grammarRoot = resolve(here, "../..");
const fixtures = resolve(grammarRoot, "fixtures");
const canonical = resolve(grammarRoot, GRAMMAR_FILE_NAME);
const packagedCopy = resolve(here, `../${GRAMMAR_FILE_NAME}`);
const examples = resolve(grammarRoot, "../../examples/capability-ladder");

function text(name) {
  return readFileSync(resolve(fixtures, name), "utf8");
}

describe(".petrinet syntax parser", () => {
  it("reads a net document", () => {
    // given: a net document with a header, a description, and one chain
    const source = text("net.petrinet");
    // when: the grammar package parses it
    const parsed = parsePetrinet(source, "net.petrinet");
    // then: the document is a net, and the result is not contribution IR
    assert.equal(parsed.kind, "net");
    assert.equal(parsed.name, "coin_deposit");
    assert.equal(parsed.sourceName, "net.petrinet");
    assert.equal(parsed.tree.constructor.name, "DocumentContext");
    assert.equal("contributions" in parsed, false);
  });

  it("reads a composition document", () => {
    // given: a composition document with use and wire facts
    const source = text("composition.petrinet");
    // when: the grammar package parses it
    const parsed = parsePetrinet(source, "composition.petrinet");
    // then: the document is still a composition, with no merged net
    assert.equal(parsed.kind, "composition");
    assert.equal(parsed.name, "wired_pulse");
    assert.equal(parsed.tree.constructor.name, "DocumentContext");
    assert.equal("contributions" in parsed, false);
  });

  it("names a headerless document unnamed", () => {
    // given: a net body with no net header
    const source = text("headerless.petrinet");
    // when: the grammar package parses it
    const parsed = parsePetrinet(source);
    // then: the document is a net whose effective name is unnamed
    assert.equal(parsed.kind, "net");
    assert.equal(parsed.name, "unnamed");
    assert.equal(parsed.sourceName, "<memory>");
  });

  it("decodes a quoted header name", () => {
    // given: net and composition headers whose names are JSON strings
    // when: the grammar package parses each document
    const net = parsePetrinet(text("quoted-net.petrinet"));
    const composition = parsePetrinet(text("quoted-composition.petrinet"));
    // then: the quotes are not part of the name
    assert.equal(net.kind, "net");
    assert.equal(net.name, "coin-deposit");
    assert.equal(composition.kind, "composition");
    assert.equal(composition.name, "wired-pulse");
  });

  it("accepts CRLF and an empty net", () => {
    // given: a net header written with CRLF, and an empty document
    const crlf = "net coin_deposit\r\n(coin_slot) -> [accept_coin]\r\n";
    // when: the grammar package parses both
    const parsed = parsePetrinet(crlf);
    const empty = parsePetrinet("");
    // then: CRLF is a net, and empty source is an unnamed net
    assert.equal(parsed.kind, "net");
    assert.equal(parsed.name, "coin_deposit");
    assert.equal(empty.kind, "net");
    assert.equal(empty.name, "unnamed");
  });

  it("rejects a syntax error without a tree", () => {
    // given: text that is not a .petrinet document
    // when: the grammar package parses it
    assert.throws(
      () => parsePetrinet("sentinel"),
      (error) => {
        assert.ok(error instanceof PetrinetParseError);
        assert.equal(error.line, 1);
        assert.equal(error.column, 1);
        assert.ok(error.message.length > 0);
        return true;
      },
    );
  });

  it("rejects a BOM and a bare CR", () => {
    // given: source text the grammar does not accept
    // when/then: each form fails before a document is returned
    for (const source of [
      "\uFEFFnet coin_deposit\n",
      "net coin_deposit\r(a) -> [b]\n",
      "\uD800",
    ]) {
      assert.throws(
        () => parsePetrinet(source),
        (error) => {
          assert.ok(error instanceof PetrinetParseError);
          assert.match(error.message, /BOM or bare CR/);
          assert.equal(error.line, 1);
          assert.equal(error.column, 1);
          return true;
        },
      );
    }
  });

  it("rejects a non-string", () => {
    // given: a number
    // when/then: the parser requires text
    assert.throws(() => parsePetrinet(1), TypeError);
  });

  it("reads the canonical grammar from a checkout", () => {
    // given: the canonical grammar and the copy this package ships
    const source = readFileSync(canonical, "utf8");
    // when: the parser reports the grammar it was generated from
    // then: a checkout reads the canonical file, and the packaged copy matches
    assert.equal(grammarText(), source);
    assert.equal(readFileSync(packagedCopy, "utf8"), source);
    assert.match(grammarText(), /grammar VelocitronPetriNet;/);
  });

  it("reads the capability-ladder examples", () => {
    // given: a real net and a real composition from the capability ladder
    const netPath = resolve(examples, "01-coin-deposit/coin-deposit.petrinet");
    const compositionPath = resolve(examples, "10-wired-pulse/wired_pulse.petrinet");
    // when: the grammar package parses each file
    const net = parsePetrinet(readFileSync(netPath, "utf8"), "coin-deposit.petrinet");
    const composition = parsePetrinet(
      readFileSync(compositionPath, "utf8"),
      "wired_pulse.petrinet",
    );
    // then: the documents keep their header names and kinds
    assert.equal(net.kind, "net");
    assert.equal(net.name, "coin_deposit");
    assert.equal(composition.kind, "composition");
    assert.equal(composition.name, "wired_pulse");
  });
});
