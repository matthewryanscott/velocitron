import {describe, expect, it} from "vitest";

import {compilePetrinetText} from "@velocitron/petrinet";
import {PetrinetDslError} from "@velocitron/dsl";
import {
  mergeComposition,
  NetValidationError,
  parseComposition,
  type CompositionLoader,
} from "@velocitron/petrinet";

// Shared places and compositions used inside compositions (spec/composition.md;
// ADR 0040, ADR 0041). Mirrors implementations/python/tests/
// test_composition_share_nest.py: `take` starts a job when the lock is free,
// `give` ends it and gives the lock back, and the two nets share the lock.
// `worker` refines the abstract [work] of `give`. The pair is also used as
// one constituent of an outer composition. Messages match the Python parser.

const TAKE = `net take "Start a job when the lock is free"
(todo) -job-> [take] -job-> (busy)
@lock_in: (lock) -key-> [take]
(lock) annotation fusion true
(busy) port output job
`;

const GIVE = `net give "Work the job, end it and give the lock back"
(busy) -job-> [work] -job-> (worked)
(worked) -job-> [give] -job-> (done)
@unlock: [give] -key-> (lock)
@unlock data {}
(busy) port input job
(worked) port input job
(done) port output job
`;

const PAIR = `composition pair
use "take.petrinet" as take
use "give.petrinet" as give
wire take.(busy) -> give.(busy)
share take.(lock) ~ give.(lock)
`;

const NESTED = `composition nested
use "pair.petrinet" as pair
use "worker.petrinet" as worker
wire pair.(take.busy) -> worker.(start)
wire worker.(end) -> pair.(give.worked)
refine pair.[give.work] by worker
`;

const WORKER = `net worker "The work, in detail"
(start) -job-> [do] -job-> (end)
(start) port input job
(end) port output job
`;

const FILES: Record<string, string> = {
  "take.petrinet": TAKE,
  "give.petrinet": GIVE,
  "pair.petrinet": PAIR,
  "nested.petrinet": NESTED,
  "worker.petrinet": WORKER,
};

function compile(source: string, sourceId = "composition.petrinet"): Record<string, unknown> {
  return compilePetrinetText(source, sourceId).document as Record<string, unknown>;
}

function loader(files: Record<string, string>, seen: string[] = []): CompositionLoader {
  return (ref) => {
    seen.push(ref);
    const source = files[ref];
    if (source === undefined) throw new Error(`no file ${ref}`);
    return compile(source, ref);
  };
}

function failure(run: () => unknown): {code: string; message: string} {
  try {
    run();
  } catch (error: unknown) {
    if (error instanceof NetValidationError) {
      const issue = error.issues[0]!;
      return {code: issue.code, message: issue.message};
    }
    throw error;
  }
  throw new Error("expected a NetValidationError");
}

