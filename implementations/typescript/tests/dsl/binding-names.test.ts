import {describe, expect, it} from "vitest";
import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";

describe("bind facts", () => {
  it("resolve to the transition's binding names", () => {
    // given: a transition that binds its input under a local name
    const text = 'net n\n("x.a") -> ["x.go"] -> ("x.b")\n["x.go"] bind a ("x.a")\n';

    // when: compiling it
    const compiled = compilePetrinetText(text, "n.petrinet");

    // then: the key reads the place
    expect(compiled.document.transitions).toEqual([{name: "x.go", bindingNames: {a: "x.a"}}]);
  });

  it.each([
    ["[nowhere] bind a (a)", "binding name refers to unknown transition [nowhere]"],
    [
      "[go] bind a (b)",
      "binding names on transition [go] must name exactly the places it consumes or reads",
    ],
    ["[go] bind a (a)\n[go] bind a (c)", "conflicting binding name facts for 'a' on transition [go]"],
  ])("are checked against the net: %s", (fact, message) => {
    // given: [go] consumes a and produces b
    const text = `net n\n(a) -> [go] -> (b)\n(c)\n${fact}\n`;

    // when/then: resolution reports the fact
    try {
      compilePetrinetText(text, "n.petrinet");
    } catch (error) {
      expect(error).toBeInstanceOf(PetrinetDslError);
      expect((error as PetrinetDslError).diagnostic).toMatchObject({code: "PN202", message});
      return;
    }
    throw new Error("expected a Petri-net DSL diagnostic");
  });
});
