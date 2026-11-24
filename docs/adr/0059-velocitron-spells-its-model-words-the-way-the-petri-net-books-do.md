# Velocitron spells its model words the way the Petri net books do, and renames three of its own words

**Status:** Accepted (2026-10-22). Answers ADR 0058's deferral ("It uses today's
words for `scenario`, `binding`, and `Engine.run`; a separate ADR will decide
the renames the Petri net books suggest"). Code facts are verified against
the tree. Cited line numbers had drifted; the current lines are given below.

## Why

Ada's steer (F21 point 5): "we want to steer Velocitron development in such a
way that it respects the terminology used by the wider Petrinet community."
The Petri net books have exact, defined words for the things Velocitron
models — transition occurrence, step, occurrence sequence, run, binding, mode —
and Velocitron uses some of those words for different things. A reader who
comes from Reisig, *Understanding Petri Nets* (2013) or Girault and Valk
(eds.), *Petri Nets for Systems Engineering* (2001) — the two books on
Ada's desk, hereafter G&V — will misread our specs where the words differ.
This record decides each place, with the book word, the quote and page, the
current sites, a cost class, and what changes. Where the word is a public
name, it proposed candidates; Ada's picks of 2026-10-22 (bundle 2) are
recorded in the item tables. The renames
themselves are follow-up cards, not this change.

Two books, one vocabulary. Where the books differ we say which word we take
and what the other book calls it.

## Evidence base

The term table and every quote below come from the Petri-net primer's research
`S10 — The most precise words, from Ada's own books`,
which read both books' extracts. Page numbers are the
printed pages; S10 records the PDF offset for each. This record then re-ran
S10's grep ("Velocitron renames to queue" gives the method) over the current
checkout, because S10 read only the definition sites of three specs; its own
unknown-list flags that.

### The site re-grep

Searched the current word list over all nine spec files
(`handler-contract.md`, `net-schema.md`, `petrinet-language.md`,
`scenario-language.md`, `firing-semantics.md`, `composition.md`, `proofs.md`,
`properties.md`, `projection-adapter.md`), `CONTEXT.md`, the Python
implementation (`engine.py`, `journal.py`, `runtime.py`, `scenario/`,
`prove/`, `dsl/`), the TypeScript implementation, the CLI (`dsl/cli.py`),
the README, and `skills/velocitron/`. Patterns: `scenario`, `trace`,
`firing sequence`, `binding`, `run`, `step`, `path`, `tape`, `stream`.

What turned up that S10's item list did not name:

- **`spec/proofs.md:486-514` ("Counterexamples as scenarios")** — the prover
  writes each witness and counterexample as a `.scenario` file; the files are
  named `...gap-1.scenario`, `...attempt-by-attempt-1.scenario`. Item 1's
  rename reaches the prover's output names and `spec/proofs.md`'s wording,
  plus `prove/counterexample.py` and `prove/report.py` (`finding.scenario`).
- **`spec/proofs.md:620-622` and `prove/report.py:115-138`** — the proof
  report's JSON has a `"scenario"` field naming the written counterexample
  file; its value is a file name, so it inherits item 1's rename (or keeps
  its name, item 1's decision).
- **`spec/conformance/scenario/`** — four conformance cases with
  `case.scenario` and `expected.trace.json` files; the directory name and the
  trace-JSON's `"scenario"` key move with items 1 and 2.
- **`context/CONTEXT.md:226-251`** — the glossary entries `Scenario`,
  `Scenario step`, `Scenario trace`, `Walkthrough` state today's words;
  every decided item below edits this glossary (the rename pass updates it
  wholesale).
- **`README.md:56`** — the CLI list says `check` covers `.scenario` files;
  the `scenario` subcommand itself (`validate`/`explain`/`check`/`skill` prose
  in the README predates it, `dsl/cli.py:109`) is an extra public CLI word
  item 1 touches.
