# Prove facts by finite data domains and explicit state exploration

**Status:** Accepted.

**Numbering.** Two branches are in flight as this is written:
`composition-refine` may take 0034 and `viz-coalesce-fusion-copies` 0035.
This record takes 0036 so that the three merge without a renumber.

ADR 0019 made the property pass a check of markings a system *actually
produced* and stated its boundary: "explicitly **not** state-space model
checking". Authors of lifecycle nets now ask questions only reachable
markings answer. Is each choice a partition of the tokens that can sit
there? Which token counts never change? Can one hold always finish, and
finish cleanly? A play found the gap where a release meets the same
"hold" verdict again, but only because someone wrote that path.

This record crosses the ADR 0019 boundary on purpose, in a separate surface
(`velocitron prove`, `velocitron.prove`), and says how. The contract is
[`packages/spec/proofs.md`](../../packages/spec/proofs.md). ADR 0019 stays as it is: the
property pass still checks only markings handed to it, and it never imports
the prover.

## Decision 1: three facts, each proved, refuted or unknown

Version 1 proves three facts: **choice coverage**, **place invariants**
(minimal P-semiflows, and invariants an author declares in Python), and
**soundness** of one lifecycle instance (van der Aalst: option to complete,
proper completion, no dead transitions). Each fact comes out `proved`,
`refuted` with a witness or a shortest counterexample, or `unknown` with the
reason. Exit 0 means nothing is refuted.

**Considered options:**

- A general temporal-logic model checker (CTL or LTL over the reachability
  graph). Rejected for now: authors ask these three questions in their own
  words, and a formula language is a second language to learn. The graph the
  explorer builds is the base a later checker would need.
- Report only `proved` or `refuted`. Rejected: when a cap is hit or a
  construct is not supported, "proved" would be a lie and "refuted" a false
  alarm; `unknown` with a reason is honest.

## Decision 2: finite data domains from the net's own CEL; the engine decides

Colored tokens carry unbounded data, so the state space is infinite. The
prover reads the CEL the net already has and gives each tested field a small
domain that separates every outcome the CEL can see: the literals plus
`⟨other⟩`, `true`/`false`, values around numeric literals, `own`/`other`
values for fields a correlate joins, three ordered slots for fields compared
with each other, and time slots for fields a timer compares with the clock.
The domains file overrides any field (stage 2 adds a `.petrinet` fact).

The prover never evaluates CEL itself. It builds concrete tokens from the
domains and asks the ordinary engine (`reserve` with a `choose` filter that
collects every viable binding, then `settle`, as a play's symbolic
firing does). Enablement, binding, correlates, inhibits, timers, priorities
and deposit stay the engine's rules (ADR 0027): the prover adds no second
enablement semantics that could drift from the first.

**Considered options:**

- Symbolic constraint solving (an SMT solver such as z3 over the CEL).
  Rejected for version 1: it needs a CEL-to-solver translation that is a
  second CEL semantics, and a native dependency. The nets in use compare
  fields with literals and with each other, which finite domains cover
  exactly. A shape the prover does not read (arithmetic on a field, a string
  function) turns `proved` into `unknown`, never into a silent pass.
- Sample random data. Rejected: a sample can miss the one value that opens a
  gap, and it is not deterministic.

## Decision 3: soundness explores one instance with an explicit environment

Soundness is checked on the explicit graph of every marking one instance can
reach. Nets in use are open: a lifecycle reads facts (a switch, a verdict),
takes shared resources (a lock), and starts from a token the world puts
down. The **environment model** makes this explicit: open places (no
producer, a fusion place the net reads, a timer clock, an instance input
port) receive tokens from the domains, each once by default; a fact the net
only reads may also be replaced once (an `update`). Time is a clock that
jumps forward between the time slots.

Option to complete assumes **progress** (an enabled transition eventually
fires, time passes) and owes nothing to the environment: a marking is good
when net moves alone reach a final marking, or when the net stops and an
arrival lets it go on. So a loop that completes only if the environment
changes a fact it already gave is refuted as a livelock. That is the
reshelve case: after `reshelve`, the desk marks the copy missing again and
again until the shelf note changes or a newer edition withdraws the hold.

Four reductions keep the graph small without dropping an instance behavior:
the environment starts the instance before it writes anything else; a tick
waits until a timed transition has its tokens; an open place no
still-possible transition reads gets no writes and does not tell markings
apart; side outputs (signals) do not either. The checkout lifecycle explores
in 632 markings.

**Considered options:**

- A closed net only (the initial marking is the whole world). Rejected: the
  nets in use start with an empty marking, and the facts they read are the
  point.
- Let the environment act without bounds. Rejected: the graph is infinite,
  and every livelock would look rescued by "the verdict may change".
- Treat timers as "eventually enabled". Rejected: it loses the case where
  two timers are due together and a priority decides, which the checkout
  lifecycle relies on.

## Decision 4: counterexamples are plays

A witness or counterexample is written as a `.play` file that
`velocitron play check` accepts: arrivals become `inject`, updates
`update`, time `advance`, firings `fire` with `->` outputs where no `data cel`
or carry rule gives them, and the last lines are `expect` statements that
state the finding. The play checker confirms each finding through a
second path, and `velocitron play walk` draws it (ADR 0031, ADR 0033).

## Decision 5: waivers use the lint suppression list

An overlap that the author intends (two transitions that may both take a
token, whichever comes first) is waived with
`annotations.lint.suppress: ["choice-overlap"]` on the place or a
transition; `choice-gap` waives gaps. The waived finding stays in the report
as `waived`. An overlap the priority policy resolves is reported as
`resolved`, not as a defect. This reuses ADR 0016 instead of a new
annotation.

## Consequences

- The engine, grammar, IR schema, composition and viz are unchanged. The
  prover is a consumer of `Net` and `Engine`, Python only, like the
  play checker. It adds no dependency.
- `reserve`'s documented `choose` filter (called once per viable binding,
  before the guard) is now load-bearing for a second consumer.
- A named guard or named predicate has no handler in the prover, so the
  facts it touches are `unknown`.
- Invariants are proved for token counts. A "per home branch" reading is
  named when the colors share a key, but not proved.
- Results hold for the domains and the environment model; the report lists
  both, so a reader can see what was assumed.
- Stage 2 (after `composition-refine` merges) adds a `domain` fact to the
  `.petrinet` language, a refinement check and an Obsidian fence that renders
  the JSON report; the report shape in `spec/proofs.md` is what that fence
  reads.
