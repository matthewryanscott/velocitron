# `packages/runtime`

The async runtime, in two language packages:

- [`python/`](python/) — distribution `velocitron-runtime`, import `velocitron_runtime`
- [`typescript/`](typescript/) — package `@velocitron/runtime` (`"private": true`)

`Runtime` owns one net's marking. It reserves consume-mode inputs, runs the
handler, and settles that reservation. Intended waits read a transition's
`wait` annotation and evaluate its CEL condition. The handler registry is
injected; this package does not own `HandlerRegistry`.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`Engine` in this package is `velocitron_engine.Engine` /
`@velocitron/engine`'s `Engine` with the default CEL adapter filled in.
Pass `cel_adapter` / `celAdapter` to select a backend. The firing core
still requires an adapter. `python3 tools/runtime_package.py check` fails
if the retired facade trees return.

## What stays outside

Journal storage stays in `packages/journal`. The firing engine stays in
`packages/engine`. `Runtime` calls `reserve` / `settle` and does not call
`Engine.fire`.

`ReplayCursor`, `ReplayBase`, and `replay_run` live in `packages/replay`.
`ReplayBase` subclasses `velocitron_netbase.VelocitronNet`, the registration
base codegen emits, and `replay_run` drives `Engine.fire` from a tape.
`packages/journal`
only folds records into a marking, so those types do not belong there.
This package does not call `Engine.fire` and cannot import the umbrella.
Analysis, codegen, the CLI, and play checking stay in their own packages.
Codegen ships in `packages/codegen`.

`HandlerRegistry` stays in `packages/engine`. Callers import
`velocitron_engine` / `@velocitron/engine`.
