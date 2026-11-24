import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdtempSync, readdirSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import {createRequire} from "node:module";
import {COMMANDS, VIZ_PROGRAM, main} from "@velocitron/cli";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@velocitron/engine", "@velocitron/petrinet"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
if (COMMANDS[0] !== "validate") throw new Error("commands");
if (VIZ_PROGRAM !== "velocitron-viz") throw new Error("viz");
try {
  main();
  throw new Error("ran");
} catch (error) {
  if (error && error.name !== "CliUnavailableError") throw error;
}
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

test("an npm pack install names the gap without the implementation", () => {
  // given: a packed tarball of this package
  const dir = mkdtempSync(join(tmpdir(), "velocitron-cli-"));
  const packed = pack(packageRoot, dir);
  writeFileSync(join(dir, "package.json"), JSON.stringify({
    name: "velocitron-cli-consumer",
    private: true,
    type: "module",
    dependencies: {"@velocitron/cli": `file:${packed}`},
  }));
  execFileSync("npm", ["install", "--ignore-scripts"], {cwd: dir, stdio: "pipe"});
  writeFileSync(join(dir, "check.js"), checkSource);
  // when: a fresh process imports the installed package
  const output = execFileSync("node", ["check.js"], {cwd: dir, encoding: "utf8"});
  // then: the gap marker runs and does not see the umbrella
  assert.equal(output.trim(), "ok");
});
