# `velocitron-viz`

Render an already-built Velocitron net as Graphviz DOT. The import name is
`velocitron_viz`. The TypeScript package is `@velocitron/viz`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/viz/python` subdirectory.

Version 0.1.0 is alpha software. The renderer may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`net_to_dot` draws one net. `net_render_model` returns that DOT plus the
line index a view needs. `apply_view` writes positions and routes through
that index. `fusion_layout` places fusion copies. `composition_to_dot`,
`composition_ports_dot`, and `composition_overview_dot` draw an
already-parsed composition. `net_twin_dots` draws one net twice so a caller
can show two markings with one layout.

Construct the net from the dataclasses in this package (`Net`, `Place`,
`Arc`, and the rest). Pass `parsed_nets` yourself when drawing a
composition. This package does not parse JSON, compile `.petrinet`, or
merge nets.

This package is the source of truth for the renderer. Python net values are
the engine's dataclasses, re-exported from `velocitron_viz.schema`.
`python3 tools/viz_package.py check` fails if the umbrella grows the
renderer back.

## What stays in the language implementation

`velocitron.viz` re-exports this package and keeps the `velocitron-viz`
console-script entry. Document loading and the command live in
`velocitron_cli`. The play walkthrough ships in `packages/play-check` and
calls this package.
This package does not install that script.

The TypeScript package ports the standalone-net surface only. Composition
diagrams, the legend, paired graphs, and per-token step marks are in this
Python package.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-viz @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/viz/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-viz = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/viz/python" }
```

```python
from velocitron_viz import (
    Arc,
    ConsumePattern,
    Net,
    Place,
    ProduceTemplate,
    Transition,
    net_to_dot,
)

net = Net(
    name="move",
    places=[Place("src", ["job"]), Place("dst", ["job"])],
    transitions=[Transition("move", handler="move")],
    arcs=[
        Arc(
            from_place="src",
            to_transition="move",
            consume=ConsumePattern("job", None, "consume"),
        ),
        Arc(
            from_transition="move",
            to_place="dst",
            produce=ProduceTemplate("job", "dst"),
        ),
    ],
)
print(net_to_dot(net))
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
