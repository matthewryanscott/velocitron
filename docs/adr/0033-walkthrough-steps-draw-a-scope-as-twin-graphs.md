# Walkthrough steps draw a scope as twin graphs, with chosen token fields

**Status:** Accepted.

ADR 0031 drew each walkthrough step as one Graphviz graph with two clusters,
before and after, over the whole touched subnet, and every token as its full
JSON. On a real net (one hold's lifecycle, 15 transitions) this was hard
to read. Each step showed the whole subnet. The two halves had different
layouts, and one often looked like a mirror image of the other. And a token
row was a wall of JSON in which the one changed field was hard to find.

## Decision 1: a step draws its scope, by default the smallest one

A play setting `scope step|neighbors|subnet`, the `velocitron play
walk --scope` flag, or the Obsidian fence option `scope=` picks what a
step's graphs draw. The flag wins over the setting.

- `step` (the default): a firing's transition and every place on its arcs,
  and no other transition. An injection, update or advance: its place alone.
- `neighbors`: also the other transitions on those places, faded and with
  unlabeled arcs, but not through a fusion place, which is drawn as one copy
  per transition and so has no single neighborhood in the picture.
- `subnet`: the whole touched subnet, as ADR 0031 drew it.

The starting marking still draws the whole touched subnet, so the reader
sees the context once.

**Considered options:** an injection's `step` scope could add the
transitions that the new token enables or disables. Rejected: that set
depends on the marking, so the picture of one statement would change with
the steps before it. `neighbors` shows those transitions for every
injection.

## Decision 2: before and after are two graphs with one layout

The two halves are two DOT graphs (`before_dot`, `after_dot`) with the same
nodes, arcs and ids, and each node has the same size in both. A marking row
that only one half draws is a transparent ghost in the other, and a
highlight label that differs between the halves (`fires`, `fired`) sits in
a fixed-width cell. `dot` lays out two such graphs the same way, measured
over every step of the hold play in all three scopes.

**Considered options:**

- One graph with two clusters, and `rank=same` plus an invisible edge
  between twins (ADR 0031). Rejected: `dot` orders and places both halves in
  one pass, and the halves drift; flat edges between twins can mirror one.
- One graph without twin edges. Rejected: still one coordinate pass; halves
  drifted by up to 58 points in the measured steps.
- One graph with `pack=true`, which lays out each half apart. Rejected:
  `dot` then drops every edge label (Graphviz 16.1), so arc predicates and
  summaries disappear.
- A layout pass in velocitron (`dot -Tjson` on one half, then pinned
  positions for `neato -n`). Rejected for now: it needs `dot` where
  velocitron runs, and Kroki renders the plugin's graphs, so two renderers
  would have to agree on fonts.
- One graph per step that shows the token flow only. Kept as the fallback if
  twin graphs fail on a later net; the twins show the before marking whole,
  which a flow graph cannot.

The Obsidian plugin shows the two graphs side by side (stacked with
`direction=LR`) at one scale. Markdown output gives two fences.

## Decision 3: a color may show chosen fields; changed fields always show

A net decoration `decorate color C show "f" "g.h"` (ADR 0028's vocabulary,
extended additively per ADR 0025) and a play setting
`show C f, g.h` name the fields a marking row shows for color `C`. The
play's choice replaces the net's for that color. A dotted path reaches
into a nested object. Without a choice, a row keeps its full JSON.

A field the step changed is always shown, bold, underlined and amber, in
the new token and in the old one. The old token is the one consumed or
replaced token of the same color; with none or several, the token is new.
The place's tooltip holds every token's full data.

## Decision 4: token marks differ for color-blind readers

Consumed and replaced rows are pink and struck through; produced and
injected rows are light blue and bold. A read row has no fill and a dashed
outline, so it differs by shape, not by a third hue.

## Consequences

- The WalkthroughDocument replaces `pair_dot` with `before_dot` and
  `after_dot`, and gains `scope` and `direction`.
- `velocitron.viz.net_pair_dot` becomes `net_twin_dots`.
- `velocitron play check` and `walk` read `-` (stdin) with
  `--origin DIR`, so an editor can walk an unsaved play.
