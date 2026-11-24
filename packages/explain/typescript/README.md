# `@velocitron/explain`

Name the net-explanation seam. The Python distribution name is
`velocitron-explain` (import `velocitron_explain`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the
`packages/explain/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`explainNet` is the TypeScript name of `explain_net`. It raises
`ExplainUnavailableError`.

This package does not render prose or explain enablement. The renderer is
the Python package. Porting it would mean a second copy of the prose
templates and of `Engine.explain_enablement`.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/explain test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/explain_package.py check` fails if the umbrella grows a
renderer back.

## What stays in the language implementations

`velocitron.explain` re-exports the Python function. The umbrella console
entry injects it. `@velocitron/core` re-exports this marker and does not
render prose. DOT drawings stay in `@velocitron/viz`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/explain": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/explain/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/explain": "github:matthewryanscott/velocitron#<ref>&path:packages/explain/typescript"
  }
}
```

```typescript
import {explainNet} from "@velocitron/explain";

export function gap(): never {
  return explainNet();
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
