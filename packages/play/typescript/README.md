# `@velocitron/play`

Parser for Velocitron `.play` documents. The Python distribution name is
`velocitron-play` (import `velocitron_play`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the `packages/play/typescript`
subdirectory.

Version 0.1.0 is alpha software. The grammar may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`parsePlay` reads one `.play` document:

1. A layout pass splits column-0 statements, indented continuations, `///`
   prose, and `//` comments. That pass is specified in
   `packages/spec/play-language.md` and is not part of the ANTLR grammar.
2. The ANTLR 4.13.2 grammar `VelocitronPlay.g4` parses one statement. A
   syntax error throws `PlayError` with code `SC101`. A JSON value the
   grammar accepts but RFC 8259 rejects is `SC102`. A time that is not
   seconds or an ordered duration is `SC103`. Repeated headers, labels, and
   similar structural mistakes are `SC104` or `SC105`.
3. The result is a `Play`. `projectPlay` projects that tree to the object
   the Python parser agrees on.

The canonical grammar lives at `packages/play/VelocitronPlay.g4`. A checkout
of this monorepo reads that file. The installed package ships a copy beside
this package, kept identical by `python3 tools/antlr.py`. Edit the canonical
file, then regenerate. Do not hand-edit the copy or the generated parser.

`tsc` compiles the generated parser and the lowerer into `dist/` before the
package can be imported. `pnpm --filter @velocitron/play test` does that
build. A git install runs the `prepare` script, which is the same build.

## What stays in the language implementations

`velocitron.play.language` re-exports the Python package. Checking a play
against a net, rendering a walkthrough, and drawing a sequence diagram ship
in `@velocitron/play-check` because they use the engine. `@velocitron/core`
does not check plays and does not depend on `@velocitron/play`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/play": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/play/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/play": "github:circuitmeridian/velocitron#<ref>&path:packages/play/typescript"
  }
}
```

```js
import { parsePlay } from "@velocitron/play";

const play = parsePlay(text, "example.play");
const name = play.name;
```

`grammarText` returns the grammar this parser was generated from.

## License

MIT. Copyright (c) 2026 Matthew R. Scott.
