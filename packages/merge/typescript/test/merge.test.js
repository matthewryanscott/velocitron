import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  NetValidationError,
  mergeComposition,
  mergeNets,
  portFusionMap,
} from "../dist/index.js";

const fixtures = resolve(dirname(fileURLToPath(import.meta.url)), "../../fixtures");
const cases = JSON.parse(readFileSync(resolve(fixtures, "cases.json"), "utf8"));

function netFrom(doc) {
  return {
    name: doc.name,
    places: doc.places.map((place) => ({
      name: place.name,
      accepts: [...place.accepts],
      ...(place.port === undefined ? {} : {port: place.port}),
      ...(place.description === undefined ? {} : {description: place.description}),
      ...(place.annotations === undefined ? {} : {annotations: place.annotations}),
    })),
    transitions: doc.transitions.map((transition) => ({
      name: transition.name,
      ...(transition.handler === undefined ? {} : {handler: transition.handler}),
      ...(transition.guard === undefined ? {} : {guard: transition.guard}),
      ...(transition.priority === undefined ? {} : {priority: transition.priority}),
      ...(transition.timer === undefined ? {} : {timer: transition.timer}),
      ...(transition.description === undefined ? {} : {description: transition.description}),
      ...(transition.annotations === undefined ? {} : {annotations: transition.annotations}),
      ...(transition.bindingNames === undefined ? {} : {bindingNames: transition.bindingNames}),
    })),
    arcs: doc.arcs.map((arc) => {
      if (arc.consume !== undefined) {
        return {
          from: {place: arc.fromPlace},
          to: {transition: arc.toTransition},
          consume: {
            type: arc.consume.type,
            mode: arc.consume.mode ?? "consume",
            weight: arc.consume.weight ?? 1,
            ...(arc.consume.correlate === undefined ? {} : {correlate: {cel: arc.consume.correlate}}),
          },
          ...(arc.description === undefined ? {} : {description: arc.description}),
          ...(arc.annotations === undefined ? {} : {annotations: arc.annotations}),
        };
      }
      return {
        from: {transition: arc.fromTransition},
        to: {place: arc.toPlace},
        produce: {
          type: arc.produce.type,
          destination: arc.produce.destination,
          ...(arc.produce.cel === undefined ? {} : {cel: arc.produce.cel}),
          ...(arc.produce.data === undefined ? {} : {data: arc.produce.data}),
        },
        ...(arc.description === undefined ? {} : {description: arc.description}),
        ...(arc.annotations === undefined ? {} : {annotations: arc.annotations}),
      };
    }),
    ...(doc.initialMarking === undefined ? {} : {initialMarking: doc.initialMarking}),
    ...(doc.annotations === undefined ? {} : {annotations: doc.annotations}),
    ...(doc.domains === undefined ? {} : {domains: doc.domains}),
    ...(doc.proofs === undefined
      ? {}
      : {
          proofs: {
            ...(doc.proofs.final === undefined ? {} : {final: doc.proofs.final}),
            ...(doc.proofs.invariants === undefined ? {} : {invariants: doc.proofs.invariants}),
          },
        }),
  };
}

function projectPlace(place) {
  return {
    name: place.name,
    accepts: [...place.accepts],
    ...(place.port === undefined ? {} : {port: {direction: place.port.direction, type: place.port.type}}),
    ...(place.description ? {description: place.description} : {}),
    ...(place.annotations ? {annotations: place.annotations} : {}),
  };
}

function projectTransition(transition) {
  const timer = transition.timer === undefined
    ? undefined
    : {
        clock: transition.timer.clock,
        cel: transition.timer.cel,
        ...(transition.timer.bind ? {bind: {...transition.timer.bind}} : {}),
        ...(transition.timer.maturity ? {maturity: transition.timer.maturity} : {}),
      };
  return {
    name: transition.name,
    ...(transition.handler === undefined ? {} : {handler: transition.handler}),
    ...(transition.guard === undefined ? {} : {guard: transition.guard}),
    ...(transition.priority === undefined ? {} : {priority: transition.priority}),
    ...(timer === undefined ? {} : {timer}),
    ...(transition.description ? {description: transition.description} : {}),
    ...(transition.annotations ? {annotations: transition.annotations} : {}),
    ...(transition.bindingNames ? {bindingNames: {...transition.bindingNames}} : {}),
  };
}

function projectArc(arc) {
  if (arc.consume !== undefined) {
    return {
      fromPlace: arc.from.place,
      toTransition: arc.to.transition,
      consume: {
        type: arc.consume.type,
        mode: arc.consume.mode,
        weight: arc.consume.weight,
        ...(arc.consume.correlate === undefined ? {} : {correlate: arc.consume.correlate.cel}),
      },
      ...(arc.description ? {description: arc.description} : {}),
      ...(arc.annotations ? {annotations: arc.annotations} : {}),
    };
  }
  return {
    fromTransition: arc.from.transition,
    toPlace: arc.to.place,
    produce: {
      type: arc.produce.type,
      destination: arc.produce.destination,
      ...(arc.produce.cel === undefined ? {} : {cel: arc.produce.cel}),
      ...(arc.produce.data === undefined ? {} : {data: arc.produce.data}),
    },
    ...(arc.description ? {description: arc.description} : {}),
    ...(arc.annotations ? {annotations: arc.annotations} : {}),
  };
}

function projectProofs(proofs) {
  if (proofs === undefined) return undefined;
  const projected = {};
  if (proofs.final !== undefined && proofs.final.length > 0) {
    projected.final = proofs.final.map((entry) => (typeof entry === "string" ? [entry] : [...entry]));
  }
  if (proofs.invariants !== undefined && proofs.invariants.length > 0) {
    projected.invariants = proofs.invariants.map((invariant) => ({
      weights: {...invariant.weights},
      ...(invariant.constant === undefined ? {} : {constant: invariant.constant}),
      ...(invariant.name === undefined ? {} : {name: invariant.name}),
    }));
  }
  return Object.keys(projected).length === 0 ? undefined : projected;
}

