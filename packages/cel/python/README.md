# `velocitron-cel`

Compile and evaluate CEL. The import name is `velocitron_cel`. The TypeScript
package is `@velocitron/cel`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/cel/python` subdirectory.

Version 0.1.0 is alpha software. The adapter may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`CelAdapter` is `compile(expr)` and `eval(compiled, data)`:

1. `compile` checks syntax. A free variable is left for evaluation. A syntax
   error is raised by the backend.
2. `eval` returns a Python value. An evaluation error raises `CelEvalError`.
3. `get_default_adapter` selects the installed backend in this order: Rust
   (`common-expression-language`), C++ (`cel-expr-python`), then bundled celpy.

`CelpyAdapter` is always available. Its code is the bundled celpy 0.5.0 tree.
`matches()` uses `google-re2` where that package has a wheel, and otherwise
`velocitron_cel._re2_standin`, which is backed by Python's `re` (ADR 0054).
celpy is imported on first use.

`CelExprAdapter` and `CelRustAdapter` construct without their extras.
`compile` and `eval` import the extra when called. Install them with
`velocitron-cel[cel-cpp]` or `velocitron-cel[cel-rust]`.

This package is the source of truth for the adapter and the bundled celpy.
`python3 tools/cel_package.py check` fails if the umbrella grows that body
back.

## What this package also owns

`CachingCelAdapter` and `slow_backend_hint` live here. `velocitron_runtime.Engine`
calls `get_default_adapter()`. The CEL scan prove uses ships in
`velocitron-analysis`. `@velocitron/cel` exports `createDefaultCelAdapter`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-cel @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/cel/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-cel = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/cel/python" }
```

```python
from velocitron_cel import get_default_adapter

adapter = get_default_adapter()
program = adapter.compile("n + 1")
value = adapter.eval(program, {"n": 1})
```

## License

[MIT](LICENSE) for this package. Matthew R. Scott is the sole author and
copyright holder. The bundled celpy tree is cel-python 0.5.0, Copyright
Capital One Services, LLC, Apache License 2.0 (`src/velocitron_cel/_vendor/celpy/LICENSE`).
