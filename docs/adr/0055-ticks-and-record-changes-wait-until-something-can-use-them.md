# Ticks and record changes wait until something can use them

**Status:** Accepted (2026-10-20). Refines ADR 0036 (the reductions of the
soundness exploration) and ADR 0047 (record places).

Two moves of the soundness exploration multiplied the markings of large
compositions without adding any behavior the facts can see.

- **Ticks.** A clock ticked as soon as every binding place of some timed
  transition held a token. A kept record that is there from the start
  (ADR 0051) and that a long timer reads, such as an alarm after a day of
  errors, satisfies that from the first marking. When the check's clock
  never reaches a day, the timer can never fire, but the clock still ticks
  through every value, interleaved with everything else the net does.
- **Record changes.** A record changes any number of times (ADR 0047), and
  the exploration changed it in every marking where some transition could
  still read it later. A gate's verdict that a later loop keeps readable is
  changed after every step of the work that follows the gate, so every
  marking after the gate exists once per verdict value, although nothing
  reads the verdict until the loop comes back to the gate.

## Decision 1: a clock ticks only when a timer on it could fire

A clock ticks in a marking only when some timed transition on that clock is
enabled with the clock at its current value or at one of its later domain
values, every other place as it is. Before, it was enough that the timed
transition's binding places held tokens; that test stays as a quick first
filter.

**Why the verdicts stay the same.** Take a marking where no timer on the
clock could fire at any value still to come. Hold a tick back there. No
move enabled in the meantime reads the clock: a timer on it is not enabled,
and as before only timers are reasons to tick. So each such move is enabled
with the old clock value too and has the same effect. The first time a
timer on the clock could fire at some value still to come, the clock may
tick again, to any later value, so it catches up with the clock value of
the path that ticked early. Every marking the old exploration reaches has
a partner the new one reaches, equal except for a lower clock value, and
every marking the new exploration reaches, the old one reaches too.

- **Proper completion** and **no dead transitions** read only what the
  partners share (a clock is never an instance place or a final place, and
  every firing is replayed), so they do not change.
- **Option to complete.** A marking whose only net moves were useless
  ticks is now a stop, so an arrival or a record change can rescue it at
  once. Before, time first ran to the clock's last value, and the rescue
  came after that. Every rescue the old exploration finds, the new one
  finds too, so every marking that was good is still good: the new
  exploration never refutes what the old one proved. The other way round,
  that every old refutation is still found, needs the timers to keep their
  answer as time passes: a timer that can fire at some time can also fire
  later, and no step computes an output from the clock. Comparisons such as
  `clock.now >= job.limit` keep it.

**Limit.** A deadline timer can turn a refutation into a proof. That needs
a timer whose binding places hold tokens, that cannot fire now or later,
and that the environment's next move would let fire only before some time
(`clock.now < reply.due`). The old exploration let the deadline pass before
the environment moved; the new one lets the environment move first. The
old rule already did the same when the timer's binding places were empty.

## Decision 2: a record changes only when a step can use it

Records that record moves join form a **group** (a switch whose flips move
a token between two record places is one group). A group **waits** in a
marking when the net has a move of its own (a firing or a tick) and no
transition that reads or writes one of its records has its other binding
places marked. The records' own tokens and the clocks do not count as
other binding places. While a group waits, its records get no update, and
no record move that touches only waiting records fires. A group that no
transition reads or writes never waits.

A record move held back in a marking where it was enabled still counts for
"no dead transitions": it can fire there.

**Why the verdicts stay the same.**

- **A waiting change commutes with the net's next move.** A move that
  reads or writes a record of the group is enabled only when its binding
  places are marked, and then the group does not wait. So no enabled move
  touches the group, and a change made now can be made just as well after
  that move. Whether a group waits does not depend on records or clocks,
  so the change does not decide what waits next.
- **The change can still be made when it matters.** Hold each change back
  until the first marking where its group no longer waits. There the
  records change freely again, any number of times, so the held changes
  happen in their old order before any step reads or writes the records.
  Writers count as users so that the net never writes a record before the
  changes the old path made to it first.
- **Proper completion** and **no dead transitions** read only what both
  explorations reach: records are never instance places or final places,
  and every firing of the net is replayed. A record move the old path fired
  while its group waited is held back where it was enabled, and so counts.
- **Option to complete** counts arrivals and record changes only at a stop,
  and at a stop no group waits. Net moves are not changed. So every marking
  the new exploration reaches is good exactly when it was good before. A
  bad marking only the old exploration reaches differs from its partner
  only in waiting records. From the partner, net moves do what they did
  before until a step that uses the records is ready or the net stops.
  There the records can change to the bad marking's values, which leads to
  a marking that net moves reach from the bad one, so it is bad too. If
  neither happens, the partner is bad itself.

**Limit.** A record move that only an earlier held-back change would
enable, in a stretch where its group waits until the instance finishes,
fires in neither place. "No dead transitions" can then name it in addition
to what it named before.

## Consequences

- The reductions are on by default and there is no switch in the CLI or the
  domains file. `Explorer` and `explore` take `postpone=False` to explore
  as before, so tests can compare both.
- A counterexample path may show a tick or a record change later than
  before, and the first refuted marking found may differ. The verdicts do
  not, within the limits above.
- Choice coverage and place invariants do not explore, so they do not
  change.
- Considered and not decided here: holding back the arrival of a fact
  (an open place that is not a record) until a step that reads it has its
  other binding places. It cuts markings further, but it needs its own
  argument, because an arrival is counted once per place and rescues a
  stop.
