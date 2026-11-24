# Contributing

Browse an example or model a small process of your own, then share what feels
clear, awkward, missing, or misleading. Send broad reactions through an
existing direct channel with the author. Report reproducible defects through
[GitHub Issues](https://github.com/circuitmeridian/velocitron/issues),
especially reports that include the affected version, input, command or API
call, expected result, actual result, and a minimal reproduction when
practical.

External code contributions and pull requests are not accepted yet. Please do
not submit code on the assumption that it will be reviewed or merged.

These feedback routes do not create a commitment to review, merge, respond,
provide support, or maintain compatibility. Any response is best-effort.

For potential vulnerabilities, follow [SECURITY.md](SECURITY.md) rather than
publishing exploit details.

## Regenerating the parsers

`tools/antlr.py` regenerates the committed ANTLR parsers from
`packages/grammar/VelocitronPetriNet.g4` and
`packages/play/VelocitronPlay.g4`. Run it from the repository root.
`generate` writes the Python petrinet parser into `packages/grammar/python`
and `packages/dsl/python`, and the play parser into `packages/play/python`.
`generate-typescript` writes the TypeScript petrinet parser into
`packages/grammar/typescript` and `packages/dsl/typescript`, and the play
parser into `packages/play/typescript`. Both commands refresh the grammar-file
copy each language package ships. No published library carries a generated
parser:

```bash
python3 tools/antlr.py generate             # Python parser
python3 tools/antlr.py check                # Python parser matches the grammar
python3 tools/antlr.py generate-typescript  # TypeScript parser
python3 tools/antlr.py check-typescript     # TypeScript parser matches the grammar
```

The tool needs Java 11 or newer, and `pre-commit` on PATH: it formats the
Python parser with the Ruff version pinned in `.pre-commit-config.yaml`. It
looks for Java in `$JAVA_HOME/bin/java`, then `java` on PATH, then Homebrew's
openjdk (`/opt/homebrew/opt/openjdk/bin/java` or
`/usr/local/opt/openjdk/bin/java`). On macOS, `brew install openjdk` is
enough; you do not need to link it onto PATH. The tool downloads the ANTLR jar
once and checks its checksum.

## Packages are the source of truth

`packages/{spec,ir,grammar,cel,dsl,petrinet,play,play-check,merge,engine,journal,runtime,analysis,properties,explain,equiv,codegen,netbase,replay,viz,cli,skill}` own the
implementations. Import `velocitron_*` or `@velocitron/*`. There is no
published `velocitron` or `@velocitron/core` library. A second copy of a
package body may not return under `implementations/`.

```bash
python3 tools/cel_package.py check
python3 tools/dsl_package.py check
python3 tools/petrinet_package.py check
python3 tools/merge_package.py check
python3 tools/play_package.py check
python3 tools/play_check_package.py check
python3 tools/engine_package.py check
python3 tools/journal_package.py check
python3 tools/runtime_package.py check
python3 tools/analysis_package.py check
python3 tools/properties_package.py check
python3 tools/explain_package.py check
python3 tools/equiv_package.py check
python3 tools/codegen_package.py check
python3 tools/netbase_package.py check
python3 tools/replay_package.py check
python3 tools/viz_package.py check
python3 tools/cli_package.py check
python3 tools/skill_package.py check
```

Each `check` fails if a facade tree returns or a forbidden definition
reappears under `implementations/`. `sync` exits with an error: copying out
of a facade is retired. Edit the package, then re-lock the dependents
(`uv lock` in `implementations/python`, and in `packages/petrinet/python`,
`packages/merge/python`, `packages/play-check/python`,
`packages/journal/python`, `packages/runtime/python`,
`packages/analysis/python`, `packages/properties/python`,
`packages/explain/python`, `packages/equiv/python`,
`packages/codegen/python`, `packages/netbase/python`,
`packages/replay/python`, `packages/viz/python`, `packages/cli/python`,
or `packages/skill/python` when a package they depend on changes).

`CachingCelAdapter` and the CLI backend hint live in `velocitron-cel`.
Prove, the CEL scan it uses, kept records, and lint ship in
`velocitron-analysis`. The `velocitron prove` command lives in
`velocitron-cli`. Net codegen and `net_sha256` ship in
`velocitron-codegen`. `VelocitronNet` ships in `velocitron-netbase`, which
re-exports that digest. Generated modules import `velocitron_netbase`.
`ReplayCursor`, `ReplayBase`, and `replay_run` ship in `velocitron-replay`.
Generated modules import `velocitron_replay`. `check_marking` ships in
`velocitron-properties`. `explain_net` ships in `velocitron-explain`.
`compare` ships in `velocitron-equiv`. `velocitron_cli.main` installs
`explain_net`, equiv's `add_parser` and `main`, canonical emission, and
the CEL backend hint. Canonical emission (`emit_petrinet`) ships in
`velocitron-dsl`. The console scripts `velocitron` and `velocitron-viz`
ship in `velocitron-cli`. The skill directory ships in `velocitron-skill`
(`skills/velocitron/` is the authoring tree). The CLI calls `skill_root`
unless `configure(skill_source=...)` overrides it. Parsing,
`parse_composition` validation, CEL compilation, and the validating merge
wrappers ship in `packages/petrinet`, which calls `velocitron_merge` /
`@velocitron/merge` and then `validate_net`. Checking a play, the
walkthrough, `records_to_play`, and the sequence diagram ship in
`velocitron-play-check`. Journal durability ships in `velocitron-journal`.
The async runtime ships in `velocitron-runtime`. That package's `Engine`
fills `get_default_adapter()` / `createDefaultCelAdapter()` when the caller
omits an adapter. `velocitron_engine.Engine` still requires one.
Document loading and the `velocitron-viz` command live in `velocitron-cli`.

`layers.yaml` lists who may import whom. There is no umbrella layer.
`python3 tools/layer_lint.py` fails on a cycle, an edge outside that list,
or a cross-layer import below the package root. When a new package lands,
update the list as `docs/layers.md` describes.

## Refreshing the release allowlist

`tools/release-allowlist.json` lists every file in the `velocitron-cli`
wheel and sdist. There is no npm library artifact. After you add or remove
a packaged file, build the artifacts and run
`python3 tools/refresh_allowlist.py ARTIFACT_ROOT`. The build commands are in
the script's docstring.

## Measuring the prover

`tools/prover_bench.py` proves each net of the benchmark set
(`benchmarks/prover/set.json5`) and prints its markings, edges, wall time,
peak memory and each proof's result:

```bash
uv run --project implementations/python python tools/prover_bench.py
```

`nox -s prover_bench` runs the same command. It fails when a net's markings,
edges or results differ from `benchmarks/prover/numbers/counts.jsonl`; time
and memory are printed beside `timings.jsonl` and never fail it. `--quick`
leaves out the nets recorded at over a minute. After a change to the prover
that changes what it explores or answers, run it with `--record` and say in
the review why the counts moved; record timings on an otherwise idle
machine. A net the set marks `fastOnly` runs on the fast path alone, as the
reference would take too long on it: a reference run leaves it out, and
`--fast --record` records it, and only it. A full record is both commands,
`--record` and then `--fast --record`.
