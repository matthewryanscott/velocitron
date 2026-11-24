# Reading a `velocitron prove` report

`velocitron prove FILE.petrinet` checks every marking a net can reach. It
needs no handlers: it builds tokens from small data domains and asks the
real engine what is enabled. `FILE` may also be a composition; then each
`refine` gets its own check. The full contract is `packages/spec/proofs.md` in the
repository; this page is what you need to act on a report.

## Say what the net does not show

Three facts in the net replace what the prover would otherwise guess:

```text
domain verdict.result "pass" "hold"
final (delivered), (skipped), (gave_up), (superseded)
invariant "lock" (destination_free) + (sending) + (attempt_ended) = 1
```

- `domain` closes a field's value set. The prover uses it with no
  `⟨other⟩`, so the gaps at `⟨other⟩` go away. It is also a runtime
  contract: the engine rejects a handler output or an injection outside it
  (a deposit violation). List every value the handlers really return.
- `final` names the final markings; `invariant` declares a weighted count.
  Only the prover reads them. A comma separates final markings, and `+`
  joins places that must all hold a token: `final (recalled),
  (loaned) + (shelved)`. A composition can declare its own `final`
  (`final lifecycle.(checkout.loaned) + catalog.(shelved)`); it replaces
  the final facts of its nets. Use it when a run follows two things at once
  and is finished only when both are done. The constant counts the tokens the
  environment puts into open places: the lock above is `= 1` because the
  environment puts the one lock token into `(destination_free)`.

A domains file still wins over the net, to try a value set first.

## The facts

- **Choice coverage.** A choice is a place with consume arcs of one color
  into two or more transitions: an inner place, the place the instance
  starts at, or an input port, but not a resource, fact or kept record the
  world shares. Every token that can sit there must enable exactly one of
  them.
  - **gap**: none is enabled. Gaps are looked for only once every place the
    choice reads holds a fact about this key and the clock is at its last
    time, so a missing fact or a timer not yet due is not a gap. Typical
    fix: a predicate that covers the rest (`result != 'pass'`), or a
    `domain` fact that says the field never takes other values.
  - **intended wait**: a gap the net means. The token waits for something
    the outside world does, such as a flip a person must see first. Declare
    the case on a transition of the choice: `[fill] annotation wait
    {"when": "binding.home.exists(h, h.isbn == binding.waiting[0].isbn &&
    !h.confirmed)", "for": "the main branch to confirm the copy"}` (one line). `when` is CEL
    over `binding`, keyed as the transition's own CEL sees it, plus the
    places the transition inhibits, so a gap an inhibitor causes can be
    declared narrowly; `for` says
    what the token waits for. Only the cases where `when` is true wait; any
    other gap still refutes. Prefer it to `{"suppress": ["choice-gap"]}`,
    which waives every gap of the choice.
  - **overlap**: two or more are enabled. Typical fix: a predicate or an
    inhibit arc that separates them, or a `priority`. If both are meant
    (whichever comes first wins), waive it: `[t] annotation lint
    {"suppress": ["choice-overlap"]}` on a transition or the place.
  - **resolved**: an overlap the priority policy settles. Not a defect.
- **Place invariants.** Weighted token counts no firing changes, such as
  `sending + attempt_ended + destination_free = 0, plus one for each token
  the environment puts into (destination_free)`: a lock invariant. Counts
  are proved; a "per destination" reading is named, not proved.
- **Soundness** of one instance:
  - **option to complete**: from every reachable marking the instance can
    still reach a final marking. Refuted as a **deadlock** (the net stops),
    **vanished** (the instance leaves without a final place, for example
    into a signal only), or a **livelock** (it can fire forever; the report
    lists the environment moves that would end it).
  - **proper completion**: when a final marking is reached, no other place
    of the instance holds a token.
  - **no dead transitions**: every transition fires somewhere.
