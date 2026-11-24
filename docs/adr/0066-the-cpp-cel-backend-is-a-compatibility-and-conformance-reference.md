# The C++ CEL backend is a compatibility and conformance reference

**Status:** Accepted (2026-11-24). Amends ADR 0010 (the CEL adapter
protocol and its auto-detection order) and ADR 0053 (which installed
backend the CLI treats as fast enough to stay quiet).

`cel-expr-python` binds Google's official CEL library. ADR 0010 made it
an optional extra. After the Rust backend landed, auto-detection used it
whenever Rust was absent: Rust, then C++, then celpy. That treated the
C++ binding as a production backend.

The C++ backend holds glibc arenas. One exploration leaves a
multi-gigabyte arena resident after its Python objects are gone, and the
next exploration grows from there. On a hosted runner the full C++ suite,
including `prove` parity and arrivals, reached about 7 GB and the runner
shut the job down. Keeping that suite green took a `malloc_trim` after
tests that still held a large arena.

ADR 0053's `CachingCelAdapter` makes backend speed nearly moot for
`prove`. On the net in that record, about 4 400 markings, the check takes
1.9 s on celpy and 1.8 s on Rust. The C++ binding does not earn a place
as a backend the library selects.

It stays, because it is the reference implementation of CEL.

## Decision

`cel-expr-python` remains an optional extra (`velocitron-cel[cel-cpp]`,
forwarded by `velocitron-cli[cel-cpp]` and by the integration-test
project). It is a compatibility and conformance reference. It is not
supported for production runs.

1. **Auto-detection leaves it unselected.** `get_default_adapter()`
   returns `CelRustAdapter` when `common-expression-language` is
   installed, and `CelpyAdapter` otherwise. A caller who wants the C++
   binding passes `CelExprAdapter()`. Installing the extra does not
   change the default.

2. **What "reference backend" means.** The binding is checked for two
   things, both of which construct `CelExprAdapter` themselves. CI's
   `cpp` job installs only the `cel-cpp` extra and runs:
   - the CEL adapter cases in
     `implementations/python/tests/test_cel_adapter.py` (compile,
     evaluation, and `CelEvalError` normalization on every installed
     backend, including the C++ binding when the extra is present);
   - the numeric conformance table
     `test_every_backend_agrees_on_cross_type_numeric_equality` in
     `implementations/python/tests/test_cel_numeric.py`. Its expectations
     are the CEL conformance suite: `int`, `uint`, and `double` share one
     number line, including the `*_lossy_double` cases.

   That job does not run the rest of the suite, `prove` parity, or
   arrivals. The core, Rust, and `all` jobs stay as they are. They select
   Rust or celpy for the suite. A program that passes `CelExprAdapter()`
   takes the glibc arenas that binding holds. The library will not choose
   it, and this alpha makes no support commitment for a run that does.

3. **The CLI note.** ADR 0053 prints its note when the adapter in use is
   celpy. Installing `cel-cpp` does not select a backend and does not
   hide the note. The note still suggests the Rust extra when celpy is in
   use and a wheel exists. It does not suggest the C++ extra. An explicit
   `CelExprAdapter` is a chosen adapter, so the note stays quiet for that
   instance, as it does for Rust.

## Consequences

- An environment with only `cel-cpp` installed runs on celpy, the same
  default as an environment with no optional backend.
- The suite-wide `malloc_trim` in `implementations/python/tests/conftest.py`
  existed so the full C++ job could finish. That job no longer runs the
  suite, so the trim is gone. The progress-line test still returns unused
  arenas before it reads the resident size, because that reading is the
  figure the test checks.
- The Rust extra's version is unchanged.
