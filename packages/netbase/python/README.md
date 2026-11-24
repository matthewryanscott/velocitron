# `velocitron-netbase`

`VelocitronNet`, the base every generated Python net extends. The import
name is `velocitron_netbase`. The TypeScript package is `@velocitron/netbase`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/netbase/python` subdirectory.

Version 0.1.0 is alpha software. The registration contract may change
without notice. Support is best-effort. Do not use Velocitron for
production or sensitive workloads.

## What this package does

`register_into` hashes a standalone net, copies it, registers adapters, and
returns a `Registration`. `handler_spec` sets a method's lane, blocking
flag, and scope. `HashMismatch` means the class digest and the net
disagree.

`net_document`, `canonical_net_json`, `net_sha256`, and `SYNTH_HANDLER`
are re-exported from `velocitron_codegen`.

```python
from velocitron_engine import HandlerRegistry
from velocitron_netbase import VelocitronNet, net_sha256

class Leaf(VelocitronNet):
    NET_NAME = "leaf"
    SOURCE = "leaf.petrinet"
    SOURCE_SHA256 = net_sha256(net)
    HANDLER_REFS = {"go@leaf": "fire_go"}
    INPUT_PLACES = {"go": ("i",)}
    OUTPUT_PLACES = {"go": ("o",)}

    def fire_go(self, *, i):
        return {"o": list(i)}

registration = Leaf().register_into(HandlerRegistry(), net)
```

`net` in that sketch is an already-built `Net`. Validation constructs
`velocitron_engine.Engine` with `get_default_adapter()`.

## What stays outside

This package does not generate a module. `generate_module` lives in
`velocitron_codegen`. Generated source still imports
`velocitron.netbase.VelocitronNet` and `velocitron.replay`.
`velocitron.netbase` re-exports this package, so a module already written
still loads. `ReplayBase` lives in `velocitron_replay` and imports
`velocitron_netbase`. `velocitron.replay` re-exports it.

`python3 tools/netbase_package.py check` fails if the umbrella grows
`VelocitronNet` back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-codegen`, `velocitron-engine`,
`velocitron-runtime`, and `velocitron-cel` are installed the same way from
their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-netbase @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/netbase/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-netbase = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/netbase/python" }
```

```python
from velocitron_netbase import SYNTH_HANDLER, VelocitronNet

print(SYNTH_HANDLER, VelocitronNet.__name__)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
