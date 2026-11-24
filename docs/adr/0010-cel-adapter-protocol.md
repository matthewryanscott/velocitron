# CEL adapter protocol for swappable evaluation backends

Inline CEL predicates (ADR 0002) are compiled at parse time (parser D5) and evaluated at runtime (engine D6). Rather than binding the engine and parser directly to a single CEL library, velocitron adopts a `CelAdapter` protocol (`compile(expr)` + `eval(bindings)`) with auto-detection: `cel-python` (celpy) is the default backend; `cel-expr-python` (binding to the official C++ CEL library) is an optional extra. The engine and parser depend on the protocol, not on any backend.

**Considered options:**

- **Replace celpy entirely with cel-expr-python**. Rejected: cel-expr-python requires a C++ toolchain to build, which blocks pure-Python environments; celpy remains the zero-dependency default. A full replacement also forces a single error-handling model on the engine.
- **Adapter protocol with raise-on-error normalization** (chosen). Each adapter normalizes its backend's error mechanism to a `CelEvalError` raise: celpy already raises `CELEvalError`; cel-expr-python returns `CelValue(type=ERROR)` (never raises), so `CelExprAdapter.eval()` converts `ERROR`/`UNKNOWN` returns to raises. This keeps the engine's `_eval_predicate` `try/except` as the sole barrier — the lock-test bite mechanism is identical under both backends (remove try/except → adapter raises → propagates). Backend-specific compile options (cel-expr-python's `disable_check=True` for free-variable compile) are encapsulated inside the adapter; the protocol signature stays clean.
- **Return-value API** (adapter returns a result/error union instead of raising). Rejected: would require every engine callsite to branch on error type, duplicating the existing try/except pattern and widening the engine's CEL surface.

**Trade-off:** the adapter adds one indirection per compile/eval. The cost is negligible (CEL evaluation is not a hot path relative to handler invocation) and the gain is backend swappability without engine changes — a future backend (e.g. a Rust/WASM CEL evaluator) slots in behind the same protocol.

**Parametrization:** the adapter tests (`test_cel_adapter.py`) run against all three backends, so a regression in any is caught. `_celpy_to_native` normalizes celpy's typed return values to native Python types (e.g. `BoolType(True)` → `True` by identity, not just equality — celpy's `BoolType(True) is True` is `False`), which the identity-asserting lock tests depend on.

## Amendment — third backend (Rust) and three-tier preference

`common-expression-language` (a binding to the Rust `cel-interpreter` crate,
imported as `cel`) was added as a `cel-rust` extra alongside `cel-cpp`, with a
`CelRustAdapter`. Auto-detection became a three-tier preference order: Rust →
C++ → pure Python. This is a behavioral change for environments with both
optional backends installed (previously C++, now Rust), set by the operator.

The Rust backend raises native Python exceptions on eval error
(`RuntimeError` for undefined variable/missing field, `TypeError` for
no-such-overload type mismatch, `ZeroDivisionError` — a subclass of
`ArithmeticError` — for divide-by-zero) and has no return-value
`ERROR`/`UNKNOWN` state, so `CelRustAdapter.eval()` wraps the raised
exception in `CelEvalError` (catch set: `RuntimeError`, `TypeError`,
`ArithmeticError`). It returns native Python primitives directly, needing no
unwrapping helper (unlike `CelpyAdapter._celpy_to_native` and
`CelExprAdapter`'s `.value()`), and free-variable compile needs no flag
(unlike `CelExprAdapter`'s `disable_check=True`) — making it the simplest of
the three adapters. The protocol signature and the engine's sole-barrier
`try/except` are unchanged; the lock-test bite mechanism holds under all
three backends. The adapter tests now parametrize over all three.

## Amendment — cel-python is not free of native code (2026-10-20)

This record calls celpy "the zero-dependency default" for "pure-Python
environments". That was wrong. cel-python 0.4 and later require
`google-re2`, a compiled C++ package, and `celpy.evaluation` imports `re2`
when celpy is imported; celpy uses it only for CEL's `matches()`. celpy
installs easily only where `google-re2` publishes wheels: not on 32-bit
Linux, musl Linux or CPython 3.15. ADR 0054 adds a stand-in for `re2`
backed by Python's `re`, and makes velocitron import celpy only when it is
used.

## Amendment — the C++ binding is a reference backend (ADR 0066)

Auto-detection is Rust, then celpy. `cel-expr-python` stays installable
and is selected by passing `CelExprAdapter`. It is a compatibility and
conformance reference, checked by the adapter cases and the numeric
conformance table, and it is not supported for production runs. ADR 0066
records the decision. The three-tier order in the amendment above is the
history of how the Rust backend was added.

