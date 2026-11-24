// The Pyodide side of the parity comparison.
//
// Usage: node pyodide_parity_driver.mjs <npmDir> <distDir> <playsDir> <outDir>
//
// <npmDir>  the pinned `pyodide` npm package (pyodide.mjs, pyodide-lock.json, ...)
// <distDir> the prepared serving root: pyodide/ (core + lock wheels) and
//           wheels/ (the dependency wheels, the leaf wheels, and velocitron-cli)
// <playsDir> the .play case directories (`<name>/case.play`, `<name>/*.petrinet`)
// <outDir>  one `<case>.<command>.{stdout,stderr,code}` file per run
//
// Serves <distDir> on 127.0.0.1 (the page's own origin), loads Pyodide from it,
// installs velocitron-cli and its leaf wheels with micropip from it, then for every case runs the same
// CLI commands the coordinator ran natively, in-process, and writes the three
// files per run so the two sides diff byte for byte.
// No network outside <origin>: `fetched` proves every HTTP request was to the
// local origin and `socketNonLoopback` that no socket reached the outside.
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";

const [npmDir, distDir, playsDir, outDir] = process.argv.slice(2);
const { loadPyodide } = await import(path.resolve(npmDir, "pyodide.mjs"));
fs.mkdirSync(outDir, { recursive: true });

const server = http.createServer((request, response) => {
  const file = path.join(distDir, decodeURIComponent(request.url.split("?")[0]));
  if (!file.startsWith(distDir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    response.writeHead(404).end();
    return;
  }
  const body = fs.readFileSync(file);
  response.writeHead(200, { "content-length": body.length }).end(body);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

const fetched = [];
const realFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : input.url ?? String(input);
  fetched.push(url);
  return realFetch(input, init);
};
const sockets = [];
const realConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  this.once("connect", () => sockets.push(this.remoteAddress ?? ""));
  return realConnect.apply(this, args);
};

const pyodide = await loadPyodide({
  // Node resolves indexURL and lockFileURL as file paths; wheels still come
  // over HTTP from the local origin (micropip insists on URLs).
  indexURL: path.join(distDir, "pyodide"),
  lockFileURL: path.join(distDir, "pyodide", "pyodide-lock.json"),
  packageBaseUrl: `${origin}/pyodide/`,
  stdout: () => {},
  stderr: (text) => console.error(text),
});
await pyodide.loadPackage("micropip", { messageCallback: () => {} });
const micropip = pyodide.pyimport("micropip");
const wheelNames = fs.readdirSync(path.join(distDir, "wheels")).filter((name) => name.endsWith(".whl"));
let installError = null;
try {
  await micropip.install(wheelNames.map((name) => `${origin}/wheels/${name}`));
} catch (error) {
  installError = String(error);
}

const result = { origin: "http://127.0.0.1:<port>", pyodideVersion: pyodide.version, wheels: wheelNames, installError };
result.installed = installError
  ? {}
  : JSON.parse(
      pyodide.runPython("import json, micropip; json.dumps({k: v.version for k, v in micropip.list().items()})"),
    );

if (!installError) {
  const cases = fs.readdirSync(playsDir).filter((name) => fs.statSync(path.join(playsDir, name)).isDirectory());
  const copyTree = (source, target) => {
    pyodide.FS.mkdirTree(target);
    for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
      const from = path.join(source, entry.name);
      if (entry.isDirectory()) copyTree(from, `${target}/${entry.name}`);
      else pyodide.FS.writeFile(`${target}/${entry.name}`, fs.readFileSync(from));
    }
  };
  copyTree(playsDir, "/work");

  pyodide.FS.mkdirTree("/out");
  pyodide.runPython(`
import io, os, contextlib
os.environ["VELOCITRON_NO_CEL_WARNING"] = "1"

def parity_cli(cwd, argv, stem):
    from velocitron_cli import main
    out, err = io.StringIO(), io.StringIO()
    previous = os.getcwd()
    os.chdir(cwd)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exit:
            code = exit.code
    os.chdir(previous)
    with open(f"/out/{stem}.stdout", "wb") as file:
        file.write(out.getvalue().encode("utf-8"))
    with open(f"/out/{stem}.stderr", "wb") as file:
        file.write(err.getvalue().encode("utf-8"))
    return code
`);
  const parityCli = pyodide.globals.get("parity_cli");

  // The same commands, in the same order, as the coordinator's CLI side.
  const COMMANDS = {
    check: (play) => ["play", "check", play],
    "check-json": (play) => ["play", "check", play, "--json"],
    walk: (play) => ["play", "walk", play],
    "walk-json": (play) => ["play", "walk", play, "--format", "json"],
    sequence: (play) => ["play", "sequence", play],
  };
  result.runs = [];
  for (const caseName of cases) {
    for (const [command, args] of Object.entries(COMMANDS)) {
      const stem = `${caseName}.${command}`;
      const code = parityCli(`/work/${caseName}`, pyodide.toPy(args("case.play")), stem);
      for (const stream of ["stdout", "stderr"]) {
        fs.writeFileSync(path.join(outDir, `${stem}.${stream}`), pyodide.FS.readFile(`/out/${stem}.${stream}`));
      }
      fs.writeFileSync(path.join(outDir, `${stem}.code`), `${code}\n`);
      result.runs.push({ case: caseName, command, exitCode: code });
      console.error(`${stem} exit=${code}`);
    }
  }
  parityCli.destroy();
}
server.close();

const outside = fetched.filter((url) => !url.startsWith(origin));
result.fetchCount = fetched.length;
result.fetchOtherOrigin = outside;
result.socketNonLoopback = [...new Set(sockets)].filter(
  (address) => address && !address.startsWith("127.0.0.1") && address !== "::1",
);
const text = JSON.stringify(
  { installError, fetchCount: fetched.length, fetchOtherOrigin: outside, pyodide_version: pyodide.version, wheels: wheelNames },
  null,
  2,
);
const summaryFile = path.join(outDir, "summary.json");
fs.writeFileSync(summaryFile, text);
console.log(summaryFile);