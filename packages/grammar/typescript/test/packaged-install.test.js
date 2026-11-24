import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const fixtures = resolve(packageRoot, "../fixtures");
const net = readFileSync(join(fixtures, "net.petrinet"), "utf8");
const composition = readFileSync(join(fixtures, "composition.petrinet"), "utf8");

const checkSource = `
import { createRequire } from "node:module";
import { PetrinetParseError, grammarText, parsePetrinet } from "@velocitron/grammar";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@marcbachmann/cel-js"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
if (!grammarText().includes("grammar VelocitronPetriNet;")) {
  throw new Error("grammar text");
}
const net = parsePetrinet(process.env.NET, "net.petrinet");
const composition = parsePetrinet(process.env.COMPOSITION, "composition.petrinet");
if (net.kind !== "net" || net.name !== "coin_deposit") throw new Error("net");
if (composition.kind !== "composition" || composition.name !== "wired_pulse") {
  throw new Error("composition");
}
if ("contributions" in net) throw new Error("lowered");
try {
  parsePetrinet("sentinel");
  throw new Error("sentinel parsed");
} catch (error) {
  if (!(error instanceof PetrinetParseError) || error.line !== 1 || error.column !== 1) {
    throw error;
  }
}
`;

test("an npm pack install parses a document without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-grammar-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-grammar-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and parses fixtures
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    env: { ...process.env, NET: net, COMPOSITION: composition },
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
