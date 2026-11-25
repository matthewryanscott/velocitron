---
name: velocitron
description: Use when creating, modifying, or discussing colored Petri net design — places, transitions, arcs, arc inscriptions (predicates, guards, CEL), token data/colors, weights, read/inhibit arcs, timers, composition, or marking — and when authoring `.petrinet` DSL, using the `velocitron` / `velocitron-viz` CLIs, or driving the Python `Engine` or `Runtime`. Read before designing a net, writing net structure, or writing engine/runtime code.
---

# velocitron

`velocitron` is a typed, durable colored-Petri-net library for agentic process coordination: a language-agnostic JSON net schema, a flat authoring language (`.petrinet`), and a Python reference implementation (parser/validator, a synchronous firing `Engine`, and an asynchronous `Runtime`). A net is pure coordination structure — places (conditions/buffers that hold typed tokens), transitions (events with consume/produce arcs, an optional behavior binding, and an optional guard), and a marking (the token distribution). A handlerless transition is valid structure; no same-name or no-op behavior is implied. The exact ordinary color `token` is the Generic token convention for classical/uncolored nets: it is not a wildcard or untyped core value, although visualization omits its generic label. Design nets so every decision is visible in the structure — a choice is two transitions sharing an input place with mutually exclusive arc predicates, never one transition with two outputs (that is an AND-split that deposits to both).

Before changing net structure or terminology, also consult the repo's `CONTEXT.md` (ubiquitous language), `packages/spec/` (the authoritative contracts), and `docs/adr/` (architectural decisions). This skill's bundled docs summarize and ground those for quick authoring.

## CLI presence check

The two console scripts are `velocitron` (validate / convert / explain / check and walk plays / prove facts / install this skill) and `velocitron-viz` (render a net as Graphviz DOT). The full, current help surface for both — every subcommand — is injected here at skill load:

!`bash "$CLAUDE_SKILL_DIR/scripts/cli-help.sh" 2>/dev/null || bash skills/velocitron/scripts/cli-help.sh 2>/dev/null || bash scripts/cli-help.sh 2>/dev/null || echo "(cli-help.sh not found — run: bash skills/velocitron/scripts/cli-help.sh)"`

The inline `!`…`` block above is a Claude Code dynamic-context feature that runs the helper at load. If the help text is absent (you are not in Claude Code, or the block did not execute), run `bash skills/velocitron/scripts/cli-help.sh` yourself to get the same output.

If the output shows `velocitron CLI NOT INSTALLED` (or `velocitron-viz CLI NOT INSTALLED`), the CLIs are not on PATH. Offer the user these two install options and wait for their choice — do not pick one yourself:

1. Install from GitHub: `uv tool install "git+https://github.com/matthewryanscott/velocitron#subdirectory=packages/cli/python"`
2. Install from a local clone the user names: `uv tool install <path-to-clone>/packages/cli/python` (add `--editable` to track edits).

## Authoring workflow

