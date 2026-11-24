# `@velocitron/properties`

Name the declarative property pass. The Python distribution name is
`velocitron-properties` (import `velocitron_properties`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the
`packages/properties/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`checkMarking`, `checkReplay`, and `capacityProperties` are the TypeScript
names of `check_marking`, `check_replay`, and `capacity_properties`. Each
raises `PropertiesUnavailableError`.

This package does not check a marking, reconstruct a journal, or compile
CEL. The checker is the Python package. Porting it would mean a second
copy of the record walker and the CEL predicates.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/properties test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/properties_package.py check` fails if the umbrella grows a
checker back.

## What stays in the language implementations

`velocitron.properties` re-exports the Python package. `@velocitron/core`
re-exports this marker and does not check a marking.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/properties": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/properties/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/properties": "github:matthewryanscott/velocitron#<ref>&path:packages/properties/typescript"
  }
}
```

```typescript
import {checkMarking} from "@velocitron/properties";

export function gap(): never {
  return checkMarking();
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
