import {execFileSync} from "node:child_process";
import {cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, symlinkSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, relative, resolve, sep} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(packageRoot, "../../..");
const engineRoot = resolve(packageRoot, "../../engine/typescript");
const celRoot = resolve(packageRoot, "../../cel/typescript");

const checkSource = `
import {createRequire} from "node:module";
import {Runtime, TokenArrival} from "@velocitron/runtime";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@velocitron/journal", "@velocitron/dsl", "@velocitron/play"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
await import("@velocitron/engine");
await import("@velocitron/cel");

const celAdapter = {compile: (source) => source, evaluate: () => false};
const net = {
  name: "move",
  places: [{name: "src", accepts: ["job"]}, {name: "dst", accepts: ["job"]}],
  transitions: [{name: "move", handler: "move"}],
  arcs: [
    {from: {place: "src"}, to: {transition: "move"}, consume: {type: "job", mode: "consume", weight: 1}},
    {from: {transition: "move"}, to: {place: "dst"}, produce: {type: "job", destination: "dst"}},
  ],
  initialMarking: {},
};
const runtime = new Runtime({
  net,
  handlers: {
    move: {
      handler: async () => ({
        status: "completed",
        outputTokens: {dst: [{type: "job", data: {done: true}}]},
        error: null,
        metadata: {},
      }),
      lane: "main",
    },
  },
  lanes: {main: 1},
  celAdapter,
});
await runtime.start();
await runtime.inject(new TokenArrival("src", {type: "job", data: {id: 1}}));
await runtime.waitIdle();
await runtime.stop();
if ((runtime.marking.src ?? []).length !== 0) throw new Error("src was not consumed");
if (runtime.marking.dst[0].data.done !== true) throw new Error("dst was not deposited");
console.log("ok");
`;

function typescriptCompiler(directory) {
  const candidates = [
    join(directory, "node_modules", ".bin", "tsc"),
    join(repoRoot, "node_modules", ".bin", "tsc"),
  ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (found === undefined) throw new Error("tsc is not installed");
  return found;
}

function pack(directory, destination) {
  // Compile a private copy. npm pack's prepare script is tsc, and another
  // package's test is compiling this same dist at the same time.
  const stageRoot = mkdtempSync(join(tmpdir(), "velocitron-stage-"));
  const stage = join(stageRoot, relative(repoRoot, directory));
  mkdirSync(dirname(stage), {recursive: true});
  cpSync(directory, stage, {
    recursive: true,
    filter(source) {
      const parts = relative(directory, source).split(sep);
      return !parts.includes("node_modules") && !parts.includes("dist");
    },
  });
  cpSync(join(repoRoot, "tsconfig.base.json"), join(stageRoot, "tsconfig.base.json"));
  const modules = join(directory, "node_modules");
  if (existsSync(modules)) symlinkSync(modules, join(stage, "node_modules"));
  execFileSync(typescriptCompiler(directory), ["-p", "tsconfig.build.json"], {
    cwd: stage,
    stdio: "pipe",
  });
  const before = new Set(readdirSync(destination));
  execFileSync("npm", ["pack", "--ignore-scripts", "--pack-destination", destination], {
    cwd: stage,
    stdio: "pipe",
  });
  const tarball = readdirSync(destination).find((name) => name.endsWith(".tgz") && !before.has(name));
  if (tarball === undefined) throw new Error(`npm pack produced no tarball in ${directory}`);
  return join(destination, tarball);
}

test("an npm pack install runs without the implementation", () => {
  // given: packed tarballs of this package and the packages it types against
  const dir = mkdtempSync(join(tmpdir(), "velocitron-runtime-"));
  const runtimePack = pack(packageRoot, dir);
  const enginePack = pack(engineRoot, dir);
  const celPack = pack(celRoot, dir);
  writeFileSync(join(dir, "package.json"), JSON.stringify({
    name: "velocitron-runtime-consumer",
    private: true,
    type: "module",
    dependencies: {
      "@velocitron/runtime": `file:${runtimePack}`,
      "@velocitron/engine": `file:${enginePack}`,
      "@velocitron/cel": `file:${celPack}`,
    },
    overrides: {
      "@velocitron/engine": `file:${enginePack}`,
      "@velocitron/cel": `file:${celPack}`,
    },
  }));
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts"], {cwd: dir, stdio: "pipe"});
  // when: a fresh module imports the installed package and runs
  const output = execFileSync(process.execPath, ["check.mjs"], {cwd: dir, encoding: "utf8"});
  // then: the tarball runs and does not import the umbrella
  if (output.trim() !== "ok") throw new Error(output);
});
