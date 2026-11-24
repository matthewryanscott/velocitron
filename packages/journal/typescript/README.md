# `@velocitron/journal`

Append, read, and replay a Velocitron journal. The Python distribution name
is `velocitron-journal` (import `velocitron_journal`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the
`packages/journal/typescript` subdirectory.

Version 0.1.0 is alpha software. The journal may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

The package root is browser-safe:

- `InMemoryJournal` appends firing, deposit-violation, and injection records
  on one sequence stream.
- `replayRecords` / `replayEvents` rebuild a marking from those records. A
  completed firing consumes only `mode: "consume"` inputs. An injection
  appends, or replaces when its kind is `update`. Failed firings, traces,
  and net revisions do nothing. No handler runs.

`@velocitron/journal/node` is the Node entry:

- `DurableJournal`, `openDatabase`, `readEvents`, and `knownInstances` use
  `node:sqlite`.
- `JsonlJournal` buffers the same channels, plus trace, runtime, and net
  revision, and flushes a timestamped `.jsonl` file.

`@velocitron/engine` supplies the record and net types. This package does
not depend on a CEL adapter.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/journal test` does that build. A git
install runs the `prepare` script, which is the same build.

## What stays outside

This package does not fire a net or run an async runtime
(`@velocitron/runtime` does). `@velocitron/core`
re-exports the browser-safe entry only. Python `ReplayCursor`, `ReplayBase`,
and `replay_run` live in `velocitron_replay` because they drive `Engine`
and subclass `velocitron_netbase.VelocitronNet`. Play checking,
analysis, and the CLI stay outside too. Codegen ships in
`@velocitron/codegen` and does not emit a module from TypeScript.
`python3 tools/journal_package.py check` fails if the umbrella grows the
journal back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. Install `@velocitron/engine` from
`packages/engine/typescript` the same way.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/journal": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/journal/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/journal": "github:circuitmeridian/velocitron#<ref>&path:packages/journal/typescript"
  }
}
```

```typescript
import {InMemoryJournal, replayRecords, type Net} from "@velocitron/journal";

export function folded(net: Net, journal: InMemoryJournal) {
  return replayRecords(net, journal.records);
}
```

Node sqlite:

```typescript
import {replayEvents, type Net} from "@velocitron/journal";
import {DurableJournal, openDatabase, readEvents} from "@velocitron/journal/node";

export function folded(net: Net): ReturnType<typeof replayEvents> {
  const database = openDatabase("events.db");
  const journal = new DurableJournal(database, "lane-1");
  return replayEvents(net, readEvents(database, "lane-1"));
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
