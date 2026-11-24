# A share fuses places without a direction

**Status:** Accepted (2026-10-17).

A wire joins an output port of one net to an input port of another
([ADR 0004](0004-structural-ports-unidirectional-wires.md)). That fits a
token that moves from one net to the next. It does not fit a record that
several nets use together. We split a checkout lifecycle of 17 transitions
into five nets, one per business rule. Three of them use the shelf slot,
the lock on a home branch: two take it and one gives it back. Two of them
read the newer editions, and nothing in the nets writes them. Three of them
write signals, and nothing reads them. To wire these places, each net had to call its copy an
output port or an input port. The validator accepted this even when nothing
produced into the "output", so the port directions did not say what the
nets do.

The wires also changed the proof. The one-file net annotates the lock
`fusion true`: the prover lets the environment supply its one token. In the
composition, the prover treats every wired place as closed, because its
producers are inside the merged net. No lock token ever arrived, so the
prover reported a deadlock and ten dead transitions for a net that is the
same as the one-file net.

## Decision 1: `share` fuses places and has no direction

A composition gets a fact that says "these places are one place":

```text
share checkout.(shelf_slot) ~ desk.(shelf_slot) ~ edition.(shelf_slot)
```

JSON: `shares: [{places: [{net, place}, ...]}]`, at least two places. The
merge puts the members into the same equivalence classes as wires, so a
share and a wire on one place give one fused place. The members need not be
ports, and no direction is checked. They must accept the same colors,
because they become one place. A class with no output port among its
members is named after all its members
(`edition.shelf_slot__desk.shelf_slot__checkout.shelf_slot`);
otherwise it is named after its output ports, as before. Description,
annotations, actors and `lives` carry through as for a wired place.

The `~` reads as "is the same place as". It is a symmetric operator, so
the order of the members does not matter, and it cannot be mistaken for a
wire's `->`.

## Decision 2: a shared place keeps the role its members had

A place that a wire fuses stays closed for the prover. A place that a share
fuses is closed only when no member is annotated `fusion true`. When a
member is, the environment still supplies the place, exactly as in the
member's own net. With this rule the split lifecycle proves the same facts
as the one-file net: the same choices, the same two invariants, the same
soundness result, from the same 1270 markings.

The rule reads the annotation the author already wrote on the record. It
needs no new keyword and no domains-file entry.

**Considered options:**

- *An `environment.open` list in the domains file.* Rejected: it fixes the
  proof but not the port directions, and it moves a fact about the net into
  a file next to it.
- *Make every fusion-annotated place open, wired or not.* Rejected: a wired
  port of a refining net (`loan_ended` in the partner-loan net) is
  annotated `fusion true` for the renderer, and opening it would let the
  environment inject outcomes from nowhere.
- *Allow a wire between two input ports.* Rejected: a wire keeps its one
  meaning, a token that moves from a producer to a consumer.

## Consequences

- `share` is a new keyword and `~` a new token. `share` can no longer be a
  composition alias; as a place, transition or color name it stays valid.
- A play that composes with `use` takes the same `share` line.
- `velocitron-viz` draws a share as a dashed line without arrowheads, and the
  ports-only view shows shared places next to the ports.
- Errors start with `share a.(p) ~ b.(q):` (an unknown place, different
  colors, a place shared with itself); the DSL reports them as `PN202` at the
  share fact.
