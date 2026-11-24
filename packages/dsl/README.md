# `packages/dsl`

Lowering of `.petrinet` text to contribution IR, in two language packages:

- [`python/`](python/) — distribution `velocitron-dsl`, import `velocitron_dsl`
- [`typescript/`](typescript/) — package `@velocitron/dsl` (`"private": true`)

`lower_petrinet_text` / `lowerPetrinetText` parse one net or composition
document into `velocitron.petrinet/contribution-ir` version 1. CEL source
stays a string. The result is not a resolved net or composition.

This is a lower-only package. Resolution compiles CEL, validates a net,
and, for a composition, loads referenced nets. That step ships in
`packages/petrinet`. Canonical emission (`emit_petrinet`) ships in the
Python package. Composition merge ships in `packages/merge`. The
validating wrappers live in `packages/petrinet`.

The lowerer vendors a second copy of the ANTLR parser that
`packages/grammar` already generates. Grammar's public parse returns a
tree without the token types and visitor base this lowerer subclasses, and
layer lint forbids importing that generated parser below the grammar
package root. Teach grammar to export the surface, then import it here.
`packages/petrinet` calls `lower_petrinet_text` / `lowerPetrinetText` and
does not vendor another copy.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

Callers import this package's public API. `emit_petrinet` renders canonical
`.petrinet` text. `python3 tools/dsl_package.py check` fails if a retired
facade grows the lowerer back.
