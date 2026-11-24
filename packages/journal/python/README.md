# `velocitron-journal`

Append, read, and replay a Velocitron journal. The import name is
`velocitron_journal`. The TypeScript package is `@velocitron/journal`.

This package is part of the [velocitron](https://github.com/matthewryanscott/velocitron)
monorepo. It is not published to PyPI. Downstream projects depend on a git
revision of `matthewryanscott/velocitron` and the
`packages/journal/python` subdirectory.

Version 0.1.0 is alpha software. The journal may change without notice.
Support is best-effort. Do not use Velocitron for production or sensitive
workloads.

## What this package does

`JsonlJournal` assigns one monotonic `sequence` and buffers every record.
`flush` writes a timestamped `.jsonl` file when a prefix was given.
`DurableJournal` appends the same records to sqlite. `open_database`,
`read_events`, and `known_instances` are the store helpers.

`replay_records` rebuilds a marking from those records. `replay_events`
does the same from decoded `StoredEvent` rows. A completed firing consumes
only consume-mode inputs and deposits recorded outputs. An injection
appends or, for `update`, replaces a place. Failed firings, deposit
violations, traces, and net revisions leave the marking unchanged. No
handler runs.

Record shapes (`FiringRecord`, `InjectionRecord`, the kind constants) come
from `velocitron-engine`.

## What stays outside

This package does not fire a net, register handlers, or run the async
`Runtime` (`velocitron-runtime` does). `ReplayCursor`, `ReplayBase`, and
`replay_run` live in `velocitron_replay`: they answer handler calls from
the tape by driving `Engine`, and `ReplayBase` subclasses
`velocitron_netbase.VelocitronNet`. Play checking,
analysis, and the CLI stay outside too. Codegen ships in `velocitron-codegen`.

`velocitron.journal` and `velocitron.durable_sqlite` re-export this
package. `python3 tools/journal_package.py check` fails if the umbrella
grows the journal back.

## Install from a git subdirectory

Replace `<ref>` with a commit, tag, or branch. These snippets describe the
intended consumer shape. They are not a claim that a particular ref is
published. They point at this repository. `velocitron-engine` is installed the same way
from `packages/engine/python`.

```toml
[project]
dependencies = [
  "velocitron-journal @ git+https://github.com/matthewryanscott/velocitron.git@<ref>#subdirectory=packages/journal/python",
]
```

With a uv source table:

```toml
[tool.uv.sources]
velocitron-journal = { git = "https://github.com/matthewryanscott/velocitron.git", rev = "<ref>", subdirectory = "packages/journal/python" }
```

```python
from velocitron_engine import Marking, Net
from velocitron_journal import JsonlJournal, replay_records

def replayed(net: Net, journal: JsonlJournal) -> Marking:
    return replay_records(net, journal.records())
```

## License

[MIT](LICENSE). Matthew R. Scott is the sole author and copyright holder.
