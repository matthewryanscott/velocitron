# `@velocitron/runtime`

Run a net asynchronously and evaluate intended waits. The Python
distribution name is `velocitron-runtime` (import `velocitron_runtime`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/runtime/typescript` subdirectory.

Version 0.1.0 is alpha software. The runtime may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`Runtime` reserves a firing (`Engine.reserve`), runs the handler, and
settles it (`Engine.settle`). It does not call `Engine.fire`.

`Engine` is `@velocitron/engine`'s `Engine` with `celAdapter` defaulting to
`createDefaultCelAdapter()`. Pass `celAdapter` to select a backend. The
firing core stays in `@velocitron/engine` and still requires one.

Pass a `HandlerRegistry` for guards, predicates, and the firing policy.
Omit `celAdapter` and the constructor uses `createDefaultCelAdapter`.
`intendedWaits`, `holds`, and `waitProblems` read the `wait` annotation.
The engine ignores it.

Build before import. `pnpm --filter @velocitron/runtime test` does that
build. A git install runs the `prepare` script, which is the same build.

## What stays outside

This package does not store a journal or render a net. Journal durability
ships in `@velocitron/journal`. The handler registry ships in
`@velocitron/engine`. Python `ReplayCursor`, `ReplayBase`, and `replay_run`
live in `velocitron_replay`: `ReplayBase` subclasses
`velocitron_netbase.VelocitronNet` and
`replay_run` drives `Engine.fire`. This package does not import
`@velocitron/core`.

`@velocitron/core` re-exports this entry.
`python3 tools/runtime_package.py check` fails if the umbrella grows the
runtime back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. Install `@velocitron/engine` and
`@velocitron/cel` from their `packages/*/typescript` directories the same
way.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/runtime": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/runtime/typescript"
  }
}
```

npm:

```json
{
  "dependencies": {
    "@velocitron/runtime": "github:circuitmeridian/velocitron#<ref>&path:packages/runtime/typescript"
  }
}
```

```typescript
import {HandlerRegistry, type Net} from "@velocitron/engine";
import {Runtime, type HandlerSpec} from "@velocitron/runtime";

export function runMove(net: Net, handler: HandlerSpec["handler"]): Runtime {
  return new Runtime({
    net,
    handlers: {move: {handler, lane: "main"}},
    lanes: {main: 1},
    registry: new HandlerRegistry(),
    celAdapter: {compile: (source) => source, evaluate: () => false},
  });
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
