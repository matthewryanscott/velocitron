import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoPackages = resolve(packageRoot, "../..");

const siblings = [
  ["@velocitron/petrinet", packageRoot],
  ["@velocitron/cel", resolve(repoPackages, "cel/typescript")],
  ["@velocitron/dsl", resolve(repoPackages, "dsl/typescript")],
  ["@velocitron/engine", resolve(repoPackages, "engine/typescript")],
  ["@velocitron/merge", resolve(repoPackages, "merge/typescript")],
];

const checkSource = `
import { createRequire } from "node:module";
import { compilePetrinetText, parseNet } from "@velocitron/petrinet";

const require = createRequire(import.meta.url);
try {
  require.resolve("@velocitron/core");
  throw new Error("unexpected dependency @velocitron/core");
} catch (error) {
  if (String(error && error.message).startsWith("unexpected dependency")) throw error;
}
const compiled = compilePetrinetText(
  'net coin_deposit "Coin deposit"\\n\\n(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)\\n',
  "coin_deposit.petrinet",
);
if (compiled.documentKind !== "net") throw new Error("kind");
if (compiled.document.name !== "coin_deposit") throw new Error("name");
if (!Array.isArray(compiled.document.places)) throw new Error("places");
if ("contributions" in compiled.document) throw new Error("unresolved");
if (parseNet(compiled.document).name !== "coin_deposit") throw new Error("parse");
`;

function pack(directory, destination) {
  const before = new Set(readdirSync(destination));
  execFileSync("npm", ["pack", "--pack-destination", destination], {
    cwd: directory,
    stdio: "pipe",
  });
  const tarball = readdirSync(destination).find(
    (name) => name.endsWith(".tgz") && !before.has(name),
  );
  if (tarball === undefined) throw new Error(`npm pack produced no tarball in ${directory}`);
  return join(destination, tarball);
}

test("an npm pack install compiles a document without the implementation", () => {
  // given: packed tarballs of this package and the packages it calls
  const dir = mkdtempSync(join(tmpdir(), "velocitron-petrinet-"));
  const packed = Object.fromEntries(siblings.map(([name, directory]) => [name, pack(directory, dir)]));
  const overrides = Object.fromEntries(
    Object.entries(packed)
      .filter(([name]) => name !== "@velocitron/petrinet")
      .map(([name, tarball]) => [name, `file:${tarball}`]),
  );
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-petrinet-consumer",
      private: true,
      type: "module",
      dependencies: {
        "@velocitron/petrinet": `file:${packed["@velocitron/petrinet"]}`,
      },
      overrides,
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts"], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and compiles text
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
