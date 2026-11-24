# Views are applied by a render model, never spliced into rendered DOT text

**Status:** Accepted.

Authored views — a view's `positions` and `routes`, plus the `arcHandles`
map needed to resolve arc handles to arcs — are applied to a rendered net by
consulting a **render model**: a structural index built by the same rendering
pass that emits the DOT (`velocitron.viz.net_render_model(net, ...) ->
RenderModel`), never by splitting a rendered DOT string. The application pass
lives in `velocitron.viz_view.apply_view(model, raw, view_name)`.

ADR 0020 keeps presentation data in `annotations["petrinet.dsl/v1"]` and out
of the compiler; ADR 0011 keeps it inert. This record settles *how* that data
reaches the rendered graph, and it is the mechanism decision the follow-on
presentation-vocabulary work (decorations, relative-position wire shapes)
builds on.

## Decision 1: a structural model, not DOT text mechanics

`RenderModel` records, for each `place:` / `transition:` subject key, the
statement line indexes of the canonical node and every fusion instance, each
arc's edge line by declaration index, and the semantically valid insertion
line for graph-level attributes (`splines=ortho`). `net_to_dot` delegates to
`net_render_model` and returns its `dot` — one formatting truth, two entry
points by convenience.

**Considered options:**

- Keep the text splice (`_selected_view_dot`) and harden its heuristics.
  Rejected: the mechanics are unrecoverably positional — caption prefix
  matching (`    "{name}" [`, `    "{name}@`), an edge ordinal derived by
  counting lines containing `" -> "`, and a `splines=ortho` insertion at a
  fixed line index. That gave `net_to_dot`'s formatting an undeclared, easily
  broken interface role (an edge label containing `" -> "` misindexes every
  later route), silenced unknown position subjects instead of failing them,
  and left nothing to compute relative offsets against.
- `net_to_dot` returns `(dot, model)`. Rejected: every call site and roughly
  forty existing test calls churn for no behavioral gain; the sibling function
  keeps signatures stable while the model remains the single source.
- Pass an attribute hook into `net_to_dot`. Rejected: callbacks threaded
  through attribute construction model neither the header nor the edge
  ordering, and tests would still need the constructed text.

## Decision 2: relative offsets resolve at render time

A relative position fact names a base subject and a delta; chains resolve in
dependency order to a fixed point, and cycles reject. The rendered layout is
never consulted (that — layout-computed positions — remains a future
render-stage feature once the pipeline owns the `dot` invocation).

**Considered options:**

- Resolve relative facts to absolute coordinates at lowering time, so the
  payload only ever stores `{x, y}`. Rejected: the canonical re-emission
  re-renders payload positions back to DSL, so baked coordinates overwrite
  authored intent on the first round trip and moving a base node strands its
  dependents — the iteration workflow this surface exists for.
- Render-time resolution (chosen): authored intent survives emission, the
  compiler stays presentation-scarce per ADR 0020, and the resolution engine
  is testable at `viz_view`'s own seam with constructed fixtures.

**The relative entry wire shape is provisional.** Until the compiler-owned
presentation vocabulary is decided (a separate record, when that work lands),
relative entries are a hand-authored convention validated only in `viz_view`;
`_reserved_payload` continues to reject them in canonical documents, so no
wire contract changes in this slice.

## Decision 3: geometry now, decorations later

The pass applies the vocabulary that exists today — positions, orthogonal
routes, the `splines=ortho` view attribute. Decoration passes (labels,
colors, highlights) ride the same model when their channel decision lands;
nothing in this record presumes their shape beyond "render-side, inert".

## Consequences

- The splice mechanics are deleted; unknown position subjects and arc indexes
  beyond the rendered arc count now raise named errors instead of silently
  no-oping.
- The `splines=ortho` insertion becomes semantic (after graph defaults,
  before the body) instead of positional (fixed line 2). Only the DOT text
  ordering of the inserted line changes; rendering is unaffected.
- Absolute-fact semantics are unchanged: `pos="x,y!"` pinning, route
  `pos="x,y ..."` rendering, and a place target positioning the canonical
  node plus every fusion instance.
- Composition renders continue to render un-viewed; if composition merge
  later carries the payload, `apply_view` accepts the merged render without
  shape change.
- TypeScript is unaffected: rendering is Python-only and stays behind the
  browser seam.