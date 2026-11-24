import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import { createRequire } from "node:module";
import { CelEvaluationError, createDefaultCelAdapter } from "@velocitron/cel";

const require = createRequire(import.meta.url);
try {
  require.resolve("@velocitron/core");
  throw new Error("unexpected dependency @velocitron/core");
} catch (error) {
  if (String(error && error.message).startsWith("unexpected dependency")) throw error;
}
const adapter = createDefaultCelAdapter();
const program = adapter.compile("n + 1");
if (adapter.evaluate(program, { n: 1 }) !== 2) throw new Error("arithmetic");
if (adapter.evaluate(adapter.compile("a.b == 1"), { a: { b: 1 } }) !== true) {
  throw new Error("field");
}
try {
  adapter.compile("value.(");
  throw new Error("syntax accepted");
} catch (error) {
  if (error instanceof CelEvaluationError || error.name !== "CelCompileError") throw error;
}
try {
  adapter.evaluate(adapter.compile("missing.field"), {});
  throw new Error("missing field accepted");
} catch (error) {
  if (!(error instanceof CelEvaluationError)) throw error;
}
`;

test("an npm pack install evaluates CEL without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-cel-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-cel-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and evaluates CEL
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    env: process.env,
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
