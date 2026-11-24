# A failed output keeps its exception in-process

**Status:** Accepted (2026-11-06). Ada asked for the gaps found while
driving a projected net to be fixed. Builds on
ADR 0058 (a net compiles to a Python base class) and ADR 0063 (a strict
advance).

## Why

`VelocitronNet`'s adapter turns a method's raise into a `failed` output with
the error's type and message, so the journal records it and the run loop can
retry. A synchronous caller that runs a projected net with a strict advance
then gets `FailedAttempt` carrying that record, but not the exception. Its
own handlers catch the error types they know (`WorkflowError`, `ToolError`
and `OSError`), and a type name in a record is not one of them. The caller
wrapped every generated method to keep what it raised and raise it again
after the advance.

## Decision

A `failed` transition handler output may carry `exception`, the in-process
exception that failed it. `VelocitronNet`'s adapter sets it to the method's
raise. The engine never puts it in a record: the journal still gets `error`,
the type and message. A strict advance raises `FailedAttempt` from it
(Python `raise FailedAttempt(...) from exception`; TypeScript
`FailedAttemptError` with `cause`), so the caller reads `__cause__` / `cause`.

**Considered options:**

- Raise the handler's own exception from a strict advance. Rejected: a
  failed output without an exception (a handler that returns `failed`, or
  `HandlerNotFound`) still needs `FailedAttempt`, and one error type to
  catch is simpler than two.
- Keep the last raise on the `VelocitronNet` instance. Rejected: it is the
  workaround moved into the base, and stale after the next firing.
- Put the exception in the record. Rejected: records are journaled as JSON.

## Consequences

- `fire` keeps its `(marking, record)` result; the strict loop reads the
  exception through a private `_fire` (`#fire`).
- Bench's wrapper can go: it catches `FailedAttempt` and raises
  `__cause__`.

## References

- `spec/handler-contract.md` — transition handler output
- `spec/firing-semantics.md` (e) — strict advance
- [ADR 0058](0058-a-net-compiles-to-a-python-base-class-and-the-journal-traces-and-replays-the-run.md),
  [ADR 0063](0063-a-strict-advance-raises-on-a-conflict-or-a-failed-attempt.md)
