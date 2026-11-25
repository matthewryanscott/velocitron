# Velocitron

Velocitron is an early, practical toolkit for authoring, validating,
visualizing, simulating, and running typed colored Petri nets in Python and
TypeScript. Its portable contracts are the `.petrinet` authoring language and
a shared JSON representation for nets and compositions.

## Status: 0.1.0 alpha

This 0.1.0 alpha is a serious working release for technical exploration, not
a compatibility or production-readiness promise. APIs, schemas, the DSL,
diagnostics, and implementation capabilities may change without notice. There
is no migration, maintenance, support-response, or security-support guarantee.

Validation is focused on the demonstrated technical paths. It is not an
assurance that a net is correct for a particular operational use. The Python
runtime is the reference implementation; cross-language parity is limited to
surfaces verified for both packages. Examples and public guides cover the
demonstrated path, not every feature or integration.

Do not use Velocitron for production, security-sensitive, or otherwise
high-consequence workloads. Support is best-effort only.

## What is here

- `packages/spec/` (`@velocitron/spec`, Python `velocitron-spec`) defines the
  shared JSON schemas and the normative net, composition, handler, firing,
  property, projection, and `.petrinet` contracts, plus the conformance
  corpus.
- `packages/ir/` (`@velocitron/ir`, Python `velocitron-ir`) loads the
  contribution-IR wire shape. CEL compilation and contribution resolution
  ship in `packages/petrinet`. Composition merge ships in
  `packages/merge`. Install snippets for this repository are in
  `packages/ir/python/README.md` and `packages/ir/typescript/README.md`.
- `packages/grammar/` (`@velocitron/grammar`, Python `velocitron-grammar`)
  parses `.petrinet` net and composition documents. The canonical grammar is
  `packages/grammar/VelocitronPetriNet.g4`. Lowering ships in `packages/dsl`.
  CEL compilation and resolution ship in `packages/petrinet`.
  Install snippets for this repository are in
  `packages/grammar/python/README.md` and
  `packages/grammar/typescript/README.md`.
- `packages/cel/` (`@velocitron/cel`, Python `velocitron-cel`) compiles and
  evaluates CEL. Engine wiring and DSL produce-cel stay in the language
  implementations. The CEL scan prove uses ships in `packages/analysis`.
  Callers import this package. Install snippets for this repository
  are in `packages/cel/python/README.md` and
  `packages/cel/typescript/README.md`.
- `packages/dsl/` (`@velocitron/dsl`, Python `velocitron-dsl`) lowers
  `.petrinet` text to contribution IR. CEL compilation and contribution
  resolution ship in `packages/petrinet`. The CLI ships in
  `packages/cli`. Callers import this package. Install snippets for this repository are in
  `packages/dsl/python/README.md` and `packages/dsl/typescript/README.md`.
- `packages/petrinet/` (`@velocitron/petrinet`, Python `velocitron-petrinet`)
  compiles `.petrinet` text and contribution IR into canonical JSON and
  validates that JSON. It does not fire a net, check a play, or own the
  CLI. Callers import this package. Install snippets for this repository are in
  `packages/petrinet/python/README.md` and
  `packages/petrinet/typescript/README.md`.
- `packages/play/` (`@velocitron/play`, Python `velocitron-play`) parses
  `.play` documents. The canonical statement grammar is
  `packages/play/VelocitronPlay.g4`. Checking a play and the walkthrough
  ship in `packages/play-check`. Callers import `velocitron_play`. Install snippets for
  this repository are in `packages/play/python/README.md` and
  `packages/play/typescript/README.md`.
- `packages/play-check/` (`@velocitron/play-check`, Python
  `velocitron-play-check`) checks a `.play` against a net and steps a
  walkthrough. It does not parse the grammar, store a journal, or own the
  CLI. Python is the reference for paired Graphviz graphs and PlantUML.
  Callers import this package. not check plays. Install snippets for this repository are in
  `packages/play-check/python/README.md` and
  `packages/play-check/typescript/README.md`.
- `packages/merge/` (`@velocitron/merge`, Python `velocitron-merge`) merges
  already-parsed nets. Parsing, `parse_composition` validation, and CEL
  compilation ship in `packages/petrinet`, which calls this package and
  revalidates the merged net. Install snippets for
  this repository are in `packages/merge/python/README.md` and
  `packages/merge/typescript/README.md`.
- `packages/engine/` (`@velocitron/engine`, Python `velocitron-engine`) fires
  and advances an already-built net. CEL is an injected adapter. Journal
  durability ships in `packages/journal`. `velocitron_runtime.Engine` supplies the default CEL adapter. DSL resolution ships in
  `packages/petrinet`. Install snippets for
  this repository are in `packages/engine/python/README.md` and
  `packages/engine/typescript/README.md`.
