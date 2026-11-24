# `velocitron-explain`

Renders a validated net as deterministic prose. The import name is
`velocitron_explain`. The TypeScript package is `@velocitron/explain`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/explain/python` subdirectory.

Version 0.1.0 is alpha software. The renderer may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`explain_net` returns one document ending in a single LF. `format` is
`"markdown"` or `"text"`. `level` is `"practitioner"` or `"newcomer"`.
Pass `marking` to add an enablement section. That path constructs
`velocitron_engine.Engine` with `get_default_adapter()`.

```python
from velocitron_explain import explain_net

print(explain_net(net, format="text"))
```

## What stays outside

This package does not install a console script. `velocitron explain` lives
in `velocitron_cli`. The umbrella console entry injects `explain_net`.
`velocitron.explain` re-exports this function. DOT drawings live in
`velocitron-viz`.

`python3 tools/explain_package.py check` fails if the umbrella grows the
renderer back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-cel` and `velocitron-engine` are
installed the same way from their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-explain @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/explain/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-explain = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/explain/python" }
```

```python
from velocitron_explain import explain_net

print(explain_net.__name__)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
