# `@velocitron/play-check`

Check a `.play` document against a net and step a walkthrough. The Python
package is `velocitron-play-check`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm (`"private": true`). Downstream
projects depend on a git revision of `circuitmeridian/velocitron`
and the `packages/play-check/typescript` subdirectory.

Version 0.1.0 is alpha software. The checker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`checkPlay(play, options?)` loads the play's net and plays each path.
`PlayCheckError` is `SC2xx`. A step that fails (`SC3xx`) ends that path's
trace. `walkthroughDocument` steps one path: statements, markings, and
checks. `renderWalkthrough` prints that document as Markdown.
`markingJson` and `traceJson` are the JSON forms.

Symbolic firing registers a handler on a copy of the net and calls
`Engine.fire`. The handler returns the play's tokens, or the carry rule.
The engine fills `data` / `data cel` templates. `with` matches the one
binding `selectBinding` returns; this runtime does not search the rest.

## What this package does not do

- Parse `.play`. The grammar and AST are `@velocitron/play`.
- Own the fire loop. Enablement and deposit stay in `@velocitron/engine`.
  There is no `reserve` / `settle` here, and no `explainEnablement`, so an
  `SC301` detail is shorter than Python's.
- Draw paired Graphviz graphs or PlantUML. Those stay in
  `velocitron-play-check`.
- Store a journal, write `recordsToPlay`, or own a CLI.
- Skip contribution-IR validation. `compilePetrinetText` has no
  `validateIr` switch.
- Import `@velocitron/core`. The umbrella does not re-export this package.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. Install `@velocitron/play`,
`@velocitron/petrinet`, `@velocitron/engine`, `@velocitron/cel`,
`@velocitron/dsl`, and `@velocitron/merge` the same way.

```json
{
  "dependencies": {
    "@velocitron/play-check": "github:circuitmeridian/velocitron#<ref>&path:packages/play-check/typescript"
  }
}
```

`tsc` compiles this package into `dist/` before it can be imported. A git
install runs the `prepare` script, which is that build.

```javascript
import {parsePlay} from "@velocitron/play";
import {checkPlay, renderWalkthrough} from "@velocitron/play-check";

const play = parsePlay(text, "shop.play");
const report = checkPlay(play, {origin: "."});
if (report.passed) console.log(renderWalkthrough(report.traces[0]));
```
