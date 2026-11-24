# `velocitron equiv` compares merged nets up to renaming

**Status:** Accepted (2026-10-17).

When we split a net into smaller nets and compose them back, we want to
know that the composition is the same net. Plays show that some paths
still play. Proofs show that some facts still hold. Neither shows that
nothing else changed: a predicate copied wrong, a priority left out, a CEL
`binding.<place>` name that now means another place. A first check was a
throwaway script that merged both sides and compared the JSON.

## Decision 1: compare the structure after the merge, up to renaming

`velocitron equiv A B` loads both sides (a net, a composition, or a
composition that uses compositions) and merges them. A place or transition
is known by its local name: its merged name without the alias of the net
that declares it (`gate.pending` is `pending`). A fused place answers to the
local names of its members. When local names collide, alias segments break
the tie, from the outside (`lifecycle.clock`) or from the inside
(`gate.pending`).

Under that renaming, both sides must have the same places, transitions and
arcs, and the same behavior facts:

- places: colors, capacity, final, initial marking, and whether the prover
  lets the environment supply the place (it is taken from, and nothing
  produces into it, or it is an unclosed fusion place);
- transitions: guard, priority, handler, timer (clock, CEL, bound places),
  and the `binding` names its CEL reads;
- arcs: endpoints, color, mode, weight, predicate, correlate, `data` and
  `data cel`;
- domains and declared invariants.

The output is "equivalent up to renaming" with the renaming, or the first
differences in the net's words: ``arc (attempt_ended) -attempt-> [wait]:
predicate `outcome == 'failed'` in the first net, `outcome == 'timeout'` in
the second``. Exit 0 when equivalent, 1 when different, 2 when a side cannot
be loaded.

Supply by the environment is compared because it changes what the prover
explores, not what the engine fires: the split lifecycle wired its lock and
lost the one-file net's proof. `equiv` reports that as a difference.

## Decision 2: ports are interface, not behavior

A port is how a net is composed, not what it does. A split usually moves
ports: `sending` is a port of the one-file lifecycle and an inner place of
the composition. `equiv` prints port differences apart and does not count
them. Descriptions, annotations other than `fusion`, actors, decorations and
views are documentation and are not compared.

**Considered options:**

- *Graph isomorphism without names.* Rejected for now: names are what the
  author keeps when splitting a net, and matching by name gives a clear
  renaming and clear differences. Two nets that rename every place are not
  matched.
- *Behavioral equivalence (the same reachable markings).* Deferred, as in
  [ADR 0037](0037-declared-domains-are-a-runtime-contract-and-proofs-check-refinements.md):
  a split that does not change the net does not need it.

## Consequences

- `equiv` is a Python CLI command, like `prove`; it reads the merged nets
  both implementations produce the same way.
- The renaming is useful when a play is rewritten for a composition:
  every line maps an old name to a new one.
