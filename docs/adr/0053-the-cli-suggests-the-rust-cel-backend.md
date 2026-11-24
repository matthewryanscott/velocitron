# The CLI suggests the Rust CEL backend

**Status:** Accepted (2026-10-20). Refines ADR 0010 (the CEL adapter
protocol and its three backends).

velocitron picks the fastest CEL backend that is installed (ADR 0010):
Rust, then C++, then the pure-Python `cel-python`. Only `cel-python` is a
core dependency, so a plain `pip install velocitron` runs every CEL
expression in pure Python. For `velocitron prove` that is several times
slower: on a net with about 4 400 markings, the check takes 14 s with
`cel-python` and 6 s with Rust. Users do not know the extra exists.

## Decision 1: the CLI prints a note, the library stays quiet

The `velocitron` CLI writes one note to stderr, at most once per process,
before a `prove`, `play` or `equiv` command. These commands evaluate
CEL many times. The note says that the Rust backend makes checks several
times faster and gives the install commands:

```
pip install 'velocitron[cel-rust]'
uv tool install --force 'velocitron[cel-rust]'
```

The library (`Engine`, `parse_net`, `prove`) never prints or warns. A
program that uses the library chose its own dependencies, and it can pass a
`cel_adapter` of its choice. `velocitron.cel.slow_backend_hint()` returns
the note, so another front end can show it too.

## Decision 2: when the note is shown

The note is shown only when all of these are true:

- The pure-Python backend is in use. The C++ backend is close to Rust in
  speed, so a user who has it gets no note.
- `common-expression-language`, the Rust backend's package, has a wheel for
  this platform: CPython 3.12 to 3.14 on macOS (x86_64, arm64), Linux with
  glibc (x86_64, aarch64, armv7l, ppc64le, s390x, i686) and Windows
  (AMD64), and CPython 3.15 on Linux x86_64 and i686. Elsewhere pip must
  build it from source with a Rust compiler, so the note would not help.
  The table is in `velocitron/cel.py`; update it when the package's wheels
  change.
- `VELOCITRON_NO_CEL_WARNING` is not set to a non-empty value.

The CLI has no setting that chooses a backend, so "the user chose the
pure-Python backend" can only mean the environment variable.

## Considered options

- **A Python `warnings` category.** It reaches library users too, and the
  default filters show a warning once per call site, not once per process.
  Library users would have to filter it, and the CLI would still need its
  own text.
- **Make the Rust backend a core dependency.** Rejected: velocitron must
  install with no native code on every platform. ADR 0010 keeps
  `cel-python` as the default for this reason.
- **Show the note only when stderr is a terminal.** Rejected: coding agents
  run the CLI without a terminal and are the users who run `prove` most.

## Consequences

- A new user learns about the faster backend the first time they run a
  check, with a command they can copy.
- The test suite sets `VELOCITRON_NO_CEL_WARNING` for every test, so the
  pure-Python CI leg sees the same stderr as the others.

## Amendment: the prover keeps CEL results

The same day, `velocitron prove` started to keep each CEL result per
expression and activation values (`CachingCelAdapter`). In a search, about
99 % of evaluations repeat an earlier one, so the backend's speed now
matters little to `prove`: the net above takes 1.9 s with `cel-python` and
1.8 s with Rust. The note's text now says that Rust evaluates CEL faster,
not that checks are faster. It still holds for `play`, `equiv` and the
engine, which do not keep results. Whether the note is still worth showing
before `prove` is open.

## Amendment: the quiet rules, and how the table stays current

- The wheel check uses the interpreter, not the kernel. A 32-bit Python on
  a 64-bit kernel needs an `i686` or `armv7l` wheel on Linux, and a `win32`
  wheel on Windows, which the Rust package does not publish; the note stays
  quiet there. It also stays quiet on Windows on ARM, musl Linux, a
  free-threaded build before 3.14 or outside Linux, CPython 3.15 except on
  Linux x86_64 and i686, and any Python version the table does not list.
- This record called `cel-python` "pure Python"; it is not (ADR 0010's
  amendment). Its texts now name it "cel-python".
- The table stays in `cel.py`, not a check of the running platform's wheel
  tags against PyPI: the CLI must not reach the network, and a tag match
  needs the `packaging` library, which velocitron does not depend on.
  `tools/cel_rust_wheels.py` prints the wheels PyPI has now. Run it when the
  `cel-rust` extra's version bound changes, and update the table and the
  tests in `test_cel_backend_hint.py`.
- When the `re2` stand-in of ADR 0054 is in use, the same note also says
  that `matches()` follows Python's regex rules. One variable,
  `VELOCITRON_NO_CEL_WARNING`, hides the whole note.

## Amendment: the Rust note only before `play` and `equiv`

`velocitron prove` keeps CEL results, so the Rust backend hardly speeds it
up. The note suggests the Rust backend only before `play` and `equiv`.
Before `prove` the note says only that `matches()` follows Python's regex
rules, when the stand-in of ADR 0054 is in use.

## Amendment — the C++ binding is not a selected backend (ADR 0066)

Auto-detection no longer picks the C++ binding, so an installed
`cel-expr-python` is not a reason the note stays quiet. The note is shown
when celpy is in use. Installing `cel-cpp` leaves the default on celpy and
the note visible. Decision 2's line that the C++ backend is close to Rust
in speed described the old auto-detection order, in which having the C++
extra meant the library was running it. ADR 0066 is the current order:
Rust, then celpy, with the C++ binding as a conformance reference.

