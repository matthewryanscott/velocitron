# `@velocitron/spec`

Portable Velocitron contracts: the JSON Schemas, the normative prose, and
the conformance corpus. The Python distribution name is `velocitron-spec`.
The TypeScript package name is `@velocitron/spec`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm or PyPI. Downstream projects depend on
a git revision and the `packages/spec` subdirectory.

Version 0.1.0 is alpha software. Schemas, prose, and conformance fixtures
may change without notice. Support is best-effort. Do not use Velocitron
for production or sensitive workloads.

## What is here

- `net.schema.json`, `composition.schema.json`, and
  `petrinet-contribution-ir.schema.json` — the canonical JSON Schemas.
  Their `$id` URLs stay on the existing `/spec/` paths.
- Normative prose: `net-schema.md`, `composition.md`,
  `petrinet-language.md`, `handler-contract.md`, `firing-semantics.md`,
  `properties.md`, `projection-adapter.md`, `play-language.md`, and
  `proofs.md`.
- `conformance/petrinet/`, `conformance/play/` and `conformance/prove/` —
  the shared conformance corpus (`prove/` holds the prover's progress line).

## What stays outside this package

Contribution-IR resolution ships in `packages/petrinet`
(`velocitron-petrinet`, `@velocitron/petrinet`). The file-free
composition merge, the CEL adapter, the contribution-IR loader, the
`.petrinet` lowerer, the `.play` parser, the firing engine, and the net
renderer live in their own packages. The implementations import those
public APIs. Checking a play stays in the Python implementation. The
`velocitron-viz` command lives in `packages/cli`. There is no published
`@velocitron/core` library. This package does not include that loader, the CEL
adapter, the lowerer, the play parser, the merge transform, the firing
engine, or the renderer.

## How this monorepo consumes the package

Both languages read these files as the schema source of truth.

- Python: `velocitron_spec.schema_text` and `schema_document` read the
  files.
  `python3 tools/generate-schemas-python.py` copies the
  contribution-IR schema into `packages/ir` so that package can ship alone.
  `--check` is the Python test gate.
- TypeScript: from `implementations/typescript/`, `pnpm generate:schema`
  and `pnpm generate:ir-schema` compile Ajv validators into
  `packages/petrinet/typescript/src/generated/`.
  `pnpm check:generated` runs both generators with `--check`.

`@velocitron/petrinet` keeps the generated Ajv validators and reads schemas
through `velocitron_spec`. There is no published `velocitron` library.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published.

### pip / uv

```toml
[project]
dependencies = [
  "velocitron-spec @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/spec",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-spec = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/spec" }
```

```python
from velocitron_spec import conformance_root, schema_text

net_schema = schema_text("net.schema.json")
corpus = conformance_root()
```

`schema_text` accepts `net.schema.json`, `composition.schema.json`, and
`petrinet-contribution-ir.schema.json`. `prose_text` reads a normative
Markdown contract by its file name.

### npm / pnpm

The package is marked `"private": true` so it is not published to the npm
registry. Git subdirectory installs still resolve it.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/spec": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/spec"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/spec": "github:circuitmeridian/velocitron#<ref>&path:packages/spec"
  }
}
```

```js
import { SCHEMA_NAMES } from "@velocitron/spec";
import netSchema from "@velocitron/spec/net.schema.json" with { type: "json" };
```

Conformance fixtures are exported under `@velocitron/spec/conformance/*`.
Prose Markdown ships in the package directory.

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
