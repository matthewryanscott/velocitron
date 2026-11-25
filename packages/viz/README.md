# `packages/viz`

The net → view / render library, in two language packages:

- [`python/`](python/) — distribution `velocitron-viz`, import `velocitron_viz`
- [`typescript/`](typescript/) — package `@velocitron/viz` (`"private": true`)

`net_to_dot` / `netToDot` draws an already-built net as Graphviz DOT.
`apply_view` / `applyView` pins an authored view onto that drawing through
the render model's line index. Fusion places draw as one local copy per
connected transition. Two neighbor transitions of one choice can share a
copy when the place is `beside` and names no side.

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

## Layout metrics

`layout_metrics(json_text)` reads one Graphviz `-Tjson` drawing and reports
how hard it is to follow. It measures the geometry Graphviz produced. It
does not guess a layout from DOT.

`velocitron-viz design.petrinet --metrics` renders the net, runs the engine
the DOT names (`dot`, or `neato` when a view pins positions), and prints
JSON. `velocitron-viz design.petrinet --metrics --view window` measures that
view. `velocitron-viz --metrics -` reads `-Tjson` from stdin. If the engine
is not on `PATH`, the command exits with an error.

Before layout, each arc edge is stamped `id="arc:<handle>"` on the statement
`RenderModel.arc_lines` names. An arc with an authored handle uses that
handle; any other arc uses its declaration index. A fusion copy is a
separate drawn edge and keeps the source arc's id. The report names each
crossing as `a→b × c→d` together with those ids.

`crossings` counts interior crossings of visible edges. A hit within ε of an
endpoint the two edges share is not a crossing. Adjacent edges that cross
away from that endpoint still count. `style=invis` edges, the `beside`
chains, are skipped. `overlaps` counts collinear runs, the shared channel an
ortho route often takes, and keeps them out of `crossings`.
`edge_node_overlaps` counts an edge drawn through a node that is not one of
its ends. `edge_length` is in points: total, mean, and the longest five
arcs. `bends` counts corners (a turn of at least 20 degrees that leaves the
straight chord), which is the useful number on an ortho route. Curves are
flattened until they are within a fixed tolerance of the chord, and hits
closer than ε are one hit. ε grows with the drawing.

`graphviz_version` and `engine` say what produced the numbers. Compare
crossings, overlaps, lengths, and bends only when they come from the same
Graphviz version. One version lays the same DOT out the same way on every
run. A different version may not. A gate should use a threshold, not an
exact count.

The metrics function and the arc-id stamp are Python. The TypeScript package
ports the standalone-net drawing (`netToDot`, `applyView`) and does not
measure a layout.
