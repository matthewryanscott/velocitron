import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const checkSource = `
import { createRequire } from "node:module";
import { PetrinetDslError, lowerPetrinetText } from "@velocitron/dsl";

const require = createRequire(import.meta.url);
for (const name of [
  "@velocitron/core",
  "@velocitron/grammar",
  "@velocitron/ir",
  "@velocitron/cel",
  "@marcbachmann/cel-js",
]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
const net = lowerPetrinetText(
  'net coin_deposit "Coin deposit"\\n\\n(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)\\n',
  "coin_deposit.petrinet",
);
if (net.format !== "velocitron.petrinet/contribution-ir") throw new Error("format");
if (net.documentKind !== "net") throw new Error("kind");
if (net.contributions[0].value.name !== "coin_deposit") throw new Error("name");
if ("places" in net || "nets" in net) throw new Error("resolved");
const composition = lowerPetrinetText(
  'composition wired_pulse\\n\\nuse "pulse_source.petrinet" as source\\n' +
    'use "pulse_sink.petrinet" as sink\\n' +
    "wire source.(pulse_out) -> sink.(pulse_in)\\n",
  "wired_pulse.petrinet",
);
if (composition.documentKind !== "composition") throw new Error("composition");
if (composition.contributions[0].value.namespace !== "wired_pulse") throw new Error("namespace");
if ("nets" in composition) throw new Error("merged");
try {
  lowerPetrinetText("net", "truncated.petrinet");
  throw new Error("truncated source lowered");
} catch (error) {
  if (!(error instanceof PetrinetDslError)) throw error;
  if (error.diagnostic.span.start.offset !== 3 || error.diagnostic.span.start.column !== 4) {
    throw error;
  }
}
`;

test("an npm pack install lowers a document without the implementation", () => {
  // given: a packed tarball of this package and a throwaway consumer
  const dir = mkdtempSync(join(tmpdir(), "velocitron-dsl-"));
  execFileSync("npm", ["pack", "--pack-destination", dir], {
    cwd: packageRoot,
    stdio: "pipe",
  });
  const tarball = readdirSync(dir).find((name) => name.endsWith(".tgz"));
  if (tarball === undefined) throw new Error("npm pack produced no tarball");
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-dsl-consumer",
      private: true,
      type: "module",
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts", join(dir, tarball)], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and lowers text
  execFileSync(process.execPath, ["check.mjs"], {
    cwd: dir,
    stdio: "pipe",
  });
  // then: the child exits 0, which is this call returning
});
