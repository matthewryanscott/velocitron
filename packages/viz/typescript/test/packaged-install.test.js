import {execFileSync} from "node:child_process";
import {mkdtempSync, readdirSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import {createRequire} from "node:module";
import {applyView, netRenderModel, netToDot} from "@velocitron/viz";

const require = createRequire(import.meta.url);
for (const name of [
  "@velocitron/core",
  "@velocitron/ir",
  "@velocitron/grammar",
  "@velocitron/cel",
  "@velocitron/dsl",
  "@velocitron/merge",
  "@velocitron/play",
  "@velocitron/engine",
]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}

const net = {
  name: "fusion-net",
  places: [
    {name: "window", accepts: ["tok"], annotations: {fusion: true}},
    {name: "src", accepts: ["job"]},
  ],
  transitions: [{name: "open", handler: "open_h"}],
  arcs: [
    {from: {place: "src"}, to: {transition: "open"}, consume: {type: "job", mode: "consume", weight: 1}},
    {from: {transition: "open"}, to: {place: "window"}, produce: {type: "tok", destination: "window"}},
  ],
  initialMarking: {window: [{type: "tok", data: {}}]},
};
const dot = netToDot(net);
if (!dot.includes('"window@open"')) throw new Error("missing fusion copy");
if (dot.includes('"window" [')) throw new Error("fusion hub was drawn");
const view = applyView(netRenderModel(net), {
  annotations: {
    "petrinet.dsl/v1": {
      views: {wired: {positions: {"place:src": {x: 1, y: 2}}, routes: {}}},
      arcHandles: {},
    },
  },
}, "wired");
if (!view.includes('pos="1,2!"') || !view.includes("layout=neato;")) throw new Error("view");
`;

test("an npm pack install renders without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-viz-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-viz-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and renders
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