- `packages/journal/` (`@velocitron/journal`, Python `velocitron-journal`)
  appends, reads, and replays journal records to a marking. Memory, JSONL,
  and sqlite adapters live here. The async runtime ships in
  `packages/runtime`. `ReplayCursor`, `ReplayBase`, and `replay_run` live in
  `packages/replay`. The browser-safe entry is this package. Install snippets for the private
  monorepo are in `packages/journal/python/README.md` and
  `packages/journal/typescript/README.md`.
- `packages/runtime/` (`@velocitron/runtime`, Python `velocitron-runtime`)
  runs a net asynchronously and evaluates intended waits. It reserves a
  firing, runs the handler, and settles it. The handler registry stays in
  `packages/engine` and is injected. It does not store a journal or call
  `Engine.fire`. `ReplayCursor`, `ReplayBase`, and `replay_run` live in
  `packages/replay`. Install snippets for this repository are in
  `packages/runtime/python/README.md` and
  `packages/runtime/typescript/README.md`.
- `packages/analysis/` (`@velocitron/analysis`, Python `velocitron-analysis`)
  proves choice coverage, place invariants, soundness, and refinement, and
  checks kept records and opt-in lint. The `velocitron prove` command lives
  in `packages/cli`.   The TypeScript package does not explore a net. Install snippets for
  this repository are in `packages/analysis/python/README.md` and
  `packages/analysis/typescript/README.md`.
- `packages/properties/` (`@velocitron/properties`, Python `velocitron-properties`)
  checks declarative properties against a produced marking or a journal
  replay. It does not explore reachable markings. The TypeScript package does not check a marking. Install snippets
  for this repository are in `packages/properties/python/README.md` and
  `packages/properties/typescript/README.md`.
- `packages/explain/` (`@velocitron/explain`, Python `velocitron-explain`)
  renders a validated net as deterministic prose, including enablement from
  a marking. The CLI installs `explain_net` into `velocitron explain`. The TypeScript package does not render
  prose. Install snippets for this repository are in
  `packages/explain/python/README.md` and
  `packages/explain/typescript/README.md`.
- `packages/equiv/` (`@velocitron/equiv`, Python `velocitron-equiv`)
  compares two merged nets up to renaming. The CLI installs `add_parser` and `main` into `velocitron equiv`. The TypeScript package does not compare nets. Install snippets
  for this repository are in `packages/equiv/python/README.md` and
  `packages/equiv/typescript/README.md`.
- `packages/codegen/` (`@velocitron/codegen`, Python `velocitron-codegen`)
  generates one Python base class per net and the sha256 registration
  checks. The `velocitron codegen` command lives in `packages/cli`.
  The TypeScript package does not generate Python. Install snippets for the
  this repository are in `packages/codegen/python/README.md` and
  `packages/codegen/typescript/README.md`.
- `packages/netbase/` (`@velocitron/netbase`, Python `velocitron-netbase`)
  is the registration base a generated Python net extends. `VelocitronNet`
  checks `net_sha256` and adapts methods onto the engine. The digest and
  `SYNTH_HANDLER` stay in `packages/codegen` and are re-exported here.
  Generated modules import `velocitron_netbase`. 
  The TypeScript package does not register a net. Install snippets for the
  this repository are in `packages/netbase/python/README.md` and
  `packages/netbase/typescript/README.md`.
- `packages/replay/` (`@velocitron/replay`, Python `velocitron-replay`)
  replays a recorded run. `ReplayCursor` reads a journal snapshot,
  `ReplayBase` subclasses `VelocitronNet`, and `replay_run` drives
  `Engine.fire`. Generated modules import `velocitron_replay`. The TypeScript package does not replay a tape. Install
  snippets for this repository are in `packages/replay/python/README.md`
  and `packages/replay/typescript/README.md`.
- `packages/viz/` (`@velocitron/viz`, Python `velocitron-viz`) renders an
  already-built net as Graphviz DOT, including fusion copies and authored
  views. The `velocitron-viz` command lives in `packages/cli`. The `velocitron-viz` console script lives in `velocitron-cli`. Install snippets for the private
  monorepo are in `packages/viz/python/README.md` and
  `packages/viz/typescript/README.md`.
- `packages/cli/` (`@velocitron/cli`, Python `velocitron-cli`) dispatches
  `velocitron` and `velocitron-viz`. `main` installs canonical emission from `velocitron_dsl`, the CEL hint
  from `velocitron_cel`, `explain_net` from `velocitron_explain`, and equiv
  from `velocitron_equiv`. The console scripts are `velocitron` and
  `velocitron-viz`. `skill` reads `velocitron_skill.skill_root`. The
  TypeScript package names the subcommands and does not dispatch. Install snippets for this repository are in
  `packages/cli/python/README.md` and
  `packages/cli/typescript/README.md`.
