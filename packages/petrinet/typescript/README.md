# `@velocitron/petrinet`

Compile `.petrinet` text and contribution IR into canonical JSON. The Python
distribution name is `velocitron-petrinet` (import `velocitron_petrinet`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the `packages/petrinet/typescript`
subdirectory.

Version 0.1.0 is alpha software. The compiler may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`compilePetrinetText` reads one `.petrinet` document:

1. `lowerPetrinetText` from `@velocitron/dsl` lowers it to contribution IR.
2. `resolveContributionIr` checks that IR, compiles CEL, and resolves
   contributions into canonical net or composition JSON.
3. A net has passed `parseNet`. A composition compiled with `loadRef` or
   `origin` has passed `parseComposition`.

```ts
import {compilePetrinetText} from "@velocitron/petrinet";

const compiled = compilePetrinetText(
  'net coin_deposit "Coin deposit"\n\n(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)\n',
  "coin_deposit.petrinet",
);
compiled.documentKind; // "net"
compiled.document.name; // "coin_deposit"
```

The return value is `{ documentKind, document }`. Python's
`compile_petrinet_text` returns the document dict directly.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/petrinet test` does that build. A git
install runs the `prepare` script, which is the same build.

## What this package does not do

It does not fire a net, check a play, store a journal, render `.petrinet`
text, or own the CLI. Canonical emission is Python `velocitron_dsl.emit_petrinet`. Validating merge wrappers live in this package.

`@velocitron/dsl` still vendors a generated ANTLR parser. This package calls
`lowerPetrinetText` and does not copy that parser.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. Install `@velocitron/cel`, `@velocitron/dsl`,
`@velocitron/engine`, and `@velocitron/merge` the same way.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/petrinet": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/petrinet/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/petrinet": "github:matthewryanscott/velocitron#<ref>&path:packages/petrinet/typescript"
  }
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
