# `@velocitron/cli`

Name the Velocitron CLI seam. The Python distribution name is
`velocitron-cli` (import `velocitron_cli`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the
`packages/cli/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`COMMANDS` is the `velocitron` subcommand list. `VIZ_PROGRAM` is
`velocitron-viz`. `main` and `vizMain` are the TypeScript names of the
Python functions. Both raise `CliUnavailableError`.

This package does not parse arguments. The dispatcher is argparse in
`velocitron_cli`. There is no TypeScript console script in this
repository. Porting it would mean a second copy of the command grammar.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/cli test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/cli_package.py check` fails if a retired facade grows a
dispatcher back.

## What stays outside

Console scripts are `velocitron = velocitron_cli:main` and
`velocitron-viz = velocitron_cli:viz_main`. `main` installs canonical
emission from `velocitron_dsl`, explain from `velocitron_explain`, equiv
from `velocitron_equiv`, and the CEL backend hint from `velocitron_cel`
when those hooks are unset. `skill` reads `velocitron_skill.skill_root`.
This package names the subcommands and does not dispatch. There is no
published `@velocitron/core` library.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/cli": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/cli/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/cli": "github:matthewryanscott/velocitron#<ref>&path:packages/cli/typescript"
  }
}
```

```typescript
import {COMMANDS, main} from "@velocitron/cli";

export function commands(): readonly string[] {
  return COMMANDS;
}

export function run(): never {
  return main();
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
