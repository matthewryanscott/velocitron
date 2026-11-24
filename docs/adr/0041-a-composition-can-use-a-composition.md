# A composition can use a composition

**Status:** Accepted (2026-10-17).

The split checkout lifecycle is a composition of five nets with seven wires
and five shares. Three larger compositions use the lifecycle: one with the
partner-loan net, and two evening shifts. Each of them had to list the
five nets and repeat every wire, because `use` accepted only a net
(`PN500: invalid referenced net`). Three copies of the same wiring drift
apart, and a reader cannot see that the lifecycle is one block.

## Decision 1: `use` accepts a composition, which is flattened

```text
composition library_holds
use "checkout-lifecycle.petrinet" as lifecycle
use "partner-loan.petrinet" as loan
wire lifecycle.(desk.waiting) -> loan.(waiting)
wire loan.(loan_ended) -> lifecycle.(checkout.loan_ended)
refine lifecycle.[checkout.borrow] by loan
```

A referenced composition needs an explicit alias. The parser parses it like
any composition and flattens it into the outer one: its nets become
`<alias>.<inner alias>` (`lifecycle.desk`), and its wires, shares and
refinements carry over under those names. The merge then runs once, over
nets only. The merged net is the same net, up to place names, as a flat
composition that lists every net and every wire; `velocitron equiv` shows
this ([ADR 0042](0042-equiv-compares-merged-nets-up-to-renaming.md)).

A nested composition's relative references are relative to its own file.
The parser rebases them onto the outer file before the loader sees them
(`pair/take.petrinet` for `take.petrinet` inside `pair/pair.petrinet`), so
every existing loader works unchanged. A composition that uses itself,
directly or through others, is an error: `composition reference cycle`.

## Decision 2: a place inside a used composition is named by its dotted path

`lifecycle.(desk.waiting)` names the place `waiting` of the net `desk`
inside the composition `lifecycle`. Outside the parentheses is the alias in
this composition, as always. Inside is the name the place has in the merged
`lifecycle` net. The same rule names a transition (`lifecycle.[checkout.borrow]`)
and works at any depth (`outer.(lifecycle.desk.waiting)`). A play names
the place by its full merged name, `(lifecycle.desk.waiting)`.

The path names a member port, not the place the inner merge fused. A wire
from the outside therefore checks the member's own direction and color, and
it joins the inner fusion class, as a second wire on the same port does in a
flat composition. This is what the partner-loan net needs: `desk.waiting`
is already wired to `checkout.waiting` inside the lifecycle, and the outer
wire adds `loan.waiting` to the same place.

**Considered options:**

- *Flattened aliases outside the parentheses (`lifecycle.desk.(waiting)`).*
  Rejected: the part before the parentheses would no longer be one alias of
  this composition, and an alias could not be checked against the `use`
  lines alone.
- *Merge the inner composition first and use the merged net as a
  constituent.* Rejected: the merge gives a fused place no port, so the outer
  composition could not wire `sending` again, and a refinement would see one
  opaque net instead of the transition it refines.
- *Re-export ports with a composition-level `port` declaration.* Not needed
  now: the dotted path reaches every member port. It can be added later if a
  composition wants to hide its inside.

## Consequences

- `refine` works through nesting. `by` must name a net, not a composition:
  the refinement check proves one net as a sound block.
- Actors, `lives in`, `reads as`, descriptions, domains, final places,
  invariants, priorities, timers and `bindingNames` carry through, because
  the merge runs once over the flattened nets.
- `velocitron prove`, `velocitron play check` and `velocitron-viz` take a
  nested composition. The composition view draws a used composition as a
  dashed cluster around its nets' clusters.
- The parsed composition keeps the references as written (`nets`), and adds
  `sources`: each flattened net's reference, rebased onto the outer file.
