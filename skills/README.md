# Skill area

`skills/velocitron/` is the Velocitron authoring skill and the agent
composition layer for this monorepo. Primers, language notes, and the
kitchen-sink net show how the packages fit together when an agent authors,
checks, proves, or runs a net. The tree stays in this repository.
`packages/skill` ships it. The libraries do not import it.

## Home and resolution

| Path | Role |
| --- | --- |
| `skills/velocitron/` | Authoring source of truth (`SKILL.md`, primers, examples, `scripts/`) |
| `packages/skill` | `velocitron-skill` / `skill_root()` — the directory the CLI copies |
| `velocitron skill <dir>` | Installs that directory at `<dir>/velocitron/` |

`packages/skill/python/src/velocitron_skill/skill` is a symlink to
`skills/velocitron/`. Hatchling follows it, so the wheel contains the
files and an editable install reads the same tree. There is one copy of
the content. There is no TypeScript skill package: the shipped surface is
the path.

The CLI calls `skill_root()` unless `configure(skill_source=...)` overrides
it. `velocitron-cli` does not package a second copy of the skill tree.

## Where to start

Read `skills/velocitron/SKILL.md`, then the primer that matches the task
(`petrinet-language.md`, `play-language.md`, `proofs.md`,
`engine-runtime-primer.md`). `CONTEXT.md` is the domain vocabulary.
`packages/spec/` is the normative contract. `docs/adr/` is design history.
`docs/layers.md` and `layers.yaml` are the import allow-list. `AGENTS.md`
is the maintainer layout.

## How the packages relate

An authoring session moves from text to a net, then to a check, a proof,
or a run. Each row is a package the skill's examples assume.

| Package | What an agent uses it for |
| --- | --- |
| `packages/spec` | Schemas, prose contracts, conformance |
| `packages/grammar`, `packages/dsl`, `packages/ir` | `.petrinet` syntax and contribution IR |
| `packages/cel` | CEL compile and eval, injected into the engine |
| `packages/petrinet` | Compile and validate a net or composition document |
| `packages/merge` | Merge an already-parsed composition |
| `packages/play`, `packages/play-check` | Parse a `.play` and check it against a net |
| `packages/engine` | Enablement, `fire`, `advance` |
| `packages/journal` | Append and replay journal records |
| `packages/runtime` | Async run loop and intended waits |
| `packages/analysis` | Prove, kept records, opt-in lint |
| `packages/codegen` | One Python module per net, and `net_sha256` |
| `packages/netbase` | `VelocitronNet`, the registration base |
| `packages/viz` | Graphviz DOT for an already-built net |
| `packages/cli` | `velocitron` and `velocitron-viz` |
| `packages/skill` | Find this directory |

Import direction runs from the CLI toward those libraries. `skill` imports
none of them. `cli` may import `skill`. `velocitron_cli` calls
`skill_root` unless `configure(skill_source=...)` overrides it. There is
no TypeScript loader for this tree.

`velocitron_cli.main` installs canonical emission (`emit_petrinet` from
`velocitron_dsl`), explain, equiv, and the CEL backend hint. Replay lives
in `packages/replay`. Properties live in `packages/properties`.
`VelocitronNet` lives in `packages/netbase`. Generated modules import
`velocitron_netbase`.
