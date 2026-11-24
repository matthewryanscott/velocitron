# `packages/engine`

The Petri-net firing engine, in two language packages:

- [`python/`](python/) — distribution `velocitron-engine`, import `velocitron_engine`
- [`typescript/`](typescript/) — package `@velocitron/engine` (`"private": true`)

`Engine` detects enablement, selects a binding, fires, and repeats.
Python `advance(outputs=)` is the symbolic-advance seam;
`symbolic_outputs` is the carry rule for a handlerless firing. TypeScript
`run` is the selection loop. Both require an injected CEL adapter.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`velocitron_runtime.Engine` and `@velocitron/runtime`'s `Engine` subclass
this package and supply the default CEL adapter. This package still
requires one. `python3 tools/engine_package.py check` fails if the retired
facade trees return. `CachingCelAdapter` and `get_default_adapter` live in
`velocitron_cel`. `createDefaultCelAdapter` lives in `@velocitron/cel`.
Journal durability
ships in `packages/journal`. The async runtime ships in `packages/runtime`.
The CLI ships in `packages/cli`. Play checking ships in
`packages/play-check`. DSL
resolution ships in `packages/petrinet`. The net render library is
`packages/viz`.