- **`skills/velocitron/`** — `SKILL.md` steps 5–6, `kitchen-sink.scenario`,
  `scenario-language.md` (byte-identical copy of the spec) and
  `engine-runtime-primer.md`; the bundled skill is a public doc that repeats
  every renamed word.
- **No new sites for items 3–7**: `handler-contract.md` uses `binding` only
  in the book-safe senses ("behavior binding", "input binding" = the token
  selection passed to handlers — which is item 6's decided wording anyway);
  `net-schema.md`'s `firing sequence` appears at `:28` and `:503` only, both
  already in S10's list; `petrinet-language.md` mentions scenarios only in
  the Actor-facts prose (`:337-338`, `:430`).

## The seven decisions

### 1. `Scenario` — rename (Ada picks the name)

Book word: Reisig's *scenario* is a different thing: "a finite partial
distributed run K of N in which the outset, ◦K, and the end, K◦, represent
the same marking" (Reisig p. 63). His scenario is a partial order that
returns to its start; Velocitron's Scenario is a straight-line authored story
from a chosen marking, no return required.

Current sites: `spec/scenario-language.md:20` (definition), the `.scenario`
file type everywhere, the `scenario` CLI subcommand with `check`/`walk`/
`sequence` (`dsl/cli.py:109-175`), `velocitron/scenario/` module and every
`Scenario*` class, the prover's counterexample files (`spec/proofs.md:486`,
`prove/counterexample.py`), conformance dir `spec/conformance/scenario/`,
ADR 0031 and 0038 and their kin, `CONTEXT.md:226`, `README.md:56`, the
bundled skill. Also every `.scenario` file in the consumer repositories.

**Cost class: public name** — file type, CLI words, Python and TypeScript
names, and the two consumer repositories. This is the most expensive item;
Ada decided it is worth it (Q63 ticked rename).

**What changes:** the file extension, the header keyword, the CLI
subcommand, the package module and class names, the spec and glossary, the
prover's output suffix, and every existing `.scenario` file (a mechanical
`.check`-verified rewrite). The ADR leaves the old word defined once, as an
alias of a past version, in the changelog — not in the spec.

Candidate names for Ada:

| Candidate | Why | What it collides with |
|---|---|---|
| **play** *(Ada's pick, 2026-10-22; was the author's pick)* | It is what the checker literally does — "the checker plays a scenario against a net" (our own prose, `spec/scenario-language.md:6`, 13); a `.play` file is played; the verb/noun pair is uniform, and both books speak of "playing the token game" (G&V p. 58). | "Play" as a noun is casual English, not a book term — no collision in either book. In Velocitron, `velocitron scenario walk` becomes `velocitron play walk`-ish; the verb "play" stays in prose either way, so the noun earns its place. The circulation desk's code has no `play`. |
| script | Plain English for "an authored ordered list of statements"; matches what a reader expects a `.script` to be. | *Script* is undefined in both books — safe there — but in the circulation desk's repository "script" means shell scripts and in Velocitron prose "script" often means a Python file; overload risk. Also loses the story flavor the prose leans on. |
| trial | An attempted check of a story against the net's rules. | Collides with "attempt": item 4 reserves *attempt* for one firing try (journal records), and Reisig p. 10/46 reserve *run*; a "trial" sits confusingly close to both. No book meaning (safe there). Weak story flavor. |
| episode | Continues the "story we check" metaphor; good for named paths inside one file. | No book meaning (safe), but reads as one installment of a longer series — a standalone `.scenario` file would feel subordinate; names for a single Path would stretch ("this episode's episode"). Nothing in the circulation desk's code. |
| course | A course of steps, as in "the course of the run" (plain English the books use informally). | Collides with item 3's candidates: *course* is one of the seed words for the injection-holding stream, and it is also Reisig's informality around "the course of the run" — using it for both an authored story and a run's extension is the confusion this ADR removes. |

### 2. `Scenario trace` and `Path` — rename to *occurrence sequence*

