# velocitron-kernel

The prover's fast path: a compiled module the Python loads in the same
process. `velocitron_analysis.tables` fills the kernel's tables from the
reference explorer; the kernel explores the net from them, keeps the graph,
and checks it.

`explore(tables, rows, max_states, progress=None, *, one_core=False)`
explores on every core, or with `one_core` on one. Either way the graph is
the one the reference explorer builds, in its order, so a run stopped at the
state cap holds the same markings and edges as the reference's: every core
expands a batch of waiting markings at once, against the rows and the graph
as they stand, and one thread merges them in the reference's order, asking
for a missing row and expanding that marking again where it stands. `tables`
holds the roles and the rows of the run's first tokens; the kernel asks
`rows` (the reference's `Rows`) for every other row the first time it needs
it, and keeps it. `progress.tick(markings, waiting)` hears how far the run
is, for the progress line.

The `Graph` it returns stays in the kernel. Its `check` runs the soundness
checks, `first_steps` and `place_counts` say what made the markings, and
`marking` and `path` give one state's marking and the moves that reached it;
all come back as numbers, which `velocitron_analysis.fast.KernelExplorer`
names in the reference's words.

`cases(tables, rows, update, transitions, place, tokens, context)` walks
every case of one choice (a choice token and one entry per context place)
and gives back the cases that enable none or more than one of
`transitions`.

Any failure inside the kernel (a row the reference cannot fill, a panic)
raises `KernelError`; the caller fails the run and names `--reference`.

Building it needs a Rust toolchain: `uv sync` in `implementations/python`
builds it through maturin.
