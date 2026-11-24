# Maintainer guidance

Velocitron is a public 0.1.0 alpha. Favor correctness and explicit contracts
over compatibility scaffolding. APIs, schemas, the DSL, diagnostics, and
capabilities may change, but changes must keep the Python and TypeScript
implementations aligned with the portable contracts in this tree.

## Sources of truth

Read the relevant contract before changing behavior:

- `CONTEXT.md` defines the project's domain vocabulary.
- `packages/spec/net-schema.md` and `packages/spec/net.schema.json` define net
  documents.
- `packages/spec/composition.md` and `packages/spec/composition.schema.json`
  define composition.
- `packages/spec/petrinet-language.md`,
  `packages/spec/petrinet-contribution-ir.schema.json`, and
  `packages/grammar/VelocitronPetriNet.g4` define the `.petrinet` frontend.
- `packages/spec/play-language.md` and `packages/play/VelocitronPlay.g4`
  define the `.play` statement syntax. Checking a play stays in the Python
  implementation.
- `packages/spec/handler-contract.md` and `packages/spec/firing-semantics.md`
  define runtime behavior.
- `packages/spec/properties.md` and `packages/spec/projection-adapter.md`
  define their named surfaces.
- `docs/adr/` records design rationale and history. ADR text is not a promise
  of API stability, compatibility, security support, or maintenance.

Normative prose and schemas take precedence over implementation convenience.
Keep terminology consistent with `CONTEXT.md`.

## Layout

- `packages/spec/` — `@velocitron/spec` / `velocitron-spec`: portable prose
  contracts, JSON Schemas, and conformance data
- `packages/ir/` — `@velocitron/ir` / `velocitron-ir`: contribution-IR wire
  shape loader. CEL compilation and contribution resolution ship in
  `packages/petrinet`. Composition merge ships in `packages/merge`
- `packages/grammar/` — `@velocitron/grammar` / `velocitron-grammar`: the
  ANTLR grammar for `.petrinet` and a syntax parse of net and composition
  documents. Lowering ships in `packages/dsl`. CEL compilation and resolution
  ship in `packages/petrinet`. Composition merge ships in
  `packages/merge`. The `.play` grammar lives in `packages/play`
- `packages/cel/` — `@velocitron/cel` / `velocitron-cel`: the CEL compile/eval
  adapter. Engine wiring and DSL produce-cel stay in the language
  implementations. The CEL scan prove uses ships in `packages/analysis`.
  Those implementations import this package's
  public API. `CachingCelAdapter` and `slow_backend_hint` live in `velocitron_cel`
- `packages/dsl/` — `@velocitron/dsl` / `velocitron-dsl`: lowers `.petrinet`
  text to contribution IR. CEL compilation and contribution resolution
  ship in `packages/petrinet`. Canonical emission (`emit_petrinet`) lives
  here. The CLI ships in `packages/cli` and installs that hook
- `packages/petrinet/` — `@velocitron/petrinet` / `velocitron-petrinet`:
  compiles `.petrinet` text and contribution IR into canonical JSON and
  validates that JSON (`compile_petrinet_text` / `compilePetrinetText`,
  `resolve_contribution_ir` / `resolveContributionIr`, `parse_net` /
  `parseNet`, `parse_composition` / `parseComposition`). It calls `dsl`,
  `cel`, `ir`, `spec`, `engine`, and `merge`. Canonical emission and firing
  stay in the implementations. Play checking ships in `packages/play-check`.
  The CLI ships in `packages/cli`
- `packages/play/` — `@velocitron/play` / `velocitron-play`: the ANTLR
  grammar for one `.play` statement and a dual-language parse to a play AST.
  The line discipline stays in the lowerer. Checking a play and the
  walkthrough live in `packages/play-check`. Callers import `velocitron_play`. Checking a play stays in
  `packages/play-check`
