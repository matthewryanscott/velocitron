# `velocitron-skill`

Resolves the bundled Velocitron authoring skill. The import name is
`velocitron_skill`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/skill/python` subdirectory.

Version 0.1.0 is alpha software. The resolver may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`skill_root` returns the directory that contains `SKILL.md`. The authoring
source of truth is the repo-root `skills/velocitron/`. This package
symlinks that tree as package data, so a wheel and an editable install
share one `importlib.resources` path.

```python
from velocitron_skill import skill_root

print(skill_root() / "SKILL.md")
```

There is no TypeScript package. [`skills/README.md`](../../../skills/README.md)
is the map of how the packages fit together for an agent.

## What stays outside

This package does not install a console script. `velocitron skill` lives
in `velocitron_cli` and copies the directory `skill_root` returns. The
umbrella console entry passes that function to `configure(skill_source=...)`.
It does not ship `velocitron/skill`. `python3 tools/skill_package.py check`
fails if that tree grows back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-skill @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/skill/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-skill = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/skill/python" }
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
