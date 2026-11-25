# Neighbor siblings share one fusion copy

**Status:** Accepted. Amended 2026-11-25 (the `share` flag, by ADR 0070).

A fusion place renders as one local copy per transition that uses it, and
`beside` keeps each copy on its transition's rank (ADR 0029). A choice often
puts two transitions that read the same fusion place next to each other: in the
hold net, `[lend]` and `[recall]` both consume from `(requested)` and both
read `(branch_home)`. The picture then shows two equal copies side by side
between them: `lend ← branch_home   branch_home → recall`. The reader sees
two places where the net has one. This record makes the renderer find such
neighbors and draw one copy between them, with an arc to each.

The number 0034 is skipped on purpose: a parallel branch may take it.

## Decision 1: siblings are found from the net's structure

The renderer does not run a layout pass to find neighbors. It finds them in
the net:

- A **sibling group** is two or more transitions whose one drawn input place
  is the same place. Fusion places do not count as inputs, because each copy
  sits beside its own transition. Any arc mode counts: consume, read and
  inhibit.
- The group's order is the order of each transition's first arc from that
  place. The author sets it by the order of the source lines.
- Two transitions are **neighbors** when they are next to each other in that
  order.

We do not trust `dot` to put siblings next to each other. The renderer puts
the transitions it links (Decision 2) into one `beside` row, so the shared
copy is always between its two transitions.

**Considered options:**

- Every transition that consumes from the place. Rejected: a transition with
  a second drawn input usually sits on a lower rank, and forcing it into the
  row bends the graph.
- Ask `dot` for a layout first, then share copies of nodes it put side by
  side. Rejected: two layout passes, and the second can move the nodes again.
- One drawn input place, in arc order (chosen).

## Decision 2: pair from the left

For each fusion place with `beside` and no side, the renderer finds the runs
of neighbors in a group that all use the place:

- It pairs a run from the left: the first two share a copy, then the next
  two, and so on. A shared copy sits right of the first transition and left
  of the second.
- In a run of odd length, the last transition keeps its own copy, on its
  right, away from the pair. Its copy then does not sit next to the shared
  one.
- The transitions a run links form one row, in group order. Their own copies
  balance as ADR 0029 Decision 3 says, and a shared copy counts on the side
  of both its transitions.
- Copies on transitions that are not neighbors stay separate.

A run of three `A, B, C` gives `A P B C P`. Pairing from the right
(`P A B P C`) would use the same number of copies. We chose the left because
the first lines of the source are the ones authors read first.

A place with `beside left` or `beside right` does not share copies. The
author has fixed a side for every copy, and a shared copy is on the right of
one of its transitions.

*Amended by ADR 0070. `beside unshared` sets `share: false` and turns this
sharing off for that place. The siblings stay in one row, and each copy is
pushed outward.*

Any arc mode shares a copy. A copy already stands for every arc between its
place and its transition (an inhibit arc and a produce arc to one transition
share one copy), so two transitions sharing it is the same kind of fact. Each
arc keeps its own edge statement, label and summary.

## Decision 3: rows keep their order with `remincross=false`

A row is one invisible cluster around a `rank=same` group, with an invisible
edge chain in row order (ADR 0029 Decision 2). A row of seven nodes in the
hold net came out rotated: `dot` put the last two nodes at the far left.
Its last crossing pass (`remincross`) runs over the whole graph with clusters,
and that pass broke the chain. With `remincross=false` the row keeps its
order. The renderer sets it next to `newrank=true`, only when the net has a
`beside` row.

## Consequences

- No syntax, IR or payload change. Sharing is automatic for every `beside`
  place with no side. A later branch may add a decoration to turn it off for
  one place. ADR 0070 is that decoration: `beside unshared` sets
  `share: false`.
- A shared copy's node id is `place@first+second`. The render model records
  it under `place:<name>` with the other copies, so a view that positions the
  place moves it too.
- A walkthrough draws the shared copy and its marking once. The twin graphs
  of a step come from the same net and decorations, so both halves share the
  same copies and get one layout.
- `remincross=false` also applies to nets with only one-transition rows. In
  the nets we checked, it did not change their pictures.
