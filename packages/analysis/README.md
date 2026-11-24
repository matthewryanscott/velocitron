# `packages/analysis`

Net analysis, in two language packages:

- [`python/`](python/) — distribution `velocitron-analysis`, import `velocitron_analysis`
- [`typescript/`](typescript/) — package `@velocitron/analysis` (`"private": true`)

`prove` checks markings a net can reach: choice coverage, place invariants,
soundness of one lifecycle, and the soundness of each refinement. `lint_net`
is the opt-in static lint. `kept_records` reads a place the net itself keeps.
The Python package is the prover. The TypeScript package reads the proof
report document from `packages/spec/proofs.md`. It does not explore a net.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

Callers import `velocitron_analysis`. The `velocitron prove` command lives
in `packages/cli`. The TypeScript package reads a proof report and does
not prove a net. `python3 tools/analysis_package.py check` fails if a
retired facade grows the prover, the kept-record checks, or the lint back.

## What this package checks

- Choice coverage, including intended waits
- Place invariants, declared and derived
- Soundness of one lifecycle instance, explored through the engine
- Refinement soundness of a composition
- Kept records and shares of kept records
- Advisory lint findings

## What stays outside

`velocitron prove` lives in `velocitron_cli`. Produced-marking properties live in
`packages/properties`. Enablement text lives in `packages/explain`.
Structural equivalence lives in `packages/equiv` and calls `load` from
this package. Codegen ships in
`packages/codegen`. Replay lives in `packages/replay`. The authoring
skill ships in `velocitron-skill`. `CachingCelAdapter` lives in `velocitron-cel`;
the prover keeps its own private result cache.
