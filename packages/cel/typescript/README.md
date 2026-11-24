# `@velocitron/cel`

Compile and evaluate CEL. The Python distribution name is `velocitron-cel`
(import `velocitron_cel`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the `packages/cel/typescript`
subdirectory.

Version 0.1.0 is alpha software. The adapter may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`CelAdapter` is `compile(source)` and `evaluate(compiled, context)`:

1. `compile` checks syntax. A free variable is left for evaluation. A syntax
   error throws `CelCompileError`.
2. `evaluate` returns JSON. The context must be a JSON object. Safe integers
   are promoted to CEL ints and normalized back to JSON numbers. An evaluation
   error throws `CelEvaluationError`.
3. `createDefaultCelAdapter` returns the bundled `@marcbachmann/cel-js`
   backend. Programs are cached per exact source string on that adapter.

`tsc` compiles the TypeScript into `dist/` before the package can be imported.
`pnpm --filter @velocitron/cel test` does that build. A git install runs the
`prepare` script, which is the same build.

This package is the source of truth. `python3 tools/cel_package.py check`
fails if the umbrella grows the adapter back.

## What stays in the language implementations

`@velocitron/core` re-exports this package. Engine wiring and DSL
produce-cel stay in `implementations/typescript`. The CEL scan prove uses
ships in `packages/analysis`.
`createDefaultCelAdapter` comes from `@velocitron/cel`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/cel": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/cel/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/cel": "github:circuitmeridian/velocitron#<ref>&path:packages/cel/typescript"
  }
}
```

```js
import { createDefaultCelAdapter } from "@velocitron/cel";

const adapter = createDefaultCelAdapter();
const program = adapter.compile("n + 1");
const value = adapter.evaluate(program, { n: 1 });
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
