# `packages/skill`

The skill-directory seam:

- [`python/`](python/) — distribution `velocitron-skill`, import `velocitron_skill`

The authoring files stay at [`skills/velocitron/`](../../skills/velocitron/).
This package symlinks that tree and exposes `skill_root()`. There is no
TypeScript package. The shipped surface is that path; the files are
markdown and examples. [`skills/README.md`](../../skills/README.md) maps how
an agent uses the packages together.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. The language
README has the install snippet.

`velocitron skill` copies the directory `skill_root()` returns. The CLI
calls that function when no host override is set. The Python umbrella's
console entry passes the same function through `configure(skill_source=...)`
and does not ship a second tree. `python3 tools/skill_package.py check`
fails if the umbrella grows `velocitron/skill` back.

## What this package ships

- `skill_root()` — the bundled skill directory

## What stays outside

Authoring content stays in `skills/velocitron/`. The copy-into-a-directory
command stays in `packages/cli`. Replay lives in `packages/replay`.
Properties live in `packages/properties`. Enablement text lives in
`packages/explain`. Structural equivalence lives in `packages/equiv`.
