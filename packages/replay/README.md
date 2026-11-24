# `packages/replay`

Tape replay, in two language packages:

- [`python/`](python/) — distribution `velocitron-replay`, import `velocitron_replay`
- [`typescript/`](typescript/) — package `@velocitron/replay` (`"private": true`)

`ReplayCursor` reads one journal snapshot. `ReplayBase` subclasses
`velocitron_netbase.VelocitronNet` and answers handler calls from that tape.
`replay_run` drives `Engine.fire` between the recorded injections.

The TypeScript package raises `ReplayUnavailableError` for those names. It
does not replay a tape. ADR 0058 leaves a TypeScript runtime off the roadmap.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`velocitron.replay` re-exports this public seam. Generated `Replay<Net>`
modules still import that name. `@velocitron/core` re-exports the TypeScript
marker. `python3 tools/replay_package.py check` fails if the umbrella grows
the driver back.

## What this package owns

- `ReplayCursor`, `ReplayBase`, and `replay_run`
- `ReplayOrderError`, `ReplayNetMismatch`, `Divergence`, and `ReplayResult`

## What stays outside

Journal storage stays in `packages/journal`. That package only folds records
into a marking, so it does not drive `Engine.fire`. The async runtime stays
in `packages/runtime` and does not call `Engine.fire`. The registration base
stays in `packages/netbase`. `parse_net` stays in `packages/petrinet`.
Properties live in `packages/properties`. Enablement text lives in
`packages/explain`. Structural equivalence lives in `packages/equiv`.
The authoring skill ships in `velocitron-skill`.

## Non-goals

This package does not append journal records, reserve an async firing, or
register a net. It does not port the driver to TypeScript.
