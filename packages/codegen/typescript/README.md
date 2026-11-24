# `@velocitron/codegen`

Name the Velocitron codegen seam. The Python distribution name is
`velocitron-codegen` (import `velocitron_codegen`).

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`matthewryanscott/velocitron` and the
`packages/codegen/typescript` subdirectory.

Version 0.1.0 is alpha software. The marker may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`SYNTH_HANDLER` is the prefix `velocitron:synth:`. `REFINED_AWAY` is the
string `RefinedAway`. `generateModule` and `generateComposition` are the
TypeScript names of the Python functions. Both raise
`CodegenUnavailableError`.

This package does not emit a module. The Python generator writes a class
that extends `velocitron.netbase.VelocitronNet` (the umbrella re-export of
`velocitron_netbase`), quotes `.petrinet` source
into docstrings, and stamps `net_sha256`. Porting that emitter would mean
keeping two byte-identical Python pretty-printers. ADR 0058 leaves
TypeScript codegen off the roadmap, the same way the analysis package's
TypeScript side reads a proof report and does not explore a net.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/codegen test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/codegen_package.py check` fails if the umbrella grows a
generator back.

## What stays in the language implementations

`velocitron.codegen` re-exports the Python package. `velocitron codegen`
lives in `packages/cli`. `@velocitron/core` re-exports this
marker and does not emit a module.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/codegen": "git+https://github.com/matthewryanscott/velocitron.git#<ref>&path:/packages/codegen/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/codegen": "github:matthewryanscott/velocitron#<ref>&path:packages/codegen/typescript"
  }
}
```

```typescript
import {SYNTH_HANDLER, generateModule} from "@velocitron/codegen";

export function prefix(): string {
  return SYNTH_HANDLER;
}

export function emit(): never {
  return generateModule();
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
