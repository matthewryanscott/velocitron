# `velocitron-equiv`

Compares two merged nets up to renaming. The import name is
`velocitron_equiv`. The TypeScript package is `@velocitron/equiv`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/equiv/python` subdirectory.

Version 0.1.0 is alpha software. The comparison may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`compare` returns an `Equivalence`. `equivalent` is true when
`differences` is empty. `interface` lists port differences and does not
count. `main` loads both paths with `velocitron_analysis.load` and exits
0, 1, or 2.

```python
from velocitron_analysis import load
from velocitron_equiv import compare

first, first_composition = load("a.petrinet")
second, second_composition = load("b.petrinet")
result = compare(first, second, first_composition, second_composition)
print(result.text("a.petrinet", "b.petrinet"))
```

## What stays outside

This package does not install a console script. `velocitron equiv` is
dispatched by `velocitron_cli` after the umbrella injects `add_parser` and
`main`. `velocitron.equiv` re-exports this package. Loading a document
lives in `velocitron-analysis` and `velocitron-petrinet`.

`python3 tools/equiv_package.py check` fails if the umbrella grows the
check back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-analysis`, `velocitron-dsl`,
`velocitron-engine`, `velocitron-merge`, and `velocitron-petrinet` are
installed the same way from their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-equiv @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/equiv/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-equiv = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/equiv/python" }
```

```python
from velocitron_equiv import compare

print(compare.__name__)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
