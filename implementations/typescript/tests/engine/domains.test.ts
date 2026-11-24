import {describe, expect, it} from "vitest";
import {Engine} from "@velocitron/runtime";
import {
  DepositViolationError,
  TokenInjectionError,
} from "@velocitron/engine";
import {HandlerRegistry} from "@velocitron/engine";
import {
  NetValidationError,
  mergeNets,
  parseNet,
} from "@velocitron/petrinet";
import type {Marking, Net, ReadonlyJsonObject} from "@velocitron/engine";
import {completed, parsedNet, token} from "./helpers.js";

// ADR 0037: a declared domain is a runtime contract. The messages match the
// Python engine's (domains-parity.test.mjs), so a journal reads the same in
// both implementations.

function gateDocument(extra: ReadonlyJsonObject = {}): ReadonlyJsonObject {
  return {
    name: "gate",
    places: [
      {name: "inbox", accepts: ["job"]},
      {name: "verdicts", accepts: ["verdict"]},
    ],
    transitions: [{name: "judge", handler: "judge"}],
    arcs: [
      {from: {place: "inbox"}, to: {transition: "judge"}, consume: {type: "job"}},
      {
        from: {transition: "judge"},
        to: {place: "verdicts"},
        produce: {type: "verdict", destination: "verdicts"},
      },
    ],
    domains: {"verdict.result": ["pass", "hold"], "verdict.meta.level": [1, 2]},
    ...extra,
  };
}

function fire(net: Net, data: ReadonlyJsonObject): Marking {
  const registry = new HandlerRegistry();
  registry.registerTransition("judge", () => completed({verdicts: [token("verdict", data)]}));
  return new Engine(registry).fire(net, {inbox: [token("job")]}, "judge", {attempt: 0}).marking;
}

describe("declared domains (ADR 0037)", () => {
  it("parses domains and proof facts onto the net", () => {
    // given/when: a net document with both members
    const net = parsedNet(
      gateDocument({proofs: {final: ["verdicts"], invariants: [{weights: {inbox: 1}, constant: 1}]}}),
    );

    // then: both are on the model
    expect(net.domains).toEqual({"verdict.result": ["pass", "hold"], "verdict.meta.level": [1, 2]});
    expect(net.proofs).toEqual({final: ["verdicts"], invariants: [{weights: {inbox: 1}, constant: 1}]});
  });

  it("rejects a domain of a color no place accepts and a proof fact on an unknown place", () => {
    // given/when/then: each document fails with its issue code
    expect(() => parseNet(gateDocument({domains: {"switch.owner": ["main"]}}))).toThrow(
      /domain "switch.owner" names color "switch", which no place accepts/,
    );
    expect(() => parseNet(gateDocument({proofs: {final: ["gone"]}}))).toThrow(
      /final place "gone" is not declared/,
    );
  });

  it("deposits a token inside every domain", () => {
    // given: a handler output inside both domains
    const net = parsedNet(gateDocument());

    // when: the transition fires
    const marking = fire(net, {result: "hold", meta: {level: 2}});

    // then: the verdict is deposited
    expect(marking.verdicts).toHaveLength(1);
  });

  it.each([
    [{result: "maybe", meta: {level: 1}}, 'token verdict into (verdicts) holds result = "maybe", outside domain verdict.result: "pass", "hold"'],
    [{meta: {level: 1}}, "token verdict into (verdicts) has no result, which domain verdict.result requires"],
    [{result: "pass", meta: {level: true}}, "token verdict into (verdicts) holds meta.level = true, outside domain verdict.meta.level: 1, 2"],
  ])("makes a token outside a domain a deposit violation", (data, message) => {
    // given: a handler output outside a declared domain
    const net = parsedNet(gateDocument());

    // when/then: firing raises a deposit violation that names the field
    expect(() => fire(net, data as ReadonlyJsonObject)).toThrow(DepositViolationError);
    expect(() => fire(net, data as ReadonlyJsonObject)).toThrow(message);
  });

  it("rejects an injection outside a domain", () => {
    // given: a net with a closed verdict.result
    const net = parsedNet(gateDocument());
    const engine = new Engine(new HandlerRegistry());

    // when/then: injecting another value fails before the marking changes
    expect(() =>
      engine.inject(net, {}, "verdicts", token("verdict", {result: "fail", meta: {level: 1}}), {attempt: 0}),
    ).toThrow(TokenInjectionError);
  });

  it("merges one value set per field and rejects two", () => {
    // given: two nets wired port to port that disagree about verdict.result
    const portNet = (name: string, direction: "input" | "output", values: string[]): Net =>
      parsedNet({
        name,
        places: [
          {name: "edge", accepts: ["verdict"], port: {direction, type: "verdict"}},
          {name: "inner", accepts: ["verdict"]},
        ],
        transitions: [{name: "move"}],
        arcs: [
          {
            from: {place: direction === "output" ? "inner" : "edge"},
            to: {transition: "move"},
            consume: {type: "verdict"},
          },
          {
            from: {transition: "move"},
            to: {place: direction === "output" ? "edge" : "inner"},
            produce: {type: "verdict", destination: direction === "output" ? "edge" : "inner"},
          },
        ],
        domains: {"verdict.result": values},
        proofs: {final: [direction === "output" ? "edge" : "inner"]},
      });
    const wire = {from: {net: "a", port: "edge"}, to: {net: "b", port: "edge"}};

    // when: equal value sets merge
    const merged = mergeNets(
      new Map([
        ["a", portNet("producer", "output", ["pass", "hold"])],
        ["b", portNet("consumer", "input", ["hold", "pass"])],
      ]),
      [wire],
    );

    // then: one domain stays, and the wired final place is no longer final
    expect(merged.domains).toEqual({"verdict.result": ["pass", "hold"]});
    expect(merged.proofs).toEqual({final: ["b.inner"]});

    // and: different value sets fail
    expect(() =>
      mergeNets(
        new Map([
          ["a", portNet("producer", "output", ["pass"])],
          ["b", portNet("consumer", "input", ["pass", "hold"])],
        ]),
        [wire],
      ),
    ).toThrow(NetValidationError);
  });
});
