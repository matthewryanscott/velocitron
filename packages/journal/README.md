# `packages/journal`

Journal durability, in two language packages:

- [`python/`](python/) — distribution `velocitron-journal`, import `velocitron_journal`
- [`typescript/`](typescript/) — package `@velocitron/journal` (`"private": true`)

Append a firing, injection, or net revision. Read the records back. Replay
them to a marking without calling handlers. Store them in memory, in a
JSONL file, or in sqlite.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. Each language
README has the install snippet.

Callers import `velocitron_journal` or `@velocitron/journal`. The sqlite
adapter and the JSONL flush are `@velocitron/journal/node`.
`python3 tools/journal_package.py check` fails if a retired facade grows
the journal back.

## What stays outside

The firing engine stays in `packages/engine`. It emits record shapes and
does not choose storage. The async runtime ships in `packages/runtime`.
The handler registry stays in `packages/engine`; the runtime injects it.
`ReplayCursor`, `ReplayBase`, and `replay_run` live in `packages/replay`
because that driver subclasses `VelocitronNet` and calls `Engine.fire`.
Putting them here would make this package fire a net. This
package only folds recorded effects into a marking. Play checking stays in
`packages/play-check`. Analysis ships in `packages/analysis`. Codegen ships
in `packages/codegen`. The CLI ships in `packages/cli`.