Book word: **occurrence sequence**. G&V's formal term: "the set `Occ(S)` of
occurrence sequences … of all sequences of the form
`m0,t0,m1,t1,m2,t2,…,tn−1,mn`" (G&V pp. 42-43, Valk); introduced with the
markings already in it at p. 34; the coloured extension
`m0,(t0,β0),m1,…` adds the bindings (G&V p. 51). Reisig's same-shape word is
*sequential run*: "a sequence `M0 −t1→ M1 −t2→ …` of steps of N, starting
with the initial marking" and "each sequential run … is a path through the
marking graph" (Reisig p. 46). G&V's *firing sequence* is transitions only
(`abdac`, G&V p. 122, `FS(S)` p. 42) — not what our trace shows, since our
trace holds the marking after every step and lets the reader rewind to one.

Current sites: "Scenario trace" defined at `spec/scenario-language.md:33`,
checker prose `:264-273` ("the failure is part of its trace", "A trace's
steps chain"), `expected.trace.json` conformance fixtures, `ScenarioTrace`
and `trace.scenario` in `scenario/check.py`, `walkthrough.py:116`,
`sequence.py:140`, `CONTEXT.md:250-251`. *Path*: `spec/scenario-language.md:25-
27` (`Path`, `path NAME from @label`, the `path` header word), `Step`'s
`PathDecl` grammar `:95`, CLI `--path`.

**Cost class: spec wording for the two terms; output name for the trace JSON
(`expected.trace.json`) and the checker's class names.**

**What changes:** the spec's terms become "occurrence sequence" for the
checker's result of one path and for a Path itself where the result is
meant; the file's own `path NAME` branch syntax keeps its word (a Path is a
source's division, not the sequence — but wherever the spec means the
sequence of a path, it says "occurrence sequence"). Note both books' words
describe the *sequence*; G&V's *trace* means a Mazurkiewicz trace, a
different object (G&V p. 232), which is the strongest reason to leave
"trace" behind. ADR 0058's Q64 already settled that "trace" stays for the
OpenTelemetry-sense trace record (`TraceJournal`); this decision covers only
the scenario checker's result, which is renamed *occurrence sequence*
alongside the Path it sequences.

### 3. The "firing sequence stream" that holds injections — spec wording only