describe("share", () => {
  it("fuses places that are not ports", () => {
    // given
    const parsed = parseComposition(compile(PAIR), {loadRef: loader(FILES)});

    // when
    const merged = mergeComposition(parsed.document, parsed.parsedNets);

    // then: one lock place, named after both members
    const names = merged.places.map((place) => place.name);
    expect(names).toContain("give.lock__take.lock");
    expect(names).not.toContain("take.lock");
    expect(names).not.toContain("give.lock");
    const lock = merged.places.find((place) => place.name === "give.lock__take.lock")!;
    expect(lock.port).toBeUndefined();
    expect(lock.annotations).toEqual({fusion: true});
    // and: the wired port is still named after its output port
    expect(names).toContain("take.busy");
  });

  it("compiles to JSON after the wires", () => {
    // when
    const document = compile(PAIR);

    // then
    expect(Object.keys(document)).toEqual(["name", "nets", "wires", "shares"]);
    expect(document.shares).toEqual([
      {places: [{net: "take", place: "lock"}, {net: "give", place: "lock"}]},
    ]);
  });

  it("deduplicates identical share facts", () => {
    // when
    const document = compile(`${PAIR}share take.(lock) ~ give.(lock)\n`);

    // then
    expect(document.shares).toHaveLength(1);
  });

  it.each([
    [
      "share take.(lock) ~ give.(nothing)",
      "composition.share.place_unknown",
      "share take.(lock) ~ give.(nothing): net 'give' has no place named 'nothing'",
    ],
    [
      "share take.(lock) ~ give.(done)",
      "composition.share.colors",
      "share take.(lock) ~ give.(done): give.(done) accepts job, but take.(lock) accepts key",
    ],
    [
      "share take.(lock) ~ take.(lock)",
      "composition.share.duplicate_member",
      "share take.(lock) ~ take.(lock): a place is shared with itself",
    ],
  ])("rejects `%s`", (share, code, message) => {
    // given
    const document = compile(PAIR.replace("share take.(lock) ~ give.(lock)", share));

    // when
    const result = failure(() => parseComposition(document, {loadRef: loader(FILES)}));

    // then
    expect(result).toEqual({code, message});
  });

  it("rejects an unknown alias in a JSON document", () => {
    // given
    const document = {
      nets: [{ref: "take.petrinet", alias: "take"}, {ref: "give.petrinet", alias: "give"}],
      wires: [],
      shares: [{places: [{net: "take", place: "lock"}, {net: "nobody", place: "lock"}]}],
    };

    // when
    const result = failure(() => parseComposition(document, {loadRef: loader(FILES)}));

    // then
    expect(result).toEqual({
      code: "composition.share.alias_unknown",
      message: "share take.(lock) ~ nobody.(lock): unknown alias nobody",
    });
  });

  it("is a PN202 at the member when it names an unknown alias", () => {
    // given
    const source = PAIR.replace("give.(lock)\n", "nobody.(lock)\n");

    // when
    let diagnostic: PetrinetDslError | undefined;
    try {
      compilePetrinetText(source, "pair.petrinet");
    } catch (error: unknown) {
      if (error instanceof PetrinetDslError) diagnostic = error;
    }

    // then
    expect(diagnostic?.diagnostic.code).toBe("PN202");
    expect(diagnostic?.diagnostic.message).toBe("share references unknown alias nobody");
    expect(diagnostic?.diagnostic.span.start.line).toBe(5);
    expect(diagnostic?.diagnostic.span.start.column).toBe(21);
  });
});

describe("the merged net's name", () => {
  it("is the composition's name", () => {
    // given
    const parsed = parseComposition(compile(PAIR), {loadRef: loader(FILES)});

    // when
    const merged = mergeComposition(parsed.document, parsed.parsedNets);

    // then
    expect(parsed.document.name).toBe("pair");
    expect(merged.name).toBe("pair");
  });

  it("is composition for a JSON composition without a name", () => {
    // given: the pair as JSON, with no name
    const {name: _name, ...document} = compile(PAIR);
    const parsed = parseComposition(document, {loadRef: loader(FILES)});

    // when
    const merged = mergeComposition(parsed.document, parsed.parsedNets);

    // then
    expect(merged.name).toBe("composition");
  });
});

