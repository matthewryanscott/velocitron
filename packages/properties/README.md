# `packages/properties`

The declarative property pass (ADR 0019), in two language packages:

- [`python/`](python/) — distribution `velocitron-properties`, import `velocitron_properties`
- [`typescript/`](typescript/) — package `@velocitron/properties` (`"private": true`)

`check_marking` checks one produced marking. `check_replay` reconstructs
intermediate markings from journal records and checks those too.
`capacity_properties` reads `capacityPerColorKey`. A violation is a finding.
The engine never reads a property.

The TypeScript package raises `PropertiesUnavailableError` for those names.
It does not check a marking.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`velocitron.properties` re-exports this public seam. `@velocitron/core`
re-exports the TypeScript marker. `python3 tools/properties_package.py check`
fails if the umbrella grows the checker back.

## Why this is its own package

The pass imports `cel`, `engine`, and `journal`. `velocitron_analysis`
proves markings a net can reach and does not import `journal`. Keeping the
property pass here leaves the prover's allow list unchanged.

## What this package owns

- `check_marking`, `check_replay`, and `capacity_properties`
- `AtMostN`, `PlaceEmpty`, `EventuallyReaches`, `MarkingInvariant`,
  `KeyCorrelation`, `FiringBinding`, `PropertyReport`, and `PropertyViolation`

## What stays outside

Reachability proofs stay in `packages/analysis`. Journal storage stays in
`packages/journal`. This package reads record types and reconstructs
markings itself. The firing engine stays in `packages/engine`.

## Non-goals

This package does not explore a reachable marking, append a journal, or
port the checker to TypeScript.