Book word: **occurrence sequence of the net together with its
environment**. An occurrence sequence (G&V pp. 42-43) lists every step of a
net; the environment is itself modeled (Reisig's cold interface transitions
with no preconditions, pp. 9-11; G&V's source places, p. 155), so the
journal's mixed stream — firings and injections interleaved — is an
occurrence sequence of the larger net (both books require every step to be a
transition of one net; an injection is not a firing of our own net: our
spec says so at `spec/firing-semantics.md:363`, and Reisig makes it a
transition of the environment side, p. 10).

Current sites: `spec/firing-semantics.md:577` ("an **explicit entry**
sharing the firing sequence stream"), the shared-wording in
`engine.py:2483` docstring, journal numbering prose in ADR 0013 and 0018.

**Cost class: spec wording only.** The stream is named by prose, not by an
identifier; no public name changes.

**What changes:** the spec prose calls the mixed journal stream an
"occurrence sequence of the net together with its environment" — one phrase,
defined once in the terms section — and stops calling it "the firing
sequence stream", since (a) G&V p. 42's firing sequence is transitions only
and (b) our own spec says an injection is NOT a firing. The journal
still numbers the entries from one monotonic `sequence`; nothing
mechanical moves.

Candidate names for Ada (for the phrase the spec and prose use; the
`sequence` field name stays):

| Candidate | Why | What it collides with |
|---|---|---|
| **trajectory** *(Ada's pick, 2026-10-22; was the author's pick)* | A run-with-injections is exactly a trajectory in the dynamics sense: a path through markings over time, with external pushes in. Short, vivid, and no book meaning to collide with in either Reisig 2013 (searched: not used) or G&V 2001 (not used as a term). | No collision in either book. In Velocitron it is fresh; in the circulation desk's code "trajectory" is unused. The cost is only that it is not a book word — the phrase "occurrence sequence of the net together with its environment" is the exact book wording, and the spec should give that phrase as the definition, with "trajectory" as the short name in prose. |
| history | Plain English for "everything that happened, in order". | Undefined in both books, but so common a word that it overruns its definition: "history" in distributed-systems prose means a partially ordered run anywhere (Reisig's *distributed run*, p. 49, is the partial-order cousin), and Velocitron's journals are strictly sequential. Overloaded everywhere else too. |
| course | "The course of the run" is how the books say it informally. | Collides with item 1's candidate table (where *course* was also seeded) and with Reisig's informal "course of a run" — the very sentence a reader would look up. Using it for the injection-holding stream and the word also floating through the books' prose invites the mix-up this ADR exists to remove. |
| environment run | Directly states the book reading: a run that includes the environment's steps. | No collision in either book, but "run" is the word Velocitron is vacating from *methods* (item 7), and Reisig reserves *run* for the sequence of a system net alone (pp. 10, 46) — "environment run" risks re-introducing the confusion this ADR removes, in a phrase. |

### 4. `FiringRecord` for a failed attempt — spec wording only

Book word: an **occurrence** — per G&V "The occurrence of a transition
should be understood as a single step" (p. 37, Valk), and by G&V Def. 4.3.2
(p. 50) an occurrence requires the transition enabled for a binding; Reisig
p. 25 the same. A failed attempt consumes nothing, changes no marking
(`spec/firing-semantics.md`, atomic rollback — the attempt "rolls back and
changes no marking", per the card), so by the books it is not an occurrence.

Current sites: `FiringRecord` at `journal.py:31` and
`spec/firing-semantics.md:346-359` (status `completed | failed` on one
record), `spec/firing-semantics.md:5-10` ("a *sequence of firing
attempts*"). The card's citations (`:345-359`) have drifted; the record
shape's current lines are `:346-359` of this checkout.

**Cost class: spec wording only. `FiringRecord` keeps its name** — ADR 0058's
replay and adapter are built on it (Q64 keeps the name).

**What changes:** the spec's prose says "attempt record" for a `FiringRecord`
of either status, and reserves *occurrence* for the event a *completed*
record records; a failed record is "a failed attempt". The books' word
*attempt* is already our field name (`attempt: int`), consistent. No code
moves.

### 5. `Scenario step` covers `expect` and `update` — spec wording only

Book word: *step* is one transition occurrence that moves tokens — Reisig:
"If a marking M enables a transition t, it results in the step `M −t→ M′`"
(p. 25); with a coloured mode, "`M −t,β→ M′`" (p. 26). G&V let a step carry
several concurrent occurrences (p. 12, Valk); the single case is ours.

Current sites: `spec/scenario-language.md:21-24` (the term includes `expect`
and changes-nothing prose), `:97-98` (`Step`, `StepBody` grammar), `Step` in
`scenario/language.py:182-186`.

**Cost class: spec wording only** (Python class name `Step` is private to
the checker; unchanged).

**What changes:** a scenario line is a **statement**; only a statement that
moves tokens (`fire`, and by our extension the environment arrivals
`inject`/`update`/`tick`, which are steps of the net-with-environment per
item 3) is a **step**. `expect` is a statement, never a step — an `expect`
step changes nothing, by our own spec (`:24`), and so is not a step in the
book sense.

### 6. `binding` means tokens per place — spec wording only

Book words: G&V's **binding** is "an assignment of values to variables"
(p. 36, Valk), also called *occurrence mode* (p. 37); Reisig's **mode** is
the same thing: "β : (x1 = u1, …, xn = un) is a mode of t" (p. 25, and p. 13
"occurrence mode … the replacing of x with a concrete value"). Reisig never
uses binding (S10 searched). Velocitron's `binding` is the chosen tokens per
arc keyed by place — a different object.

Current sites: `spec/firing-semantics.md:110` (definition), `:354` (the
record comment `# the binding`), `:156-166` (`bindingNames`), the CEL
variable `binding` and `bindingNames` in `net-schema.md:210-225`,
`handler-contract.md:68-70`, and countless CEL snippets.

**Cost class: spec wording only. The CEL variable `binding` and
`binding_names` keep their names** (Q64: ADR 0032's contract stays).

**What changes:** the spec prose names Velocitron's object "**the tokens a
firing used**" (the phrase `firing-semantics.md` prose already reaches for)
whenever it means our object, and leaves *binding* to mean the books'
variable assignment wherever the prose talks about the literature. The field
comment at `:354` is reworded (`# the place-keyed bound tokens`); nothing in
CEL, schema, or code changes shape.

### 7. `Engine.run` — rename (Ada picks the name)

Book word: *run* is the whole sequence — "A run of a system model describes
how transitions occur consecutively" (Reisig p. 10); "a sequential run of a
system net N [is] a sequence `M0 −t1→ M1 −t2→ …` of steps of N, starting
with the initial marking M0" (Reisig p. 46). Velocitron's `Engine.run` is
not a run: it is an *operation* that extends the sequence until nothing is
enabled (quiescence) or a cap is hit.

Current sites: `engine.py:2662` (`def run`), `runtime.py:375`
(`Runtime.run` — the async sibling, decided with the same word),
`spec/firing-semantics.md:304-317` (failure-budget prose) and `:526-534`
(the illustrative signature), ADR 0015's title (`run()`), `tick`'s
docstring (`engine.py:2625`), the circulation desk's own `run` (a consumer's
word, colliding only in prose, not code).

**Cost class: public name** — Python and TypeScript method names, the
engine-runtime primer, ADR 0015's title. No file type or CLI surface.

**What changes:** the method renames in both implementations and every
prose mention that means the *operation*; the noun *run* is reserved, per
Reisig, for the sequence. The circulation desk's "run" already uses the noun as
Reisig does, which is one more reason to free it.

Candidate names for Ada:

| Candidate | Why | What it collides with |
|---|---|---|
| ~~drain~~ *(author's pick — struck; Ada chose **advance** instead, 2026-10-22)* | It says exactly what the operation does: keep firing until nothing is left that can fire (or the cap). Succinct, a standard word for "empty out to quiescence", and unambiguous in a method name: `engine.drain(net, marking)`. | No meaning in either book (searched; neither uses "drain"). No Velocitron or circulation-desk meaning today. Its only weakness is that drain implies emptiness while quiescence may leave tokens sitting (enabled=None stops, not empty) — the docstring already says that, and the name is honest enough. |
| **advance** *(Ada's pick, 2026-10-22 — overrides `drain`, see below)* | What `tick` already means, and what the operation does: move the system forward. | Collides head-on with `Engine.tick`, which IS "advance the clock and fire what matured" — two advance-verbs confuse, and ADR 0018's `tick` prose says "advance" everywhere. Books: neither defines *advance*. |
| settle | Matches our existing doc language: `settle` already exists as `Engine.settle` (commit-record half of ADR 0031 symbolic firing) — the name is taken *inside the same class*, which makes this candidate invalid rather than colliding. | `Engine.settle` (Velocitron); neither book uses it. |
| quiesce | Names the stopping condition rather than the action. | Neither book defines it (our *quiescence* wording predates this ADR: `firing-semantics.md:316-317`). In Velocitron "quiescence by exhaustion" (ADR 0015) is one *kind* of stop, and quiesce reads narrower. Circulation desk: unused. |
| exhaust | The stop's failure-budget name (ADR 0015's "exhausted"). | Collides internally: *exhaustion* is our term for one transition's failure budget running out (ADR 0015), and a method `exhaust` re-uses that word for the whole loop's normal stop. Books: unused. |
| play_out | The pair to item 1's *play*: a `.play` file plays one step, the engine plays it out. | If item 1 does not pick *play*, the pair's shared word dangles; and neither book uses "play out" (G&V p. 58's "playing the token game" is informal, one citation). Circulation desk: unused. A fine name only when item 1 picks *play*. |

**Ada's bundle-2 note (2026-10-22), overriding the author's `drain` pick:**
the tick collision was the deciding point — `Engine.tick` already says
"advance the clock and fire what matured" (ADR 0018's prose says "advance"
everywhere), so `Engine.advance` reads as the step-wise counterpart of
`tick` rather than a second, confused advance-verb: the method *advances*
the run one extended stretch at a time, exactly what `tick` does for one
clock step. Bundle 2 confirmed the pick.

### Cross-checks

Every candidate above was checked against both books' term lists via S10's
quotes: *play* appears in G&V only as the informal "playing the token game"
(p. 58) — a verb for firing, not a noun, so a `.play` file name does not
define-shade it; *script*, *trial*, *episode*, *trajectory*, *history*,
*drain*, *exhaust*, *quiesce*, *play_out* are absent from both books'
definitions S10 lists; *course* appears only inside Reisig's informal
descriptions of how a run goes ("the course of the run", S10's summary of
pp. 10, 46), which is precisely why it is marked colliding in both tables;
*environment run* composes Reisig's own words (his cold interface
transition belongs "to the unmodeled environment", p. 10) but re-uses *run*
as an operation, which the decision exists to stop.

No candidate collides with a *defined* term of either book. The two marked
collisions (table 1's *course*, table 2's *environment run*) are with
Velocitron words this ADR itself is fixing, and with the books' informal
prose around them.

## The rename pass (out of scope here; input for follow-up cards)

One card per numbered item, or one card per file cluster — operator's call.
What each rename touches:

- **Item 1 (Scenario → **play**, Ada's pick, 2026-10-22).** File type: `*.scenario` everywhere in
  velocitron and the consumer repositories; the parser's header keyword and every
  grammar/fence (`spec/scenario-language.md`, `_FENCE_LANGUAGES`,
  `_CHECKED_SUFFIXES` in `dsl/check.py`); the CLI (`scenario` subcommand,
  `scenario check|walk|sequence`, `--path` flags stay if only the source
  word changes); the Python module `velocitron/scenario/` and classes
  (`Scenario`, `ScenarioPath`, `ScenarioTrace`, `ScenarioReport`,
  `ScenarioError`, `check_scenario`, `parse_scenario`, `read_scenario`,
  `load_scenario_net`); the prover's counterexample writers (`prove/
  counterexample.py`, `prove/report.py`'s `finding.scenario`,
  `--counterexamples DIR` file suffix); conformance dir
  `spec/conformance/scenario/` and its `expected.trace.json` keys; the
  bundled skill (`skills/velocitron/`: SKILL.md steps 5–6,
  `kitchen-sink.scenario`, the byte-identical spec copy,
  `engine-runtime-primer.md`); docs: `README.md:56`, `CONTEXT.md:226-251`,
  ADRs 0031, 0033, 0036, 0038, 0039, 0041, 0051, 0052, 0053, 0057, 0058
  (index lines stay; the bodies name the old word as historical); spec
  cross-pointers in all nine spec files; TypeScript once it grows a checker.
- **Item 2 (occurrence sequence).** Terms in `spec/scenario-language.md`
  (Terms, Checking, Diagnostics), conformance fixture names
  (`expected.trace.json` may keep its name if the trace record's
  OpenTelemetry sense is what it holds — Q64 kept "trace" for that sense;
  the *terms* change, the fixture file name is an operator pick), Python
  class `ScenarioTrace` if the term is renamed wholesale, `CONTEXT.md`
  (`Scenario trace`, `Path` entries), ADR 0031/0038 prose.
- **Item 3 (injection-holding stream → **trajectory**, Ada's pick, 2026-10-22, as the short name in prose; the book phrase is the definition).** Spec wording in `spec/firing-semantics.md:577` (and the
  parallel wording in ADR 0013 and ADR 0018 where they say "one sequence
  stream"), `engine.py:2483` docstring. No public name.
- **Item 4.** `spec/firing-semantics.md` intro ("sequence of firing
  attempts" → wording using "attempt record"), the record's inline comments
  (`# the binding` → item 6's wording re-uses this edit). No code shape.
- **Item 5.** `spec/scenario-language.md` Terms + grammar production names
  (`Step`, `StepBody` stay as *names*; the spec's *word* changes), the
  `expect`-is-a-step sentence at `:23-24`, `CONTEXT.md` (`Scenario step`
  entry). No code.
- **Item 6.** `spec/firing-semantics.md` (definition `:110`, comment `:354`,
  the "How binding is keyed" and "What a consume/read correlate sees"
  sections get the phrase), `spec/net-schema.md` binding-names section
  prose, `spec/handler-contract.md` input descriptions. CEL names untouched.
- **Item 7 (`Engine.run` → **advance**, Ada's pick, 2026-10-22, overriding the author's `drain`).** `engine.py:2662` and `runtime.py:375` method names (both
  implementations), `spec/firing-semantics.md` (e) signature and the
  failure-budget prose, ADR 0015's title and body, `tick`'s docstring and
  prose in ADR 0018, the engine-runtime primer, TypeScript
  `engine/engine.ts:1110` and its `RunOptions`. The circulation desk's prose
  is untouched (its "run" is the noun, which this ADR keeps).

The pass is verified by `velocitron check` over the repo and the two skill
bundled copies, plus the Python and TypeScript test suites and the
conformance fixtures.

## Notes recorded for the operator

- **The Petri net primer refreshes from this ADR** (its N35):
  after Ada picks the three names, the primer's word entries are updated from
  this record's decisions, and its `[INFERENCE]` lines around the
  net-with-environment phrase can be dropped where this ADR has decided.
- **ADR 0058 used today's words on purpose** — its own words: "It uses
  today's words for `scenario`, `binding`, and `Engine.run`; a separate ADR
  will decide the renames the Petri net books suggest, and this record does
  not wait for it." That was correct at its write time: every consumer of
  ADR 0058 (the codegen, the journal, the replay) names its code with
  today's words, and renaming under it would have changed two decisions in
  one ADR. This record is the one that moves the words; nothing in ADR 0058
  re-decides here — only the spellings of the words its decisions use.
- **Q64 keeps.** The trace event is "tokens reserved"; `TraceJournal`,
  "trace record", `ReplayOrderError`, `Replay<Net>`, and "tape" keep their
  names; `binding` and `binding_names` keep their CEL names; the trace
  record's `trace` keeps its OpenTelemetry sense. Items here do not reopen
  any of these.
- **`environment-arrival` stays.** `spec/firing-semantics.md:536-541` already
  uses the books' own idea (Reisig's cold interface transitions, pp. 9-11;
  G&V's source places, p. 155); no rename.

## Consequences

- With Ada's picks (2026-10-22: **play**, **trajectory**, **advance**), the
  three renames become follow-up cards and the rename
  pass above is their scope map; the spec wording items (3-6)
  can be edited without code change — they are prose decisions, not API
  breaks.
- Any new Velocitron prose should reuse the book
  words from this record where they are unambiguous (occurrence sequence,
  attempt record, statement/step split, tokens-a-firing-used), so the
  rename pass is smaller.

## References

- `S10 — The most precise terms, from Ada's own books`
- Reisig, *Understanding Petri Nets* (2013) — pp. 7, 9-11, 25-26, 28, 45-46, 49, 63
- Girault & Valk (eds.), *Petri Nets for Systems Engineering* (2001) — pp. 12, 34, 36-37, 42-43, 50-51, 58, 122, 155, 232
- [ADR 0058](0058-a-net-compiles-to-a-python-base-class-and-the-journal-traces-and-replays-the-run.md) — the deferral answered here; [ADR 0031] — the scenario checker as shipped; [ADR 0032] — binding names
- `spec/scenario-language.md`, `spec/firing-semantics.md`, `spec/net-schema.md`, `spec/handler-contract.md`, `spec/proofs.md`, `CONTEXT.md`
