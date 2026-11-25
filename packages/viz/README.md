# `packages/viz`

The net → view / render library, in two language packages:

- [`python/`](python/) — distribution `velocitron-viz`, import `velocitron_viz`
- [`typescript/`](typescript/) — package `@velocitron/viz` (`"private": true`)

`net_to_dot` / `netToDot` draws an already-built net as Graphviz DOT.
`apply_view` / `applyView` pins an authored view onto that drawing through
the render model's line index. Fusion places draw as one local copy per
connected transition. Two neighbor transitions of one choice can share a
copy when the place is `beside` and names no side. `beside unshared` keeps
one copy per transition and pushes a choice's copies outward. A view that
pins a transition places each unpositioned `beside` copy beside it.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

Callers import `velocitron_viz` or `@velocitron/viz`. The `velocitron-viz`
console script lives in `velocitron-cli`. `python3 tools/viz_package.py
check` fails if a retired facade grows the renderer back. The TypeScript
renderer is a port of the standalone-net surface.

## What this package draws

- Places, ports, transitions, and consume / read / inhibit / produce arcs
- A selected marking inside each place
- Fusion copies and `beside` rows, including a shared copy between neighbors
- Decorations: highlight, note, summary, quiet colors, and shown token fields
- Authored views: positions, orthogonal routes, and spline style

## What stays outside

Document loading and the `velocitron-viz` command live in `packages/cli`
(`velocitron_cli.viz_main`). The umbrella keeps the `velocitron.viz:main`
entry. That command merges a fused drawing through `velocitron_merge` and
`validate_net`. Pass an already-merged net to `net_to_dot`. `.petrinet`
compilation ships in `packages/petrinet`. The play walkthrough ships in
`packages/play-check`, which calls `net_twin_dots` from this package.

The Python package also draws composition clusters, port diagrams, the
business overview, the feature legend, and the paired graphs a walkthrough
uses (`net_twin_dots`). The TypeScript package does not. It has no
composition overview, no legend, and no per-token step marks. Those need
the parsed composition and the play checker, which this package does not
carry. `@velocitron/core` still has no renderer of its own.
