# `velocitron-cli`

Console commands for Velocitron nets. The import name is `velocitron_cli`.
The TypeScript package is `@velocitron/cli`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/cli/python` subdirectory.

Version 0.1.0 is alpha software. The dispatcher may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`main` parses `velocitron` argv and returns a process status. `viz_main`
does the same for `velocitron-viz`. `configure` installs the hooks this
package does not own.

```python
from velocitron_cli import main

raise SystemExit(main(["validate", "leaf.petrinet"]))
```

`validate`, `to-json`, `check`, `play`, `prove`, and `codegen` run from
the extracted packages alone. A merged composition is revalidated with
`velocitron_petrinet.validate_net`. `to-petrinet` needs `emit_petrinet`.
`explain` needs `explain_net`. `equiv` needs `equiv.add_parser` and
`equiv.main`. `skill` copies the directory from `velocitron_skill.skill_root`
unless `configure(skill_source=...)` overrides it. The CEL backend hint is
optional.

The console scripts are `velocitron = velocitron_cli:main` and
`velocitron-viz = velocitron_cli:viz_main`. `main` calls
`install_default_hooks` before it parses arguments.
`velocitron-viz --metrics` prints layout metrics for a net. It runs the
Graphviz engine named in the DOT, and `--metrics -` reads `-Tjson` from
stdin. Compare the numbers only across the same Graphviz version.

## What stays outside

Canonical emission lives in `velocitron_dsl` (`emit_petrinet`). Enablement
text lives in `velocitron_explain`. Structural equivalence lives in
`velocitron_equiv`. The slow-backend hint lives in `velocitron_cel`.
`main` installs those hooks when they are still unset. The skill files
ship in `velocitron-skill`. This package copies the directory `skill_root`
returns. Replay lives in `velocitron-replay`. Properties live in
`velocitron-properties`. `VelocitronNet` lives in `velocitron_netbase`.

`python3 tools/cli_package.py check` fails if a retired facade grows the
dispatcher back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. The packages this dispatcher imports are
installed the same way from their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-cli @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/cli/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-cli = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/cli/python" }
```

```python
from velocitron_cli import viz_main

raise SystemExit(viz_main(["--legend"]))
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
