import {describe, expect, it} from "vitest";
import {
  PETRINET_RESOURCE_LIMITS,
  PetrinetDslError,
  PetrinetResourceError,
} from "@velocitron/dsl";
import {SourceMap} from "@velocitron/dsl";

describe("DSL source coordinates and diagnostics", () => {
  it("maps UTF-16 indices to UTF-8 and Unicode-scalar CRLF positions", () => {
    const source = new SourceMap("scalar.petrinet", "a😀\r\n雪");

    expect(source.position(1)).toEqual({offset: 1, line: 1, column: 2});
    expect(source.position(2)).toEqual({offset: 1, line: 1, column: 2});
    expect(source.position(3)).toEqual({offset: 5, line: 1, column: 3});
    expect(source.position(4)).toEqual({offset: 6, line: 1, column: 4});
    expect(source.position(5)).toEqual({offset: 7, line: 2, column: 1});
    expect(source.eofSpan()).toEqual({
      source: "scalar.petrinet",
      start: {offset: 10, line: 2, column: 2},
      end: {offset: 10, line: 2, column: 2},
    });
  });

  it("renders the stable primary/help diagnostic and keeps resources distinct", () => {
    const span = new SourceMap("bad.petrinet", "bad").span(0, 3);
    const error = new PetrinetDslError({
      code: "PN101",
      message: "bad statement",
      span,
      help: "write a declaration",
      related: [{message: "first declaration", span}],
    });

    expect(error.message).toBe(
      "bad.petrinet:1:1: error[PN101]: bad statement\nhelp: write a declaration",
    );
    expect(error.diagnostic.related).toHaveLength(1);
    expect(Object.isFrozen(error.diagnostic)).toBe(true);

    const resource = new PetrinetResourceError("lexerTokens");
    expect(resource).not.toBeInstanceOf(PetrinetDslError);
    expect(resource.limit).toBe(PETRINET_RESOURCE_LIMITS.lexerTokens);
  });
});
