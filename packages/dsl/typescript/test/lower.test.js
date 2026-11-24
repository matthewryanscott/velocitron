import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { PetrinetDslError, lowerPetrinetText } from "../dist/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const net = `net coin_deposit "Coin deposit"

(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)
`;
const composition = `composition wired_pulse

use "pulse_source.petrinet" as source
use "pulse_sink.petrinet" as sink
wire source.(pulse_out) -> sink.(pulse_in)
`;

describe("lowerPetrinetText", () => {
  it("lowers a net to contribution IR without resolving it", () => {
    // given: a net with one chain
    // when: the package lowers it
    const ir = lowerPetrinetText(net, "coin_deposit.petrinet");
    // then: the result is contribution IR, not a resolved net
    assert.equal(ir.format, "velocitron.petrinet/contribution-ir");
    assert.equal(ir.version, 1);
    assert.equal(ir.documentKind, "net");
    assert.deepEqual(ir.document, {id: "coin_deposit.petrinet"});
    assert.equal("places" in ir, false);
    assert.equal("nets" in ir, false);
    assert.deepEqual(
      ir.contributions.map((item) => item.ordinal),
      ir.contributions.map((_, index) => index),
    );
    assert.equal(ir.contributions[0].kind, "document.net-header");
    assert.equal(ir.contributions[0].value.name, "coin_deposit");
    assert.equal(
      ir.contributions.some((item) => item.kind === "arc.declare"),
      true,
    );
  });

  it("lowers a composition without merging referenced nets", () => {
    // given: a composition whose use targets are not on disk
    // when: the package lowers it
    const ir = lowerPetrinetText(composition, "wired_pulse.petrinet");
    // then: use and wire facts are contributions, and nothing is merged
    assert.equal(ir.documentKind, "composition");
    assert.deepEqual(ir.document, {id: "wired_pulse.petrinet"});
    assert.equal("nets" in ir, false);
    const kinds = ir.contributions.map((item) => item.kind);
    assert.equal(kinds[0], "document.composition-header");
    assert.equal(ir.contributions[0].value.namespace, "wired_pulse");
    assert.equal(kinds.filter((kind) => kind === "composition.use").length, 2);
    assert.equal(kinds.includes("composition.wire"), true);
  });

  it("reports EOF as a zero-width span at source length", () => {
    // given: source truncated exactly at EOF
    // when: lowering rejects it
    // then: EOF is a zero-width span at source length
    assert.throws(
      () => lowerPetrinetText("net", "truncated.petrinet"),
      (error) => {
        assert.ok(error instanceof PetrinetDslError);
        assert.deepEqual(error.diagnostic.span, {
          source: "truncated.petrinet",
          start: {offset: 3, line: 1, column: 4},
          end: {offset: 3, line: 1, column: 4},
        });
        return true;
      },
    );
  });

  it("copies the lowerer without importing the implementation", () => {
    // given: the synced lowerer source
    const text = readFileSync(resolve(here, "../src/lower.ts"), "utf8");
    // when: its import lines are read
    const imports = text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.startsWith("import "));
    // then: schema types come from this package, and resolution stays out
    assert.equal(
      imports.some((line) => line.includes("./json-types.js")),
      true,
    );
    assert.equal(
      imports.some((line) => line.includes("../schema/") || line.includes("./resolve.js")),
      false,
    );
    assert.equal(text.includes("resolveContributionIr"), false);
  });
});
