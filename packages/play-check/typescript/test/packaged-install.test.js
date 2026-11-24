import {execFileSync} from "node:child_process";
import {mkdtempSync, readdirSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoPackages = resolve(packageRoot, "../..");

const siblings = [
  ["@velocitron/play-check", packageRoot],
  ["@velocitron/play", resolve(repoPackages, "play/typescript")],
  ["@velocitron/petrinet", resolve(repoPackages, "petrinet/typescript")],
  ["@velocitron/cel", resolve(repoPackages, "cel/typescript")],
  ["@velocitron/dsl", resolve(repoPackages, "dsl/typescript")],
  ["@velocitron/engine", resolve(repoPackages, "engine/typescript")],
  ["@velocitron/merge", resolve(repoPackages, "merge/typescript")],
];

const checkSource = `
import {createRequire} from "node:module";
import {mkdtempSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {parsePlay} from "@velocitron/play";
import {checkPlay, renderWalkthrough} from "@velocitron/play-check";

const require = createRequire(import.meta.url);
try {
  require.resolve("@velocitron/core");
  throw new Error("unexpected dependency @velocitron/core");
} catch (error) {
  if (String(error && error.message).startsWith("unexpected dependency")) throw error;
}
const root = mkdtempSync(join(tmpdir(), "play-check-pack-"));
writeFileSync(join(root, "shop.petrinet"), 'net shop "Shop"\\n\\n(orders) -purchase-> [accept] -purchase-> (accepted)\\n\\nmarking initial (orders) <- $o\\n$o: purchase {"id": "o-1"}\\n');
const text = 'play shop "One purchase"\\nnet "shop.petrinet"\\nfire [accept]\\nexpect (accepted) has purchase {"id": "o-1"}\\n';
writeFileSync(join(root, "shop.play"), text);
const report = checkPlay(parsePlay(text, join(root, "shop.play")));
if (!report.passed) throw new Error("play did not pass");
if (!renderWalkthrough(report.traces[0]).includes("accept")) throw new Error("walkthrough");
console.log("ok");
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

test("an npm pack install checks a play without the implementation", () => {
  // given: packed tarballs of this package and the packages it calls
  const dir = mkdtempSync(join(tmpdir(), "velocitron-play-check-"));
  const packed = Object.fromEntries(siblings.map(([name, directory]) => [name, pack(directory, dir)]));
  const overrides = Object.fromEntries(
    Object.entries(packed)
      .filter(([name]) => name !== "@velocitron/play-check")
      .map(([name, tarball]) => [name, `file:${tarball}`]),
  );
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({
      name: "velocitron-play-check-consumer",
      private: true,
      type: "module",
      dependencies: {
        "@velocitron/play-check": `file:${packed["@velocitron/play-check"]}`,
        "@velocitron/play": `file:${packed["@velocitron/play"]}`,
      },
      overrides,
    }),
  );
  writeFileSync(join(dir, "check.mjs"), checkSource);
  execFileSync("npm", ["install", "--ignore-scripts"], {
    cwd: dir,
    stdio: "pipe",
  });
  // when: a fresh module imports the installed package and checks a play
  const output = execFileSync("node", ["check.mjs"], {cwd: dir, encoding: "utf8"});
  // then: the tarball checks the play and does not import the umbrella
  if (output.trim() !== "ok") throw new Error(output);
});
