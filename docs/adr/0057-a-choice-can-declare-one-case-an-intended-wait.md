# A choice can declare one case an intended wait

**Status:** Accepted (2026-10-21). Extends ADR 0016 (suppression in
`annotations`) and ADR 0036 (choice coverage); reads `binding` as ADR 0032
names it.

Choice coverage calls a case a **gap** when a token at a choice place
enables none of the ways out, in a settled context: every place the choice
reads holds a token about the instance's key, and every clock is at its
last value. Some nets mean such a case. The circulation desk lends or
recalls a pending hold only after the main branch has confirmed the copy.
Until then, the hold waits, and that is the rule. The
only way to accept it was `[lend] annotation lint {"suppress":
["choice-gap"]}`, which waives every gap of the choice. A new gap there, a
real mistake, would then read as waived, and the check would still pass.

## Decision: a transition declares the cases in which its choice waits

A transition may carry the annotation `wait`:

```text
[lend] annotation wait {"when": "binding.branch_home.exists(s, s.isbn == binding.pending[0].isbn && s.branch == 'main' && !s.confirmed)", "for": "the main branch to confirm the copy"}
```

- `when` is a CEL condition over `binding`, the case's tokens keyed as the
  transition's own CEL sees them: by its input places, or in a composition
  by its binding names, so the condition keeps the net's own place names.
  The value of each key is the list of token data in that place, as in a
  `data cel`.
- `for` says in plain words what the token waits for. The report shows it.
- The value may be a list of such objects, for several cases.

Choice coverage evaluates every `wait` of the choice's transitions on each
gap case. A case for which one condition gives `true` is an **intended
wait**: it is not a defect, and the report lists it as `intended wait: the
hold waits for the main branch to confirm the copy when …; [lend]
declares this wait`. Every other gap case is still a gap, so the choice is
still refuted by any gap the condition does not name.

**Considered options:**

- A `choice-gap` suppression on the transition, as before. Rejected for
  this use: it covers every gap of the choice.
- A wait keyed on field values of the choice token only (a box of cases).
  Rejected: the case here is about a record the token correlates with (the
  branch home of the same title), and the gap's boxes already speak about
  context places. CEL over `binding` says both, in the words the net's arcs
  already use.
- A new DSL fact (`[t] waits for "…" when cel "…"`). Rejected for now: the
  annotation carve-out of ADR 0016 is where facts that only tools read live,
  and `[t] annotation end true` set the pattern for a short, intended shape.
  The `.petrinet` and JSON forms are the same, and neither parser changes.
- The condition on the choice place instead of a transition. Rejected: in a
  split lifecycle, the choice place is a port of the desk net, and the
  merged place takes another net's name. The transition keeps its own name
  and its binding names through a composition.

## Consequences

- **Fails safe.** A condition that cannot be evaluated (it reads a key the
  binding does not have, or a field the token lacks) or that gives anything
  but `true` does not hold, so the case stays a gap. A malformed `wait`
  declares nothing. `velocitron validate` reports a `PN202` error at the
  annotation when the value is not `{"when", "for"}` (or a non-empty list
  of them) or a `when` is not valid CEL.
- The engine ignores the annotation, as every annotation (ADR 0011).
  Soundness does not read it: a waiting token is a stop that an arrival or
  a record change must rescue, as before.
- The JSON finding kind is `wait`. Counterexample plays are written
  only for gaps and overlaps, so a wait gets none.
- `lint.binding_keys` is now public, so the prover keys `binding` the way
  the lint rules do.
