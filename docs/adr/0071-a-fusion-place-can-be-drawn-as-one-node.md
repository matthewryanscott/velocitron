# A fusion place can be drawn as one node

**Status:** Accepted (2026-11-25).

A fusion place is drawn as one local copy per transition that uses it
(CONTEXT.md "Fusion place", ADR 0029). The only way to draw it as one node
was `velocitron-viz --no-fusion`, which collapses every fusion place and
drops the dashed gray style that says the place is supplied from outside.
Removing `annotation fusion true` is not a substitute: the prover treats
that annotation as open. This record adds a render-only choice, per place
and per view, and marks the flag deprecated.

## Decision 1: `decorate (Place) single`

```text
decorate (Place) single
```

It lowers to the closed IR kind `decoration.single` and resolves into the
ADR 0028 payload as `decorations["place:P"].single = true`. It belongs to
no view, so it applies under `--no-view` and in a Markdown fence.

The node keeps the dashed gray fusion style. Its arcs drop
`constraint=false`, so the one node takes part in ranking. Copies of a
place that stays fused keep `constraint=false` when a `beside` row places
them.

`single` on a transition or a handle is rejected while lowering. `single`
on a place that is not annotated `fusion true` is a PN202 resolution
diagnostic, the same check ADR 0029 gives `beside`: a silent no-op would
hide a typo. The check needs the literal value `true`.

`single` and `beside` on the same place conflict. A single node has no
copies to place.

## Decision 2: a view can choose `single` or `copies`

```text
view Name fusion (Place) single
view Name fusion (Place) copies
```

Each fact lowers to `view.fusion` and resolves to
`views[Name].fusion["place:P"]`, the string `single` or `copies`. An equal
repeat is idempotent. Two modes for one place in one view conflict. The
place must be declared and annotated `fusion true`.

Precedence, highest first:

1. `--no-fusion` draws every fusion place as one ordinary node.
2. The view's `fusion` fact, when that view is applied.
3. `decorate (Place) single`.
4. The default: one copy per transition.

A view that resolves a place to `single` drops that place's `beside` rows.
The `beside` decoration stays in the payload. The whole-place position, if
the view has one, lands on the one node.

**Considered options:**

- Decoration only, with the view form later. Rejected: the request is to
  choose per view without a flag, and the view fact is one more IR kind.
- A per-copy `(P)@[T]` fact. Rejected for this record: the choice is "draw
  this place once", not "place this copy". A later per-copy target can land
  beside this rule.

## Decision 3: `--no-fusion` stays, and is deprecated

The flag keeps working. It still wins over the view and the decoration, and
it still draws ordinary nodes rather than dashed fusion nodes. Using it
prints a deprecation warning that points at `decorate (P) single` and
`view V fusion (P) single`. The help text says the same. Removal is a later
release.

## Decision 4: a single node has one position

ADR 0072 places each drawn copy from `place:<P>@transition:<T>`. A place
drawn as one node has no copies, so those facts do not apply. The one node
takes a whole-place position when the view has one. `velocitron validate`
warns (`single-copy-position`) instead of dropping the copy facts with no
sign.

## Consequences

- Python and TypeScript, the IR schema, the payload validator, emission,
  viz, and conformance case `21-decoration-single` move together, per ADR
  0025 Decision 5. The case pins the decoration, a view override in each
  direction, PN202 for `single` without `fusion true`, and the
  `single`+`beside` conflict.
- `single` is inert like every decoration. No engine, property, or
  composition code reads it. Composition renders draw no decorations, so
  they draw no `single` node.
- The CLI DOT renderer and `velocitron-viz` share one drawing path, so a
  single fusion node is the same picture from both.
