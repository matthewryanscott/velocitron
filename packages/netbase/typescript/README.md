# `@velocitron/netbase`

Name the Velocitron registration seam. The Python distribution name is
`velocitron-netbase` (import `velocitron_netbase`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the
`packages/netbase/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`SYNTH_HANDLER` is the prefix `velocitron:synth:`, re-exported from
`@velocitron/codegen`. `VelocitronNet`, `Registration`, and `handlerSpec`
raise `NetbaseUnavailableError`.

This package does not register a net, hash one, or run a handler. The
Python class adapts methods onto `velocitron_engine` and builds
`HandlerSpec` values with `velocitron_runtime`. Porting that adapter would
be a second runtime. ADR 0058 leaves TypeScript codegen, and a TypeScript
`VelocitronNet`, off the roadmap.

`net_sha256`, `net_document`, `canonical_net_json`, and `HashMismatch` stay
on `velocitron_netbase`. The digest functions are defined in
`velocitron_codegen`.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/netbase test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/netbase_package.py check` fails if the umbrella grows a
`VelocitronNet` class back.

## What stays in the language implementations

`velocitron.netbase` re-exports the Python package. Generated modules
still import that name. `@velocitron/core` re-exports this marker and does
not register a net. `ReplayBase` lives in `velocitron_replay`.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `@velocitron/codegen` is installed the same
way; this package re-exports its prefix.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/netbase": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/netbase/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/netbase": "github:matthewryanscott/velocitron#<ref>&path:packages/netbase/typescript"
  }
}
```

```typescript
import {SYNTH_HANDLER, VelocitronNet} from "@velocitron/netbase";

export function prefix(): string {
  return SYNTH_HANDLER;
}

export function base(): never {
  return new VelocitronNet() as never;
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
