# `packages/play`

Parser for `.play` documents, in two language packages:

- [`python/`](python/) — distribution `velocitron-play`, import `velocitron_play`
- [`typescript/`](typescript/) — package `@velocitron/play` (`"private": true`)

The canonical grammar is [`VelocitronPlay.g4`](VelocitronPlay.g4). It is the
syntax of one statement. A layout pass, specified in
[`packages/spec/play-language.md`](../spec/play-language.md) ("Source text"),
isolates each statement before the grammar sees it: a statement starts at
column 0, an indented line continues it, `///` lines are Markdown prose, and
`//` starts a comment. Blank-line continuation is lookahead, so it stays
outside the grammar.

Each language package ships a byte copy of the grammar and the ANTLR 4.13.2
parser generated from it. `parse_play` / `parsePlay` returns the play AST and
reports `SC1xx`. `project_source` / `projectPlay` is the shared projection the
two parsers agree on.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. Each language
README has the install snippet.

Checking a play against a net, the walkthrough, and the sequence diagram
ship in `packages/play-check`. They use the engine.
`velocitron.play.language` re-exports this package. `@velocitron/core` does
not check plays. The `.petrinet` grammar stays in `packages/grammar`.
