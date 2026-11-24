# `packages/cli`

The console commands, in two language packages:

- [`python/`](python/) — distribution `velocitron-cli`, import `velocitron_cli`
- [`typescript/`](typescript/) — package `@velocitron/cli` (`"private": true`)

`main` is the `velocitron` dispatcher: validate, to-json, to-petrinet,
explain, skill, check, prove, codegen, equiv, and play. `viz_main` is
`velocitron-viz`. The TypeScript package names those commands. It does not
parse argv.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

Console scripts are `velocitron = velocitron_cli:main` and
`velocitron-viz = velocitron_cli:viz_main`. `main` installs canonical
emission from `velocitron_dsl`, explain from `velocitron_explain`, equiv
from `velocitron_equiv`, and the CEL backend hint from `velocitron_cel`
when those hooks are unset. `skill` reads `velocitron_skill.skill_root`
unless `configure(skill_source=...)` overrides it. The TypeScript package
names the subcommands and does not dispatch. `python3 tools/cli_package.py
check` fails if the retired facade trees return.

## What this package runs

- `velocitron validate`, `to-json`, `check`, `play`, `prove`, and `codegen`
- `velocitron-viz`, including document loading
- `to-petrinet`, `explain`, and `equiv`, with the default hooks `main`
  installs
- `skill`, from `velocitron_skill.skill_root`, or from a `skill_source`
  override

## What stays outside

`emit_petrinet` lives in `velocitron_dsl`. `explain_net` lives in
`velocitron_explain`. `velocitron equiv` lives in `velocitron_equiv`.
`slow_backend_hint` lives in `velocitron_cel`. `main` installs each of
those. The skill files stay at
`skills/velocitron/` and ship in `velocitron-skill`. Replay lives in
`velocitron-replay`. Properties live in `velocitron-properties`.
`VelocitronNet` lives in `velocitron_netbase`.
The TypeScript package does not
port argparse.