- `packages/skill/` (Python `velocitron-skill`) exposes `skill_root()`,
  the bundled authoring skill. The files stay at `skills/velocitron/`.
  There is no TypeScript package. `skills/README.md` maps how an agent
  uses the packages together. Install snippets for this repository
  are in `packages/skill/python/README.md`.
- `implementations/python/` is the Python integration-test project. It is
  not a library and does not publish `velocitron`.
- `implementations/typescript/` is the TypeScript integration-test project
  (`@velocitron/typescript-tests`, private). It is not `@velocitron/core`.
- `skills/velocitron/` is the authoring skill. `skills/README.md` is the
  map of how the packages fit together for an agent. `velocitron skill`
  installs that tree from `velocitron-skill`.
- `examples/` contains progressively more capable source examples.
- `docs/adr/` records design rationale and history.

## Python from a source checkout

Python 3.12 or newer is required. The console scripts come from
`velocitron-cli` (`packages/cli/python`). With `uv` installed:

```bash
cd implementations/python
uv sync
uv run velocitron validate ../../examples/capability-ladder/01-coin-deposit/coin-deposit.petrinet
```

Install the CLI on its own with `uv tool install packages/cli/python` from a
clone, or the optional CEL extras `velocitron-cli[cel-rust]` and
`velocitron-cel[cel-rust]`. Auto-detection uses that Rust extra when it is
installed, and otherwise bundled celpy. `velocitron-cel[cel-cpp]` stays
installable as a conformance reference and is selected by constructing
`CelExprAdapter` (ADR 0066).

The `velocitron` CLI provides:

- `validate` — validate a JSON or `.petrinet` document;
- `to-json` — lower `.petrinet` to canonical JSON;
- `to-petrinet` — render JSON as canonical `.petrinet`;
- `explain` — explain a document as Markdown or text, and what can happen
  from a marking;
- `check` — check `.petrinet` and `.play` files, and their fenced
  examples in Markdown, for syntax; and
- `skill` — install the bundled Velocitron authoring skill into an existing
  directory.

`velocitron-viz` renders a net or composition JSON/`.petrinet` document as
Graphviz DOT. `velocitron-viz design.petrinet --metrics` prints crossings,
overlaps, edge length, and bends for that drawing. Compare those numbers
only when they come from the same Graphviz version.

Import the Python library from the package that owns the concept:
`velocitron_petrinet`, `velocitron_engine`, `velocitron_runtime` (its
`Engine` fills the default CEL adapter), `velocitron_journal`,
`velocitron_dsl` (`emit_petrinet`), `velocitron_cli`, and the other
`velocitron_*` packages under `packages/`.

## TypeScript and Node from a source checkout

Repository development uses Node 24.15.0 or newer and pnpm 11.13.1 or newer.
The TypeScript packages are private workspace packages. There is no
`@velocitron/core` library.

```bash
corepack enable
pnpm install
pnpm build
pnpm --filter @velocitron/typescript-tests test
```

After a local workspace build, import the package that owns the concept:

```ts
import {compilePetrinetText, parseNet} from "@velocitron/petrinet";
import {HandlerRegistry} from "@velocitron/engine";
import {Engine} from "@velocitron/runtime";

const compiled = compilePetrinetText(
  `net coin_deposit
(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)
[accept_coin] handler "accept_coin"
`,
  "example.petrinet",
);
const net = parseNet(compiled.document);
const engine = new Engine(new HandlerRegistry());
```

`Engine` from `@velocitron/runtime` fills `createDefaultCelAdapter()` when
`celAdapter` is omitted. `@velocitron/engine`'s `Engine` still requires one.

This example describes current source-tree usage. It is not a claim that
these packages are available from a public package registry.

## Feedback and contributions

Browse an example or model a small process of your own, then share what feels
clear, awkward, missing, or misleading. Send broad reactions through an
existing direct channel with the author. Report reproducible defects through
[GitHub Issues](https://github.com/matthewryanscott/velocitron/issues).

External code contributions and pull requests are not accepted yet. These
feedback routes do not create a commitment to review, merge, respond, provide
support, or maintain compatibility. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) for the
current boundaries.

## License and authorship

Velocitron is released under the [MIT License](LICENSE).

Matthew R. Scott is the sole author and copyright holder. Henrique Bastos is
acknowledged for collaboration toward an interoperable Petri-net
specification.
