import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(packageRoot, "../../..");
const codegenRoot = resolve(packageRoot, "../../codegen/typescript");

const checkSource = `
import { createRequire } from "node:module";
import { SYNTH_HANDLER, VelocitronNet } from "@velocitron/netbase";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@velocitron/engine", "@velocitron/runtime"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
if (SYNTH_HANDLER !== "velocitron:synth:") throw new Error("prefix");
try {
  new VelocitronNet();
  throw new Error("constructed");
} catch (error) {
  if (error && error.name !== "NetbaseUnavailableError") throw error;
}
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
  mkdirSync(dirname(stage), { recursive: true });
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
  const tarball = readdirSync(destination).find(
    (name) => name.endsWith(".tgz") && !before.has(name),
  );
  if (tarball === undefined) {
    throw new Error(`npm pack produced no tarball in ${directory}`);
  }
  return join(destination, tarball);
}

test("an npm pack install names the gap without the implementation", () => {
  // given: packed tarballs of this package and the codegen prefix it re-exports
  const dir = mkdtempSync(join(tmpdir(), "velocitron-netbase-"));
  const codegen = pack(codegenRoot, dir);
  const packed = pack(packageRoot, dir);
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-netbase-consumer",
      private: true,
      type: "module",
      dependencies: {
        "@velocitron/codegen": `file:${codegen}`,
        "@velocitron/netbase": `file:${packed}`,
      },
      overrides: {
        "@velocitron/codegen": `file:${codegen}`,
      },
    }),
  );
  execFileSync("npm", ["install", "--ignore-scripts"], { cwd: dir, stdio: "pipe" });
  writeFileSync(join(dir, "check.js"), checkSource);
  // when: a fresh process imports the installed package
  const output = execFileSync("node", ["check.js"], { cwd: dir, encoding: "utf8" });
  // then: the gap marker runs and does not see the umbrella
  assert.equal(output.trim(), "ok");
});
