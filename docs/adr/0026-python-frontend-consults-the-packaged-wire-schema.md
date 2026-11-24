# The Python frontend consults the packaged wire schema, and schema sync is generated

**Status:** Accepted. (Fulfills the Python half of the lockstep intent behind
ADR 0020's portable-IR contract; mirrors the TypeScript wire gate described
there.)

The Python `.petrinet` frontend validated Contribution IR with a handwritten
envelope preflight (`resolve_contribution_ir`'s document/contribution shape
checks) while the wire truth lived in `spec/petrinet-contribution-ir.schema.json`.
Two definitions of "which IR is well-formed" could drift, and the packaged
Python schema copies (net, composition, contribution IR) were kept in sync
with `spec/` by a byte-equality test — an enforcement mechanism with no
producer. This record settles the Python side: consult the packaged schema
in production resolution, keep only schema-inexpressible checks handwritten,
and replace the byte-copy test with a generator.

## Decision 1: resolution validates against the packaged IR schema first

`resolve_contribution_ir` now runs the packaged
`src/velocitron/schemas/petrinet-contribution-ir.schema.json` — loaded through
`velocitron.schema_resources` and built into a single module-level
`Draft202012Validator` — before any handwritten work. Every
`resolve_contribution_ir` call consults the schema; a wire-shape violation
never reaches the resolver's semantic merging logic, so Python and TypeScript
agree on which portable documents are importable at all.

**Considered options:**

- Keep the handwritten envelope preflight as primary and consult the schema
  only as a supplementary gate (the TypeScript implementation retains its
  per-item key checks and rejects via the schema last). Rejected: it preserves
  exactly the dual-definition drift this record exists to remove; the schema
  would remain negotiable whenever the handwritten checks were edited.
- Validate lazily, only when resolution encounters something unexpected.
  Rejected: the late paths do not see every wire fact (cross-fact merges
  consume raw facts before shape can be re-derived), so lazy validation would
  accept some schema-invalid documents.
- Hand-copied JSON with a byte test (status quo). Rejected: two copies and no
  producer — the test fails only after a human forgets to sync.

## Decision 2: handwritten checks keep only what JSON Schema cannot express

The envelope preflight is replaced by:

- **Cross-item invariants** — contribution ordinals contiguous zero-based in
  source order; contribution identity sources within the document's source
  set (single or aggregate); span `source` bound to the contribution id's
  source; unique contribution identities across the document.
- **Provenance fields the schema cannot bind** — consumed-arc
  `transitionNameSpan` source binding, composition wire endpoint spans that
  must name the wire's own source — plus every cross-fact conflict
  (conflicting facts, alias resolution, arc-handle mapping) in the per-kind
  resolution loops, unchanged.

Per-kind member/shape diagnostics that duplicate the schema's closed oneOf
(surface types, value member sets, numeric bounds) move behind the schema
gate: a schema-path failure is translated into the same PN-coded diagnostic
the handwritten check produced — same code, message, span, and help text,
pinned by the conformance corpus and the malformed-IR tests. The translation
covers the legacy document-targeted description/annotation facts that the
closed element target cannot express and resolution still accepts.

## Decision 3: the packaged schemas are generated, and `--check` is the gate

`tools/generate-schemas-python.py` (repository root `tools/`, mirroring
`implementations/typescript/tools/generate-schemas.mjs`) copies
`packages/spec/*.schema.json` into `implementations/python/src/velocitron/schemas/`
byte-for-byte. `--check` exits nonzero on drift; the Python test suite runs
that gate in place of the deleted byte-equality test, so an un-synced
`packages/spec/` edit fails suites and CI before it fails a release. Adding the
contribution-IR schema to the packaged set is part of this decision: the
wheel ships all three wire schemas, and `velocitron.schema_resources`
exposes `CONTRIBUTION_IR_SCHEMA` next to the net and composition documents.

## Consequences

- A wire-shape change is made in `packages/spec/` once, regenerated into both
  implementations, and both resolvers enforce it — the schema is the single
  definition of IR well-formedness.
- Compile/load resolution pays a pure-Python `jsonschema` traversal per
  document (measured at roughly 9 ms on average and 35 ms worst-case over the
  27-document conformance corpus, versus sub-millisecond handwritten-only
  checks; a synthetic 1,843-contribution document costs about 1.3 s). This is
  compile-path only: the firing engine never calls
  `resolve_contribution_ir`, so no runtime path — no step, no firing, no
  replay — consults the schema. Compiled artifacts (canonical JSON, frozen
  IR) keep their pre-existing costs.
- Diagnostic surface is unchanged wherever the corpus pins it; schema-path
  translations keep the exact PN codes, messages, spans, and help text the
  replaced checks produced, verified by the full Python suite (1,217 baseline
  tests plus the wire-gate and generator tests).
- The TypeScript implementation already gates on a compiled Ajv validator at
  resolve time; this record brings Python to the same consult, so future
  wire-shape decisions are settled in `packages/spec/` by construction.

## Packaging amendment

The canonical schemas, prose, and conformance corpus live in the in-repo
package `packages/spec/` (`@velocitron/spec` / `velocitron-spec`). The
generators above read that package and still write the implementation
copies this record describes. Contribution-IR resolution and composition
merge stay in the language implementations. CEL compilation stays there
too. `packages/ir/python` (`velocitron-ir`) and
`packages/ir/typescript` (`@velocitron/ir`) are the shape-only IR runtime:
they validate format, version, and this schema, and they leave CEL source
as text. Resolution, CEL compilation, and composition merge stay in the
language implementations. The published `velocitron` and `@velocitron/core`
packages do not depend on the IR packages; they keep the generated copies
and resolvers this record describes. `tools/generate-schemas-python.py`
copies `petrinet-contribution-ir.schema.json` into the IR packages so a
git-subdirectory install can validate without the rest of the checkout.