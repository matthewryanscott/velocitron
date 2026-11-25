# A view can position one copy of a fusion place

**Status:** Accepted (2026-11-25). Builds on ADR 0067.

ADR 0067 places each `beside` copy next to its pinned transition, and leaves
a whole-place `position` as the anchor for `relative (P)`. A shared lock
still wants a hand-tuned point for one copy. This record adds that target.
It does not change how an unpositioned `beside` copy is placed.

## Decision 1: `(P)@[T]` names one copy

A view target is `(Place)`, `(Place)@[Transition]`, or `[Transition]`.

```text
view pinned position (lock)@[acquire] relative [acquire] + {"x": -70, "y": 0}
view pinned position (lock)@[release] at {"x": 300, "y": 0}
```

`(P)@[T]` is the copy of fusion place `P` drawn for transition `T`. It is a
subject or a base, and it works for `at` and for `relative`. The payload key
is `place:<P>@transition:<T>` in the view's existing `positions` map. There
is no new view member.

The resolver rejects the fact (`PN202`) unless `P` is annotated
`fusion true` and `T` has an arc to `P`. A typo must not disappear.

ADR 0035 draws one copy between two neighbor transitions. `(P)@[T1]` and
`(P)@[T2]` then name that one copy. Equal positions are idempotent. Different
positions conflict. A place with `beside left` or `beside right`, or with no
`beside`, does not share copies, so the two names stay distinct.

**Considered options:**

- A new view member for copies. Rejected: the positions map already keys
  each subject, and a second member would split the relative chains.
- Accept a copy of a place that is not a fusion place. Rejected: that place
  is drawn once, and a silent no-op hides a typo. The same reason rejects
  `beside` on a place that is not a fusion place.

## Decision 2: a copy entry overrides the place entry

A whole-place `position (P)` is the default for every copy. A copy entry
replaces it for that copy only. The other copies keep the place entry.

`relative (P)` means the place entry's point, not any copy's. It is a
`PN202` diagnostic when the view has no position for `P`. `relative (P)@[T]`
means that copy's point.

A lint warning, `place-position-overridden`, flags a place entry that every
drawn copy overrides. The entry still anchors `relative (P)`. The place
silences it with `annotations.lint.suppress`. A shared copy is overridden
when either of its names is positioned. `fusion-place-position` does not
also flag that place: the copies no longer share the place point.

**Considered options:**

- Reject a view that mixes a place entry and a copy entry. Rejected: the
  common edit is one default and one exception. The mix can be rejected
  later without accepting a document this rule rejects. The other direction
  would break views.
- Let `relative (P)` mean one of the copies once they diverge. Rejected:
  the reader cannot tell which copy. The place entry is the point the
  author wrote for `(P)`.

## Consequences

- Python and TypeScript lower and resolve the target together, per ADR
  0025 Decision 5. The canonical formatter round-trips `(P)@[T]`.
- The contribution IR gains a closed `placeCopy` target, `{place,
  transition}`. The net payload does not gain a member.
- Rendering a copy entry, indexing copies by `(place, transition)`, is a
  later change. Until then a copy entry parses, resolves, and round-trips,
  and the renderer still applies whole-place positions.
- The conformance corpus gains a copy-views case: an unknown copy, a place
  that is not a fusion place, a transition with no arc to the place, and a
  conflicting shared copy.
