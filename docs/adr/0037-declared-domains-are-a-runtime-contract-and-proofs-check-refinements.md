# Declared domains are a runtime contract; prove checks compositions and refinements

**Status:** Accepted.

Stage 1 of `velocitron prove` (ADR 0036) derives a finite domain for each
token field from the net's CEL. A field compared with literals gets the
literals plus `⟨other⟩`, which stands for every string the CEL does not
name. That is the honest default: nothing in the net says that
`shelf.note` is only ever `"shelved"` or `"missing"`. So every choice on such a
field has a gap at `⟨other⟩`, and the checkout lifecycle reports four of them.
The author knows the value set; the net had no place to say it. A domains
file could say it, but it lives beside the net, and nothing checks that the
running system keeps to it.

The same is true of the final places and the invariants an author has in
mind ("one loan at a time per home branch": the shelf slot is that lock), and stage 1 could
not prove a composition at all: `velocitron prove` rejected a `.petrinet`
reference, and it had no answer to "is the refining net a correct inside for
the transition it replaces?" (ADR 0034).

## Decision 1: `domain` declares a closed value set, and the engine enforces it

A net may declare `domain shelf.note "shelved" "missing"` (JSON:
`"domains": {"shelf.note": ["shelved", "missing"]}`). The key is a color and a
dotted field path; the values are strings, numbers or booleans. A token of
that color must hold one of the values at that path. The engine checks this
at the two points where tokens enter a marking from outside the net's own
structure:

- **deposit**: a token that breaks a domain is a deposit-contract violation
  (D3), handled by the engine's `deposit_violation` mode, with the firing
  rolled back like any other violation;
- **injection**: `inject_token` / `inject` rejects it (`ValueError` in
  Python, `TokenInjectionError` in TypeScript), as it rejects a color the
  place does not accept.

A missing field breaks the domain: the fact says the field holds one of the
values. Values compare as JSON values: `1` equals `1.0`, `true` never equals
`1`. Both implementations word the violation the same way; a test runs the
same tokens through both.

ADR 0001 says the net is pure coordination: it routes and gates and never
computes. A domain does not compute, route or gate. It does not change which
transitions are enabled, which binding is chosen, or what a handler
receives. It is a type fact about a color, like `accepts`, and the engine
already enforces `accepts` at exactly these two points. A token outside the
domain is a typing error at the boundary, not a different path through the
net.

**Considered options:**

- *Proof-only, with a lint or play check.* Rejected. A proof that
  assumes `note` is `"shelved"` or `"missing"` is a proof about a different net
  when a handler can return `"maybe"`. Today such a token arrives at the
  choice place, no transition takes it, and the hold waits forever with
  no error: exactly the gap the prover reports. Rejecting it at deposit
  turns a silent stall into a recorded violation at the handler that caused
  it, and makes the proof hold for the running system. A lint cannot see
  handler output, and a play only checks the paths someone wrote.
- *Make a predicate false for a value outside the domain.* Rejected: the
  token would still sit in the place, and bad data would look like a wait.
- *Check the initial marking too.* Not done: the initial marking is a
  default a harness may replace, and the engine does not check it against
  `accepts` either.

A composition keeps every constituent's domains. Two constituents that give
one field different value sets are an error at the merge, because the merged
net cannot keep both.

## Decision 2: derive, then override

The prover uses a declared domain in place of the derived one, with no
`⟨other⟩`; the report marks it `"source": "declared"`. A domains file still
wins over the net (`"source": "override"`), so an author can try a value set
before writing it into the net. A declared field the CEL never reads is
still set on every token the prover builds, or the engine would reject the
token.

## Decision 3: `final` and `invariant` are claims that only the prover reads

A net may name its final places and declare place invariants:

```text
final (loaned), (recalled), (gave_up), (withdrawn)
invariant "lock" (shelf_slot) + (waiting) + (loan_ended) = 1
invariant 2 * (requested) + (done)
```

They lower to a top-level `proofs` member,
`{"final": [...], "invariants": [{"name", "weights", "constant"}]}`, which the
engine ignores, like `capacityPerColorKey` (ADR 0019). `final` replaces the
derived final places, unless the domains file names them. A declared
invariant is proved when no firing changes the weighted sum and the sum
equals the constant once the environment has made the arrivals its model
allows (one token per open place, the start token, the clock token).
`shelf_slot` is open: the environment puts the one lock token there,
so the lock invariant is `= 1`, not `= 0`. Without `= N`, only the first
half is checked.

