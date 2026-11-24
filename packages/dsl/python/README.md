# `velocitron-dsl`

Lower `.petrinet` text to contribution IR. The import name is
`velocitron_dsl`. The TypeScript package is `@velocitron/dsl`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/dsl/python` subdirectory.

Version 0.1.0 is alpha software. The lowerer may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`lower_petrinet_text` reads one `.petrinet` document:

1. The text is strict UTF-8 without a BOM, a bare CR, or an isolated
   surrogate. LF and CRLF are both accepted.
2. The ANTLR 4.13.2 grammar parses it. A syntax error raises
   `PetrinetDslError` and does not return a recovered tree.
3. The result is contribution IR: `format` is
   `velocitron.petrinet/contribution-ir`, `version` is `1`, and
   `documentKind` is `net` or `composition`. CEL text is still source.

Syntax-only parsing of the same grammar lives in `velocitron-grammar`.
Shape-only loading of the IR lives in `velocitron-ir`. This package does
not re-export either one. It does not resolve contributions into a net,
compile CEL, or merge a composition.

This package is the source of truth for the lowerer. The canonical grammar
remains `packages/grammar/VelocitronPetriNet.g4`. `tools/antlr.py` writes
the generated parser here and into `packages/grammar`.
`python3 tools/dsl_package.py check` fails if the umbrella grows the lowerer
back.

## What stays outside this package

Callers import `velocitron_dsl`. Contribution resolution and CEL
compilation ship in `velocitron-petrinet`. Canonical emission
(`emit_petrinet`) lives in this package. `velocitron check`
and the rest of the CLI ship in `packages/cli`. The file-free composition
merge ships in `packages/merge`. `velocitron_petrinet` revalidates a merged
net.

This module vendors a generated ANTLR parser. `packages/grammar` already
generates the same parser, but its public `parse_petrinet` does not export
the visitor base this lowerer subclasses. See the TODO above the generated
imports in `lower.py`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-dsl @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/dsl/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-dsl = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/dsl/python" }
```

```python
from velocitron_dsl import lower_petrinet_text

document = lower_petrinet_text(text, "coin_deposit.petrinet")
kind = document["documentKind"]
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
