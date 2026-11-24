# A composition refines a transition by a wired net

**Status:** Accepted.

A net often keeps one step abstract. The checkout lifecycle has
`(waiting) -hold-> [borrow] -loan-> (loan_ended)`, and a second
net, the partner loan, details that borrow: it takes the hold at an input
port `(waiting)` and gives the outcome at an output port `(loan_ended)`.
Composed with wires, both nets keep their transitions. `[checkout.borrow]`
and `[loan.request]` then both consume from the fused `waiting` place, so a
run can take the abstract shortcut and skip every step the partner library
would take. The composition cannot say "this net is the inside of that
transition".

Classic Petri-net theory has a name for this: transition refinement. A
transition is replaced by a subnet that has the same interface.

## Decision 1: `refine` removes the transition and its arcs during the merge

A composition gets an optional `refinements` list of `{net, transition, by}`
entries; in `.petrinet` the fact is `refine checkout.[borrow] by loan`
(and the same line in a play that composes with `use`). The merge leaves
out the refined transition and every arc to or from it. Everything else is
the ordinary merge: places stay, wires fuse them, `bindingNames`,
descriptions, annotations, and decorations of the remaining nodes survive.

The refined transition's handler, guard, priority, and arc inscriptions go
away with it. The refining net's own transitions decide when and how tokens
move; the abstract transition was only a placeholder for them.

A standalone net does not change. Its abstract transition stays in its own
document and its own diagram, which is where a reader wants the short story.

## Decision 2: the author writes the wires; the merge checks them

A refinement does not add wires. The merge checks that the wires the author
wrote make the refining net fit:

- each place the transition consumes from or reads is fused with an input
  port of the refining net whose type is the arc's color;
- each place the transition produces into is fused with an output port of the
  refining net whose type is the arc's color;
- the refining net may have more ports than that.

Explicit wires keep one rule for how places join: a wire. The composition
reads the same with or without the refinement, and removing the `refine` line
gives back exactly the competing net that motivated this decision, which is
easy to explain. The wires were needed anyway in our case, because the ports
have their own names in each net. Implied wires would need a rule to pair a
transition's places with the refining net's ports (by name, by color, by
order), and each such rule breaks on some net: two inputs of one color, or a
port named differently from the place.

**Considered options:**

- *`refine` implies the wires.* Rejected for the pairing problem above, and
  because the composition would then have two ways to fuse places.
- *Keep the transition and only warn.* Rejected: the merged net would still
  let a run skip the refining net, which is the bug.
- *Give the refined transition a lower priority.* Rejected: priority chooses
  between enabled transitions at one moment. It does not say that one net is
  the inside of another, and the shortcut could still fire when the refining
  net is blocked.

## Decision 3: inhibit arcs and timers are rejected

An inhibit arc tests that a place is empty, and a timer tests the clock. A
port carries tokens in one direction; it cannot carry "only while this place
is empty" or "only after this time" into the refining net. Rather than define
a meaning, the merge rejects a refined transition that has either. A read arc
is allowed: it maps to an input port like a consume arc, because the refining
net takes the token as its input.

## Consequences

- Errors are composition diagnostics. `parse_composition`, `merge_nets`, and
  the TypeScript `parseComposition` and `mergeNets` raise messages that start
  with `refine <net>.[<transition>] by <by>:` (unknown alias, a net refining
  its own transition, a transition refined twice, an unknown transition, an
  inhibit arc or timer, an unwired place, a port of another color). The DSL
  reports the alias and conflict checks at resolution and the others at the
  refined transition, all as `PN202`.
- Python and TypeScript merge the same way; a parity test fires a refined
  composition in both.
- A play step on a refined transition fails with `SC203`, and the detail
  names the refining net.
- `velocitron-viz` leaves the refined transition out of its net's cluster in
  a composition render and titles the refining net's cluster "refines
  `net.[transition]`".
- `refine` and `by` are new keywords. They can no longer be composition
  aliases; as place, transition, or color names they stay valid.
