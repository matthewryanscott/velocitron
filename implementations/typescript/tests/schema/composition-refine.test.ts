import {describe, expect, it} from "vitest";

import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";
import type {CompositionRefinement, CompositionWire, Net} from "@velocitron/engine";
import {
  mergeComposition,
  mergeNets,
  NetValidationError,
  parseComposition,
  parseNet,
} from "@velocitron/petrinet";

// Transition refinement (spec/composition.md "Refinement"; ADR 0034): the
// courier net replaces the shop's abstract [deliver] during the merge. The
// messages match the Python `_validate_refinements` word for word.

function shop(extra: {places?: unknown[]; arcs?: unknown[]; deliver?: object} = {}): Net {
  return parseNet({
    name: "shop",
    places: [
      {name: "placed", accepts: ["parcel"]},
      {name: "sending", accepts: ["parcel"], port: {direction: "output", type: "parcel"}},
      {name: "delivered", accepts: ["receipt", "note"], port: {direction: "input", type: "receipt"}},
      {name: "settled", accepts: ["receipt"], annotations: {lane: "done"}},
      ...(extra.places ?? []),
    ],
    transitions: [{name: "send"}, {name: "deliver", ...extra.deliver}, {name: "settle"}],
    arcs: [
      {from: {place: "placed"}, to: {transition: "send"}, consume: {type: "parcel"}},
      {from: {transition: "send"}, to: {place: "sending"}, produce: {type: "parcel", destination: "sending"}},
      {from: {place: "sending"}, to: {transition: "deliver"}, consume: {type: "parcel"}},
      {from: {transition: "deliver"}, to: {place: "delivered"}, produce: {type: "receipt", destination: "delivered"}},
      {from: {place: "delivered"}, to: {transition: "settle"}, consume: {type: "receipt"}},
      {from: {transition: "settle"}, to: {place: "settled"}, produce: {type: "receipt", destination: "settled"}},
      ...(extra.arcs ?? []),
    ],
  });
}

const COURIER = parseNet({
  name: "courier",
  places: [
    {name: "pickup", accepts: ["parcel"], port: {direction: "input", type: "parcel"}},
    {name: "dropped", accepts: ["receipt"], port: {direction: "output", type: "receipt"}},
  ],
  transitions: [{name: "drop"}],
  arcs: [
    {from: {place: "pickup"}, to: {transition: "drop"}, consume: {type: "parcel"}},
    {from: {transition: "drop"}, to: {place: "dropped"}, produce: {type: "receipt", destination: "dropped"}},
  ],
});

const WIRES: readonly CompositionWire[] = [
  {from: {net: "shop", port: "sending"}, to: {net: "courier", port: "pickup"}},
  {from: {net: "courier", port: "dropped"}, to: {net: "shop", port: "delivered"}},
];

const REFINE: CompositionRefinement = {net: "shop", transition: "deliver", by: "courier"};

function nets(shopNet: Net = shop()): Map<string, Net> {
  return new Map([["shop", shopNet], ["courier", COURIER]]);
}

function failure(run: () => unknown): {code: string; message: string} {
  try {
    run();
  } catch (error: unknown) {
    if (error instanceof NetValidationError) {
      const issue = error.issues[0]!;
      return {code: issue.code, message: issue.message};
    }
    throw error;
  }
  throw new Error("expected a NetValidationError");
}