function projectNet(net, fusion) {
  const proofs = projectProofs(net.proofs);
  return {
    name: net.name,
    places: net.places.map(projectPlace),
    transitions: net.transitions.map(projectTransition),
    arcs: net.arcs.map(projectArc),
    fusion: [...fusion.entries()].sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0)),
    ...(net.initialMarking === undefined
      ? {}
      : {
          initialMarking: Object.fromEntries(
            Object.entries(net.initialMarking).map(([place, tokens]) => [
              place,
              tokens.map((token) => ({type: token.type, data: {...token.data}})),
            ]),
          ),
        }),
    ...(net.domains === undefined || Object.keys(net.domains).length === 0
      ? {}
      : {domains: Object.fromEntries(Object.entries(net.domains).map(([key, values]) => [key, [...values]]))}),
    ...(proofs === undefined ? {} : {proofs}),
    ...(net.annotations ? {annotations: net.annotations} : {}),
  };
}

function projectCases() {
  return cases.cases.map((spec) => {
    const nets = new Map(Object.entries(spec.nets).map(([alias, doc]) => [alias, netFrom(doc)]));
    try {
      const merged = mergeNets(
        nets,
        spec.wires,
        spec.refinements,
        spec.shares,
        spec.mergeName,
        spec.final ?? undefined,
      );
      const fusion = portFusionMap(nets, spec.wires, spec.shares);
      return {...projectNet(merged, fusion), name: spec.name, netName: merged.name};
    } catch (error) {
      if (!(error instanceof NetValidationError)) throw error;
      return {name: spec.name, error: error.message};
    }
  });
}

describe("mergeNets", () => {
  it("fuses a single wire on the output port", () => {
    // given: a producer output wired to a consumer input
    const spec = projectCases().find((item) => item.name === "single-wire");
    // then: both ports are the output's qualified name
    assert.deepEqual(spec.fusion, [["cons.inbox", "prod.out"], ["prod.out", "prod.out"]]);
    const fused = spec.places.find((place) => place.name === "prod.out");
    assert.equal(fused.port, undefined);
    assert.deepEqual(fused.accepts, ["task", "note"]);
    assert.equal(fused.description, "from prod");
    assert.equal(fused.annotations.fusion, true);
    assert.equal(fused.annotations.lane, "prod");
    assert.equal(fused.annotations.extra, "sink");
    const take = spec.transitions.find((item) => item.name === "cons.take");
    assert.deepEqual(take.bindingNames, {inbox: "prod.out"});
  });

  it("names a fan-in place after every output", () => {
    // given / when: two outputs wired to one input
    const spec = projectCases().find((item) => item.name === "fan-in");
    // then: the fused name sorts the output ports
    assert.deepEqual(spec.fusion, [
      ["left.out", "left.out__right.out"],
      ["right.out", "left.out__right.out"],
      ["sink.inbox", "left.out__right.out"],
    ]);
  });

  it("fuses a share of places that are not ports", () => {
    // given / when: two buffers shared, with no wire
    const spec = projectCases().find((item) => item.name === "share");
    // then: the place is named after both members
    assert.deepEqual(spec.fusion, [
      ["alpha.buf", "alpha.buf__beta.buf"],
      ["beta.buf", "alpha.buf__beta.buf"],
    ]);
    const fused = spec.places.find((place) => place.name === "alpha.buf__beta.buf");
    assert.equal(fused.description, "alpha");
  });

  it("removes a refined transition", () => {
    // given / when: courier refines shop.deliver
    const spec = projectCases().find((item) => item.name === "refinement");
    // then: deliver and its arcs are gone
    assert.deepEqual(spec.transitions.map((item) => item.name), [
      "shop.send",
      "courier.pick",
      "courier.drop",
    ]);
    assert.equal(spec.arcs.some((arc) => JSON.stringify(arc).includes("shop.deliver")), false);
  });

  it("rejects the shared conflict messages", () => {
    // given / when: the fixture's rejected merges
    const errors = Object.fromEntries(
      projectCases().filter((item) => item.error !== undefined).map((item) => [item.name, item.error]),
    );
    // then: TypeScript and the fixture name the same conflicts
    assert.equal(errors["domain-conflict"], "domain task.kind differs between a and b");
    assert.equal(errors["actor-conflict"], "actor clerk is a human in one net and a system in b");
    assert.equal(errors["refinement-unknown"], "refine shop.[deliver] by ghost: unknown alias ghost");
  });

  it("mergeComposition delegates to the same nets", () => {
    // given: the single-wire nets already parsed
    const spec = cases.cases.find((item) => item.name === "single-wire");
    const nets = new Map(Object.entries(spec.nets).map(([alias, doc]) => [alias, netFrom(doc)]));
    const direct = mergeNets(nets, spec.wires, [], [], "wired");
    // when: mergeComposition is given those nets
    const merged = mergeComposition(
      {name: "wired", nets: [], wires: spec.wires, shares: [], refinements: []},
      nets,
    );
    // then: the place names match
    assert.deepEqual(merged.places.map((place) => place.name), direct.places.map((place) => place.name));
    assert.equal(merged.name, "wired");
  });

  it("matches the Python agreement projection", () => {
    // given: the oracle Python wrote for these fixtures
    const actual = projectCases();
    const expected = JSON.parse(readFileSync(resolve(fixtures, "agreement.json"), "utf8"));
    // then: TypeScript produces the same projection
    assert.deepEqual(actual, expected);
  });
});
