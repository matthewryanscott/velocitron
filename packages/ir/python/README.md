# `velocitron-ir`

Shape-only loader for Velocitron contribution IR. The import name is
`velocitron_ir`. The TypeScript package is `@velocitron/ir`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/ir/python` subdirectory.

Version 0.1.0 is alpha software. The wire shape may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`load_contribution_ir` checks three things:

1. The value is a JSON object.
2. `format` is `velocitron.petrinet/contribution-ir` and `version` is the
   integer `1`. An unsupported format or version fails before the schema walk.
3. The object matches `petrinet-contribution-ir.schema.json`.

The canonical schema lives in `packages/spec`. A checkout of this monorepo
reads that file. A wheel ships a copy under `velocitron_ir/schemas/`, kept
identical by `python3 tools/generate-schemas-python.py`. Schema `$id` URLs
stay on the existing `/spec/` path.

CEL text on a contribution is returned as the same string. This package does
not compile it, does not resolve contributions into a net or composition
document, and does not merge compositions. Identity uniqueness and contiguous
ordinals are resolver rules; the wire schema does not require them, and this
loader does not either.

## What stays outside this package

`velocitron` depends on `velocitron-ir` for the wire format and version.
Contribution resolution, including `resolve_contribution_ir` /
`resolveContributionIr` and the generated Ajv validator, ships in
`packages/petrinet`. `@velocitron/core` re-exports that package and does
not depend on `@velocitron/ir`.

The implementation resolver still accepts a small set of legacy document
metadata targets that this schema rejects (ADR 0026). This package follows
the schema.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published.

```toml
[project]
dependencies = [
  "velocitron-ir @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/ir/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-ir = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/ir/python" }
```

```python
from velocitron_ir import load_contribution_ir

document = load_contribution_ir(payload)
kind = document["documentKind"]
```

`load_contribution_ir_text` accepts UTF-8 JSON text.
`contribution_ir_schema_text` returns the schema this loader used.

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