- `packages/play-check/` — `@velocitron/play-check` / `velocitron-play-check`:
  checks a `.play` against a net and steps a walkthrough
  (`check_play` / `checkPlay`, `render_walkthrough` / `renderWalkthrough`).
  It calls `play`, `petrinet`, `engine`, `cel`, `dsl`, `merge`, and, in
  Python, `viz`. `records_to_play` stays in the implementations. The CLI
  ships in `packages/cli`.
- `packages/merge/` — `@velocitron/merge` / `velocitron-merge`: the file-free
  composition merge (`merge_nets` / `mergeNets`, `merge_composition` /
  `mergeComposition`, `port_fusion_map` / `portFusionMap`) over already-parsed
  nets. Parsing, `parse_composition` validation, and CEL compilation ship in
  `packages/petrinet`, which calls this package. The closing net
  revalidation after a merge stays in the language implementations
- `packages/engine/` — `@velocitron/engine` / `velocitron-engine`: the fire /
  advance / enablement core. Python `advance(outputs=)` and
  `symbolic_outputs` are the symbolic-advance seam. CEL is an injected
  adapter; `CachingCelAdapter` and the default adapters stay in the language
  implementations. The CLI ships in `packages/cli`. Journal durability ships in
  `packages/journal`. The async runtime ships in `packages/runtime`. Play checking ships in
  `packages/play-check`. DSL resolution ships in `packages/petrinet`.
  The net render library is
  `packages/viz`. `velocitron_runtime.Engine` subclasses this package and supplies the
  default CEL adapter
- `packages/journal/` — `@velocitron/journal` / `velocitron-journal`:
  journal durability. Append and read journal records, replay them to a
  marking, and store them in memory, JSONL, or sqlite. It calls `engine`
  for record and net shapes. The async runtime ships in `packages/runtime`.
  The handler registry stays in `packages/engine`; the runtime injects it.
  `ReplayCursor`, `ReplayBase`, and `replay_run` live in `packages/replay`:
  they drive `Engine.fire` from a generated net. The browser-safe journal entry is this package.
  The sqlite and JSONL adapters are the Node entry `@velocitron/journal/node`
- `packages/runtime/` — `@velocitron/runtime` / `velocitron-runtime`: the
  async run loop, intended waits, and handler-registry wiring. `Runtime`
  reserves a firing, runs the handler, and settles it. It calls `engine`
  and may call `cel` and `journal`. It does not call `Engine.fire`, store
  records. `Engine` in this package is `velocitron_engine.Engine` with the
  default CEL adapter filled in. `ReplayCursor`, `ReplayBase`, and
  `replay_run` live in `packages/replay`
- `packages/analysis/` — `@velocitron/analysis` / `velocitron-analysis`:
  net analysis. Python `prove` checks choice coverage, place invariants,
  soundness, and refinement, and the package also owns kept records and
  opt-in lint. It calls `engine`, `cel`, `petrinet`, `merge`, and
  `runtime` (intended waits). It revalidates a merged net with
  `validate_net`. The `velocitron prove` command lives in `packages/cli`.
  The TypeScript package reads a proof-report document and
  does not explore a net.
  Produced-marking properties live in `packages/properties`. Enablement
  text lives in `packages/explain`. Structural equivalence lives in
  `packages/equiv`
- `packages/properties/` — `@velocitron/properties` / `velocitron-properties`:
  the declarative property pass (ADR 0019). Python `check_marking`,
  `check_replay`, and `capacity_properties` check markings a system
  produced. It calls `cel`, `engine`, and `journal`. It does not explore a
  net. Callers import `velocitron_properties`. The TypeScript
  package names the checkers and raises `PropertiesUnavailableError`.
- `packages/explain/` — `@velocitron/explain` / `velocitron-explain`:
  human-readable net explanation. Python `explain_net` quotes a validated
  net and, given a marking, asks `Engine.explain_enablement`, passing
  `get_default_adapter()`. It calls `cel` and `engine`. The CLI installs
  `explain_net`. The TypeScript package names `explainNet` and raises
  `ExplainUnavailableError`.
