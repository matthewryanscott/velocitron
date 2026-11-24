# `velocitron-engine`

Fire and advance an already-built Velocitron net. The import name is
`velocitron_engine`. The TypeScript package is `@velocitron/engine`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/engine/python` subdirectory.

Version 0.1.0 is alpha software. The engine may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`Engine` runs the firing phase on a net the caller already built:

1. Enablement finds transitions with a satisfiable binding.
2. `fire` consumes, calls the handler, and deposits against the produce
   templates. A failure leaves the marking unchanged.
3. `advance` repeats that selection loop until quiescence or `max_steps`.
4. `advance(outputs=)` settles a handlerless firing from an
   `OutputProvider`. `symbolic_outputs` carries the one consumed token of
   a color the net does not fill itself.
5. An exact `name == "literal"` arc predicate is evaluated in Python. Every
   other CEL expression goes through the injected `CelAdapter`.

Constructing an engine without `cel_adapter` raises `ValueError`. The net
model (`Net`, `Marking`, `Token`, arcs) is the same dataclass module the
engine walks. Composition dataclasses live in that module; this package
does not merge nets.

This package is the source of truth for the firing core.
`python3 tools/engine_package.py check` fails if a retired facade grows it back.

## What stays outside

`velocitron_runtime.Engine` subclasses this package and injects
`get_default_adapter`. `CachingCelAdapter` lives in `velocitron-cel`.
`JsonlJournal`, tape replay, and sqlite durability ship in
`velocitron-journal`. The async `Runtime` and intended waits ship in
`velocitron-runtime`. The product CLI ships in `packages/cli`.
Play checking ships in
`packages/play-check`. DSL resolution ships in
`packages/petrinet`. The net render
library is `packages/viz`. Journal record
types are re-exported from this package.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository.

```toml
[project]
dependencies = [
  "velocitron-engine @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/engine/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-engine = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/engine/python" }
```

```python
from velocitron_engine import (
    Arc,
    ConsumePattern,
    Engine,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
)

class Adapter:
    def compile(self, expr: str) -> str:
        return expr

    def eval(self, compiled: str, data: dict) -> object:
        raise AssertionError(compiled)

def move(inp):
    token = inp["inputTokens"]["src"][0]
    return {
        "status": "completed",
        "outputTokens": {"dst": [Token("job", dict(token.data))]},
        "error": None,
        "metadata": {},
    }

registry = HandlerRegistry()
registry.register_transition("move", move)
engine = Engine(registry, cel_adapter=Adapter())
net = Net(
    name="move",
    places=[Place("src", ["job"]), Place("dst", ["job"])],
    transitions=[Transition("move", handler="move")],
    arcs=[
        Arc(
            from_place="src",
            to_transition="move",
            consume=ConsumePattern("job", None, "consume"),
        ),
        Arc(
            from_transition="move",
            to_place="dst",
            produce=ProduceTemplate("job", "dst"),
        ),
    ],
)
marking, record = engine.fire(
    net, Marking({"src": [Token("job", {"id": 1})]}), "move", attempt=0
)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
