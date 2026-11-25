# `beside` keeps fusion copies next to their transitions

**Status:** Accepted. Amended 2026-11-25 (Decision 4, by ADR 0067; the
`unshared` modifier, by ADR 0070; the nearest copy, by ADR 0069).

A fusion place renders as one local copy per transition that uses it
(CONTEXT.md "Fusion place"). With the default `dot` layout, crossing
minimization decides where each copy goes, and it often puts a copy on the far
side of the graph. Its read arc then crosses other arcs, and moving source
lines around only moves the problem. This record adds a presentation fact that
keeps the copies beside their transitions, and settles how `dot` draws it.

## Decision 1: a `beside` decoration on the fusion place

```text
decorate (Place) beside [ left | right ] [ unshared ]
```

It lowers to the closed IR kind `decoration.beside` and resolves into the
ADR 0028 payload as `decorations["place:P"].beside`, an object with an
optional `side`. It is one fact per place, and it applies to every copy of
that place. `unshared` is ADR 0070.

**Considered options:**

- A fact per copy (`decorate (P)@[T] beside`). Rejected: authors meet the
  problem as "this place's copies wander", and a per-copy fact needs one line
  per transition, kept in step as arcs change. A per-copy override can be
  added later without changing this fact.
- A renderer flag (`--fusion-beside`). Rejected for the reason ADR 0028
  Decision 4 gives for `quiet`: a Markdown fence must render right without
  flags.
- A decoration on the place (chosen).

`beside` on a transition or a handle is rejected while lowering. `beside` on a
place that is not annotated `fusion true` is a PN202 resolution diagnostic. We
reject it instead of giving it a meaning, because a place drawn once has no
copy to place, and a silent no-op would hide a typo in the place name or a
missing annotation. The check needs the literal value `true`, so it does not
depend on how each language treats other values as true or false.

## Decision 2: a ranked invisible cluster per transition

For each transition with beside copies, the renderer emits:

```dot
newrank=true;
subgraph "cluster_beside_0" { label=""; peripheries=0; margin=0;
  { rank=same; "branch_home@hold"; "hold"; "shelf_slot@hold"; } }
"branch_home@hold" -> "hold" -> "shelf_slot@hold" [style=invis];
```

**Considered options, checked by rendering a real net:**

- `rank=same` with an invisible ordering chain only. Rejected: `dot` kept the
  order, but put other nodes from the same rank between a copy and its
  transition, so a copy could still sit far away.
- The same inside a cluster, without `newrank`. Rejected: `dot` ranks a
  cluster on its own, and the cluster pulled its transition above the place
  that feeds it.
- An invisible cluster around the `rank=same` group, with `newrank=true`
  (chosen). The cluster keeps the group together, and `newrank` ranks the
  whole graph at once. `newrank` is set only when the net has a beside group,
  so other renders do not change.

## Decision 3: sides, defaults and directions

- `left` copies go before the transition and `right` copies after it. The
  first copy, in the structural emission order (ADR 0069), sits nearest.
- A copy with no side goes to the side that has fewer copies so far, `left` on
  a tie. Two copies then sit one on each side. Each read arc is a short
  straight edge, and no arc arches over another copy.
- The sides are those of a top-to-bottom layout. Graphviz turns or mirrors
  the whole picture for other directions: `bt` keeps them, and `lr` and `rl`
  put `left` below the transition and `right` above it. We keep this as is
  and do not swap the sides per direction, because the result is the TB
  picture turned, the same as every other part of the render.

## Decision 4: a view with positions drops `beside`

A view that positions nodes switches to `neato` (ADR 0024). `neato` ignores
ranks and clusters, so it cannot keep a copy beside its transition. Only the
invisible ordering edges would stay, as extra springs. The render model
records the beside statements, and applying such a view removes them. Views
with style facts only stay on `dot` and keep `beside`. The author of a
positioned view sets the geometry by hand.

*Amended by ADR 0067 and ADR 0072. A view that positions nodes places a
`beside` copy relative to its transition when the view positions neither
that copy nor its place.*

## Consequences

- Both implementations, the IR schema, the payload validator, emission, and a
  `20-decoration-beside` conformance case move together, per ADR 0025
  Decision 5.
- `beside` is inert like every decoration: no engine, property, or
  composition code reads it. `--no-fusion` and composition renders draw no
  copies, so they draw nothing for it. `--no-fusion` is deprecated (ADR 0071):
  it still wins over a `single` decoration and a view `fusion` fact, and it
  still draws every fusion place as one ordinary node.