- `packages/equiv/` — `@velocitron/equiv` / `velocitron-equiv`:
  structural equivalence up to renaming (ADR 0042). Python `compare` reads
  merged nets. `add_parser` and `main` are the `velocitron equiv` command
  body. It calls `analysis` (`load`), `dsl`, `engine`, `merge`, and
  `petrinet`. The CLI installs `add_parser` and `main`. The TypeScript package names
  `compare` and `Equivalence` and raises `EquivUnavailableError`.
- `packages/codegen/` — `@velocitron/codegen` / `velocitron-codegen`:
  net codegen. Python `generate_module` and `generate_composition` emit
  one Python module per leaf net or composition file. `net_sha256` is the
  digest registration checks; `velocitron_netbase` re-exports it.
  The package calls `dsl`,
  `engine`, `merge`, `petrinet`, and `viz`, and
  revalidates a merged net with `validate_net`. The `velocitron codegen`
  command lives in `packages/cli`. The TypeScript package names `SYNTH_HANDLER` and does not
  emit a module. Replay lives in
  `packages/replay`; generated modules import `velocitron_replay`
- `packages/netbase/` — `@velocitron/netbase` / `velocitron-netbase`:
  the registration base. Python `VelocitronNet`, `Registration`,
  `HashMismatch`, and `handler_spec` register a generated class and adapt
  its methods. `net_sha256`, `net_document`, `canonical_net_json`, and
  `SYNTH_HANDLER` stay in `velocitron_codegen`; this package re-exports
  them. It calls `cel`, `codegen`, `engine`, and `runtime`.
  Generated modules import `velocitron_netbase`. The TypeScript package re-exports `SYNTH_HANDLER` and
  raises when asked to construct `VelocitronNet`. `ReplayCursor`, `ReplayBase`, and `replay_run`
  live in `packages/replay` and import `velocitron_netbase`
- `packages/replay/` — `@velocitron/replay` / `velocitron-replay`:
  tape replay. Python `ReplayCursor`, `ReplayBase`, and `replay_run` read
  a journal snapshot and drive `Engine.fire`. `ReplayBase` subclasses
  `velocitron_netbase.VelocitronNet`. It calls `cel`, `engine`, `journal`,
  `netbase`, and `petrinet`.   Generated modules import `velocitron_replay`. The TypeScript package
  raises `ReplayUnavailableError` and does not replay a tape.
- `packages/cli/` — `@velocitron/cli` / `velocitron-cli`: the console
  commands. Python `main` is `velocitron` and `viz_main` is
  `velocitron-viz`. It calls `analysis`, `codegen`, `dsl`, `engine`,
  `merge`, `petrinet`, `play`, `play-check`, `runtime`, `skill`, and
  `viz`, and revalidates a merged net with `validate_net`. Canonical
  emission (`emit_petrinet` from `velocitron_dsl`), explain, equiv, and the
  CEL backend hint. `main` installs those hooks. `skill` reads
  `velocitron_skill.skill_root` unless `configure(skill_source=...)`
  overrides it. The TypeScript package names the subcommands and does not
  dispatch. The console scripts are `velocitron = velocitron_cli:main` and
  `velocitron-viz = velocitron_cli:viz_main`
- `packages/skill/` — `velocitron-skill`: the skill-directory seam.
  `skill_root()` returns the bundled authoring skill. The files stay at
  `skills/velocitron/`; this package symlinks that tree and ships it.
  There is no TypeScript package. The CLI calls `skill_root`
- `packages/viz/` — `@velocitron/viz` / `velocitron-viz`: the net → view /
  render library. Python `net_to_dot` / `apply_view` and TypeScript
  `netToDot` / `applyView` draw an already-built net, including fusion
  copies and authored views. The Python package also draws composition
  diagrams, the legend, and paired graphs. The TypeScript package is a
  port of the standalone-net surface. Document loading and the
  `velocitron-viz` command live in `packages/cli`. The play walkthrough ships
  in `packages/play-check`.
  The `velocitron-viz` console script lives in `packages/cli`
