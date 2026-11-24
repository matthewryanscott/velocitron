# Before the start, the environment writes what a step can read

**Status:** Accepted (2026-10-21). Refines the first reduction of the
soundness exploration (ADR 0036, spec/proofs.md § Soundness) and its
restatement for repeated starts (ADR 0052).

Until the instance was in the net, the exploration let the environment do
one thing only: send the start. The reason was that a fact arriving before
the start could arrive just after it with the same effect, since nothing
reads it before. The instance counts as not in the net while no instance
place and no final place holds a token, and either the start has not
arrived or its token waits in the start place while the net has a move.

The reason fails when a step of the net can read the fact in that stretch.
An evening-shift net shows it. The circulation desk keeps its last answer
about which branch is home for a title (a kept record, ADR 0051). The desk
asks again when the branch-home record (a record the outside world keeps,
ADR 0047) shows a move it has not confirmed, and it rewrites its answer.
At the shelf slot (the start) it lends the copy or recalls the hold by that
answer. Asking needs the branch-home record but not the slot. Under the old
rule the record could not arrive before the slot, and once the slot was
there, lending was enabled, so the record still could not arrive. The desk
never asked before a slot, and the check reported "the desk recalls the
hold" as a transition that never fires. The same gap hides a choice at the
start place between a step that reads a fact and a step that does not: the
fact could never arrive while the other step was enabled.

## Decision: before the start, the environment also writes what a step can read then

While the instance is not in the net, the environment may send the start,
and it may write (an arrival, an update or a record change) any open place
that a step **possible before the start** reads. A step is possible before
the start when each of its binding places holds a token, can still get one
from the environment, or is an output of another such step. Two exceptions
keep the rule narrow:

- The start places count only when they already hold the start token. A
  step that needs the start is possible once the start is there, and from
  then on the environment can write what it reads.
- A step that marks an instance place or a final place ends the stretch.
  Its outputs do not make other steps possible, because after it fires the
  instance is in the net and the environment writes freely.

The answer depends only on which places hold tokens and on the counts of
arrivals and firings, so it is kept per pair, as the relevance of open
places is.

**Why the verdicts are right.** Compare with the full exploration, where
the environment writes any open place at any time. Take a write to a place
`p` that the new rule holds back: no step possible before the start reads
`p`, and an inhibitor arc counts as reading. Every move made between that
write and the moment the instance is in the net is a step possible before
the start, a write the rule allows, or the start. None of them reads `p`,
so the write commutes with each of them, and it can move to just after the
instance is in the net. There the rule allows every write, at any marking.
So every marking the full exploration reaches once the instance is in the
net, the new one reaches too, and with the same moves out of it. Before
that point, the new exploration reaches the same markings without the held
writes, with the same net moves.

- **Proper completion** and **no dead transitions** do not change. Final
  markings are in the net. A firing before the instance is in the net is a
  step possible before the start, so it reads only places the rule lets the
  environment write, and the new exploration fires it too.
- **Option to complete** does not change. A marking in the net has the same
  moves in both explorations, so it is good in both or bad in both. A
  marking before the start may lack a rescue in the new exploration: a held
  write at a stop. No step reads that place before the instance is in the
  net, so the plans from the marking with and without the write go through
  the same net moves until the instance enters. Without the write, they
  reach markings in the net that both explorations reach. If one of them is
  good, the marking before the start is good in both. If all are bad, both
  explorations refute. The first refuted marking found may differ.

The old rule held back more than this one, so it reached fewer markings.
Where it held back a write that a step possible before the start reads, it
lost behavior; that is the gap above. Everywhere else the two rules reach
the same markings.

## Consequences

- The evening-shift net checked alone proves "no dead transitions" again: the
  branch-home record can arrive, and the desk can ask, before the shelf slot
  comes. The shift that composes it with the checkout lifecycle grows from
  17,078 to 21,005 markings, with the same verdicts. Nets whose open places
  only steps of the instance read keep their old size.
- A new test proves every prove fixture with the rule and with no rule at
  all (the environment writes any place at any time) and compares the
  statuses and dead transitions. The kind of the first refuted marking
  found may differ (a livelock or a vanished instance), because the search
  meets the bad markings in another order.
- Considered: no rule at all before the start. It is simplest and sound,
  but it lets every fact arrive in every order before the start, which is
  what the old rule was there to prevent.
- Considered: only the places that steps not needing the start read. It
  fixes the evening shift but keeps the hidden choice at the start place.
