import {describe, expect, it, vi} from "vitest";

import {
  mergeComposition,
  parseComposition,
  NetValidationError,
  type CompositionLoader,
} from "@velocitron/petrinet";

// ── Fixtures ─────────────────────────────────────────────────────────────
// Mirroring implementations/python/tests/test_composition.py (CO1–CO9):
// the loader is the injected replacement for the filesystem loader py uses.

const prodOutPort = {
  name: "out",
  accepts: ["task"],
  port: {direction: "output", type: "task"},
};

const consInPort = {
  name: "in",
  accepts: ["task"],
  port: {direction: "input", type: "task"},
};

function minimalNet(name: string, places: readonly unknown[]): unknown {
  // The composition seam never resolves arcs or transitions, so these stay
  // empty (no decorative structure) — same minimality convention as py.
  return {name, places, transitions: [], arcs: []};
}

function compose(
  nets: readonly {ref: string; alias?: string}[],
  wires: readonly {
    from: {net: string; port: string};
    to: {net: string; port: string};
  }[],
): void {
  parseComposition({nets, wires}, {origin: "fixture://", loadRef: (ref) => loadRef(ref)});
}

// hoisted per-test table, set by useRefs()
let refTable: Record<string, unknown> = {};
const loadRef: CompositionLoader = (ref) => {
  const document = refTable[ref];
  if (document === undefined) throw new Error(`no such ref: ${ref}`);
  return document;
};

function useRefs(entries: Record<string, unknown>): void {
  refTable = entries;
}

// ── Cluster 1: alias derivation & uniqueness ─────────────────────────────

describe("parseComposition alias derivation (CO1–CO4)", () => {
  it("CO1: an omitted alias defaults to the net's name and the wire resolves under it", () => {
    // given: a producer and consumer with NO explicit aliases and a wire
    // referencing the derived aliases (producer / consumer)
    useRefs({
      "producer.json": minimalNet("producer", [prodOutPort]),
      "consumer.json": minimalNet("consumer", [consInPort]),
    });
    const nets = [{ref: "producer.json"}, {ref: "consumer.json"}];
    const wires = [
      {from: {net: "producer", port: "out"}, to: {net: "consumer", port: "in"}},
    ];
    // when: parsing the composition
    const result = parseComposition(
      {nets, wires},
      {loadRef},
    );
    // then: the omitted aliases derived to the net names and the wire resolved
    expect(result.document.nets).toEqual([
      {ref: "producer.json", alias: "producer"},
      {ref: "consumer.json", alias: "consumer"},
    ]);
    expect(result.document.wires).toEqual(wires);
    // and: the parsed nets are keyed by the derived aliases (merge handoff)
    expect([...result.parsedNets.keys()]).toEqual(["producer", "consumer"]);
  });

  it("CO2: a derived alias from a non-identifier net name is rejected at parse", () => {
    // given: a net whose name contains a dot (a valid net name, but not a
    // valid composition alias) with no explicit alias
    useRefs({"producer.json": minimalNet("prod.line", [])});
    // when/then: the derived alias "prod.line" is not a simple identifier
    expect(() =>
      parseComposition(
        {nets: [{ref: "producer.json"}], wires: []},
        {loadRef},
      ),
    ).toThrow(NetValidationError);
  });

  it("CO3: two nets with the same explicit alias are rejected", () => {
    // given: two nets both aliased "dup", no wires
    useRefs({
      "a.json": minimalNet("net_a", []),
      "b.json": minimalNet("net_b", []),
    });
    // when/then: duplicate alias rejected
    expect(() =>
      compose(
        [
          {ref: "a.json", alias: "dup"},
          {ref: "b.json", alias: "dup"},
        ],
        [],
      ),
    ).toThrow(/duplicate composition alias/);
  });

  it("CO4: two distinct nets sharing a name collide on the derived alias", () => {
    // given: two nets both named "same" with no explicit alias
    useRefs({
      "a.json": minimalNet("same", []),
      "b.json": minimalNet("same", []),
    });
    // when/then: derived alias collision rejected
    expect(() =>
      parseComposition(
        {nets: [{ref: "a.json"}, {ref: "b.json"}], wires: []},
        {loadRef},
      ),
    ).toThrow(/duplicate composition alias/);
  });
});

// ── Cluster 2: wire validation ───────────────────────────────────────────