- `implementations/python/` — integration tests (`velocitron-python-tests`, not a library)
- `implementations/typescript/` — integration tests (`@velocitron/typescript-tests`, private)
- `examples/` — source examples arranged by capability
- `skills/velocitron/` — the authoring skill (primers, kitchen-sink
  examples, language notes). This is the agent composition layer: it shows
  how the packages fit together when an agent authors or checks a net.
  `skills/README.md` is the starting map. `packages/skill` ships the tree.
  The skill area stays in this repository
- `docs/adr/` — architectural decision records
- `tools/` — repository generation and consistency tools

## Tests

Run each implementation's tests from its own directory:

```bash
cd implementations/python
uv run pytest
```

```bash
cd implementations/typescript
pnpm test
```

The contribution-IR shape packages have their own suites:

```bash
cd packages/ir/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/ir test
```

The grammar packages have their own suites:

```bash
cd packages/grammar/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/grammar test
```

The CEL adapter packages have their own suites:

```bash
cd packages/cel/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/cel test
```

The DSL lowering packages have their own suites:

```bash
cd packages/dsl/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/dsl test
```

The `.petrinet` compile packages have their own suites:

```bash
cd packages/petrinet/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/petrinet test
```

The composition-merge packages have their own suites:

```bash
cd packages/merge/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/merge test
```

The play language packages have their own suites:

```bash
cd packages/play/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/play test
```

The play-check packages have their own suites:

```bash
cd packages/play-check/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/play-check test
```

The firing-engine packages have their own suites:

```bash
cd packages/engine/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/engine test
```

The journal packages have their own suites:

```bash
cd packages/journal/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/journal test
```

The async-runtime packages have their own suites:

```bash
cd packages/runtime/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/runtime test
```

The analysis packages have their own suites:

```bash
cd packages/analysis/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/analysis test
```

The property-pass packages have their own suites:

```bash
cd packages/properties/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/properties test
```

The net-explanation packages have their own suites:

```bash
cd packages/explain/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/explain test
```

The structural-equivalence packages have their own suites:

```bash
cd packages/equiv/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/equiv test
```

The codegen packages have their own suites:

```bash
cd packages/codegen/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/codegen test
```

The registration-base packages have their own suites:

```bash
cd packages/netbase/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/netbase test
```

The tape-replay packages have their own suites:

```bash
cd packages/replay/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/replay test
```

The CLI packages have their own suites:

```bash
cd packages/cli/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/cli test
```

The skill package has its own suite. There is no TypeScript skill package:

```bash
cd packages/skill/python
uv run --locked --no-editable --group test pytest
```

The net-render packages have their own suites:

```bash
cd packages/viz/python
uv run --locked --no-editable --group test pytest
```

```bash
pnpm --filter @velocitron/viz test
```

Tests use BDD phase comments as readable delimiters. Keep setup under
`# given:` / `// given:`, the exercised action under `# when:` / `// when:`,
and assertions under `# then:` / `// then:`. Use `and:` comments for additional
steps in the same phase. Test observable behavior and use minimal fixtures;
keep temporary filesystem work isolated to test-provided temporary paths.

## Generated artifacts and schemas

Generated sources are committed because they are part of the distributable
packages. Do not hide or remove them and do not hand-edit them.

- Edit `packages/grammar/VelocitronPetriNet.g4`, then regenerate the Python
  ANTLR output with `python3 tools/antlr.py generate` and the TypeScript
  output with `python3 tools/antlr.py generate-typescript` from the repository
  root. Each command also refreshes the grammar-file copy inside that
  language package. Generation writes the parser into `packages/grammar` and
  into `packages/dsl` (the lowerer vendors a parser). The same commands
  regenerate `packages/play/VelocitronPlay.g4` into `packages/play`.
  `check` and `check-typescript`
  fail if the grammar package and the DSL package drift apart.
