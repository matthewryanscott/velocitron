# `velocitron-play`

Parser for Velocitron `.play` documents. The import name is
`velocitron_play`. The TypeScript package is `@velocitron/play`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/play/python` subdirectory.

Version 0.1.0 is alpha software. The grammar may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`parse_play` reads one `.play` document:

1. A layout pass splits column-0 statements, indented continuations, `///`
   prose, and `//` comments. That pass is specified in
   `packages/spec/play-language.md` and is not part of the ANTLR grammar,
   because a blank line continues a statement only when another continuation
   follows.
2. The ANTLR 4.13.2 grammar `VelocitronPlay.g4` parses one statement. A
   syntax error raises `PlayError` with an `SC101` diagnostic. A JSON value
   the grammar accepts but RFC 8259 rejects (a duplicate key, a bad escape,
   a non-finite number) is `SC102`. A time that is not seconds or an ordered
   duration is `SC103`. Repeated headers, labels, and similar structural
   mistakes are `SC104` or `SC105`.
3. The result is a `Play`: headers, settings, templates, paths, and steps.
   `project_source` projects that tree to the object the TypeScript parser
   agrees on.

The canonical grammar lives at `packages/play/VelocitronPlay.g4`. A checkout
of this monorepo reads that file. A wheel ships a copy under
`velocitron_play/`, kept identical by `python3 tools/antlr.py`. Edit the
canonical file, then regenerate. Do not hand-edit the copy or the generated
parser.

This package is the source of truth for the play lowerer.
`python3 tools/play_package.py check` fails if the umbrella defines
`parse_play` again.

## What stays in the language implementations

`velocitron.play.language` re-exports this package. Checking a play against
a net, rendering a walkthrough, and drawing a sequence diagram ship in
`velocitron-play-check` because they use the engine. `@velocitron/core` does
not check plays. This package does not import `velocitron`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-play @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/play/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-play = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/play/python" }
```

```python
from velocitron_play import parse_play

play = parse_play(text, source="example.play")
name = play.name
```

`grammar_text` returns the grammar this parser was generated from.

## License

MIT. Copyright (c) 2026 Matthew R. Scott.
