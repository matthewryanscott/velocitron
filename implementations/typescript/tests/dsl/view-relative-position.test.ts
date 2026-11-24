import {resolveContributionIr, validateContributionIr} from "@velocitron/petrinet";
import {describe, expect, it} from "vitest";
import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";
import {lowerPetrinetText} from "@velocitron/dsl";

// Minimal net where one view's node sits relative to another.
const RELATIVE_NET = [
  "net laid_out",
  "(origin)",
  "(work)",
  'view board position (work) relative (origin) + {"x": 10, "y": 20}',
  "",
].join("\n");

const ABSOLUTE_NET = [
  "net laid_out",
  "(origin)",
  "(work)",
  'view board position (origin) at {"x": 0, "y": 0}',
  'view board position (work) at {"x": 30, "y": 40}',
  "",
].join("\n");

function relativeNet(base: string, subject: string): string {
  return `net laid_out\n(origin)\n(work)\n[step]\n(work) -go-> [step]\nview board position ${subject} relative ${base} + {"x": 1, "y": 2}\n`;
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

describe("view position relative fact", () => {
  it("lowers to the additive relativePosition oneOf alternative", () => {
    // given: a net positioning one node relative to another
    // when: lowering it to Contribution IR
    const ir = lowerPetrinetText(RELATIVE_NET, "board.petrinet");

    // then: the view.position contribution carries the tagged relative shape
    const fact = ir.contributions.find(
      (contribution) => contribution.kind === "view.position",
    );
    expect(fact).toMatchObject({
      target: {type: "view", name: "board"},
      value: {
        subject: {type: "place", name: "work"},
        position: {
          delta: {
            type: "object",
            entries: [
              {key: "x", value: {type: "number", lexeme: "10"}},
              {key: "y", value: {type: "number", lexeme: "20"}},
            ],
          },
          from: {type: "place", name: "origin"},
        },
      },
    });

    // and: the regenerated IR schema accepts the whole document
    expect(validateContributionIr(ir)).toEqual({ok: true});
  });

  it("resolves to the from-string payload shape owned by the compiler", () => {
    // given: the same relative net
    // when: compiling through the full pipeline
    const compiled = compilePetrinetText(RELATIVE_NET, "board.petrinet");

    // then: the canonical payload entry is resolved (from is a kind:name string)
    const payload = (compiled.document.annotations as Record<string, Record<string, any>>)[
      "petrinet.dsl/v1"
    ];
    expect(payload.views.board.positions["place:work"]).toEqual({
      from: "place:origin",
      delta: {x: 10, y: 20},
    });
  });

  it("rejects a relative fact whose base reference is malformed", () => {
    // given: a malformed Contribution IR position (from is not a plain target)
    const ir = lowerPetrinetText(RELATIVE_NET, "board.petrinet");
    const fact = ir.contributions.find(
      (contribution) => contribution.kind === "view.position",
    ) as unknown as {value: {position: Record<string, unknown>}};
    fact.value.position = {
      from: {type: "view", name: "nope", extra: true},
      delta: fact.value.position.delta,
    };

    // when/then: resolution diagnoses a PN200 shape error, not a crash
    expectDslDiagnostic(
      () => resolveContributionIr(ir),
      "PN200",
      "invalid view position contribution",
    );
  });

  it("rejects a malformed relative delta", () => {
    // given: a relative fact whose delta has a boolean member
    const text = relativeNet("(origin)", "(work)").replace(
      '{"x": 1, "y": 2}',
      '{"x": 1, "y": true}',
    );

    // when/then: resolution diagnoses the delta shape
    expectDslDiagnostic(
      () => compilePetrinetText(text, "board.petrinet"),
      "PN200",
      "invalid view position contribution",
    );
  });

  it("rejects an unknown relative base with PN202", () => {
    // given: a relative fact naming a base place that was never declared
    const text = relativeNet("(ghost)", "(work)");

    // when/then: resolution rejects the reference, not the syntax
    expectDslDiagnostic(
      () => compilePetrinetText(text, "board.petrinet"),
      "PN202",
      "view 'board' relative base references unknown place 'ghost'; presentation facts cannot declare semantic objects",
    );
  });

  it("keeps absolute view positions unchanged", () => {
    // given: a net using only absolute `at` positions
    // when: compiling it
    const compiled = compilePetrinetText(ABSOLUTE_NET, "board.petrinet");

    // then: the payload stays the exact {x, y} member shape
    const payload = (compiled.document.annotations as Record<string, Record<string, any>>)[
      "petrinet.dsl/v1"
    ];
    expect(payload.views.board.positions["place:origin"]).toEqual({x: 0, y: 0});
    expect(payload.views.board.positions["place:work"]).toEqual({x: 30, y: 40});
  });
});