- Treat `packages/spec/net.schema.json`, `packages/spec/composition.schema.json`,
  and `packages/spec/petrinet-contribution-ir.schema.json` as the canonical
  schema inputs.
  `python3 tools/generate-schemas-python.py` copies the contribution-IR schema
  into `packages/ir/python` and `packages/ir/typescript`. Python runtime code
  reads the schemas through `velocitron_spec`. `--check` gates the Python test
  suite. Regenerate TypeScript schema artifacts with `pnpm generate:schema`
  and `pnpm generate:ir-schema` from `implementations/typescript/`. Those
  commands write Ajv validators into `packages/petrinet/typescript/src/generated/`.
- Generated TypeScript Ajv validators live in
  `packages/petrinet/typescript/src/generated/`. ANTLR output under
  `packages/grammar/{python,typescript}`, `packages/dsl/{python,typescript}`,
  and `packages/play`, must match their sources.
- The packages under `packages/` are the source of truth for spec, ir,
  grammar, cel, dsl, petrinet, play, play-check, merge, engine, journal, runtime, analysis, properties, explain, equiv, codegen, netbase, replay, viz, cli, and skill.
  There is no published `velocitron` or `@velocitron/core` library.
  `velocitron_runtime.Engine` fills the default CEL adapter.
  `velocitron_petrinet` revalidates a merged net. `velocitron_cli` hosts
  the console scripts. `python3 tools/cel_package.py check` (and the
  dsl, petrinet, merge, play, play-check, engine, journal, runtime, analysis, properties, explain, equiv, codegen, netbase, replay, viz, cli, and skill twins) fail when
  a retired facade tree or a forbidden definition returns.
  `sync` refuses to copy a package out of a facade. Edit the package, then
  re-lock the dependents.
- Who may import whom is `layers.yaml`. `python3 tools/layer_lint.py` fails
  on a cycle, an edge outside that allow-list, or a cross-layer import below
  the package root. Update the list as `docs/layers.md` describes when a
  new package lands.
- The CLIs ship in `packages/cli`. Console scripts are `velocitron` and
  `velocitron-viz`. `main` installs canonical emission from
  `velocitron_dsl`, `explain_net` from `velocitron_explain`, equiv from
  `velocitron_equiv`, and the CEL backend hint from `velocitron_cel`.
  Skill-path resolution ships in `packages/skill` (`skill_root`); the CLI
  passes that function. The authoring tree stays at
  `skills/velocitron/`. The async runtime ships in
  `packages/runtime`. Journal durability ships in `packages/journal`.
  Net analysis ships in `packages/analysis`. The `velocitron prove`
  command lives in `packages/cli`. Net codegen ships in `packages/codegen`.
  The `velocitron codegen` command lives in `packages/cli`. `net_sha256`
  lives in `velocitron_codegen`. `velocitron_netbase` re-exports it.
  `VelocitronNet` lives in `velocitron_netbase`. `ReplayCursor`,
  `ReplayBase`, and `replay_run` live in `velocitron_replay`. Generated
  modules import `velocitron_replay`.
  Contribution resolution ships in `packages/petrinet`. The engine package
  requires an injected CEL adapter. `velocitron_runtime.Engine` fills the
  default. The TypeScript proof-report reader is `@velocitron/analysis`.

A contract change is incomplete until affected prose, schemas, generated
artifacts, both implementations, conformance fixtures, examples, and tests are
consistent.

## Public-alpha boundaries

Broad feedback and reproducible defect reports are welcome. External code
contributions and pull requests are not accepted yet. Do not imply that a
report will receive a response or that a proposed change will be reviewed or
merged. Security and support expectations are defined in `SECURITY.md` and
`CONTRIBUTING.md`; support is best-effort and this alpha is not intended for
production or sensitive workloads.
