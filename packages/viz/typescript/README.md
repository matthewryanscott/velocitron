# `@velocitron/viz`

Render an already-built Velocitron net as Graphviz DOT. The Python
distribution name is `velocitron-viz` (import `velocitron_viz`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the
`packages/viz/typescript` subdirectory.

Version 0.1.0 is alpha software. The renderer may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`netToDot` draws one net. `netRenderModel` returns that DOT plus the line
index a view needs. `applyView` writes positions and routes through that
index. `fusionLayout` places fusion copies, including one shared copy
between two neighbor transitions of one choice.

Pass a net in the same shape `@velocitron/engine` accepts (`Net`, `Place`,
`Arc`). This package does not parse JSON or compile `.petrinet`. It does
not draw a composition, a feature legend, or a paired walkthrough. Those
stay in the Python package, because they need a parsed composition or the
play checker.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/viz test` does that build. A git
install runs the `prepare` script, which is the same build.

`render.ts`, `view.ts`, `canonical.ts`, and the structural net types in this
package are the TypeScript renderer. Edit them here.
`python3 tools/viz_package.py check` fails if the umbrella grows a renderer
back.

## What stays in the language implementations

`velocitron.viz` re-exports the Python package. `@velocitron/core` does not
render nets and does not depend on `@velocitron/viz`. The product console
command lives in `packages/cli`. The umbrella keeps the script entry.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/viz": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/viz/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/viz": "github:circuitmeridian/velocitron#<ref>&path:packages/viz/typescript"
  }
}
```

```typescript
import {netToDot, type Net} from "@velocitron/viz";

export function draw(net: Net): string {
  return netToDot(net, {rankdir: "LR"});
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
