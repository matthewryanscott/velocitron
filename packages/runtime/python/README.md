# `velocitron-runtime`

Run a net asynchronously and evaluate intended waits. The import name is
`velocitron_runtime`. The TypeScript package is `@velocitron/runtime`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/runtime/python` subdirectory.

Version 0.1.0 is alpha software. The runtime may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`Runtime` is the run loop:

1. Admit an enabled transition whose lane has room and whose footprint does
   not conflict with a firing already in flight.
2. `Engine.reserve` takes the consume-mode tokens.
3. The `HandlerSpec` handler runs. `RuntimeContext.cancel` stops other
   firings in a scope.
4. `Engine.settle` deposits the output or restores the reservation.

Pass a `HandlerRegistry` for guards, predicates, and the firing policy.
Omit `cel_adapter` and the constructor uses `get_default_adapter`. A
journal is optional. When one is attached, lifecycle events go through
`record_runtime` and trace events through `record_trace` if the journal
has those hooks.

`Engine` is `velocitron_engine.Engine` with `cel_adapter` defaulting to
`get_default_adapter()`. Pass an adapter to select a backend. The firing
core stays in `velocitron_engine` and still requires one.

`intended_waits`, `holds`, and `wait_problems` read the `wait` annotation.
The engine ignores it. `holds` and `wait_problems` take an optional
`adapter`; otherwise they use `get_default_adapter`.

## What stays outside

This package does not store journal records, merge nets, or call
`Engine.fire`. `ReplayCursor`, `ReplayBase`, and `replay_run` live in
`velocitron_replay`. `ReplayBase` subclasses `velocitron_netbase.VelocitronNet`,
and `replay_run` fires the engine from a tape. Journal durability ships in
`velocitron-journal`. The handler registry ships in `velocitron-engine`.
Analysis ships in `velocitron-analysis`. Codegen ships in
`velocitron-codegen`. The CLI stays outside too.

`velocitron.runtime` and `velocitron.waits` re-export this package.
`python3 tools/runtime_package.py check` fails if the umbrella grows the
runtime back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-engine` and `velocitron-cel` are
installed the same way from `packages/engine/python` and
`packages/cel/python`.

```toml
[project]
dependencies = [
  "velocitron-runtime @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/runtime/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-runtime = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/runtime/python" }
```

```python
from velocitron_engine import Arc, ConsumePattern, Marking, Net, Place, ProduceTemplate, Token, Transition
from velocitron_runtime import HandlerSpec, Runtime

net = Net(
    name="move",
    places=[Place("src", ["job"]), Place("dst", ["job"])],
    transitions=[Transition("move", handler="move")],
    arcs=[
        Arc(from_place="src", to_transition="move", consume=ConsumePattern("job", None, "consume")),
        Arc(from_transition="move", to_place="dst", produce=ProduceTemplate("job", "dst")),
    ],
    initial_marking=Marking({"src": [Token("job", {"id": 1})]}),
)

async def handler(inp, ctx):
    return {
        "status": "completed",
        "outputTokens": {"dst": [Token("job", {"done": True})]},
        "error": None,
        "metadata": {},
    }

runtime = Runtime(
    net=net,
    handlers={"move": HandlerSpec(handler, "main")},
    lanes={"main": 1},
)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
