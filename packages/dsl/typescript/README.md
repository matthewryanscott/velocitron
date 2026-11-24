# `@velocitron/dsl`

Lower `.petrinet` text to contribution IR. The Python distribution name is
`velocitron-dsl` (import `velocitron_dsl`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the `packages/dsl/typescript`
subdirectory.

Version 0.1.0 is alpha software. The lowerer may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`lowerPetrinetText` reads one `.petrinet` document:

1. The text is strict UTF-8 without a BOM, a bare CR, or an isolated
   surrogate. LF and CRLF are both accepted.
2. The ANTLR 4.13.2 grammar parses it. A syntax error throws
   `PetrinetDslError` and does not return a recovered tree.
3. The result is contribution IR: `format` is
   `velocitron.petrinet/contribution-ir`, `version` is `1`, and
   `documentKind` is `net` or `composition`. CEL text is still source.

Syntax-only parsing of the same grammar lives in `@velocitron/grammar`.
Shape-only loading of the IR lives in `@velocitron/ir`. This package does
not re-export either one. It does not resolve contributions into a net,
compile CEL, or merge a composition.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/dsl test` does that build. A git
install runs the `prepare` script, which is the same build.

This package is the source of truth for the lowerer. The canonical grammar
remains `packages/grammar/VelocitronPetriNet.g4`. `tools/antlr.py` writes
the generated parser here and into `packages/grammar`.
`python3 tools/dsl_package.py check` fails if the umbrella grows the lowerer
back.

## What stays outside this package

Contribution resolution and CEL compilation ship in `@velocitron/petrinet`.
Canonical emission is the Python function `velocitron_dsl.emit_petrinet`.
The file-free composition merge ships in `packages/merge`.
`@velocitron/petrinet` calls that package and then revalidates the merged
net. There is no `@velocitron/core` library.

This module vendors a generated ANTLR parser. `@velocitron/grammar` already
generates the same parser, but its public parse does not export the visitor
base this lowerer subclasses. See the TODO above the generated imports in
`lower.ts`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/dsl": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/dsl/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/dsl": "github:circuitmeridian/velocitron#<ref>&path:packages/dsl/typescript"
  }
}
```

```js
import { lowerPetrinetText } from "@velocitron/dsl";

const document = lowerPetrinetText(text, "coin_deposit.petrinet");
const kind = document.documentKind;
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
