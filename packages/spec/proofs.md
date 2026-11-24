# Proofs: choice coverage, place invariants and soundness

## Status and boundary

This document defines version 1 of `velocitron prove`: the facts it proves
about a net or a composition, how it derives what the net does not say (data
domains and an environment model), what the net can declare instead
(`domain`, `final` and `invariant` facts), the command line, the domains file,
and the JSON report. The Python implementation is the reference
(`implementations/python/src/velocitron/prove/`); the TypeScript
implementation does not prove facts, but its engine enforces declared domains
too. The rationale is
[ADR 0036](../../docs/adr/0036-prove-facts-by-domain-abstraction-and-explicit-states.md)
[ADR 0037](../../docs/adr/0037-declared-domains-are-a-runtime-contract-and-proofs-check-refinements.md),
[ADR 0047](../../docs/adr/0047-a-place-that-lives-in-a-record-is-an-outside-record-for-the-prover.md),
[ADR 0050](../../docs/adr/0050-a-firing-cap-bounds-the-turns-of-a-loop-the-prover-explores.md),
[ADR 0051](../../docs/adr/0051-a-kept-record-is-there-from-the-start-and-only-the-net-writes-it.md)
and
[ADR 0052](../../docs/adr/0052-a-domains-file-can-start-the-instance-more-than-once.md).

The property pass ([`properties.md`](./properties.md), ADR 0019) checks
markings a system produced. `prove` checks markings a net **can reach**. It
never changes a net, and it decides every enablement through the ordinary
engine ([`firing-semantics.md`](./firing-semantics.md)): this document adds
only which tokens the prover tries and how it reads the results.

## Terms

- A **Proof** is the prover's result for one fact: `proved`, `refuted` (with
  a witness or a counterexample) or `unknown` (with the reason).
- A **Kept record** is a record the net keeps itself: it is there from the
  start, and only the net's own steps change it.
- A **Firing cap** bounds how often one transition may fire on any explored
  path. It comes from the domains file, and every result that relies on it
  lists it as an assumption.
- **Starts** say how often the instance starts, each time with the same
  keys (default once). They come from the domains file, and every soundness
  result lists them as an assumption.
- **Choice coverage**: every token that can sit at a choice place enables
  exactly one of the transitions that take it.
- A **Place invariant** is a weighted sum of token counts that no firing
  changes.
- **Soundness** (of one lifecycle instance): the instance can always
  complete, it completes cleanly, and every transition can fire.
- The **Environment model** says which places the world outside the net
  writes, with which tokens, and how often.
- A **Data domain** is the finite set of values the prover gives one token
  field. A **Declared domain** is one the net states with a `domain` fact.
- A **Refinement check** proves that the refining net of a composition's
  refinement is a sound block for the transition it replaces.
- A **witness** is a concrete marking that shows a choice finding. A
  **counterexample** is a shortest sequence of moves that shows a soundness
  finding. Both can be written as `.play` files.

## Roles of places

The prover gives each place one role for one lifecycle instance.

