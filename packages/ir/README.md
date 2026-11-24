# `packages/ir`

Shape-only contribution-IR runtime, in two language packages:

- [`python/`](python/) — distribution `velocitron-ir`, import `velocitron_ir`
- [`typescript/`](typescript/) — package `@velocitron/ir` (`"private": true`)

Both packages load a `velocitron.petrinet/contribution-ir` version 1 document
and validate it against `petrinet-contribution-ir.schema.json`. CEL source
stays a string. Resolving contributions into canonical net JSON and compiling
CEL stay in `implementations/python` and `implementations/typescript`.
Composition merge ships in `packages/merge`.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. Each language
README has the install snippet.
