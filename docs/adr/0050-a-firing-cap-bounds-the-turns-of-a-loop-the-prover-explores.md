# A firing cap bounds the turns of a loop the prover explores

**Status:** Accepted (2026-10-18). Refines ADR 0036 (the environment model
and the soundness facts).

Some business rules are loops with no fixed end. "A patron can place the
same hold again, until they stop" is one: in the library-hold nets,
`[renew]` puts the hold back into `(requested)`, and each turn can
leave new tokens behind. The markings never repeat, so `velocitron prove`
explores until the state cap and then reports every soundness fact as
`unknown`. Changing the diagram to bound the loop would change the business
rule. The check needs a bound that lives outside the net and that the
report shows.

## Decision 1: the domains file can cap the firings of a transition

```json5
{ environment: { firings: { "lifecycle.desk.renew": 2 } } }
```

`environment.firings` maps a transition to a positive count, next to
`injections` and `updates`, which bound what the environment does. A
transition of a composition has its merged name, as everywhere in the
report. An unknown name is an error, and a name that only one merged
transition ends with is suggested (`did you mean
'lifecycle.desk.renew'?`). A count that is not a positive integer is an
error.

## Decision 2: a capped transition is disabled on a path once it fired that often

Each explored state keeps how often each capped transition fired on the path
that reached it, so two markings that differ only in these counts are
different states. A transition at its cap does not fire. The priority policy
still ranks it: when it is the highest-priority enabled transition, no
lower-priority transition fires in its place. The cap removes behavior and
never adds any, so every explored path is a path of the net without the
cap.

A state where the cap stopped an enabled transition is **cut**: the net
still has a move there, but the prover does not follow it.

## Decision 3: a cap never makes a result look better or worse than it is

- A **refutation** stays a refutation. Its path fires each capped transition
  at most its cap, so the same path exists without the cap. A cut state is
  not a stop, so the cap never makes a deadlock.
- **Option to complete** is `proved` when every explored state reaches a
  final marking within the caps. It is `refuted` when some state can reach
  neither a final marking nor a cut state. Otherwise it is `unknown`: some
  states reach a final marking, if at all, only past a cut. A real livelock
  that the cap cuts is therefore `unknown`, not `proved`.
- **Proper completion** is checked on the final markings reached within the
  caps.
- **No dead transitions** is `unknown` when a cap stopped a transition and
  some transition never fired: it may fire on a later turn. When no cap
  stopped anything, the exploration is the same as without the caps, and a
  transition that never fires is `refuted` as before.

## Decision 4: the report states every cap as an assumption

Every soundness or refinement fact that is not refuted lists each cap in
`assumptions` (`[lifecycle.desk.renew] fires at most 2 times on a
path`), and the text report prints it on an `assumes:` line. The JSON
exploration has `firingCaps`, with each cap's limit and the number of
explored markings where it stopped its transition; the text prints a
`firing cap:` line that says the results hold only within the caps. A
refinement check uses the caps on the refining net's transitions, by that
net's own names.

## Consequences

- A loop with no fixed end can be checked for a few turns without changing
  the diagram, and nobody reads a capped result as an uncapped one.
- A `proved` under a cap is a bounded result: a defect that needs more
  turns than the cap allows is not found.
- Choice coverage and place invariants do not explore, so caps do not
  affect them.
