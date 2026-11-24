# `velocitron-properties`

Checks declarative properties against a produced marking or a journal
replay. The import name is `velocitron_properties`. The TypeScript package
is `@velocitron/properties`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/properties/python` subdirectory.

Version 0.1.0 is alpha software. The property pass may change without
notice. Support is best-effort. Do not use Velocitron for production or
sensitive workloads.

## What this package does

`check_marking` checks one marking. `check_replay` walks journal records.
`capacity_properties` reads `capacityPerColorKey`. Pass `cel_adapter` or
let the checker call `get_default_adapter()`.

```python
from velocitron_properties import AtMostN, check_marking

report = check_marking(net, marking, [AtMostN("shelf", 1, "id")])
report.ok, report.violations
```

The vocabulary is `AtMostN`, `PlaceEmpty`, `EventuallyReaches`,
`MarkingInvariant`, `KeyCorrelation`, and `FiringBinding`. A violation is
a `PropertyViolation` on a `PropertyReport`. A replay-only property passed
to `check_marking` raises `ValueError`.

## What stays outside

This package does not install a console script. Reachability proofs live
in `velocitron-analysis`. Journal storage lives in `velocitron-journal`.
`velocitron.properties` re-exports this package.

`python3 tools/properties_package.py check` fails if the umbrella grows
the checker back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-cel`, `velocitron-engine`, and
`velocitron-journal` are installed the same way from their
`packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-properties @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/properties/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-properties = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/properties/python" }
```

```python
from velocitron_properties import check_marking, check_replay

print(check_marking.__name__, check_replay.__name__)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
