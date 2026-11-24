# `packages/grammar`

Syntax parser for `.petrinet` net and composition documents, in two language
packages:

- [`python/`](python/) — distribution `velocitron-grammar`, import `velocitron_grammar`
- [`typescript/`](typescript/) — package `@velocitron/grammar` (`"private": true`)

The canonical grammar is [`VelocitronPetriNet.g4`](VelocitronPetriNet.g4).
Each language package ships a byte copy of that file and the ANTLR 4.13.2
parser generated from it. `parse_petrinet` / `parsePetrinet` returns the
document kind (`net` or `composition`), the header name, and the ANTLR
`document` tree.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

Lowering a parse into contribution IR ships in `packages/dsl`. The language
implementations import that lowerer. Compiling CEL, resolving a net, and
merging a composition stay in `implementations/python` and
`implementations/typescript`. The `.play` grammar lives in `packages/play`,
not in this package.
