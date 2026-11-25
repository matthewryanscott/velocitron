// @ts-expect-error -- Node globals are provided by the Vitest process; the
// browser-safe production package intentionally does not depend on @types/node.
import {readFileSync} from "node:fs";
// @ts-expect-error -- See the node:fs import above.
import {fileURLToPath} from "node:url";
import {describe, expect, it} from "vitest";
import {resolveContributionIr, validateContributionIr} from "@velocitron/petrinet";
import {compilePetrinetText} from "@velocitron/petrinet";
import {
  PetrinetDslError,
  type Diagnostic,
  type SourceSpan,
} from "@velocitron/dsl";
import {
  lowerPetrinetText,
  type ContributionIr,
} from "@velocitron/dsl";
import type {ReadonlyJsonObject} from "@velocitron/engine";

interface SourceFixture {
  readonly sourceId: string;
  readonly text: string;
}

interface ValidFixture {
  readonly canonicalComposition?: string;
  readonly canonicalNet?: string;
  readonly canonicalSource: string;
  readonly contributionIr: string;
  readonly expect: {
    readonly source?: string;
    readonly canonicalSourceFixedPoint: true;
  };
}

interface InvalidFixture {
  readonly expectation: string;
  id: string;
  readonly owner?: string;
  readonly phase: "parse" | "resolution";
  readonly structureParses: boolean;
}

interface ManifestCase {
  readonly id: string;
  readonly invalid?: readonly InvalidFixture[];
  readonly valid: ValidFixture;
}

interface Manifest {
  readonly cases: readonly ManifestCase[];
  readonly format: string;
  readonly version: number;
}

interface FixturePosition {
  readonly byteOffset: number;
  readonly column: number;
  readonly line: number;
}

interface FixtureSpan {
  readonly end: FixturePosition;
  readonly source: string;
  readonly start: FixturePosition;
}

interface FixtureDiagnostic {
  readonly code: string;
  readonly column: number;
  readonly file: string;
  readonly help?: string;
  readonly line: number;
  readonly message: string;
  readonly related?: readonly {
    readonly message: string;
    readonly span: FixtureSpan;
  }[];
  readonly span: FixtureSpan;
}

interface SourceInvalidExpectation {
  readonly diagnostic: FixtureDiagnostic;
  readonly source: SourceFixture;
}

interface NetInvalidExpectation {
  readonly diagnostic: FixtureDiagnostic;
  readonly net: ReadonlyJsonObject;
}

const corpusDirectory = fileURLToPath(
  new URL("../../../../packages/spec/conformance/petrinet/", import.meta.url),
);

function readText(relativePath: string): string {
  return readFileSync(`${corpusDirectory}/${relativePath}`, "utf8");
}

function readJson<T>(relativePath: string): T {
  return JSON.parse(readText(relativePath)) as T;
}

const manifest = readJson<Manifest>("manifest.json");
const validCases = manifest.cases.map((entry) => ({
  id: entry.id,
  fixture: entry.valid,
}));
const invalidCases = manifest.cases.flatMap((entry) =>
  (entry.invalid ?? []).map((fixture) => ({
    caseId: entry.id,
    fixture,
    id: `${entry.id}/${fixture.id}`,
  })),
);

const parseCaseIds = invalidCases
  .filter(({fixture}) => fixture.phase === "parse")
  .map(({id}) => id);

function validSource(fixture: ValidFixture): SourceFixture {
  return readJson<SourceFixture>(fixture.expect.source ?? fixture.canonicalSource);
}


function canonicalDocumentPath(fixture: ValidFixture): string {
  const path = fixture.canonicalNet ?? fixture.canonicalComposition;
  if (path === undefined) throw new Error("valid fixture lacks a canonical document");
  return path;
}

function serializeSpan(span: SourceSpan): FixtureSpan {
  return {
    end: {
      byteOffset: span.end.offset,
      column: span.end.column,
      line: span.end.line,
    },
    source: span.source,
    start: {
      byteOffset: span.start.offset,
      column: span.start.column,
      line: span.start.line,
    },
  };
}

