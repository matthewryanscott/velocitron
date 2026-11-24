# celpy runs without google-re2

**Status:** Accepted (2026-10-20). Refines ADR 0010 (the CEL adapter
protocol) and ADR 0053 (the CLI's note about the backends).

cel-python, velocitron's default CEL backend, is Python code, but since
version 0.4 it requires `google-re2`, a compiled C++ package. Importing
celpy imports `re2`, which celpy uses only for CEL's `matches()`.
`google-re2` 1.1.20251105 publishes wheels for CPython 3.10 to 3.14 on
macOS 13 and later, glibc Linux x86_64 and aarch64, and Windows (32-bit,
x64 and ARM64). It has none for 32-bit Linux (i686, armv7l), musl Linux or
CPython 3.15, and its source build needs the abseil and RE2 C++ headers.
So on a 32-bit Linux system `pip install velocitron` fails, although every
other dependency installs there, the Rust backend among them.

velocitron should install on small 32-bit systems and run as fast as it can
on 64-bit ones. The Rust backend stays an optional extra.

## Decision 1: a stand-in for `re2`, backed by `re`

When `import re2` fails, celpy uses velocitron's module
`velocitron._re2_standin` as `re2` (Decision 3 puts this fallback into the
bundled copy). The module gives what celpy uses, `search` and `error`,
from Python's `re`. The real `re2` is used whenever it imports.

With the stand-in, `matches()` follows Python's regex rules, not RE2's:

- `re` accepts backreferences (`(a)\1`) and lookaround (`(?=x)`), which RE2
  rejects as a bad pattern. A net that uses them gets a match with the
  stand-in and an evaluation error with RE2.
- RE2 runs in time linear in the input; `re` can take exponential time on
  some patterns, such as `(a+)+$`.
- They also differ in some details of syntax, such as `\Z`.

The CLI's note (ADR 0053) says so when the stand-in is in use, and
`VELOCITRON_NO_CEL_WARNING` hides it.

## Decision 2: celpy is imported only when it is used

`velocitron.cel` does not import celpy at module scope. `CelpyAdapter`
imports it when it is created, and lint and the prover's CEL scan import
it when they first parse an expression. An engine on the Rust or C++
backend never imports celpy. `velocitron lint` and `velocitron prove` still
need celpy's parser, which is Python code over `lark`.

## Decision 3: velocitron bundles celpy

cel-python itself requires `google-re2`, so pip tries to build it where
there is no wheel, and velocitron cannot put a marker on another package's
requirement. So velocitron bundles celpy from cel-python 0.5.0 (Apache
2.0) as `velocitron._vendor.celpy`, with its `LICENSE` and a `VENDORED.md`
that names the source archive, its checksum and each change. The changes
are the import paths and, in `evaluation.py`, the fallback to the stand-in.
The command line (`__main__.py`) and the Cloud Custodian functions
(`c7nlib.py`) are left out.

velocitron no longer depends on cel-python. It depends on celpy's runtime
dependencies directly, `lark` and `pendulum`, and on `google-re2` only
where `google-re2` publishes wheels: CPython before 3.15 on macOS, Windows,
and Linux x86_64 and aarch64. A marker can name the system, the machine and
the Python version, but not the C library, the macOS version, or whether
Python is free-threaded or 32-bit on a 64-bit kernel.

The bundled code is not checked by ruff or basedpyright; it keeps its
upstream form, so a later release can replace it file by file.

Checked on 2026-10-20 with a plain `pip install` of a velocitron wheel, no
override:

- Linux i686 and armv7l (Python 3.12 containers): installs without
  `google-re2`; celpy runs on the stand-in and `velocitron prove` works.
  With the `cel-rust` extra, i686 uses the Rust backend.
- CPython 3.15.0 on macOS: installs without `google-re2`; the test suite
  passes.
- musl Linux (Alpine, x86_64): fails. The marker cannot tell musl from
  glibc, so pip tries to build `google-re2` and fails, also with Alpine's
  `re2-dev` and `abseil-cpp-dev` installed. There, an override drops the
  requirement: uv with a file that holds `google-re2; sys_platform ==
  "never"`, passed as `--override` to `uv pip install` or `--overrides` to
  `uv tool install`.

Considered and rejected:

- **Fork cel-python, or change it upstream** so that `re2` is optional.
  No upstream request for now.
- **Document the uv override for every platform.** A plain `pip install`
  would still fail on 32-bit Linux.
- **A second cel-python version** where `google-re2` has no wheel
  (cel-python 0.3.0 has no `re2`). Two celpy versions with different
  behavior, and 0.3.0 needs `lark` older than 0.13.
- **`google-re2` as an optional extra.** Every platform would get Python's
  regex rules unless the user asks for RE2.

## Consequences

- celpy works without `google-re2`, with Python's regex rules in
  `matches()`, and the user is told.
- A program on the Rust or C++ backend does not import celpy.
- A plain `pip install velocitron` works on 32-bit Linux. On musl Linux it
  needs the override.
- velocitron owns updates of the bundled celpy (`VENDORED.md` says how).
- The tests check the stand-in in a fresh interpreter with `re2` hidden
  (`test_re2_standin.py`).
