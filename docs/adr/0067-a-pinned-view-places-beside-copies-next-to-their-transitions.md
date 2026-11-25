# A pinned view places `beside` copies next to their transitions

**Status:** Accepted (2026-11-25). Amends ADR 0029 Decision 4.

ADR 0029 keeps each copy of a fusion place next to the transition that uses
it. Decision 4 dropped that fact as soon as a view positioned any node:
`neato` ignores ranks and clusters, so the rank clusters could not hold the
copies in place. The copies then landed wherever `neato` put them. A
whole-place `position` made it worse. The render model maps `place:<name>`
to every copy's node, so one point was written onto all of them.
`overlap=scale` then shrank the drawing to pull the stacked nodes apart,
and Graphviz could fail on the stack.

A view that pins the transitions of a shared lock, and says nothing about
the lock's copies, should still draw each copy beside its transition.

## Decision 1: an unpositioned `beside` copy follows its pinned transition

When a view positions any node it still selects `neato` (`layout=neato`,
`inputscale=72`, `overlap=scale`) and still omits the rank clusters. Those
clusters are for `dot`. Their invisible edges would remain as springs.

For each `beside` copy, if the view pins the transition that copy sits
with, the renderer pins the copy as well. A whole-place position does not
paint those copies. It stays in the resolved positions, so another node
can still be `relative` to `(P)`.

- The offset is `slots × gap` points on x, and `0` on y, added to the
  transition's resolved position. `gap` is half the transition's width,
  plus half the wider copy's width on that side, plus a margin of 24
  points. Width is the longest label line plus 20 points of chrome. A
  character advances half its point size: names are 14pt, and color and
  behavior lines are 9pt. Both implementations use these numbers, so the
  pictures match. Marking rows are not part of the estimate.
- Left is negative x and right is positive x. `neato` does not turn the
  picture with `rankdir`, so the offset stays horizontal in the view's
  coordinates. The side is still the one ADR 0029 Decision 3 chooses,
  including a copy with no side: the side with fewer copies so far, left
  on a tie.
- The copy nearest the transition, in the beside row's order, is one gap
  away. The next on that side is two gaps, and so on.
- A copy whose transition the view does not pin stays unpinned. `neato`
  places it. The copy arcs keep `constraint=false`.

A view with no positions stays on `dot` and keeps the rank clusters.

**Considered options:**

- Keep dropping `beside` (ADR 0029 Decision 4). Rejected: the copies drift,
  and a shared lock drawn once per transition collapses when the view also
  positions the place.
- A fixed gap. Rejected: a long label overlaps the transition, and a short
  one leaves a hole. The width estimate is the same function in both
  languages, so parity does not require a constant.
- Give the offset a y component so it follows `rankdir`. Rejected: `neato`
  ignores `rankdir`, and the view's coordinates are already the picture.
- Paint the whole-place position onto every copy. Rejected: that is the
  stack this record exists to stop. The position remains the anchor for
  `relative (P)`.

## Decision 2: a shared copy sits between its two transitions

ADR 0035 draws one copy between two neighbor transitions. That copy has two
anchors.

- When the view pins both, the shared copies of that pair are spaced evenly
  along the segment that joins the two positions. One shared copy is the
  midpoint.
- When the view pins only one, the copy takes the gap offset from that
  transition, on the inner side, past any copy that is nearer.

## Decision 3: two lint warnings for a whole-place position

Both findings name the view and the place. They are advisory (ADR 0016).
The place silences one with `annotations.lint.suppress`.

- `beside-position-shadowed` flags a whole-place `position` on a fusion
  place that has `beside` and draws at least one copy. The position is
  shadowed for those copies. The message says it still anchors
  `relative (P)`.
- `fusion-place-position` flags a whole-place `position` on a fusion place
  with no `beside` that draws more than one copy. Those copies still share
  one point.

A fusion place drawn once, with no `beside`, is not flagged. The position
lands on that one copy.

**Considered options:**

- Reject the position while resolving the net. Rejected: the position is a
  defined picture, and a warning can be acknowledged. A later per-copy
  position can override one copy without making today's documents invalid.
- One rule for both shapes. Rejected: one shape is shadowed and still
  useful as an anchor, and the other stacks the drawing. A suppression
  should name which one it acknowledges.

## Consequences

- Python and TypeScript `apply_view` / `applyView` move together, per ADR
  0025 Decision 5. The render model records where each `beside` copy sits;
  applying the view writes the point. It does not parse the DOT text.
- The language accepts a per-copy `(P)@[T]` position. Applying that
  position in the drawing is a later change; until then a view that names
  one still places `beside` copies by ADR 0067.
- The beside conformance source has a pinned view and a `lanes_lock` view
  that also positions the fusion place.
- `velocitron validate` prints the warnings and still exits 0. For a
  `.petrinet` file each warning points at the view's `position` fact.
