# `packages/codegen`

Net codegen, in two language packages:

- [`python/`](python/) — distribution `velocitron-codegen`, import `velocitron_codegen`
- [`typescript/`](typescript/) — package `@velocitron/codegen` (`"private": true`)

`generate_module` writes one Python module for a leaf net. `generate_composition`
writes one module per composition file. `net_sha256` is the digest a generated
class and `VelocitronNet` registration both check. The TypeScript package
shares the synthesized-handler prefix and the `RefinedAway` name. It does not
emit Python.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. Each language
README has the install snippet.

Callers import `velocitron_codegen`. `velocitron_netbase` re-exports the
digest. Generated modules import `velocitron_netbase` and
`velocitron_replay`. The `velocitron codegen` command lives in
`packages/cli`. The TypeScript package does not emit a module.
`python3 tools/codegen_package.py check` fails if a retired facade grows
the generator back.

## What this package emits

- One abstract base class per leaf net
- Generated handlers for transitions that have no `handler` fact
- One composition class per composition file, with member instances,
  `build_registry`, and a `RefinedAway` mixin per refined transition
- The canonical net document and its sha256

## What stays outside

`velocitron codegen` lives in `velocitron_cli` and is re-exported from
`velocitron.codegen.cli`. Generated modules
still import `velocitron.netbase.VelocitronNet`, replay, and the runtime.
`VelocitronNet` lives in `velocitron_netbase`; the umbrella re-exports it.
Replay lives in `velocitron_replay`; `velocitron.replay` re-exports it.
The TypeScript package does not port
the emitter: the output is Python, and ADR 0058 leaves a TypeScript
generator off the roadmap. Properties, explain, and equiv stay
in the implementations. The authoring skill ships in `velocitron-skill`.