- **Refinement** (a composition with `refine lifecycle.[attempt] by
  attempt`): the refining net alone, from the input port wired from the
  refined transition's input place to the output ports wired into its
  output place. Every token that enters must leave as exactly one token, on
  every path, leave nothing behind, and every transition must fire. Its
  counterexamples play against the refining net's own file. A refined
  transition that takes or gives more than one token is `UNKNOWN`. A proved
  refinement plus a sound outer net give a sound composition when the
  refined transition never runs twice at once.

On a composition, every name is `alias.name` (`lifecycle.gate.pending`
inside a used composition), and the places the wires fuse are closed:
their producers are inside the merged net. A place a `share` fuses stays
open when a member is annotated `fusion true`: a shared lock or record is
still supplied by the environment, as in the one-file net. A record place
(below) stays open however it is fused; a kept place (below) is never open. To check that a
split net is the same net as the original, run `velocitron equiv
ORIGINAL SPLIT`: it merges both and compares them up to renaming (exit 0
equivalent, 1 different), listing port changes apart as interface
differences.

## What the prover assumes

- **Roles.** Open places are written by the environment: a place no arc
  produces into, a `fusion` place the net reads, a timer clock, and an input
  port of the instance color, but never a kept place. The instance color is the one most other places
  take. Final places are sinks of that color or output ports. A sink of
  another color (signals) is a side output.
- **Environment.** Each open place gets one token once; the start places
  together get one. A fact the net only reads may be replaced once. The
  environment owes nothing: a net that waits for a fact to *change* is
  refuted, unless the fact is a record (below).
- **Records the outside world keeps.** A place that lives in a `record`
  column is a record place: `record "Branch home"` and `(branch_home)
  lives in "Branch home"`, the same lines that give it a column in the
  sequence diagram. It is open however it is produced, wired or shared. The
  environment may change it any number of times. A transition that only
  takes and gives records (a person flipping the switch) is the outside
  world's move: flipping back and forth is no livelock, but the flip must
  still be able to fire. A net that waits for a record to change is
  waiting, not stuck. A loop of the net's own moves is still a livelock. Use
  it for a switch a person flips or a verdict a gate gives again, not for a
  hand-off between nets. To keep the check small, a record changes only
  when a step that reads or writes it has its other inputs, or when the net
  has nothing else to do; a clock ticks only when a timer on it could fire
  now or later. Neither changes a verdict, with the limits in ADR 0055 (a
  deadline timer, `now < …`, that only the environment's next move could
  enable; a record move that only an earlier held-back change enables).
- **Records the system keeps.** A record that the net keeps itself, there
  from the start and changed only by its own steps (one damage record per
  title), is a kept place:
  `(condition) kept by "circulation desk" starts as cel "{'isbn':
  instance.isbn, 'damaged': false}"` (one line). The check starts
  with it, built from the check's instance token (`instance` is its data,
  with the same `own-…` keys as the start token, so correlations on the
  isbn match). The environment never writes it: do not list it in
  `injections` or `updates`, and do not mark it `fusion true`. It is not
  the instance's work, so proper completion and final markings ignore what
  it holds, and it is never a choice. A share of a kept place joins only
  places kept the same way. The record starts clean once per check: a
  step that needs an earlier history of the record is dead unless one
  instance can build that history, or the instance starts again
  (`starts` in the domains file, below). Do not use a token in
  the initial marking for this (it counts as left-behind work, and its
  literal keys never match the instance), nor a fused place (the check
  injects it at any moment with any value, and the states multiply).
- **Domains**, from the net's CEL: literals plus `⟨other⟩`, `true`/`false`,
  values around numbers, `own-…`/`other-…` keys for correlated fields, `1, 2,
  3` for fields compared with each other, time slots for timer fields. A
  field that every producing arc sets to a literal, in a color the
  environment never writes, gets only those literals (no `⟨other⟩`).
  Soundness tries `⟨other⟩` only for a field some test passes with a value
  no literal names (`tool != null`, `!(tool in ['a'])`).
  Handler outputs keep the carried token and vary the fields the next place
  tests.
