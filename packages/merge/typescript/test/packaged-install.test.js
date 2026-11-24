import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import { createRequire } from "node:module";
import { NetValidationError, mergeNets, portFusionMap } from "@velocitron/merge";

const require = createRequire(import.meta.url);
for (const name of [
  "@velocitron/core",
  "@velocitron/ir",
  "@velocitron/grammar",
  "@velocitron/cel",
  "@velocitron/dsl",
]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}

const prod = {
  name: "prod",
  places: [
    {name: "src", accepts: ["task"]},
    {name: "out", accepts: ["task"], port: {direction: "output", type: "task"}},
  ],
  transitions: [{name: "make", handler: "noop"}],
  arcs: [
    {from: {place: "src"}, to: {transition: "make"}, consume: {type: "task", mode: "consume", weight: 1}},
    {from: {transition: "make"}, to: {place: "out"}, produce: {type: "task", destination: "out"}},
  ],
};
const cons = {
  name: "cons",
  places: [
    {name: "inbox", accepts: ["task"], port: {direction: "input", type: "task"}},
    {name: "done", accepts: ["task"]},
  ],
  transitions: [{name: "take", handler: "noop"}],
  arcs: [
    {from: {place: "inbox"}, to: {transition: "take"}, consume: {type: "task", mode: "consume", weight: 1}},
    {from: {transition: "take"}, to: {place: "done"}, produce: {type: "task", destination: "done"}},
  ],
};
const wire = {from: {net: "prod", port: "out"}, to: {net: "cons", port: "inbox"}};
const nets = new Map([["prod", prod], ["cons", cons]]);
const merged = mergeNets(nets, [wire], [], [], "wired");
if (merged.name !== "wired") throw new Error("name");
const names = merged.places.map((place) => place.name).sort();
if (names.join(",") !== "cons.done,prod.out,prod.src") throw new Error(names.join(","));
const fusion = portFusionMap(nets, [wire]);
if (fusion.get("prod.out") !== "prod.out" || fusion.get("cons.inbox") !== "prod.out") {
  throw new Error("fusion");
}
const left = {name: "a", places: [{name: "p", accepts: ["task"]}], transitions: [], arcs: [], domains: {"task.kind": ["one"]}};
const right = {name: "b", places: [{name: "p", accepts: ["task"]}], transitions: [], arcs: [], domains: {"task.kind": ["two"]}};
try {
  mergeNets(new Map([["a", left], ["b", right]]), []);
  throw new Error("domain conflict accepted");
} catch (error) {
  if (!(error instanceof NetValidationError)) throw error;
  if (!error.message.includes("domain task.kind differs")) throw error;
}
`;

test("an npm pack install merges without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-merge-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-merge-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and merges
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
