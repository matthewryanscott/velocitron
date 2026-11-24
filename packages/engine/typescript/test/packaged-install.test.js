import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import { createRequire } from "node:module";
import { Engine, EngineConfigurationError, HandlerRegistry } from "@velocitron/engine";

const require = createRequire(import.meta.url);
for (const name of [
  "@velocitron/core",
  "@velocitron/ir",
  "@velocitron/grammar",
  "@velocitron/cel",
  "@velocitron/dsl",
  "@velocitron/merge",
  "@velocitron/play",
]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}

const adapter = {
  compile(source) { throw new Error(source); },
  evaluate() { throw new Error("evaluate"); },
};
const registry = new HandlerRegistry();
registry.registerTransition("move", (input) => {
  const token = input.inputTokens.src[0];
  return {
    status: "completed",
    outputTokens: {dst: [{type: "job", data: {id: token.data.id, done: true}}]},
    error: null,
    metadata: {},
  };
});
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
};
const engine = new Engine(registry, {celAdapter: adapter});
const fired = engine.fire(net, {src: [{type: "job", data: {id: 1}}]}, "move", {attempt: 0});
if (fired.record.status !== "completed") throw new Error(fired.record.status);
if (fired.marking.dst[0].data.id !== 1 || fired.marking.dst[0].data.done !== true) {
  throw new Error("deposit");
}
try {
  new Engine(new HandlerRegistry(), {});
  throw new Error("missing adapter was accepted");
} catch (error) {
  if (!(error instanceof EngineConfigurationError)) throw error;
  if (!error.message.includes("celAdapter is required")) throw error;
}
`;

test("an npm pack install fires without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-engine-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-engine-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and fires
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
