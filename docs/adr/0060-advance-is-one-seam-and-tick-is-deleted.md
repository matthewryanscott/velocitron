# Advance is one seam, and `Engine.tick` is deleted

**Status:** Proposed (2026-10-22). Answers ADR 0059's item 7: the operation
name Ada picks is `advance`, valid only because this record folds `tick` into
it. Builds on ADR 0013 (the injection seam), ADR 0018 (native timed
transitions and `tick`), ADR 0015 (the failure budget), and ADR 0055 (ticks
wait until something can use them). Code facts are read from the tree. The
scope-map's line numbers were verified before the rename pass — the pass's
re-names and moves shifted the positions. Post-rename, the landed code is
the truth: the seam is `engine.py`'s `advance` and the play statement is
`play/check.py`'s `advance` step; read the landed tree, not the numbers
below.

## Why

Velocitron has two engine-level "move the net forward" methods that differ
only in whether time enters first:

- `Engine.run(net, marking, *, max_steps=1000)` (`engine.py:2662`) fires
  until quiescence or the cap.
- `Engine.tick(net, marking, place, token, *, attempt, max_steps)`
  (`engine.py:2625`) does one `inject_token(replace=True)` — the singleton
  clock-advance pattern (ADR 0013) — then calls `run`. It adds no primitive
  and no journal channel; it is a two-line composition.

The pair forces every reader to decide which verb applies, and the words
collide in the wrong way: ADR 0018's prose says "advance the clock" for
`tick`, while ADR 0059 rejected `advance` as the rename of `run` precisely
because `tick` already owned the verb. Ada's decision (2026-10-22)
resolves the collision by
merging the pair instead of re-labelling it: one seam named `advance`, with
an optional time step inside it, and `tick` deleted outright. This record
also fixes ADR 0018's prose, which names `Engine.tick` as the convenience
method, and supplies the rename-pass scope items in the shape ADR 0059 set
(out of scope here; one mechanical PR).

## Decision 1: one seam — `Engine.advance(net, marking, *, time=None)`

`Engine.advance` replaces both `run` and `tick`.

```python
def advance(self, net: Net, marking: Marking, *,
            time: tuple[str, Token] | None = None,
            attempt: int = 0, max_steps: int = 1000) -> Marking:
```

- **`time=None` (old `run` behavior, default).** Fire transitions until
  quiescence or `max_steps`, under the configured firing policy (ADR 0014)
  and failure budget (ADR 0015). No time enters the net.
