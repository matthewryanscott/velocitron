# A domains file can start the instance more than once

**Status:** Accepted (2026-10-19). Refines ADR 0036 (the environment model
and the soundness facts), ADR 0049 (final markings) and ADR 0051 (kept
records).

`velocitron prove` follows one instance: the start places together get one
arrival, and the exploration stops when one final marking is reached. ADR
0051 named the cost: a step that needs an earlier history of a kept record
is dead unless one instance can build that history.

A small example: a counter keeps, per account, whether a job came before.
It starts empty. The first job for an account sets it; a repeat job for the
same account raises an alarm. With one start, `[repeat]` never fires, and
"no dead transitions" is refuted although the net is right. The check needs
a second job for the same account, without a change to the net.

`environment.injections` did not help. It counts arrivals into a fact or a
resource, and the prover ignored it for a start place without saying so.

## Decision 1: `environment.starts` says how often the instance starts

```json5
{ environment: { starts: 2 } }
```

`starts` is a positive count, default 1, next to `injections`, `updates`
and `firings`. It counts starts of the instance, not tokens of one place:
when a net has several start places, each start goes into one of them, as
the single start does today. A count that is not a positive integer is an
error. `injections` that names a start place is now an error that points to
`starts`.

## Decision 2: each start is the same instance

Each start is a start token from the same set the first start uses: the
same `own-…` value for every key, ordered and free field, and any soundness
value of the other fields. So two starts agree on every key (the same
account), and may differ in the fields the net tests (the job's state, its
times). A start never takes another key's value: that is a different
instance, which `otherKeys` covers.

The later starts may arrive at any time after the first, also while an
earlier start is still in the net. Kept records start once, from the check's
instance token, so the later starts meet the history the earlier ones left.
"Before the instance is in the net, the environment only starts it" still
holds for the first start.

## Decision 3: the instance is finished when every start is finished

A marking is **finished** when it holds as many final markings at once as
there are starts. The final markings may repeat, and each place must hold a
token for every chosen final marking that names it. With `final (a) + (b),
(c)` and two starts, `a, b, c`, `a, a, b, b` and `c, c` are finished; `a,
b` and `a, a, b` are not. With one start this is the rule of ADR 0049.

- The exploration stops only at a finished marking. A marking where an
  earlier start has finished and a later one has not arrived yet is not a
  stop; the net waits for the next start, as it waits for any arrival.
- **Option to complete** keeps its definition with this meaning of
  finished: every marking reaches a finished marking by net moves, or the
  net waits and an arrival (a later start among them) leads on to one.
- **Proper completion**: at a finished marking, no instance place holds a
  token. A start that is still in the net when the others have finished is
  not finished, so the check goes on.
- **No dead transitions** is unchanged.

## Decision 4: every result states the starts

Every soundness fact lists `the instance starts 2 times, with the same keys
each time` in `assumptions`, also a refutation: unlike a firing cap, which
only removes behavior, a later start adds behavior, and a refutation's path
may need it. The JSON exploration has `starts`, and the text prints a
`starts:` line after the exploration. A declared place invariant counts one
start token per start in its constant. A refinement check ignores `starts`:
the refining net's instance is the one token the refined transition takes.

## Considered options

- **`injections` for a start place.** It reads well for a net with one start
  place, but `injections` counts environment tokens per place, while a
  start is the instance arriving in one of several places. A separate count
  keeps both meanings plain.
- **A second instance token in the domains file.** Rejected for the reason
  ADR 0051 gives for a start in the domains file: it moves data about the
  net into a file beside it, and its literal keys would not match the
  instance the check invents.
- **A count per final place in the final list** (`final: [{done: 2}]`). The
  author would have to list every way several starts can end. Counting final
  markings per start derives this from the final list the net already has.
- **Tracking each start separately**, by tagging its tokens. The net's tokens
  carry no start id, and tagging them would change what the engine fires.
- **Two instances with different keys.** That checks that instances stay
  apart, which `otherKeys` and choice coverage already do; it never reaches a
  step that needs one key's history.

## Consequences

- A step that needs an earlier start's history can be shown to fire, and
  the check proves the net without a change to its rules.
- The state space grows with each start, because a later start can arrive
  at any point of the earlier one. In one small net, 68 markings became
  about 1 400 with two starts.
- Counting is per place, not per start: a start that leaves tokens in two
  final markings counts as two finished starts. Nets where one start ends in
  several final markings at once should keep `starts` at 1.
- The contract is in [`packages/spec/proofs.md`](../../packages/spec/proofs.md) ("Soundness"
  and "The domains file").