1. Sketch the net structure first (places, transitions, arcs) — see `structure-library.md` for the idiom that matches the problem.
2. Write the `.petrinet` DSL — `petrinet-language.md` is the language reference; `kitchen-sink.petrinet` is a validating example of every construct.
3. Validate early and often: `velocitron validate <file>.petrinet`. It also prints advisory lint warnings on stderr — for example a `predicate cel` that names a color or place (`switch.owner`): a predicate sees only its own token's fields as bare names, so a condition between tokens belongs in `correlate cel` on an input arc, which in turn sees only `token` and `binding` (`hold.branch` there is flagged too). Each warning points at the line that wrote what it flags. A transition that consumes and produces nothing is warned about too; when that end is intended, mark it with `[t] annotation end true`. So is a transition that only reads (`->?`) or inhibits (`->0`) and produces: it consumes nothing, so it can fire again and again, adding a token each time, and `velocitron prove` never runs out of markings. Consume a token, or inhibit it on its own output so it fires once (`(checks) -check->0 [compare_files]`). Convert to canonical JSON with `velocitron to-json`, back with `velocitron to-petrinet`, and get a prose walkthrough with `velocitron explain`. It ends with what can happen from the initial marking: each transition either "can happen" or "waits", with the reason in plain words (an empty input place, or the token and the predicate, correlate, inhibit arc or timer that said no). Pick another starting marking as `velocitron-viz` does: `--marking NAME` for an authored named marking, or `--marking-json '{"pending":[…]}'` for one inline marking. No handler runs, so a named guard always holds its transition back.
4. Visualize and iterate on a standalone Net: `velocitron-viz <file>.petrinet`
   accepts DSL source directly — compiled through the real pipeline, so authored
   `view` facts carry over — and `velocitron-viz <file>.json` takes canonical
   document JSON. Both render the authored initial marking by default; use
   `--marking queued` for an authored named marking, or
   `--marking-json '{"request_in":[{"type":"request","data":{"id":"r-17"}}]}'`
   for one validated inline marking. Use `--no-marking` to omit token detail.
   Views:
   a net's `view <name> position (place)/[transition] at {"x": N, "y": N}` and
   `view <name> position <target> relative <base> + {"x": N, "y": N}` facts
   (the base stays as authored; chains resolve when the view applies)
   and `view <name> route @handle orthogonal [ … ]` facts lower into
   `annotations["petrinet.dsl/v1"]["views"]`; `--view <name>` applies that
   geometry over the render model (positions, handled-arc routes, `splines=ortho`)
   and rejects unknown subjects or stale arc handles by name. A view named
   `default` applies without the flag; `--no-view` renders the plain layout.
   `view <name> splines ortho|spline|curved|polyline|line` sets the view's edge
   style (default `ortho`), and `view <name> detail full|summary|structure`
   sets its label detail level (a `--detail` flag wins). A view may hold only
   these two facts and no positions.
   A view that positions nodes selects Graphviz `neato` (`layout=neato`,
   `inputscale=72` so coordinates are points with y up, and `overlap=scale`):
   pinned nodes keep their arrangement and neato places the rest around them.
   Views apply to standalone nets only; composition rendering ignores them.
   Decorations belong to no view and show in every render:
   `decorate (p)|[t]|@handle highlight ["label"]` fills a node (or thickens an
   arc) in amber, `decorate … note "text"` adds a short italic line,
   `decorate [t]|@handle summary "text"` replaces a guard/timer/priority or a
   predicate/correlation/data template at `--detail summary`, and
   `decorate color C quiet` (or `--quiet-color C`) hides `C`'s type label on
   consume and produce arcs, and `decorate color C show "f" "g.h"` shows
   only those fields (dotted paths reach into nested objects) in `C`'s
   marking rows. An arc decoration needs a handle that covers
   exactly one arc. `decorate (p) beside [left|right] [unshared]` draws each local copy
   of a fusion place (`(p) annotation fusion true`) on its transition's rank,
   next to it; with no side the copies are balanced, first one left. Use it
   when a copy lands far away and its read arc crosses the net; a copy the
   transition writes keeps its side too. With no
   side, two transitions that are neighbors in a choice (same one input
   place, next to each other in the drawing's structural order) and both use
   `p` share one copy, drawn between them. That order is the distance from
   the initial marking, then the name, so rearranging the source does not
   pick different pairs. `unshared`
   keeps one copy per transition instead, and pushes those copies outside
   the choice's row (`P A B P`). `beside left unshared` parses and warns:
   a fixed side already never shares. The sides
   are for `tb`/`bt`; `lr`/`rl` put left below. A view places a copy from
   its `(P)@[T]` position, else from a whole-place `(P)` position, else
   beside a pinned transition, on the side that row chose. A whole-place
   position still anchors `relative (P)`.
   `relative (P)@[T]` uses the point where that copy is drawn.
   `decorate (p) single` draws that fusion place as one dashed node in every
   render, including `--no-view` and a Markdown fence; its arcs take part in
   ranking. `view V fusion (p) single` or `copies` overrides that choice for
   one view. A view that resolves a place to `single` drops that place's
   `beside` rows. A `(P)@[T]` position does not apply to a place drawn as
   one node. `--no-fusion` is deprecated: it still forces every fusion
   place to one ordinary node, and it still wins over both facts.
   The render-inspect loop for authoring: render the DOT to an image, LOOK at
   it, then re-edit the source. Any DOT renderer composes —
   `velocitron-viz net.petrinet --view wired | dot -Tpng -o /tmp/net.png` with a
   local Graphviz, or `velocitron-viz net.petrinet | curl --data-binary @- \
   https://kroki.example/graphviz/png > /tmp/net.png` against a Kroki server.
   Keep the output path fixed across iterations so every look reads the freshest
   render. `velocitron-viz design.petrinet --metrics` prints crossings,
   overlaps, edge length, and bends for that drawing, as JSON. Compare those
   numbers only when they come from the same Graphviz version; the report
   names the version and the engine (`dot`, or `neato` when a view pins
   positions).
   Marking selectors do not apply to composition, `--merged`,
   `--ports-only`, `--overview`, or `--legend`; use `--doc --fence` for a
   Markdown-embeddable diagram.
   For a reader who wants what each part of a composition is for,
   `velocitron-viz comp.petrinet --overview` draws one box per net, named by
   its `description`, with the wired places between them, the ends (a place
   of the case nothing takes from) as double circles, and the shared records
   as cylinders labeled `takes`, `gives back` or `reads` per net. A place
   that `lives in` a `record` column is a record the outside world keeps
   (dashed border). Give each net a description and each wired or shared
   place a `description` so the labels read as business words.
   Use `--detail full|summary|structure` to set how much behavior labels
   show: `full` (default) shows every predicate, guard, timer and data
   template whole, wrapped across lines; `summary` cuts each expression to
   one line; `structure` drops handler refs, guards, timers, priorities,
   predicates, correlations and data templates.
   Use `--direction=lr` to override Graphviz layout (`tb`, `lr`, `bt`, or `rl`,
   case-insensitive). Nets and compositions default to `tb`; `--rankdir`
   remains a backward-compatible alias.
   For the ordinary Generic color `token`, visualization suppresses only redundant type labels (accepted-color rows, generic port type, generic marking type, consume/produce arc type); counts/data, weights, read/inhibit glyphs, predicates, correlations, literal data, tooltips, and non-generic colors remain visible.
5. Walk it with a play, before any handler exists: write a `.play` file beside the net — `play-language.md` is the reference and `kitchen-sink.play` a checked example. Steps are `inject (p) <- token`, `update (p) <- token`, `advance +90m` (or `advance 22.5h`, absolute), `fire [t]`, `expect …` and `assume [t] guard true|false` (scopes an assumed guard answer for the rest of the path, so a guarded transition can fire; `assume predicate "p" true|false` does the same for a named predicate handler); `///` lines are Markdown prose for the walkthrough, `@label:` marks a step, and `path NAME from @label` branches an error path that replays the shared steps. `velocitron play check FILE` plays every path through the real engine by symbolic firing: it reserves the binding, fills each output from the net's `data`/`data cel`, else the step's `-> (p) token` (`+{…}` merges over the carried token, `nothing` gives none), else the carry rule (exactly one consumed token of that color; read tokens never carry), and otherwise stops with `SC303` naming the output. A step that is not enabled prints `FILE:LINE:COL: error[SC301]` with each gate that said no and its values (predicate, correlate, inhibit, timer with clock values, unregistered guard) and what is enabled instead. `with (p) {subset}` picks a token; `expect next [t]` asserts what the priority policy would pick. `velocitron play walk FILE [--path NAME] [--scope step|neighbors|subnet] -o walk.md` renders a Markdown walkthrough: the touched subnet, then each step's marking before and after as two `dot` fences with one layout, with the step's checks and prose; render a fence and LOOK at it as in step 4. A step draws only its transition and that transition's places by default (`scope neighbors` adds the other transitions there, faded; `scope subnet` draws the whole touched subnet). `show hold id, remindAt` (or the net's `decorate color hold show "id" "remindAt"`) shows only those fields of a color; fields a step changed are always shown. `FILE` may be `-` (stdin) with `--origin DIR` for resolving `net "…"`. A play may target a composition (`net "comp.petrinet"`, or `use`/`wire`/`share`/`refine` lines in the play); names are then `alias.name`, and `alias.inner.name` inside a used composition. For a sequence diagram, say who does each step in the net: `person Operator` / `system Desk` / `record "Branch home"` declare lifelines in order, `[t] actor Operator` names who fires a transition, `net actor Desk` is the default for the rest, and `(p) actor Catalog` names who injects into a place (its owner; else `Outside`). A record that stays (a switch, a slip on a shelf) gets a column: `(switch) lives in "Branch home"`, or `(loaned) lives in cel "token.branch"`, plus `(switch) reads as cel "…"` for the value a reader sees. Actors and lived places survive `use`/`wire`/`refine`. Then `show sequence` in the play (or `show sequence only` after a `path` line, for that path) adds the diagram to the walkthrough, and `velocitron play sequence FILE [--path NAME] [--format plantuml|json]` prints it as PlantUML for GitHub: an arrow per hand-off labeled with the producer's step title, an arrow into a column per write and a dashed arrow out of it per read, an actor's own titled steps as notes (untitled steps draw nothing), `advance` as a delay, `/// ### heading` as a group and `/// ## heading` as a divider; `box "Night crew" Runner Desk` in the play boxes lifelines. Title steps in business words (an injection as an event, "Run 1 published"), drop titles from bookkeeping steps, and render it through Kroki and LOOK at it.
6. Prove it: `velocitron prove FILE.petrinet [--fact choice|invariants|soundness|refinement] [--counterexamples DIR] [--domains FILE] [--json]` checks every marking the net can reach, with no handlers. **Choice coverage**: each token at a place consumed by two or more transitions enables exactly one of them (a gap enables none; an overlap enables several, unless a priority picks one or `annotations.lint.suppress: ["choice-overlap"]` waives it). **Place invariants**: weighted token counts no firing changes (P-semiflows), stated in plain English. **Soundness** of one instance: it can always complete, completes cleanly, and every transition fires; open places (no producer, read fusion places, clocks, the instance's input port) are the environment, which writes each once and may replace a read-only fact once. A record the outside world keeps and may change (a branch home a person sets, a verdict a gate gives again) is a place that lives in a `record` column, the same lines the sequence diagram uses: `record "Branch home"` and `(switch) lives in "Branch home"`. The prover keeps it open however it is produced, wired or shared, lets the environment change it any number of times, treats a step that only takes and gives records (a flip) as the outside world's move (no livelock, but it must still be able to fire), and counts a net that waits for a record to change as waiting, not stuck. A record the system keeps itself (there from the start, changed only by the net's own steps, such as one damage record per title) is a kept place instead: `(condition) kept by "circulation desk" starts as cel "{'isbn': instance.isbn, 'damaged': false}"``. The check starts with it, built from its instance token so correlations on keys match; the environment never writes it, and proper completion and final markings ignore it. A story starts with it when it names its instance (`instance $u1`) or when the start reads no `instance`. Data domains come from the net's own CEL (literals plus `⟨other⟩`, booleans, values around numbers, own/other keys for correlated fields, time slots for timer fields). Say what the net does not show with net facts: `domain verdict.result "pass" "hold"` closes a field (no `⟨other⟩` gaps; the engine also rejects other values at deposit and injection, so list every value handlers return), `final (delivered), (gave_up)` names final places (`final (a) + (b)` is one final marking that needs both; a composition may declare its own `final lifecycle.(checkout.loaned) + catalog.(shelved)`, which replaces its nets' final facts), and `invariant "lock" (free) + (busy) = 1` declares a count to prove; a domains file still overrides them. A shared lock or record keeps its `fusion true` member's role in a composition (`share a.(lock) ~ b.(lock)`), so split nets prove like the original; `velocitron equiv ORIGINAL SPLIT` checks that a split (or a composition that `use`s compositions) is the same net up to renaming, with port changes listed apart. On a composition every `refine X.[t] by Y` is checked too: `Y` must take each token from the port wired to `t`'s input and give back exactly one through the ports wired to `t`'s output, on every path, leaving nothing behind. Each fact prints PROVED, REFUTED with a witness, or UNKNOWN with the reason; exit 1 means something is refuted. `--counterexamples DIR` writes each finding as a `.play`: run `velocitron play check` on it and walk it to see the problem. A livelock ("can keep firing [hold], [release] but never completes unless the environment acts") means the net waits for a fact to change that it should not wait for. Read `proofs.md` for the rules and limits.
7. Execute: register every behavior binding you intend to run and drive the `Engine`; on the raw `Engine`, a disabled handlerless transition remains `NotEnabled`, while firing an enabled handlerless transition fails atomically with `HandlerNotFound`. With a generated net class (`velocitron codegen`), a transition with no handler fact is pure and needs no handler code: codegen fills its outputs (`data`, `data cel`, else the carry rule) in a generated method, and `register_into` binds it, so a net of pure transitions runs with no handlers at all. For a net with proved choice coverage run from a projected marking, `engine.advance(net, marking, strict=True)` raises on a conflict or a failed attempt instead of picking or retrying. `Runtime` is for timers/long-running coordination and rejects handlerless nets at construction because every transition requires a `HandlerSpec`. See `engine-runtime-primer.md` and `engine-vs-runtime.md`.

## Bundled resources

Read these as the task calls for them:

- **`petrinet-language.md`** — the `.petrinet` DSL contract: optional net headers, standalone declarations, arbitrary-length topology chains (`-Color->`, read `->?`, inhibit `->0`, Generic-token bare `->`), arc facts (predicate/weight/data/data cel/correlate), optional transition behavior bindings plus guard/priority/timer/maturity facts, places (ports, accepts, capacity), template markings plus count-only Generic-empty marking runs, composition, and metadata. Handler absence remains absence in core JSON and canonical DSL. Read before writing or changing any `.petrinet` source. (Authoritative source: `packages/spec/petrinet-language.md` in the repo; this bundled copy is byte-identical for installed skills.)
- **`kitchen-sink.petrinet`** — one validating net whose three disconnected regions (order fulfilment, CI pipeline, document-review SLA) together exercise every DSL construct, heavily commented. Read/copy it when you need a working example of a specific construct.
- **`play-language.md`** — the `.play` contract: settings, steps (including the `assume [t] guard true|false` assumption), symbolic firing and its output rules (net data, step data, carry rule), paths, conditions, the `SCnnn` diagnostics, the `velocitron play check`/`walk`/`sequence` commands, the walkthrough and the sequence diagram. Read before writing a play. (Byte-identical copy of `packages/spec/play-language.md`.)
- **`kitchen-sink.play`** — a checked play against `kitchen-sink.petrinet`: step outputs, advances against a timer, a labeled branch, and a guarded transition a play plays with `assume [t] guard true`.
- **`proofs.md`** — how `velocitron prove` reads a net: the roles it gives places, the data domains, what gap, overlap, livelock and deadlock mean, the domains file, and what a proof does not cover. Read before acting on a prove report. (The full contract is `packages/spec/proofs.md` in the repo.)
- **`structure-library.md`** — a catalogue of reusable net idioms (sequence, choice/conflict, fork-join, mutex/semaphore, bounded producer-consumer, retry-with-limit, timeout, watchdog, saga/compensation, state-machine, composition via ports/wires, refining an abstract transition, sharing a record or lock between nets, using a composition inside a composition), each with when-to-use and a minimal `.petrinet` snippet. Read when choosing how to model a coordination problem.
- **`engine-runtime-primer.md`** — practical primer on the Python API: building a `HandlerRegistry`, parsing/loading a net, `enabled_transitions` / `fire` / `advance`, the firing journal, token injection, timed transitions via `advance`'s `time=` mode, and the async `Runtime` (lanes, token sources, event-driven timer scheduling). Every sample is grounded in the current API. Read before writing engine/runtime code.
- **`engine-vs-runtime.md`** — when to use the synchronous `Engine` alone (embedding, custom loops, tests, deterministic replay) versus the async `Runtime` (native timers, long-running coordination, concurrent handlers, token sources). Read when deciding which to reach for.
- **`scripts/cli-help.sh`** — the helper that dumps both CLIs' full help surface (used by the presence check above). Run it manually if the injected help text is missing.

## Installing/updating this skill elsewhere

`velocitron skill <pathname>` installs this skill into `<pathname>/velocitron/` (a fresh install, or an update detected by an existing `<pathname>/velocitron/SKILL.md`). `<pathname>` must already exist. Updates are a true sync driven by a `.velocitron-skill-manifest.json` the command writes: shipped files are overwritten, files a previous version managed but the skill no longer ships are removed, and files you added yourself are left untouched. The skill is read from the `velocitron-skill` package (`velocitron_skill.skill_root()`). The repo's `skills/velocitron/` is the authoring source of truth; that package symlinks the tree and ships it as package data.