function serializeDiagnostic(diagnostic: Diagnostic): FixtureDiagnostic {
  return {
    code: diagnostic.code,
    column: diagnostic.span.start.column,
    file: diagnostic.span.source,
    ...(diagnostic.help === undefined ? {} : {help: diagnostic.help}),
    line: diagnostic.span.start.line,
    message: diagnostic.message,
    ...(diagnostic.related === undefined
      ? {}
      : {
          related: diagnostic.related.map((item) => ({
            message: item.message,
            span: serializeSpan(item.span),
          })),
        }),
    span: serializeSpan(diagnostic.span),
  };
}

function captureDiagnostic(source: SourceFixture): FixtureDiagnostic {
  try {
    compilePetrinetText(source.text, source.sourceId);
  } catch (error) {
    expect(error).toBeInstanceOf(PetrinetDslError);
    return serializeDiagnostic((error as PetrinetDslError).diagnostic);
  }
  throw new Error(`expected ${source.sourceId} to produce a DSL diagnostic`);
}

const sourceInvalidCases = invalidCases.filter(({fixture}) => {
  const expectation = readJson<SourceInvalidExpectation | NetInvalidExpectation>(
    fixture.expectation,
  );
  return "source" in expectation;
});
const resolvedNetCases = invalidCases.filter(({fixture}) => {
  const expectation = readJson<SourceInvalidExpectation | NetInvalidExpectation>(
    fixture.expectation,
  );
  return "net" in expectation;
});
const compositionLoaderCases = sourceInvalidCases.filter(
  ({fixture}) => fixture.owner === "composition-loader",
);
const compilerDiagnosticCases = sourceInvalidCases.filter(
  ({fixture}) => fixture.owner !== "composition-loader",
);

describe("SIM-06 conformance manifest coverage", () => {
  it("pins the manifest identity and exhaustive case counts", () => {
    expect(manifest).toMatchObject({
      format: "velocitron.petrinet/conformance-corpus",
      version: 1,
    });
    expect(validCases).toHaveLength(42);
    expect(invalidCases).toHaveLength(119);
    expect(sourceInvalidCases).toHaveLength(98);
    expect(resolvedNetCases).toHaveLength(21);
    expect(compilerDiagnosticCases).toHaveLength(89);
    expect(compositionLoaderCases).toHaveLength(9);
  });

  it("pins the parse-phase group to manifest data", () => {
    expect(parseCaseIds).toHaveLength(16);
  });

  it("keeps resolved-net fixtures downstream and source-free", () => {
    expect(resolvedNetCases).toHaveLength(21);
    expect(
      resolvedNetCases.every(
        ({fixture}) =>
          fixture.phase === "resolution" && fixture.structureParses,
      ),
    ).toBe(true);
  });

  it("keeps composition-loader diagnostics downstream of compilation", () => {
    expect(compositionLoaderCases).toHaveLength(9);
    expect(
      compositionLoaderCases.every(
        ({fixture}) =>
          fixture.owner === "composition-loader" &&
          fixture.phase === "resolution" &&
          fixture.structureParses,
      ),
    ).toBe(true);
  });
});

describe("valid corpus lowering", () => {
  it.each(validCases)("$id lowers to the complete Contribution IR", ({fixture}) => {
    const source = validSource(fixture);
    const expected = readJson<ContributionIr>(fixture.contributionIr);

    const actual = lowerPetrinetText(source.text, source.sourceId);
    expect(actual).toEqual(expected);
    expect(validateContributionIr(actual)).toEqual({ok: true});
  });
});

describe("valid corpus resolution", () => {
  it.each(validCases)("$id resolves fixture IR to canonical JSON", ({fixture}) => {
    const contributionIr = readJson<ContributionIr>(fixture.contributionIr);
    const documentPath = canonicalDocumentPath(fixture);
    const expected = readJson<ReadonlyJsonObject>(documentPath);

    expect(resolveContributionIr(contributionIr)).toEqual(expected);
  });
});


