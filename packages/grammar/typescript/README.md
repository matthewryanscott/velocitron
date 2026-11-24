# `@velocitron/grammar`

Syntax parser for Velocitron `.petrinet` documents. The Python distribution
name is `velocitron-grammar` (import `velocitron_grammar`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the `packages/grammar/typescript`
subdirectory.

Version 0.1.0 is alpha software. The grammar may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`parsePetrinet` reads one `.petrinet` document:

1. The text is strict UTF-8 without a BOM, a bare CR, or an isolated surrogate.
   LF and CRLF are both accepted.
2. The ANTLR 4.13.2 grammar `VelocitronPetriNet.g4` parses it. A syntax error
   throws `PetrinetParseError` and does not return a recovered tree.
3. The result says whether the document is a `net` or a `composition`, and
   carries the header name. A net with no header is named `unnamed`. A quoted
   header name is decoded as a JSON string. `tree` is the ANTLR `document`
   rule context.

The canonical grammar lives at `packages/grammar/VelocitronPetriNet.g4`. A
checkout of this monorepo reads that file. The installed package ships a copy
beside `index.js`, kept identical by `python3 tools/antlr.py`. Edit the
canonical file, then regenerate. Do not hand-edit the copy or the generated
parser.

`tsc` compiles the generated TypeScript parser into `dist/` before the
package can be imported. `pnpm --filter @velocitron/grammar test` does that
build. A git install runs the `prepare` script, which is the same build.

This grammar covers net documents and composition documents. The `.play`
grammar lives in `packages/play`.

## What stays in the language implementations

The umbrella does not carry a generated parser. Lowering a parse into
contribution IR ships in `packages/dsl` (`@velocitron/dsl`), which vendors
the parser this grammar generates. `@velocitron/core` re-exports that
lowerer. Compiling CEL and resolving a net, including `compilePetrinetText`,
ship in `@velocitron/petrinet`. Composition merge ships in
`@velocitron/merge`. The umbrella does not depend on `@velocitron/grammar`.

`parsePetrinet` returns a syntax tree without the token types and visitor
base the lowerer subclasses. Until this package exports that surface,
`@velocitron/dsl` keeps its vendored parser. `@velocitron/petrinet` does
not add a third copy.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/grammar": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/grammar/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/grammar": "github:circuitmeridian/velocitron#<ref>&path:packages/grammar/typescript"
  }
}
```

```js
import { parsePetrinet } from "@velocitron/grammar";

const document = parsePetrinet(text, "example.petrinet");
const kind = document.kind;
const name = document.name;
```

`grammarText` returns the grammar this parser was generated from. The grammar
source is also exported as `@velocitron/grammar/VelocitronPetriNet.g4`.

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
