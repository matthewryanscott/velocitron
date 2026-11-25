# A view can position one fusion copy

**Status:** Accepted (2026-11-25). Builds on ADR 0067.

ADR 0067 places each `beside` copy next to its transition when a view pins
that transition. A whole-place `position (P)` does not move those copies.
It still anchors `relative (P)`. An author who wants one copy somewhere
else had no way to say so: a view target was only `(P)` or `[T]`, and one
place entry covered every drawn copy.

## Decision 1: `(P)@[T]` names one drawn copy

`ViewTarget` is `(Place)`, `(Place)@[Transition]`, or `[Transition]`.
`(P)@[T]` is one drawn copy of place `P` at transition `T`. The
contribution is a closed `placeCopy` target `{place, transition}`. The
stored position key is `place:<P>@transition:<T>` in the view's existing
`positions` map. There is no new view member.

The resolver accepts the fact only when all of these hold:

- `P` is annotated `fusion true`. A place drawn once has no copies.
- `T` is declared and has an arc to `P`. A copy exists only where the
  transition uses the place.
- The position is an absolute point or a relative offset, and the target
  may be the subject or the base.

Two facts for the same `(P)@[T]` follow the ordinary rule: equal positions
are idempotent, and different ones conflict.

## Decision 2: a shared copy is one position

ADR 0035 draws one copy between two neighbor transitions when they share
one non-fusion input and the place has `beside` with no side. `(P)@[left]`
and `(P)@[right]` name that one copy. Equal positions are idempotent.
Different positions conflict. The resolver uses the same pairing the
renderer uses, so the two cannot disagree about which transitions share a
copy.

A place with `beside left` or `beside right`, or with no `beside`, draws a
separate copy at each transition. Those targets do not have to agree.

## Decision 3: a bare place base is the place entry

Mixing rule A: a copy entry overrides the whole-place entry for that copy.
`relative (P)` means the place entry's point, not whichever copy happens to
be nearest. The resolver rejects a bare `(P)` base when the view has no
position whose subject is `(P)`. A `(P)@[T]` base is that copy's point, so
the view must position that copy. A transition base is still only checked
as a declared transition; applying the view rejects one that carries no
position.

A whole-place entry that every drawn copy overrides no longer lands on a
copy. `place-position-overridden` warns. The entry still anchors
`relative (P)`. The place silences the warning with
`annotations.lint.suppress`.

## Consequences

- Python and TypeScript accept the same target, per ADR 0025 Decision 5.
  The grammar, the contribution schema, the resolver, and the formatter
  move together.
- Drawing the copy at that point is a later change. Until then a renderer
  still places `beside` copies by ADR 0067, and a view whose positions
  include a copy key is not applied.
- Conformance group `28-place-copy-views` pins a valid view and the
  rejections: a non-fusion place, an unknown transition, a transition that
  does not use the place, a conflicting shared copy, and a bare place base
  with no place entry.
