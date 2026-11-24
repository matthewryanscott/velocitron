# `velocitron-merge`

Merge already-parsed nets into one net. The import name is
`velocitron_merge`. The TypeScript package is `@velocitron/merge`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/merge/python` subdirectory.

Version 0.1.0 is alpha software. The merge may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`merge_nets` takes nets keyed by alias, plus wires, shares, and
refinements, and returns one net:

1. Each refining net must fit the transition it replaces. A bad fit raises
   `NetValidationError`. The message matches the language implementation.
2. Place and transition names are qualified with the net alias. A refined
   transition, and the arcs of that transition, are left out.
3. Wires and shares fuse places. A wire joins an output port to an input
   port. A share joins places with no direction. The fused place is named
   after its output ports, or after every member when it has none.
4. Arc endpoints, produce destinations, timer place references, and proof
   facts are rewritten onto the qualified or fused names. CEL source is
   copied unchanged. `binding_names` keeps each constituent's local place
   names (ADR 0032).
5. Initial markings, domains, and declared actors are carried onto the
   merged net. Disagreeing domains or actor kinds raise `NetValidationError`.

`port_fusion_map` returns each wired or shared `alias.place` and the fused
name `merge_nets` gives it.

`merge_composition` reads `composition.parsed_nets` and delegates to
`merge_nets`. It does not parse net documents. A composition with
`parsed_nets is None` raises `NetValidationError`.

The returned net is not re-validated here, and CEL is not compiled. Those
steps stay in `velocitron.parser`.

The values are ordinary net and composition objects (`Net`, `Wire`,
`Share`, `Composition`, and the place, transition, and arc types). They
follow the field names of `velocitron.schema` for the attributes the
transform reads. `velocitron-ir` loads unresolved contribution IR, which
is a different document, so this package does not depend on it.

This package is the source of truth for the transform.
`python3 tools/merge_package.py check` fails if the umbrella grows it back.

## What stays in the language implementations

`velocitron.composition` calls `velocitron_merge`, then validates the merged
net, including CEL compilation. `merge_composition` there re-parses net
references when `parsed_nets` is missing. `parse_composition` and play
checking stay in `implementations/python`. The net render library is
`packages/viz`, which `velocitron` re-exports.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-merge @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/merge/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-merge = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/merge/python" }
```

```python
from velocitron_merge import Net, Place, Transition, merge_nets

merged = merge_nets({"only": net}, [])
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
