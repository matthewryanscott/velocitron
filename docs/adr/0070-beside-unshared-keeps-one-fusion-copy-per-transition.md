# `beside unshared` keeps one fusion copy per transition

**Status:** Accepted (2026-11-25). Amends ADR 0035. Extends the `beside`
syntax of ADR 0029.

ADR 0035 draws one shared copy between two neighbor transitions of a choice
when a `beside` place names no side. That is the right default: the reader
sees one place. A choice whose only drawn input is the same place can still
want a copy on each transition, without pinning every copy of the place to
one side. `beside left` turns sharing off, and it also forces every copy,
including copies outside the choice, onto the left. This record adds a
place-wide opt-out that leaves the side automatic.

## Decision 1: `unshared` sets `share` to false

```text
decorate (Place) beside [ left | right ] [ unshared ]
```

`unshared` lowers to the same closed kind, `decoration.beside`. The resolved
payload gains an optional member:

```text
decorations["place:P"].beside = { side?: "left" | "right", share?: false }
```

`share: false` is `unshared`. When `share` is absent the place shares, which
is the ADR 0035 behavior, so existing nets do not change. The member is
additive under the ADR 0028 payload. `share: true` is not a value: absence
is the default, and emission writes `unshared` only for `false`.

`explain`, `prove`, and `play` do not read it. It changes only how a
renderer places copies.

`beside left unshared` and `beside right unshared` parse. A fixed side
already never shares, so the modifier changes nothing. `velocitron validate`
warns `beside-unshared-redundant`. It is not an error. The copies stay on
the named side, one row per transition, as they do for `beside left` and
`beside right`.

## Decision 2: an unshared run stays one row, and the copies go outward

When an unshared place with no side belongs to a sibling run that ADR 0035
would have shared, the transitions stay in one `beside` row. Each transition
keeps its own copy, and the copies are pushed outward:

- The first sibling's copy goes on the left.
- The last sibling's copy goes on the right.
- A middle sibling is placed by ADR 0029 Decision 3: the side with fewer of
  its own copies so far, left on a tie.

A run of two, `A, B`, renders as `P A B P`. No copy sits between the
siblings. A transition that is not in such a run is placed as it is today:
its own row, and a copy with no side on the lighter side, left on a tie.

The copy's node id stays `place@transition`. A shared copy's
`place@first+second` id is not used for an unshared place.

That row is the only layout. ADR 0072 places each drawn copy from its
`(P)@[T]` entry, else from the whole-place entry, else from the `beside`
offset of this row (ADR 0067). The outward push is that offset. It is not
a second way to place the copy.

## Decision 3: a per-copy side wins for its own copy

`unshared` is the place-wide switch. A later fact may name one copy,
`decorate (P)@[T] beside …` (issue 8). When that fact lands, the side it
names wins for that copy. The other copies of an unshared place stay on the
rule in Decision 2. This record does not add the per-copy syntax.

## Consequences

- Both implementations, the contribution-IR schema, emission, and the
  `decorate` reference move together, per ADR 0025 Decision 5.
- A fixed side and `unshared` together are a warning, acknowledged with
  `annotations.lint.suppress` on the place.
- Issue 12's `draw` knob is a separate choice and is not this modifier.
