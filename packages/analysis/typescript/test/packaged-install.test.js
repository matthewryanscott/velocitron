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
import {readProofReport, proofReportStatus} from "@velocitron/analysis";

const require = createRequire(import.meta.url);
for (const name of ["@velocitron/core", "@velocitron/engine", "@velocitron/cel"]) {
  try {
    require.resolve(name);
    throw new Error("unexpected dependency " + name);
  } catch (error) {
    if (String(error && error.message).startsWith("unexpected dependency")) throw error;
  }
}
const report = readProofReport({
  version: 1,
  tool: "velocitron 0.1.0",
  net: "sound",
  source: null,
  status: "refuted",
  facts: [{
    fact: "soundness",
    subject: "option to complete",
    status: "refuted",
    statement: "the instance can reach a final marking",
    findings: [{kind: "deadlock", summary: "stuck"}],
  }],
  model: {},
});
if (proofReportStatus(report.facts) !== "refuted") throw new Error("status");
if (report.net !== "sound") throw new Error("net");
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

test("an npm pack install reads a report without the implementation", () => {
  // given: a packed tarball of this package
  const dir = mkdtempSync(join(tmpdir(), "velocitron-analysis-"));
  const packed = pack(packageRoot, dir);
  writeFileSync(join(dir, "package.json"), JSON.stringify({
    name: "velocitron-analysis-consumer",
    private: true,
    type: "module",
    dependencies: {"@velocitron/analysis": `file:${packed}`},
  }));
  execFileSync("npm", ["install", "--ignore-scripts"], {cwd: dir, stdio: "pipe"});
  writeFileSync(join(dir, "check.js"), checkSource);
  // when: a fresh process imports the installed package
  const output = execFileSync("node", ["check.js"], {cwd: dir, encoding: "utf8"});
  // then: the report reader runs and does not see the umbrella
  assert.equal(output.trim(), "ok");
});
