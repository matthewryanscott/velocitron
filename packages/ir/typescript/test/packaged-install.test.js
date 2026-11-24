import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fixture = readFileSync(
  resolve(packageRoot, "../fixtures/cel-string.contribution-ir.json"),
  "utf8",
);

const checkSource = `
import { createRequire } from "node:module";
import { contributionIrSchemaText, loadContributionIrText } from "@velocitron/ir";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@marcbachmann/cel-js"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
const schema = JSON.parse(contributionIrSchemaText());
if (schema.$id !== "https://velocitron.dev/spec/petrinet-contribution-ir.schema.json") {
  throw new Error("schema id");
}
const document = loadContributionIrText(process.env.FIXTURE);
if (document.documentKind !== "net") throw new Error("kind");
if (document.contributions[0].value.cel !== "token.n + 1") throw new Error("cel");
`;

test("an npm pack install loads a document without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-ir-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({ name: "velocitron-ir-consumer", private: true, type: "module" }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and loads a fixture
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    env: { ...process.env, FIXTURE: fixture },
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