`final` takes a comma between places, unlike `show`. A bare place is a
statement of its own (`(done)` declares a place), so `final (a) (b)` followed
by a line `(c)` would silently make `(c)` final.

A composition qualifies the constituents' claims: invariant weights name the
merged places (a fused place sums its members' weights) and an invariant's
name gets the alias (`lifecycle.lock`). A final place stays final only while
no arc of the composition reads or takes from it: the partner-loan net's
`(loan_ended)` is final for the loan, not for the hold.

**Considered options:**

- *The reserved `petrinet.dsl/v1` payload.* Rejected: it holds presentation
  (ADR 0025) and a composition merge drops it, so the claims would vanish
  from exactly the nets that most need them.
- *Ordinary annotations.* Rejected: they are freeform and unchecked, so a
  typo in a place name would prove nothing and say nothing.

## Decision 4: prove loads compositions and keeps the wired places closed

`velocitron prove comp.petrinet` loads `.petrinet` and `.json` references,
applies the refinements, and proves the merged net. The merge marks every
fused place `fusion: true` for the renderer, and the stage-1 role rules made
every fusion place open. A wired place is not open: its producers are inside
the merged net. The prover takes the set of fused places from the wires and
never opens them. A choice of a composition names its constituent, and the
report lists the constituent files.

## Decision 5: a refinement is checked as a sound block

For each `refine X.[t] by Y`, the prover proves facts about `Y` alone, as a
workflow net: the start place is the input port wired from the place that
`t` consumes from, and the final places are the output ports wired into the
place that `t` produces into. Then:

- every token that enters leads to exactly one token leaving through those
  ports, on every path (option to complete, and a check that one move never
  puts two tokens there);
- nothing of the instance stays in `Y` when it leaves (proper completion);
- every transition of `Y` can fire (no dead transitions).

Other open places of `Y` (a patron pin, a shelf key) are its
environment, as in ADR 0036, and its other output ports are side outputs.
The fact is `refinement checkout.[borrow] by loan`; a counterexample is
a `.play` file that plays against `Y`'s own file. A refined transition
that takes more than one token, or produces into more than one place, makes
the fact `unknown`: "exactly one token out" has no single meaning there.

The check relies on a result about refinement. Van der Aalst (2000,
"Workflow verification: finding control-flow errors using Petri-net-based
techniques") shows that replacing a transition of a sound workflow net by a
sound and safe workflow net gives a sound workflow net. Van Hee, Sidorova and
Voorhoeve (2003, "Soundness and separability of workflow nets in the
stepwise refinement approach") show that generalised soundness (sound for
any number of tokens in the start place) is kept by refinement without the
safeness condition. So a sound `X` and a refinement proved here give a sound
composition when:

- the outer net is sound with `t` as one step (its own soundness fact);
- `t` is never enabled twice at once in the outer net, or else `Y` is sound
  for several tokens at once, which this check does not prove (it follows one
  token, like ADR 0036);
- what `Y` gives back stays inside what `t` could give: an abstract `t` is a
  handler, so the outer proof already tried every domain value, and the
  engine keeps `Y`'s output inside the declared domains;
- `Y`'s environment behaves as its model says: a resource `Y` takes and never
  returns, or a fact that never arrives, is outside this check.

The prover does not combine the facts into a theorem; it reports each one,
and the conditions are listed in `spec/proofs.md`.

**Considered options:**

- *Compare the merged net with the abstract net (a simulation or
  bisimulation check).* Rejected for now: it needs a second state space and a
  notion of observable moves, and the block view answers the question
  authors ask ("can the inside get stuck or leave something behind?") with
  the explorer that exists.

## Consequences

- ADR 0036's "the engine, grammar, IR schema and composition are unchanged"
  no longer holds: the net schema gains `domains` and `proofs`, the language
  gains `domain`, `final` and `invariant` (and the `=` token), the IR gains
  `domain.values`, `proof.final` and `proof.invariant`, and the merge carries
  both members, in Python and TypeScript.
- A handler that returns a value outside a declared domain now fails its
  firing. That is the point, but a net that declares a domain must list
  every value its handlers return.
- `domain`, `final` and `invariant` are keywords, still usable as names.
- The prove report gains the `refinement` fact, `details.constituent` on a
  composition's choices, and a top-level `composition`; the version stays 1.
