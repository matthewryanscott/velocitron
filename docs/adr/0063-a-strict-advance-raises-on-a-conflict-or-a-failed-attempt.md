# A strict advance raises on a conflict or a failed attempt

**Status:** Accepted (2026-11-06). Ada asked for the gaps found while
driving a projected net to be fixed. Builds on
ADR 0005 (the firing policy), ADR 0014 (the priority policy), ADR 0015 (the
failure budget) and ADR 0060 (`advance` is the one seam).

## Why

A consumer that keeps a machine's state in its own records (a lifecycle
step, a fleet VM) runs each change as one advance of a proved net from a
projected marking (`spec/projection-adapter.md`). Choice coverage proved
that no marking enables two transitions at once, and every transition of
such a net is pure, so a failed attempt is a bug. `advance` handles neither
case the way that consumer needs:

- On a **conflict** the firing policy picks one (first-found: declaration
  order). A changed net that breaks the proof then runs one branch silently.
- On a **failed attempt** the loop retries until `max_steps`, or until the
  failure budget exhausts the transition, and returns a marking with no sign
  of the failure.

Bench wrote the loop by hand (`enabled_transitions`, raise on more than
one, `fire`, raise on a record that is not `completed`). Every projected net
it plans needs the same loop.

## Decision

`Engine.advance(..., strict=True)` (TypeScript: `run(net, marking, {strict:
true})`) runs the ordinary selection loop with two stops that raise:

- `Conflict` (`ConflictError`) when two or more transitions contend at a
  marking, before the policy is asked; nothing fires there. Under the
  built-in priority policy only the transitions at the top declared priority
  contend, as choice coverage counts an overlap the priorities resolve as
  resolved.
- `FailedAttempt` (`FailedAttemptError`) carrying the `failed` record, after
  the journal received it; the marking is unchanged by it.

`strict` defaults to `False`, so every existing caller keeps the loop it
has. The names are the glossary's: a **conflict** is two enabled transitions
competing, and a failed `FiringRecord` is a **failed attempt** (ADR 0059,
item 4). The symbolic mode (`outputs=`) honors `strict` the same way.

**Considered options:**

- A separate method (`run_to_rest`). Rejected: a second loop beside
  `advance` would copy the selection, the ledger and the journal stamping
  that ADR 0060 put in one seam, and *run* is the noun ADR 0059 reserves for
  the sequence.
- A custom firing policy that raises on two candidates. Rejected: a policy
  never sees the firing's record, so it cannot stop on a failed attempt, and
  every consumer would register its own.

## Consequences

- A projected net runs as `engine.advance(net, marking, strict=True)`;
  bench's hand-written loop can go.
- The Python and TypeScript engines both carry the option and the two
  errors.

## References

- `spec/firing-semantics.md` (e) — the selection loop and strict advance
- [ADR 0014](0014-priority-firing-policy.md), [ADR
  0015](0015-failure-budget-and-failure-aware-selection.md), [ADR
  0060](0060-advance-is-one-seam-and-tick-is-deleted.md)
