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

const unshared = `net copies

(idle) -job-> [go]
(clock) -now->? [go]
(clock) annotation fusion true
decorate (clock) beside unshared
`;

const sided = `net copies

(idle) -job-> [go]
(clock) -now->? [go]
(clock) annotation fusion true
decorate (clock) beside right unshared
`;

function besideOf(source) {
  const compiled = compilePetrinetText(source, "copies.petrinet");
  const annotations = compiled.document.annotations;
  return annotations["petrinet.dsl/v1"].decorations["place:clock"].beside;
}

describe("beside unshared", () => {
  it("lowers to share false", () => {
    // given: a fusion place decorated beside unshared
    // when: the package compiles it
    // then: the payload opts out of sharing and names no side
    assert.deepEqual(besideOf(unshared), {share: false});
  });

  it("keeps a fixed side beside the share flag", () => {
    // given: beside right unshared
    // when: the package compiles it
    // then: both the side and the opt-out are in the payload
    assert.deepEqual(besideOf(sided), {side: "right", share: false});
  });
});