describe("mergeNets with refinements", () => {
  it("removes the refined transition and its arcs and keeps the rest", () => {
    // when
    const merged = mergeNets(nets(), WIRES, [REFINE]);

    // then
    expect(merged.transitions.map((transition) => transition.name)).toEqual([
      "shop.send",
      "shop.settle",
      "courier.drop",
    ]);
    expect(
      merged.arcs.some(
        (arc) => (arc.consume !== undefined ? arc.to.transition : arc.from.transition) === "shop.deliver",
      ),
    ).toBe(false);
    expect(merged.places.find((place) => place.name === "shop.settled")?.annotations).toEqual({lane: "done"});
    expect(merged.transitions.find((t) => t.name === "shop.settle")?.bindingNames).toEqual({
      delivered: "courier.dropped",
    });
  });

  it.each([
    [{...REFINE, by: "ghost"}, "composition.refinement.alias_unknown", "refine shop.[deliver] by ghost: unknown alias ghost"],
    [{...REFINE, by: "shop"}, "composition.refinement.self", "refine shop.[deliver] by shop: a net cannot refine its own transition"],
    [{...REFINE, transition: "ship"}, "composition.refinement.transition_unknown", "refine shop.[ship] by courier: net shop has no transition [ship]"],
  ])("rejects %o", (refinement, code, message) => {
    expect(failure(() => mergeNets(nets(), WIRES, [refinement]))).toEqual({code, message});
  });

  it("rejects a transition refined twice", () => {
    const withBike = new Map([...nets(), ["bike", COURIER]]);
    const wires = [...WIRES, {from: {net: "shop", port: "sending"}, to: {net: "bike", port: "pickup"}}];
    expect(failure(() => mergeNets(withBike, wires, [REFINE, {...REFINE, by: "bike"}]))).toEqual({
      code: "composition.refinement.duplicate",
      message: "refine shop.[deliver] by bike: shop.[deliver] is already refined by courier",
    });
  });

  it.each([
    [[WIRES[1]!], "refine shop.[deliver] by courier: [deliver] takes parcel from (sending), but (sending) is not wired to an input port of courier"],
    [[WIRES[0]!], "refine shop.[deliver] by courier: [deliver] gives receipt to (delivered), but (delivered) is not wired from an output port of courier"],
  ])("rejects an unwired place", (wires, message) => {
    expect(failure(() => mergeNets(nets(), wires, [REFINE]))).toEqual({
      code: "composition.refinement.unfit",
      message,
    });
  });

  it("rejects a port of another color", () => {
    // given: [deliver] also gives a note into (delivered), whose port carries receipt
    const noted = shop({
      arcs: [{from: {transition: "deliver"}, to: {place: "delivered"}, produce: {type: "note", destination: "delivered"}}],
    });
    expect(failure(() => mergeNets(nets(noted), WIRES, [REFINE]))).toEqual({
      code: "composition.refinement.unfit",
      message: "refine shop.[deliver] by courier: [deliver] gives note to (delivered), but the output ports of courier wired to it carry receipt",
    });
  });

  it("rejects inhibit arcs and timers", () => {
    const inhibited = shop({
      places: [{name: "stop", accepts: ["halt"]}],
      arcs: [{from: {place: "stop"}, to: {transition: "deliver"}, consume: {type: "halt", mode: "inhibit"}}],
    });
    expect(failure(() => mergeNets(nets(inhibited), WIRES, [REFINE]))).toEqual({
      code: "composition.refinement.unsupported",
      message: "refine shop.[deliver] by courier: [deliver] has an inhibit arc from (stop); a refined transition may only consume, read and produce",
    });
    const timed = shop({
      places: [{name: "clock", accepts: ["tick"]}],
      deliver: {timer: {clock: "clock", cel: "clock.now > 0"}},
    });
    expect(failure(() => mergeNets(nets(timed), WIRES, [REFINE]))).toEqual({
      code: "composition.refinement.unsupported",
      message: "refine shop.[deliver] by courier: [deliver] has a timer; a refined transition may only consume, read and produce",
    });
  });
});

describe("refinement in composition documents and the DSL", () => {
  const SOURCES: Record<string, Net> = {"shop.json": shop(), "courier.json": COURIER};

  it("parses refinements and merges them", () => {
    // given
    const document = {
      nets: [{ref: "shop.json", alias: "shop"}, {ref: "courier.json", alias: "courier"}],
      wires: WIRES,
      refinements: [REFINE],
    };

    // when
    const parsed = parseComposition(document, {loadRef: (ref) => SOURCES[ref]});
    const merged = mergeComposition(parsed.document, parsed.parsedNets);

    // then
    expect(parsed.document.refinements).toEqual([REFINE]);
    expect(merged.transitions.some((t) => t.name === "shop.deliver")).toBe(false);
  });

  it("compiles `refine` and rejects a conflicting second fact", () => {
    // given
    const head =
      'composition c\nuse "shop.json" as shop\nuse "courier.json" as courier\nuse "courier.json" as bike\n' +
      "wire shop.(sending) -> courier.(pickup)\nrefine shop.[deliver] by courier\n";

    // when
    const compiled = compilePetrinetText(head, "c.petrinet");

    // then
    expect(compiled.document.refinements).toEqual([REFINE]);
    let diagnostic: PetrinetDslError | undefined;
    try {
      compilePetrinetText(`${head}refine shop.[deliver] by bike\n`, "c.petrinet");
    } catch (error: unknown) {
      if (error instanceof PetrinetDslError) diagnostic = error;
    }
    expect(diagnostic?.diagnostic.code).toBe("PN202");
    expect(diagnostic?.diagnostic.message).toBe("conflicting refine facts for shop.[deliver]");
  });
});
