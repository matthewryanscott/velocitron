# `packages/petrinet`

Compile and resolve `.petrinet` documents, in two language packages:

- [`python/`](python/) — distribution `velocitron-petrinet`, import `velocitron_petrinet`
- [`typescript/`](typescript/) — package `@velocitron/petrinet` (`"private": true`)

`compile_petrinet_text` / `compilePetrinetText` lower one source through
`packages/dsl`, resolve the contribution IR, compile CEL, and return
canonical JSON. `resolve_contribution_ir` / `resolveContributionIr` is that
close for IR that is already lowered. `parse_net` / `parseNet` and
`parse_composition` / `parseComposition` validate the canonical JSON.

This package does not fire a net, check a play, store a journal, render
`.petrinet` text, or own the CLI. Canonical emission (`emit_petrinet`)
ships in `velocitron_dsl`. `merge_nets` and `merge_composition` call
`velocitron_merge` and then `validate_net`.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. Each language
README has the install snippet.

Callers import this package's public API. There is no `velocitron` or
`@velocitron/core` library. `python3 tools/petrinet_package.py check`
fails if a retired facade grows the compiler back.

The lowerer in `packages/dsl` still vendors a second ANTLR parser.
`packages/grammar` parses the same grammar, but its public parse returns a
tree without the token types and visitor base the lowerer subclasses, and
layer lint forbids importing the generated parser below the grammar package
root. This package calls `lower_petrinet_text` / `lowerPetrinetText` and
does not vendor another copy. Teach grammar to export that surface, then
drop the vendored parser from `packages/dsl`.
