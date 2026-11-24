# `velocitron-analysis`

Prove facts about markings a net can reach, and check kept records and
opt-in lint. The import name is `velocitron_analysis`. The TypeScript
package is `@velocitron/analysis`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/analysis/python` subdirectory.

Version 0.1.0 is alpha software. The prover may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`prove` returns a `ProofReport`. Each fact is proved, refuted, or unknown.

```python
from velocitron_analysis import ProofSettings, load, prove, read_settings

net, composition = load("hold.petrinet")
report = prove(
    net,
    settings=read_settings("domains.json5"),
    composition=composition,
)
report.status, report.as_json(), report.text()
```

`load` reads a `.petrinet` or `.json` net. A composition is merged, then
revalidated with `velocitron_petrinet.validate_net`. `lint_net` returns
advisory findings. `kept_records`, `kept_problems`, and `share_problems`
read the `kept` annotation. Pass a net the caller already parsed, or let
`load` parse it.

The root also exports `FACTS`, `Proof`, `ProofSettings`, `Invariant`,
`Finding`, `Composed`, and `semiflows`.

## What stays outside

This package does not install a console script. `velocitron prove` lives in
`velocitron_cli` and calls `load` and `prove`. Produced-marking properties live in
`velocitron-properties`. Enablement explanations live in
`velocitron-explain`. `velocitron equiv` lives in `velocitron-equiv` and
calls `load`. Codegen ships in `velocitron-codegen`.
Replay lives in `velocitron-replay`. The firing engine, CEL adapter, composition merge, and
intended waits are injected from their packages. `CachingCelAdapter` lives
in `velocitron-cel`.

`python3 tools/analysis_package.py check` fails if a retired facade
grows the prover back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-engine`, `velocitron-cel`,
`velocitron-petrinet`, `velocitron-merge`, and `velocitron-runtime` are
installed the same way from their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-analysis @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/analysis/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-analysis = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/analysis/python" }
```

```python
from velocitron_analysis import load, prove

net, _composition = load("sound.petrinet")
print(prove(net).text())
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
