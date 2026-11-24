# `velocitron-petrinet`

Compile `.petrinet` text and contribution IR into canonical JSON. The import
name is `velocitron_petrinet`. The TypeScript package is `@velocitron/petrinet`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/petrinet/python` subdirectory.

Version 0.1.0 is alpha software. The compiler may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`compile_petrinet_text` reads one `.petrinet` document:

1. `velocitron_dsl.lower_petrinet_text` lowers it to contribution IR.
2. `resolve_contribution_ir` checks that IR, compiles CEL, and resolves
   contributions into canonical net or composition JSON.
3. `parse_net` or `parse_composition` validates that JSON. A composition
   loads the nets the caller passes in and checks wires through
   `velocitron_merge`.

```python
from velocitron_petrinet import compile_petrinet_text

document = compile_petrinet_text(
    'net coin_deposit "Coin deposit"\n\n'
    "(coin_slot) -coin-> [accept_coin] -coin-> (cash_box)\n",
    "coin_deposit.petrinet",
)
name = document["name"]
```

Python returns the document dict. The TypeScript twin returns
`{ documentKind, document }`.

## What this package does not do

It does not fire a net, check a play, store a journal, render `.petrinet`
text, or own the CLI. Canonical emission (`emit_petrinet`) lives in
`velocitron_dsl`. `merge_nets` and `merge_composition` call
`velocitron_merge` and then revalidate the merged net.

`packages/dsl` still vendors a generated ANTLR parser. This package calls
the lowerer's public function and does not copy that parser. The grammar
package's public parse does not yet export the visitor base the lowerer
subclasses.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. Install the sibling packages the same way:
`packages/spec`, `packages/ir/python`, `packages/cel/python`,
`packages/dsl/python`, `packages/engine/python`, and
`packages/merge/python`.

```toml
[project]
dependencies = [
  "velocitron-petrinet @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/petrinet/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-petrinet = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/petrinet/python" }
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