describe("compositions as constituents", () => {
  it("flattens a composition used inside another", () => {
    // when
    const parsed = parseComposition(compile(NESTED), {loadRef: loader(FILES)});

    // then: the pair's nets are known by a dotted alias, its facts carry over
    expect([...parsed.parsedNets.keys()]).toEqual(["pair.take", "pair.give", "worker"]);
    expect(Object.fromEntries(parsed.sources)).toEqual({
      "pair.take": "take.petrinet",
      "pair.give": "give.petrinet",
      worker: "worker.petrinet",
    });
    expect(parsed.document.nets).toEqual([
      {ref: "take.petrinet", alias: "pair.take"},
      {ref: "give.petrinet", alias: "pair.give"},
      {ref: "worker.petrinet", alias: "worker"},
    ]);
    expect(parsed.document.wires).toEqual([
      {from: {net: "pair.take", port: "busy"}, to: {net: "pair.give", port: "busy"}},
      {from: {net: "pair.take", port: "busy"}, to: {net: "worker", port: "start"}},
      {from: {net: "worker", port: "end"}, to: {net: "pair.give", port: "worked"}},
    ]);
    expect(parsed.document.shares).toEqual([
      {places: [{net: "pair.take", place: "lock"}, {net: "pair.give", place: "lock"}]},
    ]);
    expect(parsed.document.refinements).toEqual([
      {net: "pair.give", transition: "work", by: "worker"},
    ]);
    // and: the merge removes the refined transition and fuses the lock
    const merged = mergeComposition(parsed.document, parsed.parsedNets);
    expect(merged.transitions.map((transition) => transition.name)).not.toContain("pair.give.work");
    expect(merged.places.map((place) => place.name)).toEqual(
      expect.arrayContaining(["pair.take.busy", "pair.give.lock__pair.take.lock", "pair.take.todo"]),
    );
  });

  it("resolves nested references from the nested file", () => {
    // given: the pair and its nets live in a subdirectory
    const files = {
      "pair/take.petrinet": TAKE,
      "pair/give.petrinet": GIVE,
      "pair/pair.petrinet": PAIR,
      "worker.petrinet": WORKER,
    };
    const seen: string[] = [];

    // when
    const parsed = parseComposition(
      compile(NESTED.replace('"pair.petrinet"', '"pair/pair.petrinet"')),
      {loadRef: loader(files, seen)},
    );

    // then
    expect(seen).toEqual([
      "pair/pair.petrinet",
      "pair/take.petrinet",
      "pair/give.petrinet",
      "worker.petrinet",
    ]);
    expect(parsed.sources.get("pair.take")).toBe("pair/take.petrinet");
    expect(parsed.parsedNets.has("pair.take")).toBe(true);
  });

  it("normalizes a nested reference that leaves its directory", () => {
    // given: the nested pair names its nets from a sibling directory
    const files = {
      "pair/pair.petrinet": PAIR.replaceAll('"take.petrinet"', '"../nets/./take.petrinet"'),
      "nets/take.petrinet": TAKE,
      "pair/give.petrinet": GIVE,
      "worker.petrinet": WORKER,
    };

    // when
    const parsed = parseComposition(
      compile(NESTED.replace('"pair.petrinet"', '"pair/pair.petrinet"')),
      {loadRef: loader(files)},
    );

    // then
    expect(parsed.sources.get("pair.take")).toBe("nets/take.petrinet");
  });

  it.each([
    [
      "pair.(take.busy)",
      "pair.(take.nothing)",
      "composition.port_undeclared",
      'net "pair.take" has no port named "nothing"',
    ],
    [
      "pair.(take.busy)",
      "pair.(nobody.busy)",
      "composition.port_undeclared",
      "net 'pair' has no port named 'nobody.busy'",
    ],
    [
      "pair.[give.work]",
      "pair.[give.nothing]",
      "composition.refinement.transition_unknown",
      "refine pair.give.[nothing] by worker: net pair.give has no transition [nothing]",
    ],
    [
      "pair.[give.work]",
      "pair.[nobody.work]",
      "composition.refinement.transition_unknown",
      "refine pair.[nobody.work] by worker: net 'pair' has no transition named 'nobody.work'",
    ],
  ])("rejects a wrong path into a nested composition: %s -> %s", (old, replacement, code, message) => {
    // given
    const document = compile(NESTED.replace(old, replacement));

    // when
    const result = failure(() => parseComposition(document, {loadRef: loader(FILES)}));

    // then
    expect(result).toEqual({code, message});
  });

  it("rejects a composition that uses itself", () => {
    // given
    const files = {"loop.petrinet": 'composition loop\nuse "loop.petrinet" as again\n'};

    // when
    const result = failure(() =>
      parseComposition(compile(files["loop.petrinet"]), {loadRef: loader(files)}),
    );

    // then
    expect(result).toEqual({
      code: "composition.ref_invalid",
      message:
        'invalid referenced net "loop.petrinet": composition reference cycle: loop.petrinet -> loop.petrinet',
    });
  });

  it("needs an explicit alias for a nested composition", () => {
    // when
    const result = failure(() =>
      parseComposition({nets: [{ref: "pair.petrinet"}], wires: []}, {loadRef: loader(FILES)}),
    );

    // then
    expect(result).toEqual({
      code: "composition.ref_invalid",
      message:
        'invalid referenced net "pair.petrinet": a composition used inside another needs an explicit alias',
    });
  });

  it("cannot refine by a composition", () => {
    // given
    const document = {
      nets: [
        {ref: "worker.petrinet", alias: "worker"},
        {ref: "pair.petrinet", alias: "pair"},
      ],
      wires: [],
      refinements: [{net: "worker", transition: "do", by: "pair"}],
    };

    // when
    const result = failure(() => parseComposition(document, {loadRef: loader(FILES)}));

    // then
    expect(result).toEqual({
      code: "composition.refinement.by_composition",
      message: "refine worker.[do] by pair: pair is a composition; a refining net must be a net",
    });
  });

  it("compiles dotted paths in written endpoints", () => {
    // when
    const document = compile(NESTED);

    // then
    expect(document.wires).toEqual([
      {from: {net: "pair", port: "take.busy"}, to: {net: "worker", port: "start"}},
      {from: {net: "worker", port: "end"}, to: {net: "pair", port: "give.worked"}},
    ]);
    expect(document.refinements).toEqual([
      {net: "pair", transition: "give.work", by: "worker"},
    ]);
  });
});