describe("valid corpus public compilation", () => {
  it.each(validCases)("$id compiles with its document kind and full document", ({fixture}) => {
    const source = validSource(fixture);
    const documentPath = canonicalDocumentPath(fixture);
    const expected = readJson<ReadonlyJsonObject>(documentPath);
    const compiled = compilePetrinetText(source.text, source.sourceId);

    expect(compiled.documentKind).toBe(
      fixture.canonicalNet === undefined ? "composition" : "net",
    );
    expect(compiled.document).toEqual(expected);
  });
});

describe("canonical corpus source", () => {
  it.each(validCases)("$id compiles the committed canonical source", ({fixture}) => {
    expect(fixture.expect.canonicalSourceFixedPoint).toBe(true);
    const source = readJson<SourceFixture>(fixture.canonicalSource);
    const expected = readJson<ReadonlyJsonObject>(canonicalDocumentPath(fixture));
    const compiled = compilePetrinetText(source.text, source.sourceId);

    expect(compiled.documentKind).toBe(
      fixture.canonicalNet === undefined ? "composition" : "net",
    );
    expect(compiled.document).toEqual(expected);
  });
});

describe("invalid corpus diagnostics owned by the compiler", () => {
  it.each(compilerDiagnosticCases)(
    "$id serializes the exact $fixture.phase diagnostic",
    ({fixture}) => {
      const expectation = readJson<SourceInvalidExpectation>(fixture.expectation);

      expect(captureDiagnostic(expectation.source)).toEqual(expectation.diagnostic);
      expect(fixture.structureParses).toBe(fixture.phase !== "parse");
    },
  );
});

describe("invalid corpus cases owned by downstream stages", () => {
  it.each(compositionLoaderCases)(
    "$id compiles structurally and remains a composition-loader diagnostic",
    ({fixture}) => {
      const expectation = readJson<SourceInvalidExpectation>(fixture.expectation);
      const compiled = compilePetrinetText(
        expectation.source.text,
        expectation.source.sourceId,
      );

      expect(fixture.phase).toBe("resolution");
      expect(fixture.structureParses).toBe(true);
      expect(compiled.documentKind).toBe("composition");
    },
  );

  it.each(compositionLoaderCases)(
    "$id is the committed diagnostic at the fact once the nets load",
    ({fixture}) => {
      // given: a loader that compiles `<name>.source.json` beside the fixture
      const expectation = readJson<SourceInvalidExpectation>(fixture.expectation);
      const directory = fixture.expectation.slice(0, fixture.expectation.lastIndexOf("/"));
      const loadRef = (ref: string): unknown => {
        const sibling = readJson<SourceFixture>(
          `${directory}/${ref.replace(/\.petrinet$/u, ".source.json")}`,
        );
        return compilePetrinetText(sibling.text, sibling.sourceId).document;
      };

      // when: the composition compiles with its nets loaded
      let diagnostic: FixtureDiagnostic | undefined;
      try {
        compilePetrinetText(expectation.source.text, expectation.source.sourceId, {loadRef});
      } catch (error) {
        expect(error).toBeInstanceOf(PetrinetDslError);
        diagnostic = serializeDiagnostic((error as PetrinetDslError).diagnostic);
      }

      // then: the serialized diagnostic is the committed one
      expect(diagnostic).toEqual(expectation.diagnostic);
    },
  );

  it.each(resolvedNetCases)(
    "$id is represented only by a resolved-net fixture",
    ({fixture}) => {
      const expectation = readJson<NetInvalidExpectation>(fixture.expectation);

      expect(fixture.phase).toBe("resolution");
      expect(fixture.structureParses).toBe(true);
      expect(expectation).toHaveProperty("net");
      expect(expectation).not.toHaveProperty("source");
    },
  );
});
