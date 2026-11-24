# `@velocitron/engine`

Fire an already-built Velocitron net. The Python distribution name is
`velocitron-engine` (import `velocitron_engine`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the
`packages/engine/typescript` subdirectory.

Version 0.1.0 is alpha software. The engine may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`Engine` runs the firing phase on a net the caller already built:

1. `enabledTransitions` lists transitions with a satisfiable binding.
2. `fire` consumes, calls the handler, and deposits against the produce
   templates. A failure leaves the marking unchanged.
3. `run` repeats that selection loop until quiescence or `maxSteps`.
4. `tick` replaces one place and then runs. `inject` records an arrival.
5. Every CEL expression goes through the injected `CelAdapter`.

Constructing an engine without `celAdapter` throws
`EngineConfigurationError`. Python `advance(outputs=)` symbolic advance
lives in `velocitron-engine`; this package does not carry that seam.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/engine test` does that build. A git
install runs the `prepare` script, which is the same build.

This package is the source of truth for the firing core. `Engine` requires
an injected CEL adapter. `python3 tools/engine_package.py check` fails if
the umbrella grows the engine back.

## What stays in the language implementations

`@velocitron/core` subclasses this package and injects
`createDefaultCelAdapter` from `@velocitron/cel`. Journal durability ships
in `@velocitron/journal`. The async runtime ships in `@velocitron/runtime`.
DSL resolution ships in
`@velocitron/petrinet`. `@velocitron/core` does
not render nets. Symbolic advance stays in the Python package.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/engine": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/engine/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/engine": "github:circuitmeridian/velocitron#<ref>&path:packages/engine/typescript"
  }
}
```

```typescript
import {Engine, HandlerRegistry, type CelAdapter, type Net} from "@velocitron/engine";

const adapter: CelAdapter = {
  compile: (source) => source,
  evaluate: () => false,
};

export function run(net: Net) {
  return new Engine(new HandlerRegistry(), {celAdapter: adapter}).run(net, {});
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
