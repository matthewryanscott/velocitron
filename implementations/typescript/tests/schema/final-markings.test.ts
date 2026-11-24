import {describe, expect, it} from "vitest";

import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";
import {
  mergeComposition,
  parseComposition,
  type CompositionLoader,
} from "@velocitron/petrinet";

// Final markings of more than one place, on a net and on a composition
// (ADR 0049). Mirrors implementations/python/tests/test_final_markings.py.

const TWO_SIDES = `net two_sides
(order) -> [split] -> (left_pending)
[split] -> (right_pending)
(left_pending) -> [left_done] -> (left_end)
(right_pending) -> [right_done] -> (right_end)
`;

const FIRST = `net first
(order) -> [split] -> (handed_on)
[split] -> (pending) -> [work] -> (end)
(handed_on) port output token
final (end)
`;

const SECOND = `net second
(start) -> [work] -> (end)
(start) port input token
final (end)
`;

const BOTH_SIDES = `composition both_sides
use "first.petrinet" as first
use "second.petrinet" as second
wire first.(handed_on) -> second.(start)
`;

const FILES: Record<string, string> = {
  "first.petrinet": FIRST,
  "second.petrinet": SECOND,
};

function compile(source: string, sourceId = "net.petrinet"): Record<string, unknown> {
  return compilePetrinetText(source, sourceId).document as Record<string, unknown>;
}

const loader: CompositionLoader = (ref) => compile(FILES[ref]!, ref);

function diagnostic(run: () => unknown): {code: string; message: string} {
  try {
    run();
  } catch (error: unknown) {
    if (error instanceof PetrinetDslError) {
      return {code: error.diagnostic.code, message: error.diagnostic.message};
    }
    throw error;
  }
  throw new Error("expected a PetrinetDslError");
}

describe("a net's final markings", () => {
  it("lower a marking of two places to a list and keep one place a string", () => {
    // when
    const document = compile(`${TWO_SIDES}final (left_end) + (right_end), (left_end)\n`);

    // then
    expect(document.proofs).toEqual({final: [["left_end", "right_end"], "left_end"]});
  });

  it.each([
    ["final (left_end) + (left_end)", "final names (left_end) more than once in one marking"],
    [
      "final (left_end) + (right_end), (right_end) + (left_end)",
      "final names (right_end) + (left_end) more than once",
    ],
  ])("name each marking and place once: %s", (fact, message) => {
    // when
    const result = diagnostic(() => compile(`${TWO_SIDES}${fact}\n`));

    // then
    expect(result).toEqual({code: "PN202", message});
  });
});

describe("a composition's final markings", () => {
  it("replace the final places of its nets in the merged net", () => {
    // given
    const document = compile(`${BOTH_SIDES}final first.(end) + second.(end)\n`, "both.petrinet");

    // when
    const parsed = parseComposition(document, {loadRef: loader});
    const merged = mergeComposition(parsed.document, parsed.parsedNets);

    // then
    expect(document.final).toEqual([
      [
        {net: "first", place: "end"},
        {net: "second", place: "end"},
      ],
    ]);
    expect(merged.proofs?.final).toEqual([["first.end", "second.end"]]);
  });

  it("leave each net's final places when the composition declares none", () => {
    // given
    const parsed = parseComposition(compile(BOTH_SIDES, "both.petrinet"), {loadRef: loader});

    // when
    const merged = mergeComposition(parsed.document, parsed.parsedNets);

    // then
    expect(merged.proofs?.final).toEqual(["first.end", "second.end"]);
  });

  it("must name declared places", () => {
    // when
    const result = diagnostic(() =>
      compilePetrinetText(`${BOTH_SIDES}final first.(end) + second.(finish)\n`, "both.petrinet", {
        loadRef: loader,
      }),
    );

    // then
    expect(result).toEqual({
      code: "PN202",
      message: "final first.(end) + second.(finish): net 'second' has no place named 'finish'",
    });
  });
});
