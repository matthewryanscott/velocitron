# `@velocitron/analysis`

Read a Velocitron proof report. The Python distribution name is
`velocitron-analysis` (import `velocitron_analysis`).

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to npm. The package is marked `"private": true`
so a workspace publish does not send it to the registry. Git subdirectory
installs still resolve it. Downstream projects depend on a git revision of
`circuitmeridian/velocitron` and the
`packages/analysis/typescript` subdirectory.

Version 0.1.0 is alpha software. The report reader may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`readProofReport` checks the JSON document specified in
`packages/spec/proofs.md` and returns it. `proofReportStatus` applies that
document's status rule: refuted if any fact is, otherwise unknown if any
is, otherwise proved. `FACTS` names the facts the Python prover accepts
(`invariants` plural). A stored fact uses `invariant`.

This package does not explore a net. Choice coverage, place invariants,
soundness, refinement, kept records, and lint are the Python package.
Porting that search would mean porting the firing engine's symbolic
advance, the CEL scan, and the domain model. Those stay in Python for
this extract, the same way composition diagrams stay in the Python viz
package.

`tsc` compiles the TypeScript into `dist/` before the package can be
imported. `pnpm --filter @velocitron/analysis test` does that build. A git
install runs the `prepare` script, which is the same build.

`python3 tools/analysis_package.py check` fails if the umbrella grows a
prover back.

## What stays in the language implementations

`velocitron.prove` re-exports the Python package. `velocitron prove` stays
in `implementations/python`. `@velocitron/core` re-exports this report
reader and does not prove a net.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

pnpm:

```json
{
  "dependencies": {
    "@velocitron/analysis": "git+https://github.com/circuitmeridian/velocitron.git#<ref>&path:/packages/analysis/typescript"
  }
}
```

npm accepts the same git URL, and also:

```json
{
  "dependencies": {
    "@velocitron/analysis": "github:circuitmeridian/velocitron#<ref>&path:packages/analysis/typescript"
  }
}
```

```typescript
import {readProofReport} from "@velocitron/analysis";

export function netName(document: unknown): string {
  return readProofReport(document).net;
}
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
