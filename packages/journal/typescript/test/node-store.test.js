import assert from "node:assert/strict";
import {mkdtempSync, readdirSync, readFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import test from "node:test";

import {replayEvents} from "../dist/index.js";
import {DurableJournal, JsonlJournal, knownInstances, openDatabase, readEvents} from "../dist/node.js";

function firing(transition = "move") {
  return {
    firingId: `lane/${transition}/0`,
    netId: "lane",
    transition,
    attempt: 0,
    status: "completed",
    inputTokens: {src: [{type: "job", data: {id: 1}}]},
    outputTokens: {dst: [{type: "job", data: {id: 1}}]},
    error: null,
    metadata: {},
    timestamps: {firedAt: "2026-01-01T00:00:00Z"},
  };
}

const net = {
  name: "lane",
  places: [
    {name: "src", accepts: ["job"]},
    {name: "dst", accepts: ["job"]},
  ],
  transitions: [{name: "move"}],
  arcs: [],
};

test("sqlite journal appends, reopens, and replays", () => {
  // given: a fresh database and one firing plus one injection
  const directory = mkdtempSync(join(tmpdir(), "velocitron-journal-"));
  const path = join(directory, "events.db");
  const database = openDatabase(path);
  const journal = new DurableJournal(database, "lane-1");
  journal.recordNetRevision({name: "lane"});
  journal.recordFiring(firing());
  journal.recordInjection({
    injectionId: "lane/@inject/dst/1",
    netId: "lane",
    place: "dst",
    attempt: 1,
    kind: "inject",
    tokens: [{type: "job", data: {id: 2}}],
    replaced: [],
    timestamps: {firedAt: "2026-01-01T00:00:01Z"},
  });

  // when: the records are read back and the database is reopened
  const records = journal.records();
  const events = readEvents(database, "lane-1");
  const reopened = new DurableJournal(openDatabase(path), "lane-1");
  reopened.recordDepositViolation(firing("drop"));

  // then: sequence continues and replay deposits both tokens
  assert.deepEqual(knownInstances(database), ["lane-1"]);
  assert.deepEqual(events.map((event) => event.kind), ["net_revision", "firing", "injection"]);
  assert.deepEqual(records.map((record) => record.sequence), [0, 1, 2]);
  assert.equal(records[0].kind, "net_revision");
  assert.equal(typeof records[0].recorded_at, "string");
  const marking = replayEvents(net, events, {});
  assert.deepEqual(marking.dst, [
    {type: "job", data: {id: 1}},
    {type: "job", data: {id: 2}},
  ]);
  assert.deepEqual(reopened.records().map((record) => record.sequence), [0, 1, 2, 3]);
  assert.equal(reopened.records()[3].kind, "deposit_violation");
});

test("sqlite records are fresh copies", () => {
  // given: one stored firing
  const directory = mkdtempSync(join(tmpdir(), "velocitron-journal-"));
  const journal = new DurableJournal(openDatabase(join(directory, "events.db")), "lane-1");
  journal.recordFiring(firing());

  // when: a caller mutates the read-back object
  const records = journal.records();
  records[0].transition = "mutated";

  // then: the next read still has the stored transition
  assert.equal(journal.records()[0].transition, "move");
});

test("jsonl flush writes one object per line and a missing prefix writes nothing", () => {
  // given: a memory journal and a file-backed journal
  const directory = mkdtempSync(join(tmpdir(), "velocitron-journal-"));
  const memory = new JsonlJournal();
  memory.recordFiring(firing());
  memory.flush();
  const journal = new JsonlJournal(join(directory, "run"));
  journal.recordFiring(firing());
  journal.recordNetRevision({name: "lane"});

  // when: flush writes the timestamped file
  journal.flush();
  const written = readdirSync(directory).filter((name) => name.endsWith(".jsonl"));

  // then: the memory journal created no file, and the file has two JSON lines
  assert.equal(readdirSync(directory).some((name) => name.startsWith("undefined")), false);
  assert.equal(written.length, 1);
  const lines = readFileSync(join(directory, written[0]), "utf8").trim().split("\n");
  assert.equal(lines.length, 2);
  assert.equal(JSON.parse(lines[0]).sequence, 0);
  assert.equal(JSON.parse(lines[0]).inputTokens.src[0].type, "job");
  assert.deepEqual(journal.records().map((record) => record.sequence), [0, 1]);
});
