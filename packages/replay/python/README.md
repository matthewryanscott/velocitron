# `velocitron-replay`

`ReplayCursor`, `ReplayBase`, and `replay_run`. The import name is
`velocitron_replay`. The TypeScript package is `@velocitron/replay`.

This package is part of the [velocitron](https://github.com/circuitmeridian/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `circuitmeridian/velocitron` and the
`packages/replay/python` subdirectory.

Version 0.1.0 is alpha software. The replay contract may change without
notice. Support is best-effort. Do not use Velocitron for production or
sensitive workloads.

## What this package does

`ReplayCursor` is one snapshot of `journal.records()`. `ReplayBase` is the
mixin a generated `Replay<Net>` class puts first: handler calls answer from
the tape, and the methods underneath are not called. `replay_run` builds an
`Engine` over the registration's registry, replays each recorded injection,
and lets the engine fire between them.

Strict mode raises `ReplayOrderError` when the engine's firing misses the
tape, and `ReplayNetMismatch` when the recorded net revision hashes
differently. Compare mode records the first `Divergence` and stops.

```python
from velocitron_engine import HandlerRegistry
from velocitron_journal import JsonlJournal
from velocitron_replay import ReplayBase, ReplayCursor, replay_run

class ReplayMove(ReplayBase):
    NET_NAME = "move"
    SOURCE = "move.petrinet"
    SOURCE_SHA256 = digest
    HANDLER_REFS = {"move@move": "fire_move"}
    INPUT_PLACES = {"move": ("src",)}
    OUTPUT_PLACES = {"move": ("dst",)}

    def fire_move(self, *, src):
        raise AssertionError("replay never calls fire_move")

cursor = ReplayCursor.from_journal(recording)
replay = ReplayMove(cursor)
registration = replay.register_into(HandlerRegistry(), net)
result = replay_run(net, replay, registration, cursor, journal=JsonlJournal())
```

`recording`, `digest`, and `net` in that sketch are the journal, the
registration digest, and the `Net` the live run used. `replay_run` passes
`get_default_adapter()` into `velocitron_engine.Engine` unless the caller
passes `cel_adapter`.

## What stays outside

This package does not store a journal. `JsonlJournal` and `DurableJournal`
live in `velocitron_journal`, which only folds records into a marking.
`Runtime` lives in `velocitron_runtime` and does not call `Engine.fire`.
`VelocitronNet` lives in `velocitron_netbase`. `parse_net` lives in
`velocitron_petrinet`.

Generated source still imports `velocitron.replay`. `velocitron.replay`
re-exports this package, so a module already written still loads.

`python3 tools/replay_package.py check` fails if the umbrella grows
`ReplayCursor`, `ReplayBase`, or `replay_run` back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-netbase`, `velocitron-engine`,
`velocitron-journal`, `velocitron-petrinet`, and `velocitron-cel` are
installed the same way from their `packages/*/python` directories.

```toml
[project]
dependencies = [
  "velocitron-replay @ git+https://github.com/circuitmeridian/velocitron.git@<ref>#subdirectory=packages/replay/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-replay = { git = "https://github.com/circuitmeridian/velocitron.git", rev = "<ref>", subdirectory = "packages/replay/python" }
```

```python
from velocitron_replay import ReplayBase, ReplayCursor, replay_run

print(ReplayCursor.__name__, ReplayBase.__name__, replay_run.__name__)
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