describe("parseComposition wire validation (CO5–CO8)", () => {
  it("CO5: a wire referencing an unknown alias is rejected", () => {
    // given: a consumer wire whose from references "ghost"
    useRefs({"consumer.json": minimalNet("consumer", [consInPort])});
    // when/then: unknown alias rejected
    expect(() =>
      compose(
        [{ref: "consumer.json", alias: "cons"}],
        [{from: {net: "ghost", port: "out"}, to: {net: "cons", port: "in"}}],
      ),
    ).toThrow(/unknown net alias: "ghost"/);
  });

  it("CO6: a wire referencing a missing port on a known alias is rejected", () => {
    // given: producer and consumer, wire references port "nonexistent"
    useRefs({
      "producer.json": minimalNet("producer", []),
      "consumer.json": minimalNet("consumer", []),
    });
    // when/then: missing port name rejected
    expect(() =>
      compose(
        [
          {ref: "producer.json", alias: "prod"},
          {ref: "consumer.json", alias: "cons"},
        ],
        [{from: {net: "prod", port: "nonexistent"}, to: {net: "cons", port: "in"}}],
      ),
    ).toThrow(/has no port named "nonexistent"/);
  });

  it("CO7: a wire whose from port is an input port is rejected (source-is-input)", () => {
    // given: the from port declares direction "input"
    useRefs({
      "producer.json": minimalNet("producer", [
        {name: "ctrl", accepts: ["task"], port: {direction: "input", type: "task"}},
      ]),
      "consumer.json": minimalNet("consumer", [consInPort]),
    });
    // when/then: direction mismatch rejected
    expect(() =>
      compose(
        [
          {ref: "producer.json", alias: "prod"},
          {ref: "consumer.json", alias: "cons"},
        ],
        [{from: {net: "prod", port: "ctrl"}, to: {net: "cons", port: "in"}}],
      ),
    ).toThrow(NetValidationError);
  });

  it("CO7: a wire whose to port is an output port is rejected (target-is-output)", () => {
    // given: the to port declares direction "output"
    useRefs({
      "producer.json": minimalNet("producer", [prodOutPort]),
      "consumer.json": minimalNet("consumer", [
        {name: "ack", accepts: ["task"], port: {direction: "output", type: "task"}},
      ]),
    });
    // when/then: direction mismatch rejected
    expect(() =>
      compose(
        [
          {ref: "producer.json", alias: "prod"},
          {ref: "consumer.json", alias: "cons"},
        ],
        [{from: {net: "prod", port: "out"}, to: {net: "cons", port: "ack"}}],
      ),
    ).toThrow(NetValidationError);
  });

  it("CO8: a wire joining ports of different types is rejected", () => {
    // given: a task output and an email input
    useRefs({
      "producer.json": minimalNet("producer", [prodOutPort]),
      "consumer.json": minimalNet("consumer", [
        {name: "in", accepts: ["email"], port: {direction: "input", type: "email"}},
      ]),
    });
    // when/then: type mismatch rejected
    expect(() =>
      compose(
        [
          {ref: "producer.json", alias: "prod"},
          {ref: "consumer.json", alias: "cons"},
        ],
        [{from: {net: "prod", port: "out"}, to: {net: "cons", port: "in"}}],
      ),
    ).toThrow(/different types: "task" -> "email"/);
  });
});

// ── Cluster 3: net validity + loader seam ────────────────────────────────

describe("parseComposition net validity and loader (CO9 + seam)", () => {
  it("CO9: an invalid constituent net is rejected at parse, wrapped as invalid ref", () => {
    // given: a net structurally invalid against the net schema (a place
    // missing `accepts`)
    useRefs({
      "badnet.json": {
        name: "badnet",
        places: [{name: "out", port: {direction: "output", type: "task"}}],
        transitions: [],
        arcs: [],
      },
    });
    // when/then: the inner parseNet failure surfaces wrapped
    expect(() =>
      parseComposition({nets: [{ref: "badnet.json"}], wires: []}, {loadRef}),
    ).toThrow(/invalid referenced net "badnet.json"/);
  });

  it("a loader failure is wrapped as a composition loader failure", () => {
    // given: a loader that throws for the requested ref
    useRefs({});
    // when/then: the throw maps to a NetValidationError naming the ref
    expect(() =>
      parseComposition({nets: [{ref: "missing.json"}], wires: []}, {loadRef}),
    ).toThrow(/composition loader failed for reference "missing\.json"/);
  });

  it("a document with nets but no loader is rejected (no filesystem default)", () => {
    // given: a shape-valid document and no injected loader
    // when/then: parsing fails rather than touching the filesystem
    expect(() =>
      parseComposition({nets: [{ref: "producer.json"}], wires: []}, {}),
    ).toThrow(NetValidationError);
  });

  it("feeds mergeComposition with the returned document and parsed nets", () => {
    // given: a valid producer/consumer composition parsed through the seam
    useRefs({
      "producer.json": minimalNet("producer", [
        prodOutPort,
        {name: "work", accepts: ["task"]},
      ]),
      "consumer.json": minimalNet("consumer", [
        consInPort,
        {name: "done", accepts: ["task"]},
      ]),
    });
    const parsed = parseComposition(
      {
        nets: [
          {ref: "producer.json", alias: "prod"},
          {ref: "consumer.json", alias: "cons"},
        ],
        wires: [
          {from: {net: "prod", port: "out"}, to: {net: "cons", port: "in"}},
        ],
      },
      {loadRef},
    );
    // when: merging via the seam's outputs
    const merged = mergeComposition(parsed.document, parsed.parsedNets);
    // then: the composed net is the aliased join the seam validated
    expect(merged.places.map((place) => place.name)).toContain("prod.out");
    // the fused place replaces both port places (cons.in fuses into prod.out)
    expect(merged.places.map((place) => place.name)).not.toContain("cons.in");
  });

  it("does not call the loader for an invalid composition shape", () => {
    // given: a document failing the canonical composition schema
    let loaderCalls = 0;
    const loader = (): unknown => {
      loaderCalls += 1;
      return undefined;
    };
    // when/then: schema validation rejects before any ref resolves
    expect(() =>
      parseComposition({nets: []}, {loadRef: loader}),
    ).toThrow(NetValidationError);
    expect(loaderCalls).toBe(0);
  });
});