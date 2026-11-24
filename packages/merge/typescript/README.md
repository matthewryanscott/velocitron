# `@velocitron/merge`

Merge already-parsed nets into one net. The Python distribution name is
`velocitron-merge` (import `velocitron_merge`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the `packages/merge/typescript`
subdirectory.

Version 0.1.0 is alpha software. The merge may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`mergeNets` takes nets keyed by alias, plus wires, shares, and
refinements, and returns one net:

1. Each refining net must fit the transition it replaces. A bad fit throws
   `NetValidationError`. The message matches the Python package.
2. Place and transition names are qualified with the net alias. A refined
   transition, and the arcs of that transition, are left out.
3. Wires and shares fuse places. A wire joins an output port to an input
   port. A share joins places with no direction. The fused place is named
   after its output ports, or after every member when it has none.
4. Arc endpoints, produce destinations, timer place references, and proof
   facts are rewritten onto the qualified or fused names. CEL source is
   copied unchanged. `bindingNames` keeps each constituent's local place
   names.
5. Initial markings, domains, and declared actors are carried onto the
   merged net. Disagreeing domains or actor kinds throw `NetValidationError`.

`portFusionMap` returns each wired or shared `alias.place` and the fused
name `mergeNets` gives it.

`mergeComposition` takes the composition document and the nets the caller
already resolved, and delegates to `mergeNets`. It does not read files.

The returned net is not re-validated here, and CEL is not compiled. Those
steps stay in `@velocitron/core`.

The values are the structural net and composition types (`Net`,
`CompositionWire`, `CompositionShare`, `CompositionDocument`). They follow
the field names of `@velocitron/core` for the attributes the transform
reads. `@velocitron/ir` loads unresolved contribution IR, which is a
different document, so this package does not depend on it.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/merge test` does that build. A git
install runs the `prepare` script, which is the same build.

This package is the source of truth for the transform.
`python3 tools/merge_package.py check` fails if the umbrella grows it back.

## What stays in the language implementations

`@velocitron/core` calls this package, then re-validates the merged net,
including CEL compilation, before returning it. `parseComposition` and the
engine stay in `implementations/typescript`. `@velocitron/core` does not
render nets.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/merge": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/merge/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/merge": "github:circuitmeridian/velocitron#<ref>&path:packages/merge/typescript"
  }
}
```

```js
import { mergeNets } from "@velocitron/merge";

const merged = mergeNets(new Map([["only", net]]), []);
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
