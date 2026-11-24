# A copy into a side output does not keep environment tokens apart

**Status:** Accepted (2026-11-11, Ada: "A alone. 3.80× measured, the same
results on the whole benchmark set, almost no code"). Refines ADR 0061
(Decision 2, rule 3: what a handler output reads of an environment token)
and, through the same reading, ADR 0062 (which places are counted).

A net can copy an environment token into a place nothing reads.
`implementations/python/tests/fixtures/prove/side-copy.petrinet` is the
small case: a page event that is not the end is copied into `(followed)`,
and no step reads `(followed)`. On a larger net the same shape dominated
the state space. One open place held every combination of its tokens while
the instance sat where no step took that place. The steps that did take a
token told only a few kinds apart: two tokens that pass the same arc tests
were kept apart anyway, because a handler output built from the consumed
token reads the whole token (ADR 0061, Decision 2, rule 3) and the step
put that token into a side output. A side output has no arc leaving it and
is not final. Nothing ever reads what was copied there, and the explorer
already leaves the tokens of a side output out of what tells two markings
apart.

## Decision: a handler output into a side output reads nothing of the token it is built from

ADR 0061, Decision 2, rule 3 says two environment tokens of an open place
`p` are in one class only when they agree on every field any other reader
of `p` reads, and it lists as a reader "a handler output the prover builds
from a consumed token of `p`", which reads the whole token.

That reader now counts only when its output lands where a step can read
it. A handler output whose destination is a **side output** (a place no
arc leaves, that is not final: `sideOutputs` in the report's model) reads
nothing of the token of its own color it starts from (the carry rule's
base). A transition that has such an output and another handler output of
the same color into any other place still reads the whole token, as
before. A handler output that copies a token embedded in, or embedding,
the consumed one still reads the whole consumed token wherever it lands:
the engine checks the copy under its own color (see Limit).

Nothing else in ADR 0061 changes: rule 1 (the color), rule 2 (each arc
predicate's answer), the other readers of rule 3 (a correlate, a timer's
bind, a produce `data cel`), the first token of each class in the domains'
order, and `group_tokens=False` to explore without the classes. One rule
is added for the Limit below, for a place whose tokens a step copies into
a side output: two of its tokens are in one class only when the net's
declared domains accept both or refuse both.

**Why the verdicts stay the same.** It is ADR 0061's swap argument, with
the side output as one more place the swap may touch. Take tokens `a` and
`b` that are in one class now and were not before: they agree on
everything rules 1 to 3 name, and differ only in fields that some step
copies into a side output `q`. Swap `a` for `b` in a marking `m`, and in
every move from it.

- Every arc test that sees the token gives the same answer, so the engine
  accepts the same bindings, up to the swap.
- Every output is the same, up to the swap, except the copy in `q`, which
  holds `a`'s fields in one successor and `b`'s in the other. The net's
  declared domains accept both copies or refuse both (the Limit), so the
  engine deposits both or neither. So the successors are equal up to the
  swap, and the swap now reaches `q` as well as `p`.
- Nothing reads `q`. No arc leaves it, so no predicate, correlate, timer or
  `data cel` sees its tokens and no handler output is built from one. It
  is not final, so "finished" does not ask about it; it is not an instance
  place, so proper completion does not; no dead transitions reads the
  firings, which are the same; option to complete reads the moves, which
  are the same up to the swap.

So the markings reached with `a` and with `b` are bisimilar, and keeping
one of them keeps every verdict. The explorer already leaves the tokens of
a side output out of a marking's key ("tokens in side outputs do not tell
markings apart", `spec/proofs.md`): once the page event is copied, the two
markings are one today. The classes only kept them apart for as long as
the token still waited in `p`.

The same reading decides ADR 0062's counted places, which ask that no
reader sees a token's data. The prover takes a token a step reads, as well
as one it consumes, as the base of a handler output of its color, though
the engine builds such an output fresh. A closed place that a step reads
beside a handler output of its color into a side output is now counted.
ADR 0062's argument holds unchanged: it cuts only equal tokens, and no step
reads the output. `fixtures/prove/side-copy-count.petrinet` is
`redelivery.petrinet`'s loop with such an output; it ends with no firing
cap, with the verdicts of `[redeliver]` capped at 3.

**Limit.** The classes are decided before the run, and a deposit is
checked during it. A domains file can give a field a value outside the
domain the net declares for it; the engine then refuses the copy of a
token that holds it (a deposit-contract violation), and the exploration
notes a failed deposit and turns the soundness results that were proved
unknown. The swap argument breaks there: the copy of `a` lands and the
copy of `b` does not. Neither token stands for the other: trying only the
accepted one hides the failed deposit, and trying only the refused one
makes the step that copies it dead. So, for a place whose tokens a step
copies into a side output, a token the net's declared domains refuse is
never in one class with one they accept, and both are tried.
`fixtures/prove/side-copy.petrinet` with `side-copy-outside.domains.json5`
gives `page.running` the value `"unset"` beside `true` and `false`: page
events are tried as `waiting` and `done`, each with `true` and with
`"unset"`, and the three results and the dead transitions equal those of
the exploration without the classes (option to complete refuted, the
other two unknown for the failed deposit). The check is on the consumed
token, under its own color, so it covers the carry rule's copy only; a
copy of an embedded token keeps the whole token read
(`side-copy-embedded.petrinet`).

## Considered options

Four ways to hold fewer markings for tokens that wait in an open place. A
(the decision) and B keep every verdict; C and D do not.

| | Candidate | What it changes | Verdicts |
|---|---|---|---|
| | today | every environment token stays distinct | |
| A | a copy into a side output is no reader (this decision) | fewer markings, the classes ADR 0061 already argues | the same |
| B | a waiting arrival is counted, not valued | fewer still, by a new argument | the same |
| A + B | both | the two reductions together | the same |
| C | an arrival waits at a stop too | fewer again | can refute what today proves |
| D | the environment writes only at a stop | fewer | can call a live transition dead |

The comparison is the shape of each rule, not a count from one net. A
scratch copy of the compiled kernel's prototype loop (which reproduces the
reference explorer edge for edge) tried each candidate with one switch.
B, applied to every open place it can see rather than the one place that
waits, holds counted and valued tokens side by side and saves less.

**B. A waiting arrival is counted, not valued.** While an open place
waits (ADR 0061), an arrival puts down a pending token that stands for any
environment token of the place; the step that ends the wait gets one
successor for each choice of values for the pending tokens. While a place
waits, no enabled step has an arc from it, so no test, correlate or output
sees its tokens, and the arrival still happens where it happened: the same
verdicts. A token that a step could once see keeps its value for good:
giving it a new one when the place waits again would let a marking
complete with a value its token never had. B saves markings on its own and
more with A, but it needs a second representation of a token in both the
reference and the kernel (a pending token, a fan-out where the wait ends,
a guard that no binding sees one), a counterexample that is no longer a
plain replay of its edges, and parity proved again. Deferred until the
kernel built on A has measured how much room A alone leaves under 2 GB.

**C. An arrival waits at a stop too.** ADR 0061's opt-in wait holds an
arrival back only while the net has a move; C holds it back at a stop as
well. An arrival counts as a rescue only at a stop, so C can refute what
today proves. Take `[u]: (A) + (p) → (done)`, `[c]: (A) → (B)`,
`[d]: (B) + (switch on) → (A) + (switch off)`, with `(p)` a fact and
`(switch)` a record. Today the net stops in `(B)`, the fact arrives there,
the switch is flipped, and `[u]` completes: option to complete is proved.
With C the fact may not arrive in `(B)`, where `[u]` cannot use it, and in
`(A)` the net is never at a stop, so its arrival is never owed: option to
complete is refuted. B is the exact form of C: it remembers that the
arrival happened. The example is argued from `_good`'s rule, not run
through the prover, and C's verdict on a large net is not known.

**D. The environment writes only at a stop.** Every arrival waits while
the net has a move. A step that needs an arrival while the net is busy
never fires: with `[u]: (A) + (p) → (done)` and `[a]: (A) → (B)`, today
`(p)` arrives beside `(A)` and `[u]` fires; with D `[u]` is dead.

**Measured** (the rule as a patch over the reference explorer and as a
switch in the kernel's prototype loop). Where both runs finished, A left
the verdicts unchanged and cut the markings of a net that copies an
environment token into a side output. Nets that do not copy that way, and
the examples' and fixtures' nets, kept their markings, edges and verdicts.
The benchmark set in this tree is recorded again under the rule
(`benchmarks/prover/numbers/counts.jsonl`).

## Consequences

- The rule is on with the classes, with no switch of its own in the CLI or
  the domains file.
- A large net's soundness proof then fits in the memory the proof may
  use, with no kernel change: the kernel's tables take the environment's
  tokens and their classes from the reference explorer.
- A counterexample shows the first token of a larger class, as ADR 0061
  already has it.
- The report's counts change for every net that copies an environment
  token into a side output. The benchmark set's counts
  (`benchmarks/prover/numbers/counts.jsonl`) are recorded again with this
  rule, and the diff shows sizes only, never a result.
- Not decided here: B (deferred, above); classes that follow a copy into a
  place whose own readers read only some fields; and an open place whose
  readers do tell its tokens apart, which still multiplies the markings.
