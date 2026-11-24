# `@velocitron/equiv`

Name the structural-equivalence seam. The Python distribution name is
`velocitron-equiv` (import `velocitron_equiv`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the
`packages/equiv/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`compare` and `Equivalence` are the TypeScript names of `compare` and
`Equivalence`. Calling `compare`, or constructing `Equivalence`, raises
`EquivUnavailableError`.

This package does not load a net or compare one. The check is the Python
package. Porting it would mean a second copy of composition loading and
the renaming.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/equiv test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/equiv_package.py check` fails if the umbrella grows a
comparison back.

## What stays in the language implementations

`velocitron.equiv` re-exports the Python package. The umbrella console
entry injects `add_parser` and `main`. `@velocitron/core` re-exports this
marker and does not compare nets.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/equiv": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/equiv/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/equiv": "github:matthewryanscott/velocitron#<ref>&path:packages/equiv/typescript"
  }
}
```

```typescript
import {compare} from "@velocitron/equiv";

export function gap(): never {
  return compare();
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