- **Open** places are written by the environment: a place that some arc
  reads or takes from and that no arc produces into; a place annotated
  `fusion: true` that some arc reads or takes from, unless a composition
  closed it (see [Compositions](#compositions)); a
  timer's clock place; an input port that takes the instance color; and
  every record place (below). Another input port that the net produces into
  stays closed: inside this net its own producer fills it, as a composed
  partner would.
- A **record place** is a place whose `lives in` names a lifeline of kind
  `record` (`record "Branch home"` and `(branch_home) lives in "Branch
  home"`, ADR 0039): a record the outside world keeps and may change at
  any time. It is open whatever produces into it, wires it or shares it, and
  it is an updatable fact, never a start place, a resource, a sink or a
  final place. A place that lives in a `system` column or in a computed
  column (`lives in cel "…"`) is not a record place.
- A **kept place** holds a kept record:
  `(condition) kept by "circulation desk" starts as cel "{'isbn':
  instance.isbn, 'damaged': false}"`
  ([ADR 0051](../../docs/adr/0051-a-kept-record-is-there-from-the-start-and-only-the-net-writes-it.md)).
  It is never open, whatever produces into it, fuses it or shares it, and
  it is never a start place, a fact, a resource, a record place, a clock, a
  sink, a final place or an instance place. The rules below that name these
  roles leave it out. A `final` fact or domains file that names it, and a
  domains file whose `injections` or `updates` name it, are errors.
- The **instance color** is the color that the most places that are neither
  open nor kept accept (the first declared, on a tie), unless the domains
  file names it.
- **Start** places are the open places where the instance arrives: an open
  place that takes the instance color, or an open place that no arc produces
  into and whose consumer makes the instance color without taking it.
- **Resources** are the other open places some arc takes from (a lock),
  except record places. **Facts** are the remaining open places. A fact
  that no arc produces into, and every record place, is **updatable**.
- **Sinks** are places that no arc reads or takes from. A sink that accepts
  the instance color or is an output port is **final**, unless the net's
  `final` fact or the domains file lists the final markings (the file wins).
  Other sinks are **side outputs** (a signal place).
- A **final marking** is a set of final places that must all hold a token
  ([ADR 0049](../../docs/adr/0049-a-final-marking-can-need-several-places.md)):
  `final (skipped), (delivered) + (checked)` has two. A derived final place
  is a final marking by itself. The **final** places are the places of all
  final markings, whatever reads them.
- **Instance places** are all places that are not open, not sinks and not
  final.

### Kept records

The exploration starts with one token in each kept place: its start value,
the CEL of `starts as` evaluated with `instance` bound to the data of the
**check's instance token**. That token takes its own value for each `key`,
`ordered` and `free` field of the instance color, and the first value of a
declared or overridden field, so it agrees with the start token on every
key (`own-destination`). A start that reads a field this token does not
have, or whose value breaks a declared domain, is an error. Each field the
start sets from a literal counts as a literal output of the record's color
("set from literals only", below), and each field it copies from the
instance joins that field of the instance color, as a `data cel` copy does.

The environment never writes a kept place: no arrival, no update, no record
change. Proper completion does not look at it, and a final marking is
reached whatever it holds. Values the net writes into it still come from
the domains, through the arcs' `data` and `data cel`. In a refinement
check, the instance is the refining net's own (the color of the refined
transition's input arc).

## Data domains

The prover reads every CEL inscription of the net (predicates, correlates,
timers, `data cel`) and literal `data`, without evaluating them. A field is
named by color and path (`switch.owner`, `attempt.delivery.destination`).

**Embedded tokens.** A field holds a whole token of another color when a
`data cel` puts a bound token there (`{'hold': binding.quote_result[0]}`),
when a `data cel` result is a field of a bound token
(`binding.loan_ended[0].hold`), or when the field is named after a
color and its subfields are read (`result.hold.isbn`). Paths
through an embedded token name the embedded color's fields:
`result.hold.isbn` is `hold.isbn`. Every token the
prover builds of the embedded color has that field, so a fresh hold
that an abstract step wraps into a result token carries `isbn`.

**Joins.** A comparison between two fields (`token.isbn ==
binding.waiting[0].isbn`), or a `data cel` that copies one field into
another, puts the fields in one class.

Each field gets one domain, by the first rule that applies:

| Kind | When | Values | Soundness values |
|---|---|---|---|
| `time`, `clock` | the class holds a clock field compared in a timer | slots `1..n` for `n` timer fields, the clock also `0`; with numeric literals, the values around them | the same |
| `ordered` | a joined class compared with `<`, `<=`, `>`, `>=` | `1, 2, 3`; the instance's own value is `2` | the same |
| `key` | a joined class compared with `==` or `!=` only | `own-NAME`, `other-NAME` | `own-NAME`, and `other-NAME` too when the class is compared with `!=` or `otherKeys` is set |
| `list` | `size(field)` compared with a number | lists of `⟨item⟩` of the sizes around the numbers | the same |
| `bool` | the field is used as a boolean (`connected`, `!x`) | `true`, `false` | the same |
| `number` | compared with numbers only | each number, and values below and above it | the same |
| `literal` | compared with literals (`==`, `!=`, `in`) | the literals, then `⟨other⟩`; only the produced literals when the field is set from literals only (below) | the literals, and `⟨other⟩` too when a test passes a value no literal names (`!=`, or `==`/`in` under `!`) |
| `free` | read but never tested | `own-NAME` | the same |
| `declared` | a `domain` fact in the net | the listed values | the same |
| `override` | named in the domains file | the listed values | the same |

A field is **set from literals only** when every arc that produces its
color sets it to a literal (in `data`, or as a literal entry of a `data
cel` map), and no open place accepts the color, so the environment writes
none of its tokens. Its `literal` domain is then the literals those arcs
and the initial marking give it, with no `⟨other⟩`. A handler output (no
`data`, no `data cel`) or a copied value is not a literal, so it keeps
`⟨other⟩`.

A declared or overridden domain replaces the derived one ("derive, then
override"); the domains file wins over the net. A path through an embedded
token names the embedded color's field, as above. A declared field that no
CEL reads is still set on every token the prover builds, because the engine
rejects a token without it (ADR 0037).

`NAME` is the last key of the first field of the class. Around a number `n`
means `n - 1`, `n`, `n + 1` for integers, and halfway to the next number
(or `n / 2`, `n * 2` at the ends) for decimals. `double()`, `int()` and
`uint()` are read as their argument.

A field used in a shape the prover does not read (arithmetic, a macro, a
string function, `has()`) keeps the domain the other rules give it, and the
facts that test it report `unknown` instead of `proved` (a refutation stays
a refutation: its witness is a real token). A timer that compares the clock
with a sum of fields and numbers (`clock.now >= idle.since + idle.wait`,
`clock.now - idle.since >= idle.wait`) is read: its clock gets time slots,
and a term is opaque only while its values cannot say when the sum is due
(below).

**Building tokens.** An **instance token** takes its own value for `key`,
`ordered` and `free` fields. An **environment token** ranges over keys and
slots too. A handler output (a produce template with no `data` and no `data
cel`) starts from the carry rule's token (the one consumed token of its
color), or else from a token of its color embedded in a consumed token, or
else from a fresh instance token. The fields that the destination place's
readers test then take every value of their domain; an embedded token is
copied from the one consumed token of its color.

## Choice coverage

A **choice** is a place that is not kept, and not open unless a token arrives
there (a start place or an input port), with consume arcs of one color into two
or more transitions. A resource or fact that two transitions take from is shared
with the world, so it is no choice of this instance; the transitions that take a
token where it arrives decide what the net does with it. For each choice, the prover builds the choice
token (an instance token whose tested fields vary) and the **context**: for
every other input place of those transitions (read, consume or inhibit) and
every timer clock, an option per value: empty, or one environment token. It
asks the engine which of the transitions are enabled in each case.

- A **gap** is a case where none is enabled. Gaps are looked for in
  **settled** contexts only: a place that a choice transition reads or takes
  from, and that none inhibits, holds a token about the instance's own key,
  and every clock is at its last value. So a missing fact, a held lock or a
  timer not yet due is a wait, never a gap.
- An **overlap** is a case where two or more are enabled. An overlap is
  **resolved** when the net declares priorities and exactly one enabled
  transition has the highest one (the priority policy picks it). It is
  **waived** when the place or one of the enabled transitions carries
  `annotations.lint.suppress` with `choice-overlap`. `choice-gap` waives gaps
  the same way ([ADR 0016](../../docs/adr/0016-lint-surface-annotations-suppression.md)).
- An **intended wait** is a gap case for which a `wait` condition of one of
  the transitions is true
  ([ADR 0057](../../docs/adr/0057-a-choice-can-declare-one-case-an-intended-wait.md)).
  The annotation `wait` on a transition is `{"when": CEL, "for": text}`, or
  a list of them. `when` reads `binding`: for each binding key of the
  transition (its place names, or its binding names in a composition), and
  for each place the transition inhibits (by its name in the net that
  declares it), the data of the case's tokens in that place. The condition holds only when it
  gives `true`; an error or any other value does not hold. `for` says what
  the token waits for, in plain words. A wait is not a defect, and it covers
  only the cases its condition is true for; the report lists them as
  `intended wait`.

A choice is `refuted` by any gap or overlap that is not resolved, waived or
an intended wait.
It is `unknown` when a transition takes more than one token from the place,
a transition has a named guard or a named predicate (no handler runs), the
cases exceed 200 000, or a tested field is used in a shape the prover does
not read.

Findings group cases into **boxes**: for each field and context place, the
set of values for which the finding holds. The boxes of one finding are
disjoint, so no case is reported twice. Each box has one concrete witness
marking. The summary names a run of `number`, `time` or `list` values as the
range it stands for, by the numbers the CEL compares with:
`wearShare ≥ 0.01`, `size(notes) > 0`, `10 ≤ amount ≤ 50`.

## Place invariants

The incidence matrix `C[p][t]` counts the tokens a firing of `t` adds to
`p` minus those it takes: a consume arc counts its weight, a produce
template one token, read and inhibit arcs nothing. A **P-semiflow** is a
non-negative integer vector `y` over places with `y · C = 0`. The prover
computes the minimal semiflows with the Farkas algorithm, dropping after
each column every row whose support is not minimal (Martinez and Silva). A
semiflow on places that no firing changes says nothing and is left out.

Each semiflow is reported as `proved`: in every reachable marking,
`y · M` equals `y · M0` (`M0` holds each kept record's start token), plus `y(p)` for every token the environment puts
into an open place `p` of the support. The statement lists the colors in
the support. When their fields share a `key` class and a `correlate` names
those fields, the report names the key ("it likely holds per destination");
a key that only a copy (`data cel`) joins is not named. Version 1 proves the
total count only, not the per-key form. A handler may emit more than one
token per template; the matrix counts one.

**Declared invariants** (`invariant "lock" (free) + (busy) = 1` in the net,
or `Invariant(weights, constant=None, name=None)` in Python) are `proved`
when `weights · C = 0` and the constant, if given, equals `weights · M0` plus
what the environment model adds to the sum: for each open place `p` in the
support, `weights[p]` times its arrivals (one, or `injections[p]`), a clock
token in each empty clock place, and one start token per start (`starts`)
in one start place.
Otherwise they are `refuted`, with each transition that changes the sum and
by how much, or with the sum the initial marking and the arrivals give. When
the start places have different weights, the constant has no single value
and the fact is `unknown`.

## Soundness

The prover explores every marking one instance can reach, breadth first,
from the net's initial marking with each kept place at its start and each
empty clock place set to its first value. Moves:

- **Net moves**: a firing, for every binding the engine accepts and every
  handler output the domains allow; and a **tick** that sets a clock to a
  later value: a later value of its domain, or a time a timer on it says it
  matures at (its `timer maturity`, in the marking at hand). A deadline the
  net dates from the clock (`clock.now + 60`) lands on no domain value when
  the clock reached that value late; its maturity is the time it is due.
  A maturity that reads a time the net copies straight from the clock
  (`since + idleFor`, with `'since': binding.clock[0].now`) counts only while
  each such copy holds one of the clock's domain values, the values the copy
  takes as a time slot. A latch taken at a maturity would otherwise date
  the next maturity later still, and the ticks would never end. Past it the
  timer sees the domain values only, as a timer without a maturity does; a
  marking it leaves stopped is not refuted (see `unknown` below).
  When any transition declares a priority, the priority policy
  is assumed: only the highest-priority enabled transitions fire.
- **Arrivals**: the environment appends a token to an open place. The start
  places together get one arrival per start (one fewer when the initial
  marking already holds the instance). Each fact and resource gets one arrival by default.
  Arrival tokens are environment tokens with soundness values; a start
  token is an instance token with every known field set.
- **Updates**: the environment replaces the contents of an updatable fact
  that holds a token with one other token, once per place by default.
- **Record changes**: an update of a record place, any number of times (the
  count is not part of the state), and a **record move**: a firing of a
  transition whose input and output places are all record places, such as
  a person flipping a switch. A record move is the outside world's move, not
  a net move; the priority policy does not rank it.

The exploration stops at a **finished** marking: every place of one final
marking holds a token. With more than one start, a marking is finished when
it holds one final marking per start at once (see Starts, below). Eight
reductions keep it small; none of them drops a behavior of the instance
(for the limits of the tick, record and arrival reductions, see
[ADR 0055](../../docs/adr/0055-ticks-and-record-changes-wait-until-something-can-use-them.md),
[ADR 0061](../../docs/adr/0061-arrivals-wait-and-environment-tokens-group-by-what-their-readers-see.md)
and [ADR 0065](../../docs/adr/0065-a-copy-into-a-side-output-does-not-keep-environment-tokens-apart.md)):

- Before the instance is in the net (the first start), the environment
  starts it, or writes an open place that a step possible before then
  reads. Such a step's binding places hold tokens, can get one from the
  environment (the start only once it is there), or are outputs of other
  such steps; a step that marks an instance or final place ends the stretch
  ([ADR 0056](../../docs/adr/0056-before-the-start-the-environment-writes-what-a-step-can-read.md)).
- A tick happens only when some timed transition on the clock is enabled
  with the clock at its current value or at a later domain value, the
  other places as they are; a later tick reaches the same markings as an
  earlier one.
- Record places form groups: records that record moves join. A group
  **waits** when the net has a move (a firing or a tick) and no transition
  that reads or writes one of its records has its other binding places
  marked (records and clocks aside). A waiting group's records get no
  update, and a record move that touches only waiting records does not
  fire: the change commutes with the net's moves, and it can still happen
  once a step can use the records or the net stops. A group that no
  transition reads or writes never waits. A record move held back where it
  was enabled counts as fired for no dead transitions.
- With `--wait-arrivals` (`prove(..., wait_arrivals=True)`; off by
  default), an open place other than a start place **waits** for its
  arrival when
  the net has a move (a firing or a tick) and none of its users has its
  other binding places marked (open places and clocks aside). A user is a
  transition with an input arc from the place (consume, read or inhibit, a
  timer's bind included) or an output arc into it. A waiting place gets no
  arrival: the arrival commutes with the net's moves, and it can still
  happen, with any value, once a user is ready or the net stops. It is
  opt-in because a run that hits `--max-states` can explore about twice
  the edges with it (ADR 0061, note of 2026-11-02).
- The environment tokens of an open place (its arrival and update values)
  fall into classes, and the exploration tries the first token of each
  class in the domains' order. Two tokens are in one class when they have
  the same color, every CEL predicate of an arc from the place gives the
  same answer for both, and they agree on every field another reader
  reads: a correlate on an arc from the place or one that names it in
  `binding`, a timer that binds it, a produce `data cel` that reads it, and
  a handler output the prover builds from it (the carry rule's base, or a
  token it embeds), which reads the whole token. A handler output into a
  side output whose base is the token itself reads nothing: no step sees
  what it copies. Of a place whose tokens a step copies so, two tokens are
  in one class only when the net's declared domains accept both or refuse
  both (ADR 0065). An update to a token of the class the place holds is
  not tried.
- An open place that no still-possible transition reads gets no arrivals or
  updates, and its tokens do not tell markings apart. A transition is still
  possible when each of its binding places holds a token, can still get one
  from the environment, or is an output of a still-possible transition.
- Tokens in side outputs do not tell markings apart.
- A place the net only counts keeps as many equal tokens as its readers
  count: its largest read weight, or 1 when it has only inhibit arcs. A
  place is counted when no arc takes from it, no arc from it has a
  predicate or a correlate, no other reader sees its tokens' data (as in
  the classes above), and it is not open, final or kept
  ([ADR 0062](../../docs/adr/0062-a-place-the-net-only-counts-keeps-as-many-tokens-as-its-readers-count.md)).
  A loop that leaves such tokens behind closes, so it needs no firing cap.

The three facts:

- **Option to complete.** A marking is good when net moves alone reach a
  final marking from it, or when net moves reach a marking with no net move
  (the net waits) from which an arrival or a record change leads to a good
  marking. Every
  reachable marking must be good. The assumption is progress: an enabled
  transition eventually fires and time passes, while the environment owes
  nothing. A refutation is a **deadlock** (the net stops with the instance
  in a place, and no arrival helps), **vanished** (the instance has left
  every place without reaching a final marking), or a **livelock** (the net can
  fire forever without completing; the summary lists the environment moves
  that would end it, such as an update of a fact). A loop of record moves is
  not a livelock: it is the outside world changing its records.
- **Proper completion.** When a finished marking is reached, every instance
  place is empty. Places of the other final markings and kept places may
  hold tokens.
- **No dead transitions.** Every transition fires on some explored move; a
  record move counts.

**Firing caps.** A transition named in the domains file's
`environment.firings` does not fire on a path once it fired that many times
there; the counts are part of the explored state. The priority policy still
ranks a transition its cap stopped, so no lower-priority transition fires in
its place. A marking where a cap stopped an enabled transition is **cut**:
it is not a stop, and what lies past it is not explored. A refutation stays
a refutation, because its path is a path of the net without the caps. The
facts read the caps this way
([ADR 0050](../../docs/adr/0050-a-firing-cap-bounds-the-turns-of-a-loop-the-prover-explores.md)):

- Option to complete is `proved` when every marking reaches a final marking
  within the caps, `refuted` when a marking can reach neither a final
  marking nor a cut marking, and `unknown` otherwise (some markings complete,
  if at all, only past a cut).
- Proper completion checks the final markings reached within the caps.
- No dead transitions is `unknown`, not `refuted`, when a cap stopped a
  transition and some transition never fired.

Every soundness and refinement fact that is not refuted lists each cap in
`assumptions`.

**Starts.** The domains file's `environment.starts` (a positive count,
default 1) says how often the instance starts
([ADR 0052](../../docs/adr/0052-a-domains-file-can-start-the-instance-more-than-once.md)).
It counts starts, not tokens of one place: each start goes into one of the
start places. Each start is a start token from the same set the first one
uses, so every start has the same `own-…` keys; the fields the net tests may
differ. A later start may arrive at any time after the first, also while an
earlier one is still in the net. Kept records start once, so a later start
meets the history the earlier ones left.

A marking is finished when it holds as many final markings at once as there
are starts: the final markings may repeat, and each place must hold a token
for every chosen final marking that names it. With `final (a) + (b), (c)`
and two starts, `a, b, c` and `c, c` are finished, and `a, a, b` is not.
With one start this is the rule above. A marking where an earlier start has
finished and a later one has not arrived is not finished: the net waits for
the arrival. The three facts read "final marking" as a finished marking.
Counting is per place, so a start that leaves tokens in two final markings
counts twice.

Every soundness fact lists the starts in `assumptions` when there is more
than one (`the instance starts 2 times, with the same keys each time`), a
refutation too: a later start adds behavior, and the refutation's path may
need it. A refinement check ignores `starts`: the refining net's instance is
the one token the refined transition takes. A domains file whose
`injections` name a start place is an error.

A fact is `unknown` when the state cap is hit (except a proper-completion
refutation, whose path is concrete), when the net has no final place (option
to complete),
when a transition has a named guard or predicate, when a timer compares the
clock with arithmetic and a field the comparison reads keeps derived values
(time slots or a placeholder say nothing about when a sum is due; a domains
file that gives those fields values lifts it), when a marking from which no
final marking is reached waits on a maturity left out because the copy of
the clock it reads holds no domain value (option to complete; no dead
transitions, when a transition never fired), or when a firing failed
its deposit on a built token. In a sum, a field that holds time (the net
compares it with the clock or copies it from the clock) needs no values of
its own when the clock holds real times (a domains file gives them, or the
net's numbers bound them): it is placed as a deadline field such as
`clock.now >= idle.stopAt` is. When the state cap is hit and the net has a
transition the lint rule `read-only-producer` flags (it reads but consumes
nothing, so it can fire again and again), the report names it as the likely
cause: the text adds a `likely cause:` line, and the JSON exploration lists
it in `readOnlyProducers`.

**What this can and cannot show.** Results hold for the data domains and the
environment model. Time is abstracted to the order between the clock and the
timer fields; a timer that compares the clock with arithmetic on a field is
read only as far as the domains go. Tokens about another key are left out of
soundness by default (choice coverage checks that a correlate keeps them
apart). The exploration covers one instance, started once or `starts` times
with the same keys; two instances with different keys competing for a lock,
or a resource another instance never returns, are outside it.

## Compositions

`FILE` may be a composition, in `.petrinet` or JSON, whose references are
`.petrinet` or `.json` nets, or other compositions, relative to its
directory. The prover merges it (`spec/composition.md`), applying the
refinements, and proves the choice, invariant and soundness facts on the
merged net. A place the composition fused is closed: its producers are
inside the merged net, so its `fusion` annotation no longer opens it. One
exception keeps a split net provable: a place that a `share` fused stays
open when one of its members is annotated `fusion: true`, because the
environment still supplies that record or lock
([ADR 0040](../../docs/adr/0040-a-share-fuses-places-without-a-direction.md)).
A place that a wire fused is closed, unless it is a record place: a record
place stays open however it was fused, because the outside world keeps it. A
kept place stays kept, and never open, though the merge marks it `fusion`;
every member of a share that joins a kept place must be kept the same way
(ADR 0051). Every name in those facts is the
merged name (`lifecycle.pending`, or `lifecycle.gate.pending` inside a used
composition); a choice also names its constituent (`details.constituent`,
the longest alias that prefixes the place). The merged net keeps the
constituents' declared domains and proof facts. A composition's own `final`
markings replace the constituents' final facts, so a run that follows two
things at once can finish when both are done (`spec/composition.md`, "Final
markings"). Then each refinement gets its own check.

To check that a composition is the same net as another net, up to renaming,
use `velocitron equiv`
([ADR 0042](../../docs/adr/0042-equiv-compares-merged-nets-up-to-renaming.md)).
It compares whether the environment supplies each place, so it reports a
wired lock that was a supplied one before.

## Refinement check

For each refinement `refine X.[t] by Y`, the prover checks `Y` alone, with
its own place names, as a workflow net for one token:

- The **start** place is the input port of `Y` that the wires fuse with the
  place `t` consumes from; the instance color is that arc's color.
- The **final** places are the output ports of `Y` that the wires fuse with
  the place `t` produces into.
- `Y`'s other open places are its environment, as above (the domains file's
  `injections` and `updates` apply to them under their merged names,
  `loan.form`), and its other output ports are side outputs.
- A sink of `Y` that is not a port is not a side output: no composed net
  can take a token from it, so a token there is left behind (proper
  completion).

The fact `refinement X.[t] by Y` is `proved` when all of these hold:

- **option to complete**, **proper completion** and **no dead transitions**,
  exactly as in Soundness;
- no move puts more than one token into the final places: one token in
  leads to exactly one token out.

Its findings are the soundness findings of `Y` (a deadlock, a livelock, a
vanished instance, an improper completion, a dead transition) and an
`improper` finding for a second token. The fact is `unknown` when `t` takes
tokens from more than one place, or produces into more than one place, or
when no port of `Y` is wired to its places, and for the reasons Soundness
gives.

**What the check means for the composition.** Van der Aalst (2000) showed
that replacing a transition of a sound workflow net by a sound and safe
workflow net gives a sound workflow net; van Hee, Sidorova and Voorhoeve
(2003) showed that generalised soundness is kept by refinement without the
safeness condition. Here the outer net with the abstract `t` and the
refinement check together give a sound composition when:

- the outer net is sound with `t` as one step;
- `t` is never enabled twice at once in the outer net, or `Y` is sound for
  several tokens at once (not checked: the check follows one token);
- what `Y` gives back stays inside what `t` could give (an abstract `t` is a
  handler whose outputs the outer proof tried over every domain value, and
  the engine keeps `Y`'s outputs inside the declared domains);
- `Y`'s environment behaves as its model says.

## Counterexamples as plays

With a directory, the prover writes one `.play` per choice gap or
overlap box and per soundness finding with a path, named after the net, the
fact and the finding (`hold-lifecycle.choice-at-pending.gap-1.play`,
`hold-lifecycle.option-to-complete-1.play`), with a `net` line
relative to that directory.

- A choice witness starts from `marking none`, injects the witness marking
  (it updates a kept place whose start reads no `instance`, because the
  story already holds that record), and expects the choice transitions `not
  enabled` (a gap) or the overlapping ones `enabled`.
- A soundness counterexample starts from `marking initial`, after an
  `instance` line with the check's instance token when a kept record's
  start reads it. Then: `advance` for each
  clock, `inject` for an arrival, `update` for an update, and `fire` with
  `-> (p) token` for each handler output the carry rule does not give and
  `with (p) {data}` where a binding place holds more tokens than the binding
  takes. The counterexample contract follows the code: the prover's clock
  move is the machine form of the authoring word — `Move` holds
  `"kind": "advance"` (the kind the machine form of `advance` names, the
  one `velocitron_analysis.report` writes), and the *written play* spells the move as
  an `update`, so the file is immune to the advance statement's maturation
  and replays the walk's move order exactly
  (`velocitron_analysis.counterexample`). It ends with `expect quiescent` and the
  final places' counts, empty
  where nothing reached them (a deadlock),
  the instance places before and after one round of the loop (a livelock), or
  the counts of the final and instance places (improper completion).

A refinement finding plays against the refining net's own file, so its
`net` line names that file
(`partner-loan.refinement-lifecycle-checkout-borrow-by-loan-1.play`).

`velocitron play check` accepts every file it writes, and `velocitron
play walk` draws it.

## The domains file

A JSON or JSON5 object; every key is optional, and an unknown key is an
error.

```json5
{
  // The complete list of values for a field, replacing the derived domain
  // and the net's own domain fact.
  domains: { "result.outcome": ["loaned", "due_soon", "damaged"] },
  instance: "hold",              // the instance color
  final: ["loaned", ["loaned", "shelved"]],  // the final markings, replacing the net's final fact
  environment: {
    injections: { editions: 2 },  // arrivals per open place (default 1)
    updates: { editions: 0 },      // updates per updatable fact (default 1; a record place has no limit; a kept place: an error)
    otherKeys: true,                      // soundness also tries another key's tokens
    firings: { "lifecycle.request.reopen": 2 },  // at most 2 firings on any path (merged name)
    starts: 2,                            // the instance starts twice, with the same keys (default 1)
  },
}
```

`firings` names transitions by their merged names; an unknown name, or a
count that is not a positive integer, is an error. `starts` that is not a
positive integer, and `injections` that name a start place, are errors.

## Command line

```text
velocitron prove FILE [--json] [--fact choice|invariants|soundness|refinement]...
                      [--counterexamples DIR] [--domains FILE] [--max-states N]
                      [--wait-arrivals]
```

`FILE` is a `.petrinet` or `.json` net or composition (merged). Without
`--fact`, every fact runs (`refinement` only does something for a
composition). `--max-states` bounds each exploration: the merged net's and
each refining net's (default 50 000). `--wait-arrivals` turns on the
arrival wait above, for the merged net and each refining net.
The text output prints each fact as `PROVED`, `REFUTED` or
`UNKNOWN` with its findings, an `assumes:` line per firing cap and for the
starts, then the exploration's line, what made the markings when it stopped
at the state cap (below), a `firing cap:` line per cap and a `starts:` line,
then `result:`. `--json` prints the report
below. The exit code is 0 when nothing is refuted and 1 otherwise; a net or
domains file that cannot be read prints `FILE:1:1: error[PN200]: …` (or the
DSL diagnostic) and exits 1; argument misuse exits 2.

### The progress line

An exploration that runs longer than ten seconds writes one line every ten
seconds to the error stream, never to the report or `--json`:

```text
prove item: 1 240 000 markings · 4 100 a second · 1.4 GB · 5 min 02 s · 15 % of the state cap · 310 000 waiting, rising
```

In order: the net's name; the markings so far; the markings a second since
the line before (since the start, for the first); the memory the process
holds (macOS: its physical footprint; Linux: its resident size), in MB
below 1 GB and in GB to a tenth above; the time so far (`12 s`,
`5 min 02 s`, `1 h 02 min`); the markings as a whole percent of the state
cap, rounded down; and how many markings still wait to be explored,
`rising`, `falling` or `steady` against the line before (against the one
marking that waits at the start, for the first). Numbers group their
thousands with a space. The memory figure is how an author knows to lower
the state cap: there is no memory limit of its own. A refining net's
exploration writes the line under the refining net's name.

Any prover writes the same words for the same figures:
`conformance/prove/progress-lines.json` holds the cases.

### What made the markings

When the exploration stops at the state cap, the report says what made its
markings, in two parts. First, the ten steps that first reached the most
markings, each with its kind, its place or transition, how many markings
it first reached and its share of the markings reached by a step (every
one but the initial marking); one line counts the rest. A step is a
`firing` of a transition, an `arrival` in an open place, an `update` of a
read-only fact, a `record` change (an update of a record, or a record move
by its transition), or a clock `advance`. Second, up to ten places that
multiply the markings most, each with its factor: how many markings become
one when the place is ignored, the markings counted as the exploration
keeps them (the used counts included), rounded to a tenth; a place whose
factor rounds to 1.0 is left out. The places are found in one pass over the
stored markings when the run stops. The list is for the author: two provers
are not compared on it.

```text
explored 11 markings, 12 moves (state cap hit)
what made the markings: the steps that first reached them
   50 %  5  firing [b]
   30 %  3  firing [a]
   10 %  1  arrival in (start)
   10 %  1  firing [tidy]
places that multiply the markings: how many become one when the place is ignored
   ×2.2  (xs)
   ×1.8  (ys)
```

The rest reads `everything else (N kinds of step)`; the other labels are
`update of (place)`, `record change of (place)`, `record change by
[transition]` and `clock advance of (clock)`.

## The JSON report

The report is stable and deterministic: the same net, domains file,
options and tool version give the same bytes. `tool` names the program and
its version (`velocitron --version` prints the same text), so a saved
report says which prover wrote it. Version 1:

```text
{
  "version": 1,
  "tool": "velocitron <version>",
  "net": "<net name>",
  "source": "<file as given>" | null,
  "status": "proved" | "refuted" | "unknown",     // refuted if any fact is, else unknown if any is
  "facts": [ Fact, ... ],              // choices, invariants, soundness, refinements, in that order
  "model": {
    "roles": { "instanceColor", "start", "facts", "updatable", "records",
               "kept", "resources", "clocks", "final", "sideOutputs" },  // sorted place lists
    "domains": { "<color.path>": { "kind", "values", "source", "soundnessValues"?, "own"? } },
                                                    // source: derived | declared | override
    "unsupported": { "<transition>": ["<reason>", ...] }
  },
  "exploration"?: { "states", "edges", "capped", "maxStates",
                    "readOnlyProducers"?,    // when soundness ran; the list only when capped
                    "madeBy"?: MadeBy,       // only when capped
                    "firingCaps"?: { "<transition>": { "limit", "stopped" } },
                    // with firing caps; stopped: markings where the cap stopped it
                    "starts"? },             // with more than one start
  "composition"?: { "nets": { "<alias>": "<file>" } }           // when FILE is a composition
}

Fact = {
  "fact": "choice" | "invariant" | "soundness" | "refinement",
  "subject": "choice at (pending): [hold] | [skip]" | "place invariant 1"
           | "<declared name>" | "option to complete" | "proper completion"
           | "no dead transitions" | "refinement lifecycle.[attempt] by attempt",
  "status": "proved" | "refuted" | "unknown",
  "statement": "<the claim in plain English>",
  "reason"?: "<why unknown>",
  "assumptions"?: ["the instance starts 2 times, with the same keys each time",
                   "[t] fires at most 2 times on a path", ...],
                   // starts on every soundness fact; firing caps not on a refutation
  "details"?: { ... },     // choice: place, color, transitions, cases, constituent?;
                           // invariant: weights, initial, open, colors, sharedKey?, arrivals?;
                           // refinement: net, transition, by, file, inputs, outputs,
                           //   sideOutputs, exploration?
  "findings": [ Finding, ... ]
}

Finding = {
  "kind": "gap" | "overlap" | "resolved" | "waived" | "waived-gap"
        | "deadlock" | "vanished" | "livelock" | "improper" | "dead"
        | "changes" | "initial",
  "summary": "<one sentence>",
  "witness"?: { "<place>": [Token, ...] },          // choice findings
  "cases"?: { "<field or (place)>": "<value>" | ["<value>", ...] },
  "count"?: <cases in this finding's group>,
  "enabled"?: ["<transition>", ...],
  "transition"?: "<transition>",                     // dead, changes
  "path"?: [Move, ...],                              // from the initial marking
  "cycle"?: [Move, ...],                             // a livelock's loop
  "marking"?: { "<place>": [Token, ...] },           // where the path ends
  "play"?: "<file written>"
}

Move = { "kind": "fire" | "inject" | "update" | "advance", "transition"?, "place"?,
         "token"?: Token, "binding"?: { "<place>": [Token] }, "outputs"?: { "<place>": [Token] } }
Token = { "type": "<color>", "data": { ... } }

MadeBy = {
  "markings": <markings reached by a step>,
  "steps": [ { "kind": "firing" | "arrival" | "update" | "record" | "advance",
               "transition"? | "place"?, "count", "share" }, ... ],
                                    // at most ten, most first; share of "markings", to 4 places
  "rest"?: { "steps": <kinds of step left out>, "count", "share" },   // beyond the ten
  "places": [ { "place", "factor" }, ... ]    // at most ten, largest first; factor to a tenth
}
```

## Python API

`prove`, `load`, and `read_settings` live in `velocitron_analysis`.
`velocitron.prove` re-exports them. The command stays `velocitron prove`.

```python
from velocitron.prove import Invariant, ProofSettings, load, prove, read_settings

net, composition = load("library-holds.petrinet")    # composition is None for a net
report = prove(
    net,
    facts=("choice", "invariants", "soundness", "refinement"),
    settings=read_settings("domains.json5"),          # or ProofSettings(...)
    invariants=[Invariant({"free": 1, "crit1": 1, "crit2": 1}, constant=1)],
    max_states=50_000,
    counterexamples="cex/", net_file="library-holds.petrinet",
    composition=composition,
    progress=sys.stderr.write,                        # the progress lines; None for none
)
report.status, report.as_json(), report.text()
```

`load_net(path)` returns only the net. Invariants given in Python are proved
next to the ones the net declares. `progress` takes each progress line with
its newline; without it, `prove` writes none.

## Not in version 1

- A simulation or bisimulation check between a refining net and the
  transition it refines (the refinement check proves the block sound).
- Per-key invariants, several instances (a refining net used by two tokens at
  once among them), fairness, and temporal logic.
