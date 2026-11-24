# Scenarios check firing sequences by symbolic firing

**Status:** Accepted. (Amendment: the carry rule's helpers — `produce_templates`, `net_fills`, `carry_rule` — moved from `play/check.py` to one shared home, `velocitron/outputs.py`, read by both the play checker and the engine's symbolic `advance(outputs=...)`; Decision 2 is unchanged.)

Authors of a net want to write down what should happen: "a patron places a
hold, the loan fails, ninety minutes later the next loan
starts, and past the time limit recalling the hold wins". Until now that lived in
prose next to the net, and nothing told the author when the net stopped
agreeing with it. A net often has no handlers yet, so it cannot run.

This record settles how such a sequence is written, how it is checked
against a net without handlers, and how it is shown. The contract is
[`packages/spec/play-language.md`](../../packages/spec/play-language.md).

## Decision 1: a `.play` file with `///` prose

A Play is one `.play` file beside the net. Statements start at
column 0, with the `.petrinet` brackets for places and transitions
(`fire [borrow]`, `inject (shelf_note) <- …`), short step lines,
and `///` Markdown prose that belongs to the next step. A coding agent can
update one compact file each design round, and it diffs cleanly.

**Considered options:**

- Play fences inside a Markdown note, so the note is the walkthrough.
  Rejected: a play spread over fences breaks when someone moves a
  paragraph, and a test fixture would need a note around it.
- Bare names (`fire start_attempt`). Rejected: the brackets show at a glance
  which name is a place and which a transition, as in `.petrinet`.
- An ANTLR grammar, like `.petrinet`. Deferred: the language is small and
  line-based, so the Python reference is a hand-written scanner. The grammar
  in the spec is the contract; a generated parser can come with the
  TypeScript port.

## Decision 2: symbolic firing through `reserve` and `settle`

The checker plays a `fire` step through the engine's existing two-phase
seam: `Engine.reserve` selects the binding and takes the consumed tokens,
the play builds the `TransitionHandlerOutput`, and `Engine.settle`
deposits it. An injection goes through `inject_token(s)`, and an `advance` is
an update of the clock place. Enablement, binding order, read and inhibit
arcs, correlates, timers, priorities and the deposit contract are therefore
the engine's own rules, and the records are the engine's own records.

Two engine additions carry this. `reserve(..., choose=)` takes a filter over
candidate bindings, for `with` clauses; it runs inside the first-success
consumer, before the guard, and cannot make a rejected binding viable.
`explain_enablement(net, marking, t)` takes its verdict from the one binding
enumeration (ADR 0027) and names, with values, the gate behind each
rejection: a false or failing predicate, a correlate miss (ADR 0030), an
inhibit hit, a timer hold with the clock and bound values, an empty clock,
or an unregistered guard.

**Considered options:**

- A fake handler registry that returns the play's outputs. Rejected: it
  needs a handler name on every transition, and `fire` would call it with no
  way to state the binding.
- A second enablement check inside the play checker. Rejected: two
  definitions of "enabled" drift; every new engine gate would need a twin.
- `fire(binding=)`. Rejected: it hands the engine a binding to trust; a
  filter over the engine's own enumeration cannot smuggle one in.

## Decision 3: output data, in order, and never a guess

For each produce template of a fired transition, in declaration order:
the net's `data` or `data cel` fills it, and a step may not override that;
otherwise the step's `->` clause gives it (`+{…}` merges over the carry
token); otherwise the carry rule copies the one consumed token of the
template's color; otherwise the step fails with `SC303`, naming the
template.

The carry rule takes consume-mode tokens only. A read token is the
environment (a branch-home record, a shelf note, a clock), and copying one forward would
invent a token that the net never produces. A transition that changes a
token's color (`hold → loan`) therefore needs `->` data, and the
failure points at exactly the information the net does not determine.

**Considered options:**

- Carry from read tokens too. Rejected for the reason above.
- An empty `{}` when nothing applies. Rejected: a wrong silent default looks
  like data in the walkthrough and hides a gap in the net.

## Decision 4: paths branch from labels and replay their prefix

A step may carry `@label:`; `path NAME from @label` starts a branch that
replays the trunk (or an earlier path) up to and including that step. The
shared steps are written once and played again for each path. A failure in
a shared prefix is reported once, with the paths it blocks.

## Decision 5: plays across composed nets

`net` may name a composition document, and a play may compose nets
itself with `use` and `wire`. Names are then `alias.name`, and a fused port
answers to each member's qualified name, through `port_fusion_map` from the
merge. One of the reasons to model with nets is that a process can be split
into single nets, composed, and still be walked end to end.

## Decision 6: the walkthrough is one graph per step

`velocitron play walk` renders a path: the touched subnet with its
starting marking, then one section per step with the marking before and
after side by side in one Graphviz graph (two clusters, `newrank=true`, a
`rank=same` group per node pair), the checks, and the prose. One graph
renders the same in Graphviz, Kroki and the Obsidian plugin; two fences in a
Markdown table do not. Graphs go through the render model (ADR 0024), so the
net's decorations, fusion copies and `beside` carry over. The render model
gains one input, per-token row marks (consumed, produced, read, replaced,
injected), and decorations gain a `failure` style that only a walkthrough
sets. `--format json` emits the same content for the Obsidian plugin.

## Consequences

- A net change that breaks a play fails `velocitron play check` with
  the line of the broken step and the values of the failing gate.
- Nets that change a token's color at most steps need many `->` clauses.
  That is the honest cost of handlerless nets; `data cel` in the net removes
  it where the net can state the output.
- `correlate` and `data cel` expressions that name a place
  (`binding.pending[0]`) do not survive a merge, because the merge renames
  places (`lifecycle.pending`). Plays across composed nets surface this;
  it is a composition issue, not a play rule.
  (Resolved by ADR 0032: the merge records `bindingNames`, so these
  expressions keep their local names.)
- The checker is Python only. TypeScript parity is deferred; the conformance
  traces in `spec/conformance/play/` are its target.
- Deferred: firings the engine chooses, recording a journal into a
  play, checking with real handlers, and `advance until` a timer's
  maturity.
