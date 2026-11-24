import {describe, expect, it} from "vitest";

import type {Net} from "@velocitron/engine";
import {
  mergeNets,
  NetValidationError,
  parseNet,
} from "@velocitron/petrinet";

// Actors through the merge (ADR 0038): a transition without an `actor`
// annotation takes its net's default actor, and every constituent's declared
// actors land on the merged net. Messages match the Python `merge_nets`.

function stage(
  name: string,
  annotations: Record<string, unknown>,
  stepAnnotations?: Record<string, unknown>,
): Net {
  return parseNet({
    name,
    annotations,
    places: [
      {name: "start", accepts: ["job"]},
      {name: "done", accepts: ["job"]},
    ],
    transitions: [
      {name: "step", ...(stepAnnotations === undefined ? {} : {annotations: stepAnnotations})},
      {name: "skip"},
    ],
    arcs: [
      {from: {place: "start"}, to: {transition: "step"}, consume: {type: "job"}},
      {from: {transition: "step"}, to: {place: "done"}, produce: {type: "job", destination: "done"}},
      {from: {place: "start"}, to: {transition: "skip"}, consume: {type: "job"}},
      {from: {transition: "skip"}, to: {place: "done"}, produce: {type: "job", destination: "done"}},
    ],
  });
}

describe("merge carries actors (ADR 0038)", () => {
  it("stamps the net default on bare transitions and merges declared actors", () => {
    // given: two nets, each with a default actor and declarations; one transition overrides
    const old = stage(
      "old",
      {actor: "Annex", actors: [{name: "Annex", kind: "system"}, {name: "Operator", kind: "person"}]},
      {actor: "Operator", lane: "manual"},
    );
    const fresh = stage("fresh", {
      actor: "Main",
      actors: [{name: "Main", kind: "system"}, {name: "Operator", kind: "person"}],
    });

    // when: the nets merge without wires
    const merged = mergeNets(new Map([["old", old], ["fresh", fresh]]), []);

    // then: a transition keeps its own actor; the others take their net's default
    const actors = Object.fromEntries(
      merged.transitions.map((transition) => [transition.name, transition.annotations]),
    );
    expect(actors).toEqual({
      "old.step": {actor: "Operator", lane: "manual"},
      "old.skip": {actor: "Annex"},
      "fresh.step": {actor: "Main"},
      "fresh.skip": {actor: "Main"},
    });
    // and: the merged net lists every declared actor once, first declaration first
    expect(merged.annotations).toEqual({
      actors: [
        {name: "Annex", kind: "system"},
        {name: "Operator", kind: "person"},
        {name: "Main", kind: "system"},
      ],
    });
  });

  it("leaves transitions and the merged net bare when no net names an actor", () => {
    // given: two nets with no actor facts
    // when: they merge
    const merged = mergeNets(new Map([["a", stage("a", {})], ["b", stage("b", {})]]), []);

    // then: nothing gains an actor annotation
    expect(merged.transitions.every((transition) => transition.annotations === undefined)).toBe(
      true,
    );
    expect(merged.annotations).toBeUndefined();
  });

  it("rejects an actor that is a person in one net and a system in another", () => {
    // given: Operator declared with different kinds
    const left = stage("left", {actors: [{name: "Operator", kind: "person"}]});
    const right = stage("right", {actors: [{name: "Operator", kind: "system"}]});

    // when/then: the merge reports the conflict in the Python wording
    const merge = (): Net => mergeNets(new Map([["left", left], ["right", right]]), []);
    expect(merge).toThrow(NetValidationError);
    expect(merge).toThrow("actor Operator is a person in one net and a system in right");
  });
});
