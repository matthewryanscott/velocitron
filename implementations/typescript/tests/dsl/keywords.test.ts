import {describe, expect, it} from "vitest";
import {VelocitronPetriNetLexer} from "@velocitron/dsl";
import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";

const KEYWORDS = VelocitronPetriNetLexer.literalNames
  .map((literal) => (literal ?? "").replaceAll("'", ""))
  .filter((word) => /^[A-Za-z]+$/.test(word) && !["true", "false", "null"].includes(word));

function timerNet(bindName: string): string {
  return [
    "net timed",
    "(waiting) -job-> [retry] -job-> (done)",
    "(clock) -tick->? [retry]",
    '[retry] timer clock (clock) cel "clock.now >= 1"',
    `[retry] timer bind ${bindName} (waiting)`,
    "",
  ].join("\n");
}

describe("keywords as names", () => {
  it.each(KEYWORDS)("%s names a place, a transition and a color", (keyword) => {
    // given: a net whose place, transition and color all use the bare keyword
    const text = `net named\n(${keyword}) -${keyword}-> [${keyword}]\n`;

    // when: compiling it
    const compiled = compilePetrinetText(text, "named.petrinet");

    // then: the keyword is an ordinary name everywhere
    expect(compiled.document.places).toEqual([{name: keyword, accepts: [keyword]}]);
    expect(compiled.document.transitions).toEqual([{name: keyword}]);
  });

  it.each(KEYWORDS.filter((keyword) => keyword !== "clock"))(
    "%s names a timer bind",
    (keyword) => {
      // given: a timer that binds its input token under a keyword
      // when: compiling it
      const compiled = compilePetrinetText(timerNet(keyword), "timed.petrinet");

      // then: the bind keeps the keyword as its name
      const transitions = compiled.document.transitions as {timer: {bind: unknown}}[];
      expect(transitions[0].timer.bind).toEqual({[keyword]: "waiting"});
    },
  );

  it("keeps clock reserved as a timer bind", () => {
    // given: a timer that binds a token under the clock's own name
    // when/then: resolution rejects the bind
    expect(() => compilePetrinetText(timerNet("clock"), "timed.petrinet")).toThrow(
      PetrinetDslError,
    );
  });

  it("reads a keyword net name whose header needs full-context prediction", () => {
    // given: a header that could also read as a net actor fact
    const text = 'net actor "Annex desk"\n(a) -> [b]\n';

    // when: compiling it
    const compiled = compilePetrinetText(text, "actor.petrinet");

    // then: the first statement is the header, as in Python
    expect(compiled.document.name).toBe("actor");
    expect(compiled.document.description).toBe("Annex desk");
  });

  it("reads a bare initial after marking as the initial marking", () => {
    // given: a place named initial, an initial marking and a named marking
    const text = [
      "net marked",
      "(initial) -> [start]",
      "marking initial (initial) <- 1",
      "marking order (initial) <- 2",
      "",
    ].join("\n");

    // when: compiling it
    const compiled = compilePetrinetText(text, "marked.petrinet");

    // then: the bare initial is the initial marking and order names a marking
    expect(compiled.document.initialMarking).toEqual({initial: [{type: "token", data: {}}]});
    const payload = (compiled.document.annotations as Record<string, Record<string, any>>)[
      "petrinet.dsl/v1"
    ];
    expect(Object.keys(payload.markings)).toEqual(["order"]);
  });
});