- **`time=(place, token)` (old `tick` behavior).** One
  `inject_token(replace=True)` — the singleton clock-advance pattern (ADR
  0013) — then the same run-to-quiescence, in one call. The injection and
  the firings still share one journal sequence stream, so the timeline
  replays deterministically; the ADR 0015 exhaustion analysis applies to
  timed transitions unchanged (ADR 0018's own argument, restated here as
  the seam's invariant).
- One failure ledger per call (the engine-owned `_FailureLedger`,
  `engine.py:488`; `Engine.selection_ledger` hands a fresh one out at
  `engine.py:2734-2742`), one journal stream, one return. `tick`'s
  `attempt` parameter feeds the injection's deterministic `injectionId` and
  moves to `advance` unchanged; the inner loop numbers its firing attempts
  from its own step counter.
- Consumers needing append-mode injection (a deadline token rather than a
  clock advance) compose `inject_token` + `advance` directly, as they
  compose `inject_token` + `run` today.

**Considered options:**

- Keep `run` and rename `tick` to `advance` (two methods). Rejected: the
  pair's bodies differ by one line, and every "which verb do I call"
  question stays alive; the clock-advance-then-fire pattern is the common
  case for timed nets and deserves the plain name.
- Keep `tick` as an alias over `advance`. Rejected — see Decision 2.
- Name the operation `drain` (ADR 0059 item 7's author pick). Superseded by
  Ada's pick: `advance` was the rejected candidate only because `tick` held
  the verb, and this record removes the reason.

## Decision 2: `Engine.tick` is deleted — no alias, no deprecation shim

`tick` is removed, not deprecated. Rationale, recorded: Velocitron is a
public alpha with no third-party users — the only consumers are this
repository, its conformance fixtures, its test suites, and the
circulation-desk code behind the packaged skill — so the API surface can move in one
commit without breaking anyone. A deprecation shim would spend review and
maintenance on a compatibility promise the alpha does not make (the ADR
index's own preamble: an ADR is not an API or compatibility promise).

## Decision 3: `Runtime.run` renames to `Runtime.advance`

`Runtime.run` (`runtime.py:375`, the async sibling that loops the engine
until `stop` or cancellation) takes the same name as the seam it drives,
with the identical rationale: its noun *run* is reserved for the sequence,
per Reisig pp. 10, 46 (ADR 0059 item 7), and the verb should match the
engine call it wraps. No `time` parameter reaches the Runtime here — its
scheduler drives time through the injection seam itself (`spec/
firing-semantics.md` (f) prose on `maturity` scheduling) — so the rename is
the word only.

## Decision 4: the `.play` statement `tick` renames to `advance`

The checker's statement keyword moves with the seam, per Q72(b):

- Landed semantics: `advance` keeps the replace-injection, and the statement
  is **update-only** where no firing can mature — an absolute settle onto an
  empty clock place (`advance 0` included). Otherwise the statement carries
  one maturation pass, to quiescence (the spec's wording:
  `spec/firing-semantics.md` (e) — the loop stops on policy `None` or
  `max_steps`, quiescence by exhaustion included), symbolically; a
  transition whose outputs the play cannot
  determine is skipped (left enabled for the author's own `fire` step), a
  failing maturation firing is recorded and the pass continues, and a
  maturation that does not quiesce raises `SC315`. The statement plays what
  this record's seam does, minus what a play cannot mirror: the checker
  registers no handlers, so the candidate set narrows to the determined
  outputs and the priority policy picks among those only.
- The statement `tick` renamed in one mechanical PR together with the ADR
  0059 pass (item 1's `.scenario` → picked name rewrite touched the same
  files, so the two renames landed as one pass).
- The token COLOR `tick` is untouched: `domain tick.now 0 1 2`, fixture
  colors like `tick` in `tests/fixtures/`, and the read-arc fixture color
  in `spec/`-level examples are data words, not statements.
- The checker mechanism is unchanged: the play calls
  `inject_token(replace=True)` directly (the mechanism ADR 0018 gave
  `tick`; the statement is spelled differently, the engine call is the
  same). The statement lives in `play/check.py`'s `advance` step; the seam
  is `engine.py`'s `advance` at its landed position.

## Decision 5: TypeScript keeps `tick`/`run` for now — lockstep waiver

The TypeScript engine keeps its method names (`tick` at `implementations/
typescript/src/engine/engine.ts:1096`, `run` at `:1110`, `RunOptions`
alongside). Lockstep applies to codegen output and trace parity, not to
method names, so this is a documented waiver of internal API lockstep. The
TS methods are renamed in the follow-up PR that lands Decision 1's TS side
(often the same PR; if not, the waiver lapses when it lands). The Python
and TypeScript *behaviors* — one seam replacing two methods — stay in
lockstep; only the naming move is waived for now.

## Decision 6: prose updates — ADR 0018 and `spec/firing-semantics.md`

These are listed as rename-pass scope items; this lane edits neither file.

**ADR 0018 (`docs/adr/0018-native-timed-transitions.md`).** Its prose
names `Engine.tick` as a decision. Exact edits:

- `:38-44` — the convenience-method paragraph: `Engine.tick(net, marking,
  place, token, *, attempt, max_steps)` becomes the one convenience method
  `Engine.advance(..., time=...)`; the sentence "advance the clock (one
  `inject_token(replace=True)`, ADR 0013) and `run` to quiescence" becomes
  "advance the clock (one `inject_token(replace=True)`, ADR 0013) and fire
  to quiescence, in one call".
- `:63-66` — motivation item 3: "engine-owned via `tick`, built on
  `Engine.run`" becomes "engine-owned via `advance`, the one seam".
- `:143-150` — the replay bullet: "`tick` composes the existing
  primitives… `tick` = `inject_token(replace=True)` + `run`" and "a
  `tick`-driven timeline" become the same statements about `advance`'s
  `time=` semantics.
- Status line of 0018 gains one sentence: the convenience method's name
  moved to `advance` per [ADR 0060]; the decision (declarative timer,
  deadline-in-token) is unchanged.

**`spec/firing-semantics.md`.** The convenience section sits at `:629-656`
(the card's `~:698-729` had drifted; these are the verified lines in this
checkout). Exact edits:

- `:630-637` — heading prose "Native timed transitions and `tick` (ADR
  0018)" and the lead-in "the engine owns that re-evaluation via one
  convenience method" become "Native timed transitions and the advance
  seam (ADR 0018, ADR 0060)".
- `:639-650` — the illustrative signature `def tick(...)` becomes `def
  advance(self, net, marking, *, time=None, ...)` with the two-mode
  docstring (no time = fire to quiescence; time = replace-inject then fire).
- `:652-656` — "`tick` adds no new journal channel and no new primitive" /
  "the next `tick` re-evaluates" rewrite to `advance`; the appendix pointer
  at `:818-819` ("the engine-owned `tick` re-evaluation loop in (f)")
  renames likewise.
- `:544-547` — "advances time only through the injection seam below and
  `Engine.tick`" drops the method name (the seam is the primitive; the
  convenience is `advance`).
- `:526-534` — the illustrative `def run(...)` selection-loop signature in
  (e) becomes `def advance(...)` (modeless there: (e) is the no-time
  behavior; the prose keeps one illustrative signature, in (f)).

## The rename pass (out of scope here; input for the mechanical PR)

What each move touches, with verified line numbers at this checkout:

- **engine.py** — `def tick` `:2625-2658`; `def run` `:2662-` (selection
  loop through `:2740`); `_FailureLedger` `:488` (unchanged);
  `Engine.selection_ledger` `:2734-2742` (unchanged). Docstrings naming
  `tick`/`run` to update: `:16-18`, `:557-559`, `:2467-2478`, `:2642-2654`.
- **runtime.py** — `async def run` `:375` → `async def advance`.
- **TypeScript** — `implementations/typescript/src/engine/engine.ts`:
  `tick` `:1096-1108`, `run` `:1110-`, `RunOptions` (waived now; renamed in
  the follow-up PR, Decision 5).
- **spec/firing-semantics.md** — the six edits listed in Decision 6.
- **docs/adr/0018-native-timed-transitions.md** — the four edits listed in
  Decision 6; **docs/adr/0015-failure-budget-and-failure-aware-selection.md**
  title/body says `run()` and moves with the same pass (ADR 0059 item 7
  already listed it).
- **scenario** — statement keyword `tick` → `advance` (Decision 4):
  `scenario/language.py:1021-1025` (parser word and `StepKind` at `:178`),
  `scenario/check.py:381-412` and `:994-995` (planning) and `:1061-` (the
  step), `scenario/sequence.py:517` and `:626`, `scenario/walkthrough.py`
  `:527`/`:596` verbs, `prove/counterexample.py:130-138`, `prove/report.py`
  `:48`/`:97-98`, `prove/soundness.py:244`/`:434` (`Move("tick", ...)`
  keeps kind-name spelling in step with the statement), and the test
  fixtures spelling the statement (`tests/fixtures/scenario/*.scenario`,
  e.g. `evening-shift.scenario:17,29`, `shop.scenario:19`). COLOR `tick` tokens
  (`deadline.petrinet:10-11`, `never-due.petrinet:10`, `shop.petrinet:9`,
  `readarc` fixtures' `tick` color) are untouched.
- **Verification for the pass**: `velocitron check` over the repo, the
  Python and TypeScript test suites (`.venv/bin/python -m pytest -q` from
  `implementations/python`; the TS suite from `implementations/typescript`),
  and the conformance fixtures.

## Consequences

- Two verbs become one; timed and untimed calls share one journal stream,
  one failure ledger, and one docstring each.
- ADR 0059 item 7 resolves: the operation name is `advance`, and the
  candidate-table reason for rejecting it ("collides head-on with
  `Engine.tick`") is voided by this record. ADR 0059's status comment for
  item 7 moves to Accepted when this record is accepted.
- `scenario tick`/`advance` renaming rides the ADR 0059 pass's PR, so
  authors see the statement rename at most once.
- The TS naming waiver is temporary and tracked in the pass's PR list;
  lockstep over codegen and trace parity is not affected.

## References

- [ADR 0013](0013-clock-timer-injection-seam.md) — the injection seam whose
  replace-mode is the time step; [ADR 0018](0018-native-timed-transitions.md)
  — the timed transitions `tick` served; [ADR 0015]
  (0015-failure-budget-and-failure-aware-selection.md) — the budget the seam
  keeps; [ADR 0055](0055-ticks-and-record-changes-wait-until-something-can-use-them.md)
  — ticks wait until something can use them; [ADR 0059]
  (0059-velocitron-spells-its-model-words-the-way-the-petri-net-books-do.md)
  — item 7, answered here
- `spec/firing-semantics.md` (c, e, f) — the selection loop and the seam