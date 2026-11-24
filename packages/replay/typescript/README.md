# `@velocitron/replay`

Name the Velocitron tape-replay seam. The Python distribution name is
`velocitron-replay` (import `velocitron_replay`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the
`packages/replay/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`ReplayCursor`, `ReplayBase`, `ReplayOrderError`, `ReplayNetMismatch`,
`Divergence`, `ReplayResult`, and `replayRun` raise `ReplayUnavailableError`.

This package does not read a journal, subclass `VelocitronNet`, or call
`Engine.fire`. The Python driver does that with `velocitron_journal`,
`velocitron_netbase`, and `velocitron_engine`. Porting it would be a second
runtime. ADR 0058 leaves TypeScript codegen, and a TypeScript replay driver,
off the roadmap.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/replay test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/replay_package.py check` fails if the umbrella grows a
`ReplayCursor` class back.

## What stays in the language implementations

`velocitron.replay` re-exports the Python package. Generated modules still
import that name. `@velocitron/core` re-exports this marker and does not
replay a tape.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/replay": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/replay/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/replay": "github:circuitmeridian/velocitron#<ref>&path:packages/replay/typescript"
  }
}
```

```typescript
import {ReplayCursor, replayRun} from "@velocitron/replay";

export function cursor(): never {
  return new ReplayCursor() as never;
}

export function run(): never {
  return replayRun();
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
