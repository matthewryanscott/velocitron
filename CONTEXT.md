# Velocitron

Velocitron is a public-alpha toolkit for authoring, validating, visualizing, simulating, and running typed colored Petri nets across Python and TypeScript. Its portable surfaces are the `.petrinet` authoring language and a shared JSON representation. Matthew R. Scott is the sole author and copyright holder. Henrique Bastos is acknowledged for collaboration toward an interoperable Petri-net specification. The current contracts live in `packages/spec/`, with design rationale and history in `docs/adr/`. The contribution-IR wire-shape loader lives in `packages/ir/`. The `.petrinet` grammar and its syntax parser live in `packages/grammar/`. The CEL compile/eval adapter lives in `packages/cel/`. The `.petrinet` lowerer, from source text to contribution IR, lives in `packages/dsl/`. The file-free composition merge, over already-parsed nets, lives in `packages/merge/`. The firing engine lives in `packages/engine/`. Net analysis (prove, kept records, and lint) lives in `packages/analysis/`. Produced-marking properties live in `packages/properties/`. Enablement text lives in `packages/explain/`. Structural equivalence lives in `packages/equiv/`. Net codegen (one Python base class per net, and the registration sha256) lives in `packages/codegen/`. The registration base `VelocitronNet` lives in `packages/netbase/`. Tape replay (`ReplayCursor`, `ReplayBase`, `replay_run`) lives in `packages/replay/`. The console commands live in `packages/cli/`. The authoring skill lives at `skills/velocitron/` in this repository; `packages/skill` exposes that tree to the CLI. The net render library lives in `packages/viz/`.

## Language

### Net structure

**Net**:
A declarative colored Petri net: places, transitions, arcs, and a marking. The coordination/control structure, separate from behavior.
_Avoid_: workflow, state machine, graph, DAG

**Place**:
A condition or buffer that holds tokens and declares which token types it accepts.
_Avoid_: node, state, queue

**Transition**:
An event with input arcs (consume) and output arcs (produce), an optional behavior binding (`handler` ref), and an optional guard. A transition without a behavior binding is valid coordination structure; no same-name or no-op handler is implied.
_Avoid_: step, action, task, node

**Source transition**:
A declared transition with no input arcs (typically produce-only). Structurally enabled with the empty binding — it consumes nothing, so it is a firing candidate against any marking. Execution still requires an explicit behavior binding at the Engine/Runtime boundary. Distinct from an undeclared transition name, which is an error, never a firing (firing-semantics D10).
_Avoid_: generator, spawner, entry node, root

**Timed transition**:
A transition carrying a `timer` declaration (`{clock, cel, bind?}`): enabled only when the temporal CEL condition holds for the candidate binding, evaluated against the clock place's token plus explicitly bound input tokens. The deadline lives in token data; the engine holds no timer state; time advances only by token injection.
_Avoid_: delayed transition, scheduled transition, timeout node, timer transition

**Clock place**:
The place a `timer` names as its time reference; its first token (conventionally a singleton `tick`, advanced by replacement through the token-injection seam) is exposed to the timer's CEL as the reserved variable `clock`. An empty clock place means the timed transition is not enabled.
_Avoid_: timer place, time node, scheduler place

**Arc**:
A directed edge between a place and a transition. Input arcs carry consume patterns; output arcs carry produce templates.
_Avoid_: edge, link, connection

**Token**:
A typed JSON value flowing through the net. Has a `type` (string) and `data` (object). The "color" is the type.
_Avoid_: message, event, payload, item

**Marking**:
The distribution of tokens across places at a point in time. The net's state.
_Avoid_: state, snapshot, configuration

**Initial marking**:
The optional authored marking a Net declares as its default token distribution before any firing. It is static net data, distinct from a Runtime Marking.

**Named marking**:
An authored, named alternative token distribution on a Project Document. A consumer selects it explicitly; selection does not mutate or redefine the Net's initial marking.

**Inline marking**:
A marking supplied directly by a consumer rather than authored in the source document. It is an inspection or invocation input, not a mutation of the Net.

**Color**:
The type of a token. Distinguishes token kinds so places, arcs, and guards can filter by type.
_Avoid_: tag, label, category

**Generic token**:
A token whose color is the ordinary string `token`, used by convention for classical/uncolored nets. It is semantically an ordinary color — never a wildcard, inferred type, or untyped core value — but presentation layers omit the generic color label where no distinction would be conveyed.
_Avoid_: wildcard token, untyped token, any token

**Fusion place**:
A place tagged `fusion=True` that is a single logical place depicted by the renderer as a local dashed instance at each transition that connects to it (one place, many local copies). Two neighbor transitions of one choice that both use a `beside` fusion place with no side share one copy, drawn between them. Used for shared/environmental places like `git_tree_diff` so the rendered graph reads as per-transition islands rather than a single global hub.
_Avoid_: hub place, shared node, global place

