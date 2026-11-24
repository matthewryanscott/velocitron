# `velocitron-codegen`

Generate one Python base class per Velocitron net, and the sha256 that
class registers with. The import name is `velocitron_codegen`. The
TypeScript package is `@velocitron/codegen`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/codegen/python` subdirectory.

Version 0.1.0 is alpha software. The generator may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`generate_module` returns a `GeneratedModule`. `generate_composition`
returns `{module stem: text}` for a composition and its nested files.
`generate_composition_full` also returns each leaf member's text and the
directory it is written beside. `RefinedAway` is the exception a refined
mixin raises. `net_document`, `canonical_net_json`, and `net_sha256` are
the registration digest. `SYNTH_HANDLER` is `velocitron:synth:`.

```python
from velocitron_codegen import generate_module, net_sha256
from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import compile_petrinet_text, parse_net

text = open("leaf.petrinet", encoding="utf-8").read()
lowered = lower_petrinet_text(text, "leaf.petrinet")
net = parse_net(compile_petrinet_text(text, "leaf.petrinet"))
module = generate_module(
    net,
    source="leaf.petrinet",
    source_name="leaf.petrinet",
    text=text,
    contributions=lowered["contributions"],
)
module.text, module.sha256 == net_sha256(net)
```

A composition is merged with `velocitron_merge`, then revalidated with
`velocitron_petrinet.validate_net`, before its digest is stamped.

## What stays outside

This package does not install a console script. `velocitron codegen` lives
in `velocitron_cli` and calls `generate_module` and
`generate_composition_full`. `velocitron.codegen.cli` re-exports that
command. Generated source imports
`velocitron.netbase.VelocitronNet`, `velocitron.replay`, and, for a
composition mixin, `RefinedAway` from
`velocitron.codegen.composition_generator`. `VelocitronNet` lives in
`velocitron_netbase`. Replay lives in `velocitron_replay`. The umbrella
re-exports both, so a module already written still loads. `velocitron_netbase`
re-exports `net_document`, `canonical_net_json`, `net_sha256`, and
`SYNTH_HANDLER`, and `velocitron.netbase` re-exports that package.

`velocitron.codegen` re-exports this package. `python3 tools/codegen_package.py check`
fails if the umbrella grows the generator back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-petrinet`, `velocitron-dsl`,
`velocitron-engine`, `velocitron-merge`, and `velocitron-viz` are installed
the same way from their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-codegen @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/codegen/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-codegen = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/codegen/python" }
```

```python
from velocitron_codegen import generate_composition

print(generate_composition("composition.petrinet")["composition"])
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
