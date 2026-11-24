# Arrivals wait, and environment tokens group by what their readers see

**Status:** Accepted (2026-11-01); amended 2026-11-02 (Decision 1 is
opt-in, see the note at the end). Refines ADR 0055 (it settles the arrival
case that ADR 0055 left open) and ADR 0036 (the data domains of the
soundness exploration).

The soundness exploration of a large composition is mostly the environment.
On a composition of three question nets, a VM net and an outside agent's
destroy requests, 94.5 % of the edges at 300 000 states are arrivals: the
14 `done` values of each of three `ticks` records, 9 destroy requests, a
budget and a session count, in every order and every value combination,
before the instance has done more than its first step. Net firings are
4.7 % of the edges. The run passes 4 million states without finishing.
Two kinds of move add markings that no fact can tell apart:

- **Early arrivals.** An open place gets its token as soon as some
  transition could still read it later, although no transition can use it
  yet. Every arrival then interleaves with everything the net does until a
  reader is ready.
- **Values nobody tells apart.** Each arrival tries every environment
  token the domains allow. A reader that only asks
  `done.choice == "approve"` sees two values, not 14, so the other tokens
  lead to markings that differ only in what the reader does not look at.

## Decision 1: an arrival waits while no step can use it

Extend ADR 0055's wait from record changes to arrivals. A **user** of an
open place is a transition with an input arc from it (consume, read or
inhibit, a timer's bind included) or an output arc into it. In a marking
where the net has a move of its own (a firing or a tick), an open place
**waits** when none of its users has its other binding places marked. Open
places and clocks do not count as other binding places: the environment
can fill them. (ADR 0055 leaves out records and clocks; leaving out every
open place is what keeps two places that one step reads from waiting for
each other.) A waiting place gets no arrival. A place with no user is
already left out by the relevance rule.

For a record place this holds back the first token at most where ADR
0055 already holds back its changes. For a fact or a resource it is the
case ADR 0055 left open. Start places keep their own rule (ADR 0056).

**Why the verdicts stay the same.** The argument is ADR 0055's, with the
arrival in the place of the change.

- **A waiting arrival commutes with the net's next move.** A move that uses
  the place needs its other binding places marked, and then the place does
  not wait. So no enabled move reads, writes or is inhibited by the place,
  and the arrival can be made just as well after that move. Whether a place
  waits depends only on places that are neither open nor clocks, which no
  arrival changes, so an arrival never decides what waits next.
- **The arrival can still be made when it matters.** Hold it back until the
  first marking where the place no longer waits: a user's other places are
  marked, or the net stops. There it can arrive with any value it could
  have had before. The arrival count is unchanged (it still happens once),
  and the update budget of a fact is unchanged (an update needs a token
  there, and the old path's arrive-then-update is the same as arriving with
  the updated value, which the old exploration also tries).
- **The new exploration reaches nothing new.** It only removes arrivals
  from waiting markings, and the old exploration allowed an arrival
  anywhere, so every path of the new one is a path of the old one.
- **Proper completion** and **no dead transitions** read only what both
  reach: an open place is never an instance or final place, and every
  firing of the net is replayed, with the held arrival made just before the
  first move that needs it.
- **Option to complete.** Arrivals rescue a marking only at a stop, and at
  a stop nothing waits, so every marking both reach is good exactly when it
  was good before. A bad marking only the old exploration reaches differs
  from its partner only in places that waited. From the partner, net moves
  do what they did before until a user is ready or the net stops; there the
  held arrivals can be made with the bad marking's values, which reaches a
  marking that net moves reach from the bad one, so it is bad too. If
  neither happens, the partner is bad itself. This is the step ADR 0055
  worried about for facts ("an arrival is counted once and rescues a
  stop"): the rescue happens at a stop, where nothing waits.

**Limit.** As in ADR 0055: a record move that only an earlier arrival would
enable, in a stretch where its place waits until the instance finishes,
fires in neither place, so "no dead transitions" can name it in addition.

**Measured** (the record half only, with ADR 0055's group wait, as a
prototype behind an environment switch, on the benchmark nets that
motivated this): `ask` 2 125 states and 18 918 edges become 2 125 and
17 284; `spend` 2 889 states become 2 697; every verdict is the same. On
the composition, the 4-million-state run drops from 39.7 M to 22.5 M
edges, 836 s to 457 s and 15.8 to 11.6 GB, and still does not finish,
because the three `ticks` records then cycle through their 14 values each
once a question waits. That is Decision 2's job.

## Decision 2: environment tokens group by what their readers see

For each open place `p`, split its environment tokens (the arrival and
update values the domains give) into classes, and let the exploration try
one token per class: the first in the domains' order, so every witness and
counterexample stays a concrete play.

Two tokens of `p` are in one class when:

1. they have the same color;
2. every single-token CEL that can see a token of `p` gives the same
   answer for both: the predicate of each consume, read or inhibit arc
   from `p`;
3. they agree on every field that any other reader of `p` reads: a
   `correlate` on an arc from `p` or one that names `p` in `binding`, a
   timer that binds `p`, a produce `data cel` that reads `binding.p`, and
   a handler output the prover builds from a consumed token of `p` (the
   carry rule's base, and the bound values it copies into outputs).

Rule 3 keeps every token whose data can flow further apart, so the class is
decided by what the transitions reading `p` can see, not by its domain.

**Why the verdicts stay the same.** Take tokens `a` and `b` of one class
and a marking `m`. Swap `a` for `b` in `m`, and in every move from it.

- Every arc test that sees the token gives the same answer (rules 2 and 3),
  so the engine accepts the same bindings, up to the swap, and its
  rejections are the same.
- Every output is the same: a handler output depends on the consumed data
  only through the fields rule 3 keeps equal, and a `data cel` reads only
  those fields too. So the successor markings are equal up to the swap,
  and the swap stays inside `p` and the places that copy nothing from it.
- The facts read no data of an open place: "finished" asks which places
  hold tokens, proper completion looks at instance places, no dead
  transitions at firings, and option to complete at the moves that are
  possible. All of them are equal up to the swap.

So the markings reached with `a` and with `b` are bisimilar, and keeping one
of them keeps every verdict. Choice coverage can use the same classes for
the context tokens of a choice, which is what its 120-million-case contexts
need.

**Expected effect** [estimate, not measured]: each `ticks` place reads its
`done` token through a few predicates, so its 14 tokens fall into about 3
classes; the 9 destroy requests into about 3. On the composition that is at
most (14/3)³ · (9/3) ≈ 300 times fewer environment value combinations,
before Decision 1's cut.

## Consequences

- Both reductions are on by default, with no switch in the CLI or the
  domains file. `Explorer` and `explore` take `wait_arrivals=False` and
  `group_tokens=False` to explore without them, as ADR 0055's
  `postpone=False` does, so tests can compare
  (`implementations/python/tests/test_prove_arrivals.py`). The comparison
  runs on the examples, the fixtures and the library-hold domains files:
  every verdict equal; states and edges may drop.
- A counterexample may show an arrival later than before, and it shows the
  first token of a class rather than any value of it.
- The report's state counts change. The pinned prove reports
  (`tests/test_prove_parity.py`) are regenerated in the same change, and
  the diff shows only exploration sizes and paths, never a status.
- Not decided here: partial-order reduction across independent
  constituents (which needs the ignoring-problem fix and loses shortest
  counterexamples), and a place-scoped domain override in the domains file.

## Note (2026-11-02): the arrival wait is opt-in

Decision 1 is now off by default. `Explorer`, `explore`,
`soundness_proofs`, `check_refinement` and `prove` take
`wait_arrivals=True` to turn it on, and `velocitron prove` takes
`--wait-arrivals`. Decision 2 stays on by default, as decided.

Why: on a run that hits `--max-states`, Decision 1 explores a different
part of the state space with about twice the edges per state. On the
benchmark nets' capped loop composition (300 000 states), the run took 67 s and
1.90 M edges with it and 25 s and 0.93 M edges without it; at 1.5 M
states, 234 s against 118 s. The verdicts were the same. On runs that end
without a cap it keeps the result the same or smaller (`spend` 2 889 to
2 685 states, `triage` 29 to 14), so it stays available for those.
The soundness argument above is unchanged; only the default is.

The pinned prove reports (`tests/test_prove_parity.py`) go back to the
exploration sizes without the arrival wait; no status changes.