**Conflict**:
The Petri-net structural condition where two or more transitions are simultaneously enabled over a shared place and compete for the same token — at most one can fire and consume it. Velocitron's default first-found firing policy (ADR 0005) resolves conflict by net declaration order, making selection deterministic and replayable rather than random.
_Avoid_: race, contention, collision, tie

### Schema representation

**ConsumePattern**:
The per-arc consume contract: `{type, predicate, mode, correlate?}`, where `type` is the token type to match (must be one of the source place's `accepts`), `predicate` is an optional arc-level filter, `mode` is `"consume"` (the default — requires a matching token and removes it on fire), `"inhibit"` (a zero-test requiring the absence of a matching token; consumes nothing), or `"read"` (test-without-consume — requires a matching token and binds it, like consume, but removes nothing on fire; ADR 0012), and `correlate` adds a test between tokens: on an inhibit arc it upgrades the zero-test to a **correlated inhibit**, on a consume or read arc it makes a **correlated arc (join)** (both below; ADR 0017, ADR 0030). Separates *which* token type, *which* tokens of that type (predicate), and presence-vs-absence-vs-read (mode).
_Avoid_: input contract, consume spec, arc input

**Correlated inhibit (anti-join)**:
An inhibit arc carrying a `correlate` CEL inscription, making its zero-test per-binding: the transition is enabled under a candidate binding only if no token in the inhibit place — of the arc's type, passing its predicate — also correlates with that binding (`correlate` sees `token`, the candidate's data, and `binding`, the bound tokens' data keyed by place). The classic anti-join: "no mod_flag for THIS account", "no parent with the SAME copy_id". Without `correlate` an inhibit arc stays a whole-place zero-test. (ADR 0017.)
_Avoid_: keyed inhibitor, negative join, binding predicate, conditional inhibit

**Correlated arc (join)**:
A consume or read arc carrying a `correlate` CEL inscription: under a candidate binding, every token the arc binds must make `correlate` exactly true, with `token` set to that token's data and `binding` set to the whole candidate binding's data keyed by place (this arc's own tokens included). It states a join between tokens on different arcs — "the settings token for THIS order's account", "the note for THIS hold's title" — that a single-token `predicate` cannot, since a predicate sees only its own token's fields as bare names. An eval error or non-boolean rejects the binding. (ADR 0030.)
_Avoid_: cross-token predicate, join guard, binding predicate

**Binding names**:
A transition's optional `bindingNames` map, key → place, that sets the keys of the `binding` its CEL sees (`correlate`, produce `cel`). Without it, `binding` is keyed by place name. The composition merge writes it with each constituent's local place names, so `binding.inbox` keeps its meaning after `inbox` becomes `shipping.inbox` or a fused place; handlers still see place-keyed `inputTokens`. Merge output, written in `.petrinet` as `[t] bind key (place)` facts so a merged net round-trips. (ADR 0032, ADR 0043.)
_Avoid_: alias map, rename map, CEL scope, local names

**ProduceTemplate**:
The per-arc produce contract: `{type, destination, data?, cel?}`. A routing contract, not a token factory: it declares the allowed `{type, place}` a bound handler may deposit against; the transition handler supplies the actual output tokens and the engine deposits them against the template. The optional literal `data` lets a bound passthrough or routing handler emit a fixed token when it returns no token for that destination; the optional `cel` (mutually exclusive with `data`, ADR 0023) is the **computed fallback** — an inline CEL expression over `binding` (the bound tokens' data keyed by place, as `correlate` sees it) whose object result becomes the emitted token's data. Neither fallback gives a handlerless transition structural firing behavior.
_Avoid_: output contract, produce spec, arc output, output expression, produce cel template (say computed fallback)

**Predicate (discriminated)**:
The `predicate` on a consume arc is a discriminated object: either `{cel}` (an inline Common Expression Language expression, `cel: "<expr>"`, evaluated against the candidate token's data) or `{handler}` (a named pure predicate handler ref, `handler: "<ref>"`, resolved by the registry) — mutually exclusive, never both. An absent predicate matches any token of the declared `type`. Predicates only; no data transformation. (A companion to **Predicate** under Behavior; that entry remains in force.)
_Avoid_: filter, condition, matcher, expression

**Arc-centric representation**:
Arcs are a flat, top-level list with explicit `from`/`to` endpoints, not inputs/outputs nested under transitions; direction determines consume vs produce. This `arc-centric` form treats every edge uniformly and unifies `Arc` with `Wire` (a cross-net arc, defined in `spec/composition.md`), so the same shape carries both intra-net and inter-net connections.
_Avoid_: nested arcs, transition-scoped arcs, port-list form

**Port facet**:
A `port` is a facet on a place — `port: {direction: "input"|"output", type}` — not a separate top-level kind. A place carrying the `port` facet is a boundary place (the composition interface); declaring it keeps the net a single place set, and composition wires these port-places together (see **Port** under Composition). A port's `type` must be one of its place's `accepts`.
_Avoid_: port node, port kind, endpoint type

### Behavior

**Handler**:
External behavior bound to a name and resolved by the runtime's handler registry. Transition handlers do work and return tokens; guard handlers return booleans (may be impure); predicate handlers return booleans (pure).
_Avoid_: function, callback, service, worker

**Handler ref**:
A named string in the net (e.g., `"agent.review_pr"`) that the runtime resolves to a registered handler. The net says *which* handler; the registry says *what* it does.
_Avoid_: function pointer, callback id, symbol

**Behavior binding**:
The optional association between a Transition and a transition-handler ref. In core JSON the `handler` key is absent when no behavior is bound; in the parsed model `Transition.handler` is `str | None`, defaulting to `None`. An empty string or `null` is never a binding, and absence never implies a same-name or no-op handler. Handlerless transitions remain valid for parsing, composition, and visualization. For execution, `Engine.fire` returns `NotEnabled` first when structural enablement fails; firing an enabled handlerless transition records `HandlerNotFound`. `Runtime` rejects a handlerless net at construction.
_Avoid_: default handler, implicit handler, structural handler

**Guard**:
A transition-level condition, referenced by a named handler. Sees the full input binding across all input arcs. May be impure (may consult external state).
_Avoid_: condition, rule, gate, check

**Predicate**:
An arc-level condition that filters which tokens are consumed from a place. Either an inline CEL expression or a named pure predicate handler. Predicates only — no data transformation.
_Avoid_: filter, condition, expression, matcher

**Firing policy**:
A pluggable handler that decides which enabled transition(s) to fire. Two built-ins: first-found (the default — nondeterministic-in-principle, deterministic list order in practice, replayable) and priority (opt-in — highest declared Transition.priority wins, ties fall back to declaration order). Custom policies can be registered without changing the core.
_Avoid_: scheduler, dispatcher, selector, router

### Engine runtime

**Enablement**:
A transition is enabled when every consume arc can be satisfied (a matching token is present for each), every inhibit arc is satisfied (no matching token is present), and its guard (if any) returns true. Enablement detection is the engine's first phase; only enabled transitions are candidates for firing.
_Avoid_: activation, readiness, eligibility

**Binding**:
The concrete set of tokens a transition will consume when it fires — one token per consume arc, each matching that arc's declared type and predicate. In prose the spec calls this ==🟡the tokens a firing used==; the books' word *binding* is an assignment of values to variables (G&V p. 36), a different object. The engine selects a binding deterministically (lexicographic by insertion order) so firings are replayable.
_Avoid_: match, selection, token set

**Deposit**:
The engine placing a fired transition's output tokens into their destination places, routed through the transition's produce templates. A deposit violation is a programmer-error signal: the handler returned tokens to a place with no matching produce template, or with the wrong token type, or a token outside a Declared domain.
_Avoid_: emit, output, write, place

**Selection loop**:
The engine's repeated cycle in `advance`: detect enabled transitions, ask the firing policy which (if any) to fire, fire it, and repeat — until no transition is enabled or a step cap is reached.
_Avoid_: run loop, main loop, scheduler loop

**Atomic rollback**:
On a firing failure the input marking is untouched by construction — the engine consumes from an immutable, persistent marking, so a failed fire leaves state exactly as it was, with no partial mutation to undo.
_Avoid_: transaction, revert, undo step

**Failure budget**:
An opt-in, per-advance cap on a transition's consecutive failed firings. A transition that fails its budget is exhausted — no longer selectable by the firing policy — until any completed firing resets the counts (the marking changed, so its inputs may differ). Prevents a persistently failing transition from spinning the selection loop or starving later-declared transitions; deterministic (counted from the recorded attempt records, never wall-clock), so replay holds. Off by default.
_Avoid_: retry limit, backoff, circuit breaker, rate limit

**Strict advance**:
An opt-in `advance(..., strict=True)` (TypeScript `run(..., {strict: true})`) that raises `Conflict` instead of letting the firing policy pick when two or more transitions contend (under the priority policy, those at the top priority), and `FailedAttempt` instead of retrying a failed attempt; either carries the `marking` it stopped at. For a net with proved choice coverage run from a projected marking. `fire(..., strict=True)` raises `FailedAttempt` on its one failed attempt the same way. (ADR 0063.)
_Avoid_: run to rest, deterministic mode, checked run

**Firing record**:
The durable record the engine emits per firing attempt: the transition id, input/output tokens, status (`completed` or `failed`), error, metadata, and timestamps. The engine fills every field except `sequence`, which the journal assigns.
_Avoid_: log entry, audit record, event

**Injection (environment-arrival seam)**:
The one sanctioned way a token from outside the net — a file arrival, an environment observation, a clock tick or deadline — enters a running net between firings. A consumer-driven marking event, not a firing: validated against the receiving place, journaled in the same sequence stream as firings so replay is deterministic across injected tokens. Originated as the clock/timer seam (ADR 0013, as amended).
_Avoid_: push, insert, external write, marking mutation

### Composition

**Port**:
A named boundary place on a net, declared via a `port` facet (`{direction: "input"|"output", type}`) rather than a separate top-level kind — see **Port facet** under Schema representation. A port carries a declared token type and marks the composition interface; wires join an output port of one net to an input port of another.
_Avoid_: endpoint, interface, channel, socket

**Wire**:
A unidirectional cross-net arc connecting an output port to an input port. A special form of an arc formed by joining two nets. Composition = merging net schemas and adding wires; the composed system is a single larger net.
_Avoid_: connection, link, bridge, pipe

**Share**:
A composition fact (`share outcome.(lock) ~ gate.(lock)`) that fuses places of several constituents into one place with no direction. The places need not be ports and must accept the same colors. Used for a record or lock several nets read, take or give back, and for a final place more than one net ends in. A shared place keeps its members' proof role: a member annotated `fusion` stays supplied by the environment, where a wired place is closed. (ADR 0040.)
_Avoid_: bidirectional wire, two-way wire, link

**Nested composition**:
A composition used as one constituent of another (`use "hold-lifecycle.petrinet" as lifecycle`). It is flattened into the outer composition: its nets become `lifecycle.shelf`, its wires, shares and refinements carry over, and a place inside it is named by its dotted path (`lifecycle.(shelf.lending)`, merged `lifecycle.shelf.lending`). (ADR 0041.)
_Avoid_: sub-composition, include, import

**Refinement**:
A composition fact (`refine lifecycle.[attempt] by attempt`) that replaces one constituent's transition with another constituent, the refining net, during the merge. The merge removes the transition and its arcs; the author's wires join each place it took from to an input port of the refining net, and each place it gave to from an output port, with the same color, and the merge checks that fit. The standalone net keeps its abstract transition. (ADR 0034.)
_Avoid_: expansion, substitution, override, inlining

**Overview diagram**:
The business-level drawing of a composition (`velocitron-viz --overview`): one box per constituent net, named by its description, with its wired places, its ends (a place of the case no net takes from) and its records between the boxes. A record is a shared place, or a Lived place in a `record` column (one the outside world keeps). It draws no transition. (`spec/composition.md` § Overview diagram.)
_Avoid_: architecture diagram, component diagram, ports-only view (that is the wiring view)

**Chip**:
A reusable subnet with input/output ports. A composable component, analogous to a chip on a mainboard.
_Avoid_: module, component, subnet, fragment

### Artifacts

**Pattern**:
A documented net structure solving a recurring coordination problem. The "cookie cutter" artifact: a doc layer (problem, structure, properties), a JSON schema layer (the net definition), and language-specific code layer.
_Avoid_: template, recipe, example, snippet

**Firing journal**:
A durable, deterministic record of all firings. Enables replay: same net + same inputs + same handler results = same recorded attempt-record stream. Its numbered stream is an occurrence sequence of the net together with its environment (the **trajectory**, since injections are the environment's steps, not firings).
_Avoid_: log, history, audit trail, event log

**Side-effect triplet**:
A `requested → deliver → completed` place structure modeling an external side effect's lifecycle. The handler performs the actual call; the net models the lifecycle, making the side effect observable, durable, retryable, and inspectable.
_Avoid_: side effect, effect, external call, integration

**Human attention queue**:
A place holding tokens that need human review. A transition with a human-facing handler consumes from it. The handler returns `completed` with a resolution token (accept, correct, or reject).
_Avoid_: inbox, task list, review queue, pending list

**Sink transition**:
A transition with one or more consume arcs and zero produce arcs — it consumes tokens and produces nothing (e.g. a `clear_flag` transition discarding a flag token; a terminal discard). A legitimate construct, which is why it is a lint finding and never a validation error. An intended one is marked with the transition annotation `"end": true` (`[t] annotation end true`), which silences the finding.
_Avoid_: dead end, terminal node, drain, black hole

**Lint rule**:
An opt-in, advisory static check over a parsed net that flags a legitimate-but-usually-buggy shape (`consume-without-produce`, the sink shape a dropped produce arc leaves behind; `predicate-names-color-or-place`, a `predicate cel` that selects a field of a color or place name, which should be a bare field or a `correlate`; `correlate-free-name`, a `correlate cel` that uses a name other than `token` and `binding`; `read-only-producer`, a transition whose inputs are all read or inhibit arcs and that produces, so it can fire again and again and add a token each time, unless an inhibit arc on its own output makes it fire once). A finding carries a stable rule id, the flagged transition's name, and a human message; declining to lint changes nothing, and `velocitron validate` prints findings as warnings. An intentional occurrence is acknowledged per-transition (or, for an arc rule, per-arc) via an `annotations.lint.suppress` list naming the rule id (the ADR 0011 carve-out; ADR 0016, ADR 0030).
_Avoid_: validation error, parse error, schema check, warning-as-error

**Projection adapter**:
A consumer-owned component that derives a `Marking` (or an incremental batch of tokens) from external resource state — filesystem, database, queue, API, clock, or an in-memory fixture — and hands the result to the engine, which runs *after* and *outside* projection. Projection is not an engine primitive. The protocol shape is *enumerate correlation keys → probe evidence → deposit observation tokens*, with three normative rules — never de-duplicate on the color key (duplicates are a signal to flag, not noise to collapse), union mirror mounts, and flag duplicates so the net can route them. A projection is a pure function of the probed evidence; probing is the impure edge. See `spec/projection-adapter.md`.
_Avoid_: importer, loader, sync, scanner, marking builder

### Plays

**Play**:
An authored, ordered list of play statements played against one Net (or one composition) from a chosen marking, with Markdown prose attached to statements. A design and documentation artifact: it states what should happen, and the checker proves each statement against the current net. Stored as a `.play` file. (ADR 0031.)
_Avoid_: test case, script, walkthrough (that is the rendered document), firing sequence (that is one path's firings only), trace (that is a Mazurkiewicz trace — see Occurrence sequence)

**Statement**:
One line a play runs in order: a firing (`fire`), an Injection (`inject`, `update`, or `advance`, which updates the clock place), or an expectation (`expect`), which changes nothing. Only a statement that moves tokens is a step; every statement has a marking before and after it.
_Avoid_: action, event, command, line

**Path**:
One sequence of play statements. The steps before any `path` line form the trunk; a branch path names a labeled step of the trunk or an earlier path, and replays every step up to and including it before its own. The shared steps are played again, never copied.
_Avoid_: branch (as a noun), fork, variant, alternative

**Symbolic firing**:
Playing a firing step through `Engine.reserve` and `Engine.settle`, with the output data the play supplies in place of a handler. Enablement, binding, read, inhibit, correlate, timer, guard and deposit rules are the engine's; only the source of output data changes. A named guard with no registered handler is not enabled.
_Avoid_: simulation, dry run, mock firing, fake handler

**Carry rule**:
The symbolic-firing default for a produce template with no `data` or `data cel` and no `->` clause in the step: when the binding's consume-mode tokens hold exactly one token of the template's color, its data is copied. Read tokens never carry (they are the environment). When the rule does not apply, the step fails and names the template; nothing is guessed. One home: `velocitron/outputs.py` (`produce_templates`, `net_fills`, `carry_rule`, `symbolic_outputs`) — the play checker and the engine's `advance(outputs=...)` read the same judgement, `carry_rule`; do not copy it.
_Avoid_: pass-through, identity handler, default output, inference

**Symbolic advance**:
Fire a handlerless net's maturing transitions through `advance(..., outputs=provider)`: the provider (`velocitron/outputs.py`'s `symbolic_outputs` is the default) fills each firing's outputs from a live reservation — net-filled templates pass through to the deposit, the rest carry — or returns `None` to skip the transition, which stays enabled. Returns an `AdvanceOutcome`: final marking plus per firing `(record, marking_after)`; records carry `maturedBy` like their journal copies.
_Avoid_: simulation, dry run, mock advance, fake handler

**Walkthrough**:
The document rendered from one checked Path: the touched subnet with its starting marking, then one section per marking-changing step with the marking before and after side by side in one graph, the checks that follow it, and its prose.
_Avoid_: play (the source), report (the check output), storyboard, animation

**Occurrence sequence** (was _Play trace_):
The checker's result for one Path: the starting marking and, per step, the marking before and after, the engine records, the tokens a firing used and the consumed, read, produced or replaced tokens, and the checks. The first failing step ends the sequence with a structured diagnostic. The books' word *trace* names a Mazurkiewicz trace (G&V p. 232), a different object; the Python class `PlayTrace` keeps its name.
_Avoid_: journal (an occurrence sequence holds journal records and more), log, result, trace (that is a Mazurkiewicz trace)

**Actor**:
Who does a step, in business words: a transition's `actor` fact (`[flip] actor Operator`), else its net's default (`net actor Platform`); for an injection, the owner of the place (`(switch) actor Operator`). A `person`, a `system` or a `record` (a column a Lived place is drawn on), declared in that order for the lifelines. Stored as the annotation key `actor` (and the net's `actors` list); the engine ignores it, the merge carries it. (ADR 0038.)
_Avoid_: role, participant (that is the PlantUML word), lane, owner (say the place's owner only for injections)

**Hand-off**:
A step that consumes or reads a token another actor produced. The producer is the step that made the token (or the owner of an injected place); tokens of the starting marking and clock ticks have none. Drawn as an arrow in a Sequence diagram, labeled with what was handed over (the producer's step title): a consumed token's hand-off is a solid arrow that starts an activation; a read one is a dashed arrow. A token in a Lived place is never a hand-off. (ADR 0038, ADR 0039.)
_Avoid_: message, call, signal

**Sequence diagram**:
The projection of one checked Path onto its Actors: a lifeline per actor and per Lived place column, an arrow per Hand-off and per write into or read from a column, an actor's own titled steps as notes, ticks as delays, `###` headings as groups and other headings as dividers. A reduced view of the occurrence sequence, not a separate model; PlantUML is its rendering. Asked for with `show sequence [only]`. (ADR 0038, ADR 0039.)
_Avoid_: swimlane, storyboard, interaction diagram

**Lived place**:
A place that a Sequence diagram draws as a column of its own, because it is a record that stays rather than a hand-off: `(switch) lives in "Branch home"`, or computed from the token, `(delivered) lives in cel "token.destination"`. A write into it is an arrow into the column; a read is a dashed arrow out of it, labeled with the value read (`reads as cel "…"`). (ADR 0039.)
_Avoid_: lane, store, database (that is only how a `record` column is drawn)

### Proofs

**Proof**:
The result `velocitron prove` gives for one fact about every marking a net can reach: proved, refuted (with a witness marking or a shortest counterexample, which it can write as a `.play`) or unknown (with the reason: a state cap, an unsupported construct, a CEL shape the domains do not cover). Distinct from the property pass, which checks markings a system produced (ADR 0019, ADR 0036).
_Avoid_: verification, check (that is the property pass or a play), test

**Prover**:
The part of Velocitron that gives Proofs: `velocitron prove`, which checks choice coverage, place invariants, soundness and the refinement check, the last two by exploring every marking the net can reach, up to the State cap. The Python explorer in `packages/analysis` is the reference that any faster way to explore is compared with.
_Avoid_: proofing tools, checker (that is the play checker), verifier

**State cap**:
The most markings one exploration of the Prover may hold (`--max-states`, default 50 000). An exploration that reaches it stops, and the facts it was for (soundness, the refinement check) are unknown, with the cap as the reason; choice coverage and place invariants do not explore and do not depend on it. The word is "state" by long use; what it counts are Markings.
_Avoid_: marking cap, state limit, max states

**Benchmark set**:
The nets, each with its domains file, that the Prover's speed is measured on: the nets under `benchmarks/prover/nets/`, listed in `benchmarks/prover/set.json5`. `tools/prover_bench.py` proves each and prints its markings, edges, wall time, peak memory and each Proof's result; the counts and results are recorded in `benchmarks/prover/numbers/`, and a run that differs from them fails. A net too large to explore whole within minutes runs at a lower State cap and is marked heavy; where `prove --fast` explores it whole within minutes, the set lists it once more, whole and marked fast only, and only `--fast` runs that line.
_Avoid_: test set, fixtures, corpus

**Choice coverage**:
The fact that every token that can sit at a choice place (one color, consumed by two or more transitions) enables exactly one of them, in every context its read, consume and inhibit places and its timers can show. A **gap** enables none; an **overlap** enables several, unless the priority policy picks one (resolved) or a `choice-overlap` suppression waives it.
_Avoid_: exhaustiveness, determinism, decision table

**Intended wait**:
A gap case of a choice that the net means: the token waits for something the outside world does. A transition of the choice declares it with the annotation `wait`, `{"when": CEL over binding, "for": "what it waits for"}`. Choice coverage counts only the cases where the condition is true as waits, and every other gap still refutes; a `choice-gap` suppression waives all of them. (ADR 0057.)
_Avoid_: waived gap, expected gap

**Place invariant**:
A weighted sum of token counts over places that no firing changes: a P-semiflow `y` with `y · C = 0` over the skeleton's incidence matrix (read arcs count nothing, inhibit arcs are ignored, weights count). It holds as a count of tokens of any color; a per-key reading is named but not proved.
_Avoid_: conservation law, marking invariant (that is the property-pass kind over one marking)

**Soundness**:
The fact, for one lifecycle instance under the Environment model, that from every reachable marking it can still complete (option to complete), that a reached final marking leaves no other token of the instance (proper completion), and that every transition can fire (no dead transitions). Van der Aalst's workflow-net soundness, checked by explicit state exploration with the progress assumption.
_Avoid_: correctness, liveness (one part of it), termination

**Environment model**:
What the prover assumes about the world outside one instance: open places (no producer, a fusion place the net reads that a composition did not close, a timer clock, the instance's input port, a Record place; never a Kept record) receive tokens from the Data domains, once each by default; a fact the net only reads may be replaced once, and a Record place any number of times; time jumps forward to a later time slot, or to the time a timer declares it matures at (for a maturity read from a copy of the clock, only while the copy holds a time slot). Moves of the environment are not owed: the net must not depend on the environment changing a fact it already gave, unless that fact is a Record place.
_Avoid_: context, world, stub, mock

**Record place**:
A Lived place whose column is a `record` lifeline (`(branch_home) lives in "Branch home"`): a record the outside world keeps and may change at any time. For the prover it is open however it is produced, wired or shared, and the environment may change it without limit. A transition that only takes and gives Record places is a **record move**, the outside world's move: a loop of record moves is no livelock, and a net that waits for a record to change is waiting, not stuck. (ADR 0047.)
_Avoid_: outside fact, mutable fact, external state

**Waiting record**:
A Record place the prover does not change in a marking, because the net has a move of its own and no transition that reads or writes the record (or a record joined to it by a record move) has its other binding places marked. The change commutes with the net's moves and can still happen once a step can use the record, or the net stops. A record move held back where it was enabled still counts as able to fire. (ADR 0055.)
_Avoid_: idle record, frozen record

**Kept record**:
A record this system keeps itself, there from the start and changed only by the net's own steps: `(condition) kept by "circulation desk" starts as cel "{'isbn': instance.isbn, 'damaged': false}"`. Its place is a **kept place**. The prover starts with it, built against the check's instance token, and the environment never writes it; it is not instance work, so proper completion and final markings ignore it, and it is never a choice. A story starts with it too, from its `instance` token. The opposite of a Record place, which the outside world keeps. (ADR 0051.)
_Avoid_: seed, initial token, global, singleton

**Firing cap**:
A bound from the domains file (`environment.firings`) on how often one transition, by its merged name, may fire on any path the prover explores, so a loop with no fixed end ("redeliver until stopped") is checked for a few turns without changing the net. A state where a cap stopped an enabled transition is cut: not a stop, and not followed further. A refutation stays real; a result that is not refuted lists each cap as an assumption, and no dead transitions turns `unknown` when a cap stopped something. (ADR 0050.)
_Avoid_: loop bound, unrolling, fuel

**Starts**:
How often the prover starts the instance, from the domains file (`environment.starts`, default 1). Each start has the same keys, so a later start meets the history an earlier one left in a Kept record. A marking is finished when it holds one final marking per start at once, counted per place. Every soundness result lists the starts as an assumption, a refutation too. (ADR 0052.)
_Avoid_: repeat arrivals, second instance, replay

**Data domain**:
The finite set of values the prover gives one token field, derived from the net's own CEL (the literals and `⟨other⟩`, booleans, values around numbers, own and other keys for joined fields, ordered and time slots; no `⟨other⟩` for a field the net sets only from literals), taken from a Declared domain, or given in a domains file, which wins. Choice coverage uses every value; Soundness leaves out `⟨other⟩` and other keys unless a test passes a value they stand for (`!=`, or a negated `==` or `in`) or they are asked for.
_Avoid_: type, range, enum, sample

**Declared domain**:
The closed list of values a token field holds, stated in the net: `domain verdict.result "pass" "hold"` (JSON `domains`). It is a runtime contract: the engine rejects a deposit or an injection of a token of that color whose field is missing or holds another value, as it rejects a color the place does not accept. The prover uses it as that field's Data domain, with no `⟨other⟩`. (ADR 0037.)
_Avoid_: enum type, allowed values, validation rule

**Final marking**:
A set of places that must all hold a token before one instance is finished: `final (recalled), (loaned) + (shelved)` declares two. A final marking of one place is a final place. A composition may declare its own (`final lifecycle.(checkout.loaned) + catalog.(shelved)`); they replace its nets' final facts, so a run that follows two things at once finishes when both are done. (ADR 0049.)
_Avoid_: end state, terminal state, goal

**Proof facts**:
Claims in a net that only the prover checks: its final markings (`final (loaned), (withdrawn)`, or `final (loaned) + (shelved)` for a final marking that needs every place marked; ADR 0049) and declared place invariants (`invariant "lock" (free) + (busy) = 1`), stored in the net's `proofs` member. The engine ignores them. A declared invariant's constant counts the tokens the Environment model puts into open places. (ADR 0037.)
_Avoid_: assertions, annotations, properties (that is the property pass)

**Equivalence up to renaming**:
What `velocitron equiv A B` checks: after both sides are merged, a renaming by local names (a merged name without its aliases; a fused place by its members' names) maps every place, transition and arc of one onto the other with the same behavior facts (colors, capacities, environment supply, final places and markings, initial marking, guards, priorities, handlers, timers, arc inscriptions, CEL binding names, domains, declared invariants). Ports are interface, not behavior, and are reported apart. A structural check: it does not compare reachable markings. (ADR 0042.)
_Avoid_: bisimulation, behavioral equivalence, isomorphism (it matches by name)

**Refinement check**:
The Proof that the refining net of a Refinement is a sound block for the transition it replaces: each token entering through the input port wired from the transition's input place leaves as exactly one token through the output ports wired into its output place, on every path; nothing of the instance stays behind; every transition of the refining net can fire. Refining a transition of a sound net by such a block keeps the net sound when the transition is never enabled twice at once (van der Aalst; van Hee, Sidorova and Voorhoeve). (ADR 0037.)
_Avoid_: refinement validation (that is the merge's fit check), equivalence check, bisimulation

### Language tooling

**Workspace Root**:
The client-declared filesystem boundary within which project discovery may search. A workspace root can contain multiple Petri-net projects and loose DSL source files.
_Avoid_: project, repository, source root

**Petri-net Project**:
The manifest-owned collection of project documents beneath one project root. The nearest manifest determines ownership; a workspace root is not itself a Petri-net project.
_Avoid_: workspace, workspace folder, repository

**Project Document**:
One ordered semantic aggregate declared by a Petri-net project. It may be assembled progressively from multiple DSL source files and has an identity independent of its header name.
_Avoid_: file, source, compilation unit

**DSL Source File**:
One physical `.petrinet` file with a canonical source identity. Several DSL source files may contribute facts to one project document.
_Avoid_: document, project, source

**Document Namespace**:
The decoded, renameable header name shared by every DSL source file contributing to one project document. It is a semantic name, not the project document's stable identity.
_Avoid_: document id, project id, source id

**Current Contribution State**:
The facts proved from intact syntax in one exact current document version, possibly partial while the source is damaged. It never borrows facts from an older successful analysis.
_Avoid_: current snapshot, partial tree, latest good state

**Retained Resolved Snapshot**:
The most recent fully resolved semantic snapshot retained after successful project analysis. It may predate the current contribution state and must never be presented as current.
_Avoid_: current state, current snapshot, latest good facts

**Runtime Marking**:
A `Marking` used by an executing lifecycle net. It is distinct from current contribution state, a retained resolved snapshot, and a named marking authored as DSL metadata.
_Avoid_: document state, project snapshot, named marking

**Lifecycle Projection**:
A stable, redacted observation derived only from lifecycle-net markings and static net metadata. It exposes conformance-relevant lifecycle state without exposing full runtime markings or operational metrics.
_Avoid_: runtime snapshot, full marking, metrics view

**View**:
An authored, named presentation layer on a Net: positions for places and transitions, orthogonal route points for handled arcs, and optionally an edge style (`splines`) and a label detail level (`detail`). A View named `default` applies when a render names no view. A position is absolute (`{"x", "y"}`) or **relative** (`{"from", "delta"}`): it lowers verbatim into the reserved payload, with only shape and reference checks at compile time, and is resolved against the other positions of the same View when the View is applied (chains in dependency order; an unpositioned base or a cycle rejects the application). Presentation data only — inert, like all reserved payload contents — never affecting parsing, enablement, binding, or firing. Authored in the `.petrinet` frontend, preserved in the reserved payload (`annotations["petrinet.dsl/v1"]`), and applied when a Net is visualized; not consumed by the parser, engine, or journal. Distinct from a named marking, which authors token placement, not geometry.
_Avoid_: overlay, scene, canvas state, layout hint

**Decoration**:
An authored, inert presentation fact on one place, transition, handled arc, or color: a highlight (with an optional short label), a note, a summary that the `summary` detail level shows in place of an expression, `quiet`, which hides a color's type label on consume and produce arcs, `show`, which names the token fields (dotted paths such as `owner.name`) a renderer shows for a color, or `beside`, which keeps each local copy of a Fusion place next to its transition (with no side, two neighbor transitions of one choice share one copy). Unlike a View, a Decoration belongs to no view and shows in every render. A View that positions nodes places each `beside` copy beside its transition (ADR 0067). A whole-place position is ignored for those copies and still anchors a relative position. Stored in the reserved payload (`annotations["petrinet.dsl/v1"].decorations`); never consumed by the parser, engine, or journal.
_Avoid_: annotation, marker, tag

### External

**CEL**:
Common Expression Language (`google/cel-spec`). A side-effect-free expression language used for arc predicates. Velocitron 0.1.0 evaluates CEL through its Python and TypeScript implementations.
_Avoid_: expression language, DSL, query language
