# A renderer places each fusion copy from its own position

**Status:** Accepted (2026-11-25). Builds on ADR 0068. Amends ADR 0067.

ADR 0068 stores a position for one fusion copy as
`place:<P>@transition:<T>`. The renderer still mapped `place:<P>` to every
copy of `P`, so it could not paint that entry. ADR 0067 also kept a
whole-place position off every `beside` copy. An author who pinned six
copies of one lock still had no way to put each copy on its own point, and
a whole-place position stacked them. `overlap=scale` then shrank the drawing.

## Decision 1: the render model indexes each drawn copy

`copy_lines` maps `(place, transition)` to the statement line of that copy's
node. `node_lines["place:<P>"]` still lists every copy of `P`. A shared copy
(ADR 0035, one node `P@a+b`) is one line under both transitions. Python and
TypeScript record the same index, per ADR 0025 Decision 5.

Applying a view looks the copy up by that pair. It does not parse the DOT
text. Two entries for one shared copy that resolve to different points are
rejected. The resolver already requires them to agree; the renderer rejects
a payload that does not.

## Decision 2: copy, then place, then `beside`

For each drawn copy, the first of these that applies is the point written
on its node:

1. The copy entry `place:<P>@transition:<T>`, after relative resolution.
2. The whole-place entry `place:<P>`.
3. The `beside` offset from a pinned transition (ADR 0067).

A whole-place entry still anchors `relative (P)`. It is not a copy's point
once a copy entry exists. `relative (P)@[T]` adds its delta to the point
where that copy is drawn, which is the resolved copy entry. A view with no
positions stays on `dot` and keeps the rank clusters.

**Considered options:**

- Keep ADR 0067's rule that `beside` wins over a whole-place entry.
  Rejected: the place entry would never land on a `beside` copy, so the
  copy entry would be the only way to move one, and a place entry would
  keep meaning two different things.
- Drop `overlap=scale` once every copy is pinned. Rejected: the attribute
  still keeps orthogonal edges, and distinct pins give it nothing stacked
  to scale. The scale of that drawing stays 1.

## Decision 3: one lint for a stacked place position

`beside-position-shadowed` is retired. The position is no longer shadowed.

`fusion-place-position` flags a whole-place position that lands on more than
one drawn copy, whether or not the place has `beside`. A copy entry removes
that copy from the count. One remaining copy is not a stack.
`place-position-overridden` still flags a place entry that every copy
overrides. The place silences either rule with `annotations.lint.suppress`.

## Consequences

- `apply_view` / `applyView` move together. A golden drawing of one lock
  with six pinned copies is the same text in both languages. No two copies
  share a point, and `neato` with `overlap=scale` does not scale that
  drawing down.
- A suppression of the retired rule has no effect.
