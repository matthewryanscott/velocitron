# `packages/explain`

Human-readable net explanation, in two language packages:

- [`python/`](python/) — distribution `velocitron-explain`, import `velocitron_explain`
- [`typescript/`](typescript/) — package `@velocitron/explain` (`"private": true`)

`explain_net` quotes a validated net. Given a marking, it asks
`Engine.explain_enablement` and passes `get_default_adapter()`, because the
engine package requires an injected CEL adapter. No handler runs.

The TypeScript package raises `ExplainUnavailableError` from `explainNet`.
It does not render prose.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`velocitron.explain` re-exports `explain_net`. The umbrella console entry
injects it into `velocitron explain`. `@velocitron/core` re-exports the
TypeScript marker. `python3 tools/explain_package.py check` fails if the
umbrella grows the renderer back.

## Why this is its own package

`explain_net` imports `cel` and `engine`. `velocitron_analysis` also
imports `petrinet`, `merge`, and `runtime`. `velocitron_viz` draws DOT and
ships a real TypeScript renderer. This package keeps the prose surface on
the engine cone, and keeps the TypeScript gap next to that prose surface.

## What this package owns

- `explain_net`

## What stays outside

Graphviz drawings stay in `packages/viz`. Document loading and the
`velocitron explain` argv parser stay in `packages/cli`. The umbrella
injects `explain_net`.

## Non-goals

This package does not draw DOT, parse a document, or port the prose
renderer to TypeScript.
