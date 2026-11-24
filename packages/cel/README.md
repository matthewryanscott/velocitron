# `packages/cel`

CEL compile and eval adapters, in two language packages:

- [`python/`](python/) — distribution `velocitron-cel`, import `velocitron_cel`
- [`typescript/`](typescript/) — package `@velocitron/cel` (`"private": true`)

`compile` / `eval` (Python) and `compile` / `evaluate` (TypeScript) are the
portable adapter. Python bundles celpy. Auto-detection uses the optional
Rust backend when it is installed, and otherwise celpy. The optional C++
backend is a compatibility and conformance reference (ADR 0066); construct
`CelExprAdapter` to use it. TypeScript uses `@marcbachmann/cel-js`. A result is a host value
the caller can treat as data. The Python adapter raises `CelEvalError` on
evaluation failure. The TypeScript adapter throws `CelCompileError` or
`CelEvaluationError`.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `matthewryanscott/velocitron`. Each language
README has the install snippet.

`CachingCelAdapter` and `slow_backend_hint` live in `velocitron_cel`.
The firing engine in `packages/engine` accepts an injected adapter and
does not depend on this package. `velocitron_runtime.Engine` calls
`get_default_adapter()`. The CEL scan prove uses ships in
`packages/analysis`. `python3 tools/cel_package.py check` fails if the
retired facade trees return.