- **Time** jumps forward between slots. With priorities declared, the
  priority policy is assumed.

## The domains file

```json5
{
  domains: { "result.outcome": ["loaned", "due_soon", "damaged"] },
  instance: "hold",
  final: ["loaned", "recalled", "withdrawn", "shelved"],
  environment: {
    injections: { editions: 2 },
    updates: { editions: 0 },
    otherKeys: true,
    firings: { "lifecycle.request.reopen": 2 },
    starts: 2,
  },
}
```

`starts` starts the instance more than once, each time with the same keys
(default 1). Use it when a step needs what an earlier start left in a kept
record, such as an alarm on a repeat job for the same account. A later start
may arrive at any time, also while an earlier one is still running. The
check finishes only when every start has reached a final marking: it needs
one final marking per start at once, counted per place. Every soundness fact
says `assumes: the instance starts 2 times, with the same keys each time`, a
refutation too, and a `starts:` line follows the exploration. Do not list a
start place in `injections`: that is an error that points to `starts`.

`firings` caps how often a transition fires on any path, by its merged
name (`lifecycle.start.redeliver`). Use it for a loop with no fixed end,
such as "deliver again until a person stops": the prover explores that many
turns instead of running into the state cap. The report lists each cap: an
`assumes:` line under every fact that is not refuted, and a `firing cap:`
line after the exploration. A refutation is still real. A result under a cap
is bounded: "no dead transitions" says `UNKNOWN` when a cap stopped a
transition and something never fired, and "option to complete" says
`UNKNOWN` when some markings complete only past the cap.

## Unknown

`UNKNOWN` means the prover cannot say: the state cap was hit
(`--max-states`), a transition has a named guard or predicate (no handler
runs), the net has no final place (name one with `final`), or a field
is used in a CEL shape the domains do not cover (arithmetic, string
functions, `has()`).

A timer may compare the clock with a sum: `clock.now >= idle.since +
idle.wait`, or `clock.now - idle.since >= idle.wait`. When `since` is copied
from the clock (`'since': binding.clock[0].now`) and the domains file gives
the clock times, `since` needs no values; give `wait` its values, and the
prover reads the timer as it reads a deadline field such as `clock.now >=
idle.stopAt`.

Time moves to the clock's domain values and to the time each timer's
`timer maturity` names. A deadline dated from the clock (`'retryAt':
binding.clock[0].now + 60`) needs a maturity (`timer maturity cel
"retrying.retryAt"`): the clock may reach a domain value late, and the
deadline then falls on none of them.

A latch the net can take again and again (an idle VM that goes busy and
idle again) copies the clock straight (`'since': binding.clock[0].now`) and
matures at `idle.since + idle.wait`. Such a maturity counts only while
`since` holds one of the clock's domain values; a latch taken at a maturity
is due at a time the prover does not move to, so the markings end. A marking
that only that time would end makes option to complete UNKNOWN, not
REFUTED. A deadline kept whole in the token (`'stopAt':
binding.clock[0].now + 60`) is followed every time, so a latch taken again
at its maturity runs into the state cap.

When the state cap is hit, look for a step that reads but consumes nothing
and produces a token: it can fire again and again, so the markings never
end. The report names such a step on a `likely cause:` line (`velocitron
validate` warns about it as `read-only-producer`). Consume a token there, or
inhibit the step on its own output so it fires once. When the loop is the
business rule, cap it in the domains file (`firings`) instead.

## Counterexamples

`--counterexamples DIR` writes each gap, overlap and soundness finding as a
`.play` that ends with `expect` lines stating the finding. Check it with
`velocitron play check` and draw it with `velocitron play walk`.
When a kept record's start reads `instance`, the play has an `instance`
line with the check's instance token, so it starts from the same record. In
your own stories, `instance $delivery` does the same; a story with no
`instance` line starts without that record and may inject it itself.
