import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import { createRequire } from "node:module";
import { PlayError, grammarText, parsePlay, projectPlay } from "@velocitron/play";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@velocitron/grammar", "velocitron"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
if (!grammarText().includes("grammar VelocitronPlay;")) throw new Error("grammar");
const play = parsePlay('play shop "One purchase"\\nadvance 90m\\n', "shop.play");
if (play.name !== "shop") throw new Error("name");
const step = play.paths[0].steps[0];
if (step.kind !== "advance" || step.body.seconds !== 5400 || step.body.relative !== false) {
  throw new Error("advance");
}
const projected = projectPlay('play s\\ninject (p) <- c {"a": 1, "a": 2}\\n');
if (projected.ok !== false || projected.code !== "SC102") throw new Error("duplicate");
try {
  parsePlay("  play s\\n");
  throw new Error("indented source parsed");
} catch (error) {
  if (!(error instanceof PlayError) || error.code !== "SC101" || error.line !== 1) throw error;
}
`;

test("an npm pack install parses a play without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-play-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-play-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and parses a play
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    stdio: "pipe",
  });
  // then: the child process exits 0, which is this test passing
});
