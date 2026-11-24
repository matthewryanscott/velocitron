# `velocitron-grammar`

Syntax parser for Velocitron `.petrinet` documents. The import name is
`velocitron_grammar`. The TypeScript package is `@velocitron/grammar`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/grammar/python` subdirectory.

Version 0.1.0 is alpha software. The grammar may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`parse_petrinet` reads one `.petrinet` document:

1. The text is strict UTF-8 without a BOM, a bare CR, or an isolated surrogate.
   LF and CRLF are both accepted.
2. The ANTLR 4.13.2 grammar `VelocitronPetriNet.g4` parses it. A syntax error
   raises `PetrinetParseError` and does not return a recovered tree.
3. The result says whether the document is a `net` or a `composition`, and
   carries the header name. A net with no header is named `unnamed`. A quoted
   header name is decoded as a JSON string. `tree` is the ANTLR `document`
   rule context.

The canonical grammar lives at `packages/grammar/VelocitronPetriNet.g4`. A
checkout of this monorepo reads that file. A wheel ships a copy under
`velocitron_grammar/`, kept identical by `python3 tools/antlr.py`. Edit the
canonical file, then regenerate. Do not hand-edit the copy or the generated
parser.

This grammar covers net documents and composition documents. The `.play`
grammar lives in `packages/play`.

## What stays in the language implementations

The umbrella does not carry a generated parser. Lowering a parse into
contribution IR ships in `packages/dsl` (`velocitron-dsl`), which vendors the
parser this grammar generates. `velocitron` imports that lowerer. Compiling
CEL and resolving a net, including `compile_petrinet_text`, ship in
`packages/petrinet`. Composition merge ships in `packages/merge`. The
umbrella does not depend on `velocitron-grammar`.

`parse_petrinet` returns a syntax tree without the token types and visitor
base the lowerer subclasses. Layer lint also forbids importing
`velocitron_grammar.generated`. Until this package exports that surface,
`packages/dsl` keeps its vendored parser. `packages/petrinet` does not add
a third copy.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-grammar @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/grammar/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-grammar = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/grammar/python" }
```

```python
from velocitron_grammar import parse_petrinet

document = parse_petrinet(text, source_name="example.petrinet")
kind = document.kind
name = document.name
```

`grammar_text` returns the grammar this parser was generated from.

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
