import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { compilePetrinetText, parseNet } from "../dist/index.js";

const net = `net coin_deposit "Coin deposit"

(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)
`;

describe("compilePetrinetText", () => {
  it("compiles a net to canonical JSON", () => {
    // given: one net with a single chain
    // when: the package compiles it
    const compiled = compilePetrinetText(net, "coin_deposit.petrinet");
    // then: the result is a frozen canonical net, not contribution IR
    assert.equal(compiled.documentKind, "net");
    assert.equal(compiled.document.name, "coin_deposit");
    assert.equal(compiled.document.description, "Coin deposit");
    assert.equal("contributions" in compiled.document, false);
    assert.equal("format" in compiled.document, false);
    const parsed = parseNet(compiled.document);
    assert.equal(parsed.name, "coin_deposit");
  });
});
