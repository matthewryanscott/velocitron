# `packages/play-check`

Check a `.play` document against a net and step a walkthrough, in two language packages:

- [`python/`](python/) — distribution `velocitron-play-check`, import `velocitron_play_check`
- [`typescript/`](typescript/) — package `@velocitron/play-check` (`"private": true`)

`check_play` / `checkPlay` resolves the play's `net` or `use` lines, then plays
each path through the firing engine. A handlerless firing is symbolic: the
play supplies output tokens, and the engine fills `data` / `data cel`.
`render_walkthrough` / `renderWalkthrough` and `walkthrough_document` /
`walkthroughDocument` step one checked path.

This package does not parse `.play` (that is `packages/play`), own the fire
loop (`packages/engine`), store a journal, resolve `.petrinet` beyond the
load the checker needs (`packages/petrinet`), or own the CLI. `records_to_play`
writes a `.play` from journal records and lives in this package.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

Python is the reference for paired Graphviz graphs and PlantUML. TypeScript
checks through `@velocitron/engine` and steps a walkthrough document.
There is no published `@velocitron/core` library.
`python3 tools/play_check_package.py check` fails if a retired facade grows the
checker back.
