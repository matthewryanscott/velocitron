import {execFileSync} from "node:child_process";
import {mkdtempSync, readdirSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const engineRoot = resolve(packageRoot, "../../engine/typescript");

const checkSource = `
import {createRequire} from "node:module";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {InMemoryJournal, replayRecords} from "@velocitron/journal";
import {DurableJournal, openDatabase, readEvents} from "@velocitron/journal/node";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@velocitron/cel", "@velocitron/dsl", "@velocitron/play"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
await import("@velocitron/engine");

const net = {
  name: "move",
  places: [
    {name: "src", accepts: ["job"]},
    {name: "dst", accepts: ["job"]},
  ],
  transitions: [{name: "move", handler: "move"}],
  arcs: [
    {from: {place: "src"}, to: {transition: "move"}, consume: {type: "job", mode: "consume", weight: 1}},
    {from: {transition: "move"}, to: {place: "dst"}, produce: {type: "job", destination: "dst"}},
  ],
  initialMarking: {src: [{type: "job", data: {id: 1}}]},
};
const record = {
  firingId: "move/move/0",
  netId: "move",
  transition: "move",
  attempt: 0,
  status: "completed",
  inputTokens: {src: [{type: "job", data: {id: 1}}]},
  outputTokens: {dst: [{type: "job", data: {id: 1, done: true}}]},
  error: null,
  metadata: {},
  timestamps: {firedAt: "2026-01-01T00:00:00Z"},
};
const journal = new InMemoryJournal();
journal.recordFiring(record);
const marking = replayRecords(net, journal.records);
if (marking.src.length !== 0) throw new Error("src was not consumed");
if (marking.dst[0].data.done !== true) throw new Error("dst was not deposited");
const directory = mkdtempSync(join(tmpdir(), "velocitron-journal-pack-"));
const database = openDatabase(join(directory, "events.db"));
const durable = new DurableJournal(database, "move");
durable.recordFiring(record);
const events = readEvents(database, "move");
if (events[0].kind !== "firing" || events[0].payload.transition !== "move") throw new Error("sqlite");
console.log("ok");
`;

function pack(directory, destination) {
  const before = new Set(readdirSync(destination));
  execFileSync("npm", ["pack", "--pack-destination", destination], {
    cwd: directory,
    stdio: "pipe",
  });
  const tarball = readdirSync(destination).find((name) => name.endsWith(".tgz") && !before.has(name));
  if (tarball === undefined) throw new Error(`npm pack produced no tarball in ${directory}`);
  return join(destination, tarball);
}

test("an npm pack install replays without the implementation", () => {
  // given: packed tarballs of this package and the engine it types against
  const dir = mkdtempSync(join(tmpdir(), "velocitron-journal-"));
  const journalPack = pack(packageRoot, dir);
  const enginePack = pack(engineRoot, dir);
  writeFileSync(join(dir, "package.json"), JSON.stringify({
    name: "velocitron-journal-consumer",
    private: true,
    type: "module",
    dependencies: {
      "@velocitron/journal": `file:${journalPack}`,
      "@velocitron/engine": `file:${enginePack}`,
    },
    overrides: {
      "@velocitron/engine": `file:${enginePack}`,
    },
  }));
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts"], {cwd: dir, stdio: "pipe"});
  // when: a fresh module imports the installed package and replays
  const output = execFileSync(process.execPath, ["check.mjs"], {cwd: dir, encoding: "utf8"});
  // then: the tarball replays and does not import the umbrella
  if (output.trim() !== "ok") throw new Error(output);
});
