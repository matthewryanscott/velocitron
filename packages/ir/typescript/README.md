# `@velocitron/ir`

Shape-only loader for Velocitron contribution IR. The Python distribution
name is `velocitron-ir` (import `velocitron_ir`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the `packages/ir/typescript`
subdirectory.

Version 0.1.0 is alpha software. The wire shape may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`loadContributionIr` checks three things:

1. The value is a JSON object.
2. `format` is `velocitron.petrinet/contribution-ir` and `version` is `1`.
   An unsupported format or version fails before the schema walk.
3. The object matches `petrinet-contribution-ir.schema.json`.

The canonical schema lives in `packages/spec`. A checkout of this monorepo
reads that file. The installed package ships a copy beside `index.js`, kept
identical by `python3 tools/generate-schemas-python.py`. Schema `$id` URLs
stay on the existing `/spec/` path.

CEL text on a contribution is returned as the same string. This package does
not compile it, does not resolve contributions into a net or composition
document, and does not merge compositions. Identity uniqueness and contiguous
ordinals are resolver rules; the wire schema does not require them, and this
loader does not either.

## What stays outside this package

`velocitron` depends on `velocitron-ir` for the wire format and version.
`resolveContributionIr` and the generated Ajv validator ship in
`@velocitron/petrinet`. The `ContributionIr` type is produced by
`@velocitron/dsl`. `@velocitron/core` re-exports the compiler and does
not depend on `@velocitron/ir`.

The implementation resolver still accepts a small set of legacy document
metadata targets that this schema rejects (ADR 0026). This package follows
the schema.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/ir": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/ir/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/ir": "github:circuitmeridian/velocitron#<ref>&path:packages/ir/typescript"
  }
}
```

```js
import { loadContributionIr } from "@velocitron/ir";
import schema from "@velocitron/ir/petrinet-contribution-ir.schema.json" with { type: "json" };

const document = loadContributionIr(payload);
```

`loadContributionIrText` accepts JSON text. `contributionIrSchemaText`
returns the schema this loader used.

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
