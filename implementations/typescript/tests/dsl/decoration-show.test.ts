import {resolveContributionIr} from "@velocitron/petrinet";
import {describe, expect, it} from "vitest";
import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";
import {lowerPetrinetText} from "@velocitron/dsl";

const SHOWN_NET = [
  "net shown",
  "(queued) -job-> [start]",
  "decorate color job quiet",
  'decorate color job show "id" "owner.name"',
  "",
].join("\n");

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

describe("decorate color show", () => {
  it("resolves to the color's field paths beside quiet", () => {
    // given: a net that quiets job and shows two of its fields
    // when: compiling through the full pipeline
    const compiled = compilePetrinetText(SHOWN_NET, "shown.petrinet");

    // then: the color entry carries both facts, with paths in source order
    const payload = (compiled.document.annotations as Record<string, Record<string, any>>)[
      "petrinet.dsl/v1"
    ];
    expect(payload.decorations["color:job"]).toEqual({
      quiet: true,
      show: ["id", "owner.name"],
    });
  });

  it("keeps show usable as a name", () => {
    // given: a net whose place and color are both named show
    const text = "net shown\n(show) -show-> [start]\n";

    // when: compiling it
    const compiled = compilePetrinetText(text, "shown.petrinet");

    // then: the keyword did not steal the names
    expect(compiled.document.places).toEqual([{name: "show", accepts: ["show"]}]);
  });

  it.each([[[]], [["a..b"]], [[".a"]], [["a."]], [[""]], [["id", "id"]], [[1]]])(
    "rejects imported show fields %j",
    (fields) => {
      // given: lowered IR whose show fact carries a bad field list
      const ir = lowerPetrinetText(SHOWN_NET, "shown.petrinet");
      const fact = ir.contributions.find(
        (contribution) => contribution.kind === "decoration.show",
      ) as unknown as {value: {fields: unknown}};
      fact.value.fields = fields;

      // when/then: resolution rejects the closed kind
      expectDslDiagnostic(
        () => resolveContributionIr(ir),
        "PN200",
        "invalid show decoration contribution",
      );
    },
  );
});
