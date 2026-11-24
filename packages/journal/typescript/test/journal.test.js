import assert from "node:assert/strict";
import test from "node:test";

import {
  InMemoryJournal,
  replayEvents,
  replayRecords,
  serializeRecordValue,
} from "../dist/index.js";

function lane() {
  return {
    name: "lane",
    places: [
      {name: "src", accepts: ["job"]},
      {name: "dst", accepts: ["job"]},
      {name: "clock", accepts: ["tick"]},
    ],
    transitions: [{name: "move", handler: "move"}],
    arcs: [
      {from: {place: "src"}, to: {transition: "move"}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {place: "clock"}, to: {transition: "move"}, consume: {type: "tick", mode: "read", weight: 1}},
      {from: {transition: "move"}, to: {place: "dst"}, produce: {type: "job", destination: "dst"}},
    ],
    initialMarking: {
      src: [{type: "job", data: {id: 1}}],
      clock: [{type: "tick", data: {n: 0}}],
    },
  };
}

function firing(status = "completed") {
  return {
    firingId: "lane/move/0",
    netId: "lane",
    transition: "move",
    attempt: 0,
    status,
    inputTokens: {
      src: [{type: "job", data: {id: 1}}],
      clock: [{type: "tick", data: {n: 0}}],
    },
    outputTokens: {dst: [{type: "job", data: {id: 1, done: true}}]},
    error: null,
    metadata: {},
    timestamps: {firedAt: "2026-01-01T00:00:00Z"},
  };
}

test("in-memory journal numbers firing, violation, and injection together", () => {
  // given: an empty memory journal
  const journal = new InMemoryJournal();

  // when: one record is appended on each channel
  journal.recordFiring(firing());
  journal.recordDepositViolation(firing("failed"));
  journal.recordInjection({
    injectionId: "lane/@inject/src/0",
    netId: "lane",
    place: "src",
    attempt: 0,
    kind: "inject",
    tokens: [{type: "job", data: {id: 2}}],
    replaced: [],
    timestamps: {firedAt: "2026-01-01T00:00:01Z"},
  });

  // then: the sequence is one stream and the stored objects are frozen
  assert.deepEqual(journal.records.map((record) => record.sequence), [0, 1, 2]);
  assert.equal(Object.isFrozen(journal.records[0]), true);
});

test("replay consumes only consume arcs and deposits outputs", () => {
  // given: a completed firing that also bound a read-arc clock token
  const net = lane();

  // when: replayRecords applies it from the initial marking
  const marking = replayRecords(net, [firing()]);

  // then: the job moved, and the clock stayed
  assert.deepEqual(marking.src, []);
  assert.deepEqual(marking.clock, [{type: "tick", data: {n: 0}}]);
  assert.deepEqual(marking.dst, [{type: "job", data: {id: 1, done: true}}]);
});

test("a failed firing, a trace, and a net revision do not change the marking", () => {
  // given: records with no marking effect
  const net = lane();

  // when: replay folds them
  const marking = replayRecords(net, [
    firing("failed"),
    {event: "handler_started", firingId: "lane/move/0"},
    {name: "lane"},
  ]);

  // then: the initial marking is what remains
  assert.deepEqual(marking, net.initialMarking);
});

test("an injection appends and an update replaces", () => {
  // given: an inject on src and an update on clock
  const net = lane();

  // when: replayRecords folds both
  const marking = replayRecords(net, [
    {
      injectionId: "lane/@inject/src/0",
      place: "src",
      kind: "inject",
      tokens: [{type: "job", data: {id: 2}}],
      replaced: [],
    },
    {
      injectionId: "lane/@inject/clock/1",
      place: "clock",
      kind: "injection",
      tokens: [{type: "tick", data: {n: 5}}],
      replaced: [{type: "tick", data: {n: 0}}],
      sequence: 3,
      recorded_at: "2026-01-01T00:00:00Z",
    },
  ]);

  // then: src grew and clock was replaced, including a durable-row kind
  assert.deepEqual(marking.src, [
    {type: "job", data: {id: 1}},
    {type: "job", data: {id: 2}},
  ]);
  assert.deepEqual(marking.clock, [{type: "tick", data: {n: 5}}]);
});

test("replayEvents can start from a caller marking", () => {
  // given: a marking the caller already holds
  const start = {src: [{type: "job", data: {id: 9}}]};

  // when: one injection is applied from that marking
  const marking = replayEvents(lane(), [
    {
      seq: 0,
      kind: "injection",
      payload: {
        place: "src",
        kind: "inject",
        tokens: [{type: "job", data: {id: 8}}],
      },
    },
  ], start);

  // then: both tokens are in src
  assert.deepEqual(marking.src, [
    {type: "job", data: {id: 9}},
    {type: "job", data: {id: 8}},
  ]);
});

test("serializeRecordValue rejects a class instance that is not a token", () => {
  // given: a token-shaped class and an unrelated class
  class Token {
    constructor(type, data) {
      this.type = type;
      this.data = data;
    }
  }
  class Note {
    constructor(text) {
      this.text = text;
    }
  }

  // when: the serializer sees each value
  // then: the token becomes a plain object and the note throws
  assert.deepEqual(serializeRecordValue(new Token("job", {id: 1})), {type: "job", data: {id: 1}});
  assert.throws(() => serializeRecordValue(new Note("hi")), TypeError);
});
