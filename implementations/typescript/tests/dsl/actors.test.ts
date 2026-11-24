import {describe, expect, it} from "vitest";
import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";
import {parseNet} from "@velocitron/petrinet";
import type {Net} from "@velocitron/engine";

// Actor facts (ADR 0038): `X actor Name` is an ordinary `actor` annotation;
// `person`/`system` lines declare the net's actors.

const DESK = [
  "net desk",
  "",
  "person Clerk",
  "system Annex",
  "",
  "(running) -> [stop] -> (stopped)",
  "(stopped) -> [flip] -> (running)",
  "",
  "net actor Annex",
  "[flip] actor Clerk",
  "(stopped) actor Clerk",
  "",
].join("\n");

function compileNet(source: string): Net {
  return parseNet(compilePetrinetText(source, "desk.petrinet").document);
}

function expectDslDiagnostic(
  action: () => unknown,
  code: string,
  message: string,
): void {
  try {
    action();
  } catch (error) {
    expect(error).toBeInstanceOf(PetrinetDslError);
    expect((error as PetrinetDslError).diagnostic).toMatchObject({code, message});
    return;
  }
  throw new Error("expected a Petri-net DSL diagnostic");
}

describe("actor facts (ADR 0038)", () => {
  it("compiles a net default, a transition override, and declared actors", () => {
    // given: a net with a default actor, an overriding transition, and two declarations
    // when: the source is compiled
    const net = compileNet(DESK);

    // then: the net carries its default actor and the declarations in order
    expect(net.annotations).toEqual({
      actor: "Annex",
      actors: [
        {name: "Clerk", kind: "person"},
        {name: "Annex", kind: "system"},
      ],
    });
    // and: only the annotated transition and place carry an actor of their own
    const transitions = Object.fromEntries(
      net.transitions.map((transition) => [transition.name, transition.annotations]),
    );
    expect(transitions).toEqual({stop: undefined, flip: {actor: "Clerk"}});
    const places = Object.fromEntries(
      net.places.map((place) => [place.name, place.annotations]),
    );
    expect(places).toEqual({running: undefined, stopped: {actor: "Clerk"}});
  });

  it("keeps a repeated equal declaration once", () => {
    // given: Clerk declared twice as a person
    const source = DESK.replace("person Clerk", "person Clerk\nperson Clerk");

    // when: the source is compiled
    const net = compileNet(source);

    // then: the declaration list is unchanged
    expect(net.annotations?.actors).toEqual([
      {name: "Clerk", kind: "person"},
      {name: "Annex", kind: "system"},
    ]);
  });

  it("rejects one actor declared as a person and as a system", () => {
    // given: Clerk declared as both kinds
    const source = DESK.replace("person Clerk", "person Clerk\nsystem Clerk");

    // when/then: resolution reports the conflict in the Python wording
    expectDslDiagnostic(
      () => compilePetrinetText(source, "desk.petrinet"),
      "PN202",
      "conflicting actor declarations for 'Clerk'",
    );
  });

  it("rejects an empty actor name", () => {
    // given: a transition assigned the empty quoted name
    const source = DESK.replace("[flip] actor Clerk", '[flip] actor ""');

    // when/then: lowering reports the empty name
    expectDslDiagnostic(
      () => compilePetrinetText(source, "desk.petrinet"),
      "PN202",
      "an actor name must not be empty",
    );
  });
});
