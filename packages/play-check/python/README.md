# `velocitron-play-check`

Check a `.play` document against a net and step a walkthrough. The import
name is `velocitron_play_check`. The TypeScript package is
`@velocitron/play-check`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/play-check/python` subdirectory.

Version 0.1.0 is alpha software. The checker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`check_play(play, *, paths=None, validate_ir=True)` loads the play's net
and plays each path. `SC2xx` is raised. A step that fails (`SC3xx`) ends
that path's trace. `render_walkthrough` writes one path as Markdown,
including paired Graphviz graphs. `walkthrough_document` is the same path
as JSON. `trace_document` and `render_plantuml` project the path onto a
sequence diagram.

Symbolic firing uses `velocitron_engine`: `reserve` and `settle`, with
outputs from the play or the carry rule. The engine still decides
enablement, binding, timers, and deposit.

## What this package does not do

- Parse `.play`. The grammar and AST are `velocitron_play`.
- Own the fire loop or journal durability. `records_to_play` writes the
  play that replays a journal and lives in this package.
- Compile `.petrinet` except to load the net a play names. That compiler
  is `velocitron_petrinet`.
- Own the product CLI. `velocitron play` calls this package.
- Prove a net. Kept-record starts are evaluated here so a play can begin.
  The kept-record model lives in `velocitron_analysis`.

`records_to_play` lives in this package. It builds an engine with
`get_default_adapter()`. This package does not import `velocitron`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. Install `velocitron-play`, `velocitron-petrinet`,
`velocitron-engine`, `velocitron-cel`, `velocitron-dsl`, `velocitron-merge`,
and `velocitron-viz` the same way, from their own subdirectories.

```toml
[project]
dependencies = [
  "velocitron-play-check @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/play-check/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-play-check = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/play-check/python" }
```

```python
from velocitron_play import read_play
from velocitron_play_check import check_play, render_walkthrough

report = check_play(read_play("shop.play"))
assert report.passed
print(render_walkthrough(report.traces[0]))
```
