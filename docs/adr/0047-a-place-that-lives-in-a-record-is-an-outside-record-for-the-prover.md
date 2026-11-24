# A place that lives in a record is an outside record for the prover

**Status:** Accepted (2026-10-17). Refines ADR 0036 (the environment model)
and ADR 0040 (which places a composition keeps open).

Some places are records that the outside world keeps and may change at any
time: a title's home branch, which a clerk records, and a shelf note that the
union catalog writes again when it looks again. `velocitron prove` read each of them
as a fact that arrives once and then stays, or as a resource. That gave
three false findings on the library-hold nets:

- **A step reported dead.** The desk's `[lend]` waits for the
  shelf note to stop saying `missing`. `[reshelve]` writes the note back, so the
  note was not an updatable fact. Once it said `missing`, nothing changed it,
  and `[lend]` was reported as a step that never fires.
- **A livelock that is a person's choice.** The evening-shift net's two recordings take
  the branch-home record and give it back. They were net moves, so a clerk who records the
  home branch back and forth, main then annex then main, was read as the net running in circles.
- **A record never seeded.** In the evening shift, the shift's branch-home record is wired
  into the lifecycle's branch-home record. A wired place is closed (ADR 0040), so no
  branch-home record ever arrived, and 19 of the 20 steps were reported dead.

## Decision 1: the prover reads the record column the net already declares

A place whose `lives in` names a lifeline of kind `record` (ADR 0039) is a
**record place**:

```text
record "Branch home"
(branch_home) lives in "Branch home"
```

The sequence diagram already draws it as a column of its own because it is
a record that stays. The prover reads the same fact, as it reads the
`fusion` annotation (ADR 0040). There is no new keyword. A place that lives
in a computed column (`lives in cel "…"`) or in a `system` column is not a
record place: `loan_ended` lives in the partner library's column and stays a closed
hand-off.

## Decision 2: the rules for a record place

1. It is **open**, whatever produces into it, wires it or shares it. The
   environment puts one token into it after the instance starts, as for any
   fact. It is never a start place, a resource, a sink or a final place.
2. It is **updatable without limit**: the environment may replace its token
   with any other value of its domain, any number of times. The domains are
   finite, so the state space stays finite; the count of changes is not part
   of the state.
3. A transition whose input and output places are all record places is a
   **record move**: a move of the outside world, like an update, not a net
   move. A loop of record moves is not a livelock. A record move must still
   be able to fire: "no dead transitions" counts it. The priority policy
   ranks net moves only.
4. A record change (an update of a record, or a record move) **rescues a
   waiting net** as an arrival does: a marking with no net move, from which
   a record change leads to a good marking, is good.

A livelock made of net moves is still refuted: record changes never make a
loop good. A net that waits for a fact that is not a record to change is
still refuted, as before.

## Considered options

- **A new place fact** (`(branch_home) record`). Explicit and independent
  of the sequence diagram, but it needs a keyword in both grammars and the
  canonical round trip, and it declares the same thing twice on every
  record.
- **Read `fusion true` as "record".** No new text, but ADR 0040 rejected it:
  `loan_ended` is `fusion true` for the renderer and must stay closed in
  a composition.
- **A list in the domains file.** Rejected for the reason ADR 0040 gives: it
  moves a fact about the net into a file next to it, and every proof would
  have to name the file.
- **Decide by actor** (a step a `person` fires is the outside world's).
  Reads well for the recordings, but `[reshelve]` is a clerk's step that moves
  the hold and must stay a net move. The structural rule (the step
  touches records only) needs no judgment.
- **Updates once, or a count per record.** Rejected: a copy the catalog marks
  missing, then shelved, then missing again would be outside what the prover tries.

## Consequences

- The report's roles list the record places (`roles.records`); they are
  also in `updatable`. A rescue by a record reads "a change of the shelf
  note (shelf_note)".
- The library-hold desk and lifecycle need one more line each:
  `record "Shelf note"` and `(shelf_note) lives in "Shelf note"`. The
  same lines give the note its own column in the sequence diagram.
- The contract is in [`packages/spec/proofs.md`](../../packages/spec/proofs.md) ("Roles of
  places", "Soundness" and "Compositions").
