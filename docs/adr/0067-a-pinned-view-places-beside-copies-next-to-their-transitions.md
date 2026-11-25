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

For each `beside` copy the view does not position, if the view pins the
transition that copy sits with, the renderer pins the copy as well:

- The offset is `slots × 130` points on x, and `0` on y, added to the
  transition's resolved position. `130` clears a short name plus one color
  line on both nodes at the default Helvetica sizes. Both implementations
  use this constant.
- Left is negative x and right is positive x. `neato` does not turn the
  picture with `rankdir`, so the offset stays horizontal in the view's
  coordinates. The side is still the one ADR 0029 Decision 3 chooses,
  including a copy with no side.
- The copy nearest the transition, in the beside row's order, is one gap
  away. The next on that side is two gaps, and so on.
- A copy whose transition the view does not pin stays unpinned. `neato`
  places it.
- A position of the place itself still applies to every copy of that place.
  The offset does not replace it.

A view with no positions stays on `dot` and keeps the rank clusters.

**Considered options:**

- Keep dropping `beside` (ADR 0029 Decision 4). Rejected: the copies drift,
  and a shared lock drawn once per transition collapses when the view also
  positions the place.
- Derive the gap from label width. Rejected for this change: both
  implementations would need the same font metrics. A fixed gap keeps the
  pictures identical. A later change can measure labels.
- Give the offset a y component so it follows `rankdir`. Rejected: `neato`
  ignores `rankdir`, and the view's coordinates are already the picture.

## Decision 2: a shared copy sits between its two transitions

ADR 0035 draws one copy between two neighbor transitions. That copy has two
anchors.

- When the view pins both, the shared copies of that pair are spaced evenly
  along the segment that joins the two positions. One shared copy is the
  midpoint.
- When the view pins only one, the copy takes the gap offset from that
  transition, on the inner side, past any copy that is nearer.

## Decision 3: a whole-place position on several copies is a lint warning

`fusion-place-position` flags a view that sets a whole-place `position` on
a fusion place the renderer draws as more than one copy. The finding names
the view and the place. It is advisory, like every lint rule (ADR 0016).
The place silences it with `annotations.lint.suppress`. A place drawn as
one copy is not flagged: one transition uses it, or `beside` with no side
has already shared every use into one copy.

**Considered options:**

- Reject the position while resolving the net. Rejected: the position is a
  defined picture, and a warning can be acknowledged. A later per-copy
  position can override one copy without making today's documents invalid.
- Let the offset replace the place position. Rejected: the author asked for
  that point. The warning says the point hits every copy.

## Consequences

- Python and TypeScript `apply_view` / `applyView` move together, per ADR
  0025 Decision 5. The render model records where each `beside` copy sits;
  applying the view writes the point. It does not parse the DOT text.
- No grammar, payload, or contribution-IR change. A per-copy position is a
  later change.
- `velocitron validate` prints the warning and still exits 0. For a
  `.petrinet` file the warning points at the view's `position` fact.
