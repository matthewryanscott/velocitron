# `packages/netbase`

The registration base a generated Python net extends, in two language packages:

- [`python/`](python/) — distribution `velocitron-netbase`, import `velocitron_netbase`
- [`typescript/`](typescript/) — package `@velocitron/netbase` (`"private": true`)

`VelocitronNet.register_into` checks `net_sha256`, copies the net, stamps
`velocitron:synth:` refs, and adapts methods onto a `HandlerRegistry`.
`handler_spec` declares an async method's lane. `HashMismatch` is the digest
gate. The TypeScript package re-exports `SYNTH_HANDLER` and raises
`NetbaseUnavailableError` for the registration classes. It does not register
a net.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`net_document`, `canonical_net_json`, `net_sha256`, and `SYNTH_HANDLER`
live in `velocitron_codegen`. This package re-exports them so registration
checks the same digest the generator stamps. Generated modules import
`velocitron_netbase`. `python3 tools/netbase_package.py check` fails if a
retired facade grows the base class back.

## What this package owns

- `VelocitronNet`, `Registration`, `HashMismatch`, and `handler_spec`
- The sync adapter and the async `HandlerSpec` table
- The `NotThisActor` synthesized handler

## What stays outside

`net_sha256` and `SYNTH_HANDLER` stay in `packages/codegen`. Replay
(`ReplayCursor`, `ReplayBase`, `replay_run`) lives in `packages/replay`
and imports this package. Properties, explain, and equiv stay in the
implementations. The TypeScript package does not port the adapter: ADR
0058 leaves a TypeScript runtime off the roadmap. The authoring skill
ships in `velocitron-skill`.
