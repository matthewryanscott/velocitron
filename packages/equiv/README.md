# `packages/equiv`

Structural equivalence of two merged nets (ADR 0042), in two language
packages:

- [`python/`](python/) — distribution `velocitron-equiv`, import `velocitron_equiv`
- [`typescript/`](typescript/) — package `@velocitron/equiv` (`"private": true`)

`compare` maps places, transitions, and arcs by local name and compares
behavior facts. Ports are interface and do not count against equivalence.
`main` loads both sides with `velocitron_analysis.load`.

The TypeScript package raises `EquivUnavailableError` from `compare` and
`Equivalence`. It does not compare nets.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`velocitron.equiv` re-exports this public seam. The umbrella console entry
injects `add_parser` and `main` into `velocitron equiv`. `@velocitron/core`
re-exports the TypeScript marker. `python3 tools/equiv_package.py check`
fails if the umbrella grows the check back.

## Why this is its own package

`compare` and `main` import `analysis`, `dsl`, `engine`, `merge`, and
`petrinet`. The dependency on `velocitron_analysis.load` points at the
prover. `velocitron_analysis` keeps its existing allow list.

## What this package owns

- `compare` and `Equivalence`
- `add_parser` and `main`, the `velocitron equiv` command body

## What stays outside

Loading and merging a composition stay in `packages/analysis`,
`packages/petrinet`, and `packages/merge`. The argv dispatcher stays in
`packages/cli`. The umbrella injects this command.

## Non-goals

This package does not compare reachable markings, and it does not port the
check to TypeScript.
