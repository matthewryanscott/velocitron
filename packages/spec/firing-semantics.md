# Firing Semantics

The canonical, prose-and-types definition of the **runtime firing semantics and policy**
for a colored Petri net — the engine that turns a net's static structure (places,
transitions, arcs) and its optional named behavior bindings into a stream of
**attempt records** (one record per firing attempt, of either status — an
occurrence, in the books' sense, is only what a `completed` record records, since a
failed attempt consumes nothing and changes no marking): enablement detection,
consume/invoke/deposit, atomic rollback on failure, the
firing-policy handler's *integration* into the engine loop, and the decoupled firing
journal that makes the run replayable as an occurrence sequence — of the net together
with its environment once injections join the stream, the **trajectory** by the short
name. The net declares *what* may happen *where*
and may bind a transition handler; the handler contract pins down what each bound handler
receives and returns; this spec pins down how the engine drives firing attempts against
that.

The net document (`spec/net-schema.md`) and the handler registry contract
(`spec/handler-contract.md`) are the two layers this spec builds on. It reopens
**neither** as a contract layer except through documented additive amendments: optional
consume-pattern `weight` (D7), and the optional transition behavior binding recorded by
the 2026-07-15 amendment to ADR 0003 (D11). The machine-checkable surface originally
introduced here is the **firing journal hook contract** — the shape of the record the
engine emits to an attached journal — **not** an on-disk schema the engine imposes (the
journal implementation owns storage and sequence; see design decision D4).

Like `handler-contract.md`, this document is **normative prose plus illustrative type
definitions** — the firing engine is a code module, not a serialized document. The
JSON-serializable I/O messages (the `FiringRecord`) belong here; the net document does
not carry them. The Python `TypedDict`/`Protocol` shapes reproduced below are the
machine-checkable surface that keeps prose and code from drifting; their names match
`implementations/python/src/velocitron/engine.py` and `journal.py` exactly.

## Purpose and the engine's place in the layering

A net is **pure coordination**: it routes and gates, never computes (ADR 0001, stated in
`net-schema.md`). Executed computation lives in explicitly bound **handlers** resolved by
name through the registry (ADR 0003 amendment, stated in `handler-contract.md`). The
firing engine is the glue between the two: it reads structure, resolves a declared
binding when present, and drives the consume → invoke → deposit → record cycle
deterministically. A handlerless transition is valid structure but has no structural
firing semantics. The engine itself holds no domain logic. Replay holds because the net
never computes: same net + same inputs + same handler results produce the same firing
sequence, and the journal is that sequence's deterministic record (D5).

This document covers six concerns — (a) enablement, (b) firing, (c) failure handling,
(d) the decoupled firing journal, (e) selection (firing-policy integration), and (f) the
environment-arrival token-injection seam and native timed transitions — each pinned to
prose plus the illustrative type shapes that keep spec and code from drifting.

## (a) Enablement

A transition is **enabled** when all of the following hold.

**Boolean condition constant.** Every boolean condition is strict: only the exact
boolean value `true` satisfies CEL predicates, named predicate handlers, guards, timer
conditions, correlated inhibits, and correlated consume/read arcs; exact `false` is the
ordinary negative result. Every non-boolean result is a condition-evaluation error, and
implementations must never apply host-language truthiness. The result then follows that
surface's existing error posture: predicate/timer false, guard not-enabled, and
correlated inhibit or correlated consume/read arc fail-closed.
The numeric `timer.maturity` scheduling expression is not a boolean condition and remains
unchanged.

- Every **input arc** is satisfiable:
  - `mode: "consume"` — there exist at least `weight` tokens (default `weight: 1`) of the
    arc's declared `type` in the source place, each passing the arc's `predicate` (inline
    CEL or named pure predicate handler; absent predicate ⇒ any token of the type). The
    arc consumes exactly `weight` matching tokens on fire. With an optional
    **`correlate: {cel}`** inscription (ADR 0030) the arc is also a **join**: every token
    it binds must satisfy `correlate` over `{token: <that token's data>, binding: <the
    candidate binding as place-keyed data>}`. See the evaluation-order paragraph below.
  - `mode: "inhibit"` — a **zero-test**: there is **no** matching token in the source
    place. An inhibit arc gates enablement on emptiness and **consumes nothing**; it
    never contributes tokens to the binding. `weight` is ignored on inhibit arcs
    (validated to be absent or `1` by the parser, D7). With an optional
    **`correlate: {cel}`** inscription (ADR 0017) the zero-test becomes **per-binding**
    (the anti-join): a token "matches" — and blocks — only if, beyond the arc's
    `type`/`predicate`, its `correlate` CEL holds over `{token: <candidate data>,
    binding: <the candidate binding as place-keyed data>}`. See the evaluation-order
    paragraph below; an uncorrelated inhibit arc keeps the whole-place zero-test,
    evaluated before any binding work, unchanged.
  - `mode: "read"` — **test-without-consume** (ADR 0012): there exist at least `weight`
    matching tokens in the source place, exactly the same presence test as `consume`. A
    read arc **contributes** its `weight` bound tokens to the binding (they are visible to
    the guard, handler, and firing record) but **removes nothing** on fire. It is the
    presence-side dual of `inhibit`. A read arc may carry `correlate` exactly like a
    consume arc (ADR 0030).
- The **timer** (if the transition declares one, ADR 0018) holds for the chosen binding:
  the `timer.cel` expression evaluates to exact boolean `true` against a closed
  environment — the reserved variable `clock` is the `data` of the **first** token in the
  `timer.clock` place, and each `timer.bind` variable is the `data` of the first token
  bound from its named place in the candidate binding. An **empty clock place ⇒ not
  enabled** (no time reference, not matured). A runtime CEL eval error or non-boolean
  result degrades to condition-false for that binding (symmetric with D6), never a crash.
  The timer is evaluated **per candidate binding**,
  after the sub-multiset validity check and **before the guard** (pure before
  possibly-impure) — so binding enumeration skips unmatured tokens and finds a matured
  one, which is what makes per-instance deadline isolation automatic: two tokens carrying
  distinct deadlines against one shared clock mature independently.
- The **guard** (if present) returns `true` for the chosen binding. The guard sees the
  full input binding across all *consume-mode* **and *read-mode*** arcs — all `weight`
  tokens per arc; inhibit arcs are not in the binding (they contribute no tokens). If no
  guard is declared, this check is skipped. A guard that **raises** (an impure guard's runtime error, ADR 0002)
  **degrades to not-enabled** — the engine catches the exception and treats the transition
  as not enabled, symmetric with a predicate handler's runtime error (D6 ⇒ predicate
  false) and an unresolved guard ref (`resolve_guard` `HandlerNotFound` ⇒ not enabled); it
  is never a runtime crash.

A transition's `handler` is **not an enablement condition**. A handlerless transition may
therefore appear in `enabled_transitions` when its arcs, timer, and guard are satisfied.
Behavior availability is enforced at the execution boundaries below, not disguised as
structural disablement.

**Binding selection (the colored-Petri-net core).** A *binding* is, per consume-mode
arc, a selection of exactly `weight` tokens (each satisfying its arc's predicate), drawn
from the current marking. In prose the spec names the recorded object **the tokens a
firing used** (see (d)'s record comment) — the books' word *binding* is an assignment of
values to variables (G&V p. 36), a different object the CEL `binding` variable keeps its
name for. A transition is enabled iff **some** binding satisfies all
consume arcs (including their correlates) **AND** the timer (if declared) holds for it
**AND** the guard returns
`true` for it. The engine selects the **first such
binding in deterministic order** (design decision D2) as the firing binding. This is the
seam where determinism meets the CPN "exists a binding" semantics; `weight` generalizes
the classical one-token-per-arc case (the `weight: 1` default) to multi-token arcs (the
petrinet.org `storage >> {Abstract: 2} >> distribute` form referenced in Q1).

**Evaluation order with correlated arcs (ADR 0017, ADR 0030).** The exact order per
transition is:

1. **Uncorrelated inhibit arcs** (no `correlate`) run their whole-place zero-test
   **before any binding work** — cheap, binding-independent, exactly the pre-ADR-0016
   behavior. Any match fails the whole transition.
2. **Candidate bindings are enumerated** over the consume- and read-mode arcs in the
   deterministic order of D2 (arcs in declaration order; per-arc lexicographic
   `weight`-combinations; cartesian product).
3. **Per candidate binding, in that order**: the sub-multiset validity check (D1), then
   every **correlated consume or read arc**'s join (ADR 0030) — arcs in declaration
   order, each arc's `weight` tokens in bound order, each token evaluated over
   `{token: <that token's data>, binding}` and required to yield exact `true` — then
   every **correlated inhibit arc**'s per-binding zero-test — satisfied iff **no** token
   in its source place, of the declared `type` and passing the arc's single-token
   `predicate` (which narrows the correlation candidates), satisfies `correlate` over
   `{token, binding}` — then the timer (if declared), then the **guard**. The correlated
   tests sit after the structural sub-multiset check and **before** the guard: they are
   pure, structural, arc-level filters, and the possibly-impure guard (ADR 0002) only
   sees bindings that passed every structural gate.
4. The **first surviving binding** is selected. A correlated arc of any mode
   **filters** candidate bindings; it never reorders them — a rejected binding is skipped
   exactly like a sub-multiset-invalid combo or a guard-rejected binding, so
   first-surviving selection and replay determinism (D2/D5) hold unchanged.

**What a consume/read correlate sees (ADR 0030).** `binding` is the **complete**
candidate binding — every consume- and read-mode arc of the transition, the correlated
arc's own tokens included — assembled before any correlate runs. So a correlate may refer
to an arc declared before or after it, and the declaration order of the checks only
decides which failing check stops the evaluation first, never whether the binding
survives. The arc's single-token `predicate` has already filtered its candidates, and the
other arcs' tokens in `binding` have passed their own predicates. A correlate that needs
an arc's token which that arc does not bind (for example `binding.p[1]` on a weight-1
arc) is an eval error.

**How `binding` is keyed (ADR 0032).** Every CEL surface that sees `binding` — a
`correlate` on any input mode and a produce template's `cel` — sees the same map: for
each consume- and read-mode source place, the list of its bound tokens' `data`. The
key is the place name, unless the transition declares `bindingNames` (key → place);
then the keys are exactly those names, and two names for one place see the same list.
Composition merge writes `bindingNames` with the constituent net's local place names, so
`binding.inbox` in a constituent still means the tokens bound from that net's `inbox`
after the merge renames it (`shipping.inbox`, or a fused name). Timers do not see
`binding`: their `bind` variables already name places, and the merge rewrites those
places. The guard handler, the transition handler, and the firing record keep
place-keyed `inputTokens` under the net's own place names (`spec/handler-contract.md`,
"Composition-safe handlers").

A `correlate` **eval error or non-boolean result fails closed**: the candidate token is
treated as blocking and the binding is rejected — degrading toward not-enabled like a
guard that raises (D9), never a crash. This is deliberately **not** D6's
predicate-false rule: error-as-false on an inhibit test would fail *open* (enable a
transition whose safety test crashed). The single-token `predicate` on an inhibit arc
keeps its existing D6 behavior (eval error or non-boolean ⇒ that token does not match).
A correlated **consume or read** arc fails closed the same way: an eval error or a
non-boolean result rejects the binding, because the join is unproven and the token may
not be bound. This matches D6's degrade-toward-not-enabled posture for a single-token
predicate on a consume arc. `correlate` is compiled at parse time like all inline CEL
(D6) and is valid on every input mode (`spec/net-schema.md`).

The illustrative engine surface for enablement:

```python
def enabled_transitions(net: Net, marking: Marking, *,
                        attempt: int = 0) -> list[str]:
    """Every transition whose enablement holds with at least one binding.

    Deterministic: returns transition ids in net declaration order.
    Includes weight-token satisfaction, inhibit zero-tests, predicate
    evaluation, and guard evaluation over the selected binding (D2).
    `attempt` is threaded to `select_binding` so an attempt-sensitive
    guard sees the same attempt the subsequent fire will use (D9)."""

def select_binding(net: Net, transition: Transition, marking: Marking,
                   *, attempt: int = 0) -> dict[str, list[Token]] | None:
    """The first enabled binding in deterministic order (D2), or None.

    A binding is `weight` bound tokens per consume-mode AND read-mode arc,
    keyed by source place (D1). When arcs share a source place, their bound
    tokens are concatenated in arc-declaration order. Inhibit arcs
    contribute nothing; read arcs contribute their tokens but those are not
    removed on fire (test-without-consume, ADR 0012). None ⇒ the transition
    is not enabled. `attempt` is threaded so the enablement probe and the
    subsequent fire share one attempt (D9)."""
```

## (b) Firing

When a transition fires with its selected binding, the engine runs a fixed four-phase
cycle. Consumption is **tentative**: the marking change is committed only if the fire
completes without a deposit violation (see (c) and D3). **Atomicity:** any firing failure
(`NotEnabled`, handler `failed`, absent or unresolved handler, or deposit-contract
violation) leaves the marking **unchanged** — tentative consumption is never committed.

1. **Consume (tentative)** — remove, from each consume-mode arc's source place, the
   `weight` bound tokens. Inhibit arcs consume nothing; **read arcs consume nothing
   either** — their bound tokens stay in the marking (test-without-consume, ADR 0012).
2. **Invoke** — if the transition has a behavior binding, resolve that handler ref via
   the registry and call it with `{transitionId, inputTokens, firingContext}`
   (`handler-contract.md`). `inputTokens` is the resolved binding (shape per D1:
   `weight` tokens per consume- **and read-mode** arc, keyed by source place,
   concatenated across arcs sharing a place in arc-declaration order — read tokens are
   present here but are not removed by step 1). A declared ref that is unregistered is a
   transition failure, not a crash. Because binding/enablement was checked first, a
   disabled handlerless transition has already returned `NotEnabled`. If the enabled
   transition has **no** behavior binding, `Engine.fire` returns an atomic `failed`
   record with `error.type == "HandlerNotFound"` and a clear message that the transition
   has no handler. It does not derive a ref from the transition name or invoke a no-op.
3. **Deposit (on `completed`)** — preserve every produce arc as a
   declaration-ordered template; parallel templates may share a destination and type,
   and no destination-keyed last-template collapse is permitted. Each handler token is
   valid when its `{type, place}` matches **any** template and is deposited once in
   handler order. A destination may therefore receive every type its templates declare;
   a handler token whose destination/type pair matches no template is a
   **deposit-contract violation**, handled by the engine-instantiation mode (D3).
   For every template whose destination/type pair has no handler token, literal `data`,
   when present, emits one fixed token in template declaration order; a template's
   `cel` (ADR 0023, mutually exclusive with `data`) instead emits one **computed** token —
   the expression is evaluated over `{binding: <place-keyed bound-token data>}` (the
   ADR 0017 binding map: consume- and read-mode arcs, keyed by `bindingNames` when the
   transition declares them, ADR 0032) and the result, which must be a
   JSON object, becomes the token's `data`. A `cel` evaluation error or non-object
   result is a **deposit-contract violation** (D3): the firing fails atomically with
   `error.type == "DepositViolation"`, exactly like a handler token outside the
   contract — deposit runs post-consume, so there is no binding to skip; the
   predicate's degrade-to-false (D6) and the guard's not-enabled (D9) postures do not
   apply here. Handler tokens for
   a pair win over that pair's literal and computed fallbacks. Handlerless transitions
   never reach deposit; template fallback data, literal or computed, is not structural
   firing behavior. Last, every deposited token, from a handler or a fallback, is
   checked against the net's declared `domains` (ADR 0037): a token whose color has a
   domain and whose field is missing or holds a value outside it is a
   **deposit-contract violation** (D3), with the message
   `token <color> into (<place>) holds <path> = <value>, outside domain <key>: <values>`
   (or `has no <path>, which domain <key> requires`), the same in every implementation.
4. **Record** — emit a firing record to the attached journal hook, if any (see (d)).
   Recording is **optional**: the engine fires correctly with no journal attached.

`outputTokens` may be empty (a consume-only transition, e.g. a commit).

The illustrative engine surface for firing:

```python
def fire(net: Net, marking: Marking, transition: str, *,
         attempt: int, strict: bool = False) -> tuple[Marking, FiringRecord]:
    """The tentative consume -> invoke -> deposit -> record cycle.

    Returns the post-fire marking and the engine-emitted FiringRecord
    (no `sequence` — the journal owns unique-id numbering if it wants
    one, D4). On any failure (`NotEnabled`, handler `failed`, absent or
    unresolved handler, or deposit-contract violation) the returned marking
    equals the input marking (atomic rollback) and the record carries
    `status: "failed"`. With `strict=True` that failure raises
    `FailedAttempt` instead, as a strict advance does ((e)).
    """
```

## (c) Failure handling

On handler `status: "failed"` (or a deposit-contract violation, a declared-ref
resolve-miss, or an absent transition behavior binding): the engine **does not consume
input tokens** — the marking is unchanged (consume rolled back, per the atomicity rule in
(b)). The failure is emitted to the attached journal hook (if any) as a record with
`status: "failed"` and structured error information. Both an unregistered declared ref
and an **enabled** handlerless Engine firing use
`error.type == "HandlerNotFound"`; the latter's message states that the transition has no
handler. A disabled handlerless transition fails earlier as `NotEnabled`. Retry is
**net-modeled**: the net's places and arcs drive any next attempt, never a hidden handler
or engine no-op (`handler-contract.md` decision 4). The only defined handler statuses are
`"completed"` and `"failed"`; `"pending"` is unsupported.

**Deposit-contract violation handling is configurable at engine instantiation** (D3):

- With **no journal**, the default is to **raise** (a programmer-bug signal).
- With a **journal attached**, the engine may be configured to **record-then-raise**
  (default — emit the violation record to the journal, then raise) or **record-then-drop**
  (emit the record, leave the marking unchanged, and continue the advance loop).

In every case the marking is **unchanged** on a violation (atomic rollback of the
tentative consume). `"raise"` is the only legal `deposit_violation` value when
`journal is None`.

**The failure budget (opt-in, ADR 0015).** Because atomic rollback leaves a failed
transition's inputs in place, a persistently failing transition stays enabled forever:
each failed fire burns one step of the selection loop with the marking unchanged (**spin**), and under
`first-found` it starves every transition after it in declaration order (**starvation** —
the reading hour's livelocked deadline). `Engine(registry, max_consecutive_failures=N)` caps
this: within one `advance` call, the engine counts each transition's **consecutive failed
firings** — every `failed` record `fire` returns to the loop counts, whatever the cause
(handler-`failed`, resolve-miss, not-enabled, or a deposit violation under
`record_then_drop`) — and a transition whose count reaches `N` is **exhausted**: excluded
from the enabled list handed to the firing policy (see (e)), so selection moves past it.
A guard that raises degrades to not-enabled at the *enablement* step (D9), so the
transition is never selected and never counted. **Reset:** any `completed` firing resets
**every** count — the marking changed, so an exhausted transition's inputs may differ and
it earns a fresh budget; counts are scoped to a single `advance` call (a new `advance` starts
clean; `fire` called directly never counts). When every enabled transition is exhausted
the advance stops (**quiescence-by-exhaustion**) instead of burning the remaining steps. The
default is `None` — no budget, exactly the prior behavior (a persistently failing
transition may spin to `max_steps`); `N < 1` is a configuration error (`ValueError` at
construction). The budget is **deterministic** — derived from the recorded attempt records themselves,
never wall-clock — so replay (D5) holds: the journal shows the `N` failed records and
then the transition's absence until a `completed` record, which is also why exhaustion is
not separately journaled (it is a pure function of the recorded sequence). `fire` and
`enabled_transitions` are untouched — the budget is a *selection* concern, like the
policy (ADR 0014's scoping argument).

## (d) The firing journal — decoupled from the engine via hooks (D4)

The journal is **not tightly coupled to the engine**. The engine exposes **hooks** to
which a journal may be attached; the journal may be **absent** (the engine fires and
discards records) or implemented in any number of ways. The engine emits a **firing
record** (an **attempt record**, of either status — see the intro) through a `Journal`
hook; it does **not** assign a `sequence`, does **not**
choose a storage format, and does **not** know whether records are kept at all.

The numbered stream a journal produces — firing attempt records and injection records
interleaved from one monotonic `sequence` — is an **occurrence sequence of the net
together with its environment** (the books' phrase: an injection is not a firing of our
net, it is a step of the environment side); its short name in prose is the
**trajectory**.

`sequence` (the monotonic unique id) is the **journal implementation's concern**, never
the engine's. The engine-emitted record carries **no `sequence`**; the
journal implementation assigns one if it wants a unique id. `firingId` keeps its
`handler-contract.md` meaning (the per-attempt logical id, deterministic for replay,
derived from `netId` + transition + `attempt`); it is **not** amended or replaced by the
engine.

The hook contract (illustrative Python shape; the authoritative version lives in
`implementations/python/src/velocitron/journal.py`):

```python
class FiringRecord(TypedDict):
    # What the engine emits per firing attempt — an **attempt record**, either
    # status: an occurrence, in the books' sense, is only what a *completed*
    # record records (a failed attempt consumes nothing and changes no
    # marking). NO sequence — the journal
    # implementation owns unique-id numbering if it wants one (D4).
    firingId: str                              # per-attempt logical id (handler-contract.md)
    netId: str
    transition: str
    attempt: int
    status: Literal["completed", "failed"]
    inputTokens: dict[str, list[Token]]        # the tokens the firing used, keyed by place (empty on failure)
    outputTokens: dict[str, list[Token]]        # tokens deposited (empty on failure)
    error: HandlerError | None
    metadata: dict[str, Any]
    timestamps: FiringTimestamps                # metadata/logging only (handler-contract.md)

class InjectionRecord(TypedDict):
    # What the engine emits per token injection — any environment arrival,
    # clock/deadline tokens included (see (f)).
    # A consumer-driven marking event, NOT a firing. NO sequence.
    injectionId: str                            # <netId>/@inject/<place>/<attempt>
    netId: str
    place: str
    attempt: int                                 # first-class attempt (also in injectionId)
    kind: Literal["inject", "update"]           # append vs replace-place
    tokens: list[Token]                          # token(s) now present by injection
    replaced: list[Token]                        # token(s) an "update" removed
    timestamps: FiringTimestamps                # metadata/logging only

class Journal(Protocol):
    def record_firing(self, record: FiringRecord) -> None: ...
    def record_deposit_violation(self, record: FiringRecord) -> None: ...
    def record_injection(self, record: InjectionRecord) -> None: ...
```

- `record_firing` is called on **every firing attempt that is not a
  deposit-contract violation** — i.e. on `completed` attempts and on `failed`
  attempts whose failure is a not-enabled, resolve-miss, or handler-`failed`
  result — iff a journal is attached. A **deposit-contract violation attempt
  is NOT routed through `record_firing`**; it is routed exclusively through
  `record_deposit_violation` (below), so each attempt occupies exactly one
  sequence slot in a journal that numbers both methods from one stream (e.g.
  `JsonlJournal`). This avoids double-recording the same failed record and
  keeps the attempt record and the violation alert as distinct,
  non-overlapping hook channels.
- `record_deposit_violation` is called on a deposit-contract violation **only
  when the engine is configured to record it** (D3 — `record_then_raise` or
  `record_then_drop`; never under `raise`, which raises before any hook
  emission); it receives the failed record (marking unchanged, `status:
  "failed"`, `error` describing the violation). `record_firing` is **not**
  called for the same attempt.
- `record_injection` is the **third hook channel**, called on every
  `Engine.inject_token` — and once per token of an `Engine.inject_tokens`
  batch (see (f)) — iff a journal is attached. It carries an
  `InjectionRecord` — a consumer-driven marking event, **not** a firing, so it
  is never routed through `record_firing`. A journal that numbers all three
  channels from one stream (e.g. `JsonlJournal`) gives an injection and an
  interleaved firing consecutive sequence slots, so replay stays deterministic
  across injected time (ADR 0013).

**Default journal implementation** — `JsonlJournal`: assigns each record a
monotonic, **0-based `sequence`** (this implementation's own unique id; the
engine never sees it, D4) and buffers it in memory. With `prefix=None` (the
default) records accumulate in memory only and nothing is written to disk;
`flush` is a no-op. With `prefix` set, `flush` writes all buffered records as
one JSON object per line to a **timestamped `.jsonl` file**
(`<prefix>-<ISO8601>.jsonl`), creating parent directories as needed. The Python reference
provides this journal as the default in-memory/JSONL implementation; the `Journal`
protocol remains storage-format-neutral.

```python
class JsonlJournal:
    """The default Journal: assigns a monotonic 0-based `sequence`
    (its own unique id; the engine never sees it, D4), buffers each
    record in memory, and on `flush` writes all buffered records as one
    JSON object per line to `<prefix>-<ISO8601>.jsonl`. With
    `prefix=None` (the default) `flush` is a no-op and nothing reaches
    disk."""

    def __init__(self, prefix: str | None = None) -> None: ...
    def record_firing(self, record: FiringRecord) -> None: ...
    def record_deposit_violation(self, record: FiringRecord) -> None: ...
    def record_injection(self, record: InjectionRecord) -> None: ...
    def record_net_revision(self, net_document: dict) -> None: ...
    def flush(self) -> None: ...
```

Like `record_trace`, `record_net_revision` is an optional hook channel in the
same shared sequence stream: `register_into` (the net base and the generated
composition classes) calls it only through a capability check. The stored
record IS the net document's own keys — no wrapper field names the channel on
a JSONL line; `handler-free` tape replay re-derives the channel from the
record's key shape (a net document carries none of `firingId` / `injectionId`
/ `event`), and a durable log names the channel in its `kind` column.

**Replay contract (D5).** Replay = re-run the engine from the same net + same initial
marking + the same handler bindings (which return the same results) with the same journal
attached, and assert the produced journal equals the recorded journal, record-for-record.
Comparison **excludes `timestamps`** (metadata-only, non-deterministic wall-clock) and
treats `sequence` as deterministic (monotonic per journal; equal across re-runs with identical
firing counts/order). The journal is the deterministic *record*. Handler-free tape replay
is a separate durability surface in the Python reference and is not part of this
engine/journal replay contract (D5).

### (d-2) The trace journal — an optional capability (ADR 0058, Decision 6)

A **trace record** is a timing and observability record in the OpenTelemetry
sense — a point-in-time observation of the engine's and runtime's progress,
for dashboards, latency breakdowns, and debugging — **not** a causal trace of
the Petri net books: it changes no marking and carries no replay decision.
The journal is the one place records go; a journal **may also implement** the
optional `TraceJournal` capability:

```python
@runtime_checkable
class TraceJournal(Protocol):
    def record_trace(self, record: TraceRecord) -> None: ...
```

When the attached journal has the hook, the Engine and the Runtime emit one
record at each of **six events**:

- **`tokens_reserved`** (Runtime only) — after `engine.reserve` returns a
  reservation in the Runtime's admission step; the sync Engine `fire` has no
  reserve step.
- **`handler_started`** / **`handler_returned`** — immediately around the
  handler call in the Engine's `fire` and around the Runtime's `_invoke`.
  A generated net class's method raise reaches the journal as
  **`handler_returned` with `status: "failed"`** and the `error` — the
  `VelocitronNet` base turns a method's raise into a `failed` output before
  the Engine sees it. `handler_returned` carries the returned output's
  `status`. **`handler_raised`** — a handler callable that raises OUT of
  `Engine.fire` (a hand-registered plain function): the Engine wraps the
  call, emits, and re-raises; its crash behavior is unchanged. The Runtime
  catches a raise and turns it into a `failed` output (unchanged); it emits
  `handler_raised` at that catch.
- **`guard_checked`** — around the guard call in binding selection, one
  record **per guard call, probes included** (enablement probes call the
  guard like any other consumer): with `result` True/False, or with the
  exception in `error` and `result: None` when the guard raises (which the
  Engine reads as not-enabled, unchanged).
- **`predicate_checked`** — around the **named predicate handler** call, one
  record per call with the answer in `result`, or the exception in `error`
  (which the Engine reads as predicate-false, unchanged). Inline CEL
  predicates are compile/eval, not handlers, and get **no** record.

**Record shape** — `TraceRecord`: `event`, `netId`, `firingId`, `transition`,
`handler` (the ref the engine resolved: the transition `handler`, the
`guard`, or the predicate `handler` string), `method` (the callable's
`__qualname__` when present, via `getattr(handler, "__qualname__", None)`;
informational), `at` (ISO 8601 UTC wall-clock), `status`, `result`
(`guard_checked`/`predicate_checked` only), `error` (`HandlerError` on any
raised call).

- **Join by `firingId`, never by sequence.** The journal numbers records as
  they arrive, and `handler_started` is written before the firing record
  exists; both records carry the `firingId`, so a reader joins them on it.
- **Tokens are not repeated.** The firing record's `inputTokens` already
  holds every token the firing used (consumed and read alike).
- **`sequence` is the journal's own.** The emitter never sets it; a journal
  that numbers all channels from one stream (`JsonlJournal`,
  `DurableJournal`) interleaves trace records in that same stream.
- **A journal without the hook is unchanged.** `record_trace` is called only
  through a capability check; a journal lacking the hook records exactly
  what it recorded before this capability existed.
- The durable backend stores trace records with event kind `trace`;
  handler-free tape replay skips them (no marking effect), like deposit
  violations and net revisions.
- The TypeScript Engine is not updated for this capability (lockstep waived
  for the codegen work; ADR 0058, Decision 6).

```python
class JsonlJournal:  # trace records are one more kind in the same stream
    ...
    def record_trace(self, record: TraceRecord) -> None: ...
```

## (e) Selection (firing-policy integration)

The engine loop, per step:

1. **Compute `enabledTransitions`** — every transition whose enablement (a) holds with
   at least one binding. The loop passes its step counter as `attempt` to
   `enabled_transitions`, and the subsequent `fire` uses the same `attempt`, so the
   enablement probe and the fire share one `attempt` and an attempt-sensitive guard
   cannot flip between them (D9). With a **failure budget** configured (see (c); ADR
   0015), exhausted transitions (consecutive-failure count ≥ `max_consecutive_failures`)
   are then excluded from the list — they remain *enabled* in the enablement sense, but
   are not selectable until a `completed` firing resets the counts. An empty
   post-exclusion list stops the advance (quiescence-by-exhaustion). In the
   symbolic-advance mode (an `outputs=` provider, below), a candidate the
   provider skips with `None` is excluded in the same spirit — no record, the
   transition stays enabled — and a candidate whose settled firing fails is
   likewise excluded for the remainder of this advance (that one does record,
   as (f) says); either way the loop quiesces instead of spinning.
2. **Call the configured firing-policy handler** with `{marking, enabledTransitions,
   priorities, consecutiveFailures}`; receive one transition id or `None`
   (`handler-contract.md`).
3. `None` ⇒ **stop** (quiescence). Otherwise fire that transition (binding selection per
   (a)), emit the record to the journal hook (if attached), update the transition's
   consecutive-failure count (increment on a `failed` record; any `completed` record
   clears all counts), and repeat.

**The firing-policy ref is validated at engine construction.** The policy is Engine
config (not net-referenced), known at `Engine.__init__` with no transition context to
fail within. An unresolvable policy ref raises `HandlerNotFound` at construction as a
**configuration error** — distinct from the net-referenced-handler failure rules in
(a)/(b). The sandwich-rule generalization is delivered as a **public, opt-in**
`Engine.validate(net)` instance method. The Engine is net-agnostic at construction
(`Engine(registry, *, policy, …)` takes no `net`), so `validate(net)` is the earliest
boundary where the net and registry meet. It walks only **declared** refs: each present
transition `handler`, transition `guard`, and consume-arc named predicate `handler`
(inline CEL predicates are compile/eval, not registry-resolved). An absent transition
binding is valid structure and is skipped. The method raises `HandlerNotFound` on the
first declared but unresolvable ref, before any `advance`. `advance` does **not** invoke it: the
caller chooses whether and when to validate, and `advance` retains the (a)/(b)
graceful-degradation rules. A structurally enabled handlerless transition selected by
`advance` produces the same atomic `HandlerNotFound` failed record as direct `fire` and may
spin to `max_steps` unless the failure budget exhausts it.

The asynchronous **Runtime** has a stricter construction boundary. Its execution model
requires a `HandlerSpec` for every transition, so it rejects any net containing a
handlerless transition at Runtime construction. Runtime never supplies a same-name
binding, no-op, or structural firing fallback.

The policy is **engine-level**, defaulting to `first-found`
(`handler-contract.md`; ADR 0005). It returns one transition id or `None`; concurrent
firing is unsupported. `priority` is consumed by the **built-in
opt-in `priority` policy** (ADR 0014): the highest-priority enabled transition fires,
ties falling back to `enabledTransitions` (declaration) order. The engine threads each
enabled transition's declared priority to **every** policy via
`FiringPolicyInput.priorities` (absent declaration = 0); the default `first-found`
policy ignores it. Likewise the engine threads each enabled transition's
consecutive-failure count via `FiringPolicyInput.consecutiveFailures` (keyed by exactly
the `enabledTransitions` entries; no failure history = 0), whether or not a failure
budget is configured, so a custom failure-aware policy (skip, deprioritize, deterministic
attempt-based backoff) needs no engine access; both built-in policies ignore it (ADR
0015).

**Strict advance** (opt-in, `advance(..., strict=True)`; TypeScript `run(net, marking,
{strict: true})`; ADR 0063). It runs the same loop, with two stops that raise instead of
selecting or retrying:

- **Conflict.** Before step 2, when two or more transitions in the (post-exclusion)
  `enabledTransitions` contend, the advance raises `Conflict` (`ConflictError`) naming
  them in declaration order, and fires nothing at that marking. Under the built-in
  `priority` policy only the transitions at the top declared priority contend, so a
  conflict the priorities resolve is no error; under any other policy every enabled
  transition contends.
- **Failed attempt.** After step 3, a `failed` record raises `FailedAttempt`
  (`FailedAttemptError`) carrying that record. The record reached the journal as usual and
  the marking is unchanged by it (atomic rollback); the advance does not retry. When the
  handler's failed output carried an `exception` (`handler-contract.md`), it is the
  error's cause (Python `raise ... from`, TypeScript `Error.cause`), so a synchronous
  caller can catch the handler's own error type.

Either error carries `marking`: the marking the advance stopped at, which the firings
before it moved and the failed attempt left unchanged. A caller that keeps a marking
between runs (a journaled instance) goes on from there without replaying its journal.

It is for a net whose choice coverage is proved, run from a projected marking
(`projection-adapter.md`): the proof says no marking enables two transitions at once, and
a strict advance turns a changed net that does into an error, never a silent pick. The
default (`strict=False`) is the loop above, unchanged.

The illustrative engine surface for the selection loop:

```python
class Engine:
    """The firing engine: enablement -> policy -> fire -> record, looped.

    Parameters
    ----------
    registry : HandlerRegistry
        The per-kind handler registry (handler-contract.md).
    policy : str
        Firing-policy ref name; default DEFAULT_FIRING_POLICY ("first-found").
    journal : Journal | None
        Optional journal hook. If None, records are discarded.
    deposit_violation : {"raise", "record_then_raise", "record_then_drop"}
        Deposit-contract violation behavior (D3). "raise" is the default and
        the only legal value when journal is None.
    max_consecutive_failures : int | None
        The opt-in failure budget (ADR 0015; see (c)). None (default) = no
        budget — a persistently failing transition stays selectable forever.
        An int >= 1 exhausts a transition after that many consecutive failed
        firings within an advance; < 1 raises ValueError at construction.
    """

    def __init__(self, registry: HandlerRegistry, *,
                 policy: str = DEFAULT_FIRING_POLICY,
                 journal: Journal | None = None,
                 deposit_violation: str = "raise",
                 max_consecutive_failures: int | None = None) -> None: ...

    def advance(self, net: Net, marking: Marking, *,
                max_steps: int = ..., strict: bool = False) -> Marking:
        """The selection loop (e): stop on policy None or max_steps.
        Emits records to the journal hook (if attached). Returns the final
        marking only — the journal, if any, is external state owned by the
        attached Journal. The enablement probe and the fire share the same
        ``attempt`` (the step counter), so an attempt-sensitive guard sees a
        consistent attempt (D9)."""
```

## (f) The environment-arrival token-injection seam and native timed transitions

The injection seam is the general **environment-arrival seam**: the one sanctioned,
journaled, replay-deterministic way any external token enters a running net between
firings — file arrivals, environment observations, external events, and clock/deadline
tokens alike (ADR 0013, as amended). The clock/timer case below is the seam's motivating
origin and remains its canonical example; nothing in the mechanism is time-specific.

Timing enters a net as **token data** — a clock/tick token carrying `now`, or a
work/deadline token carrying `enqueued_at` / `deadline_at` in epoch seconds. `Engine`
**never reads a wall clock** (ADR 0001); direct synchronous use advances time only
through the injection seam below — the convenience is `advance`'s optional
``time=`` step (ADR 0060). A `Runtime` can instead schedule
native timers event-driven when each timer declares `maturity`: it recomputes every
candidate after a marking mutation, sleeps until the earliest declared timestamp or
another mutation, samples its clock once, then replace-injects every due clock in lexical
order before admitting work. `maturity` is advisory scheduling metadata; `timer.cel`
remains the sole enablement authority.

Neither Engine nor Runtime holds per-instance timer state: deadlines stay in tokens and
clock advances are still ordinary journaled injection records. The Runtime's clock is
injectable for deterministic scheduler tests; replay remains deterministic from those
recorded injections. Nets without `maturity` remain synchronous-Engine compatible but
Runtime rejects them rather than falling back to periodic polling.

**`Engine.inject_token`** is the one write primitive a consumer uses instead of touching
the marking:

- **inject** (`replace=False`, default) — append `token` to `place`. The deadline-token
  pattern: injecting a `deadline` token into a gate place enables a timed transition.
- **update** (`replace=True`) — replace `place`'s entire contents with `[token]`. The
  singleton clock-advance pattern: bump the one `tick`/`clock` token's `now`. Intended
  for a place that holds a single clock/deadline token.

It returns a new persistent `Marking` (untouched places shared structurally) and an
`InjectionRecord`. The token `type` is **validated against the place's `accepts`** (an
unknown place or an unaccepted type is a programmer error → `ValueError`), and the token
against the net's declared `domains` (ADR 0037), mirroring the deposit contract — the
seam cannot smuggle an ill-typed token past the net's structure.
`inject_token` does **not** drive the loop: the consumer re-runs `enabled_transitions`
after injecting (or advancing) to fire any now-enabled timed transition. Each injection is
emitted through the journal's `record_injection` hook (see (d)) as an **explicit entry**
sharing the same stream — the journal reads as an occurrence sequence of the net
together with its environment (a **trajectory**, the short name in prose) — so replay
is deterministic across injected time.

```python
def inject_token(self, net: Net, marking: Marking, place: str, token: Token, *,
                 attempt: int, replace: bool = False) -> tuple[Marking, InjectionRecord]:
    """Inject (replace=False, append) or update (replace=True, replace the
    place's contents with the single token) an environment-arrival token,
    recording the event through the record_injection hook. Validates token.type against
    the place's accepts (ValueError otherwise). Does not re-drive enablement —
    the consumer calls enabled_transitions after. (ADR 0013.)"""

def inject_tokens(self, net: Net, marking: Marking,
                  placements: Sequence[tuple[str, Token]], *,
                  attempt: int) -> tuple[Marking, list[InjectionRecord]]:
    """Batch inject: append every (place, token) pair in one
    journal-consistent step. Append-only (no replace mode — the singleton
    clock-advance pattern stays on inject_token(replace=True))."""
```

**`Engine.inject_tokens`** is the batch convenience over `inject_token` for the arrival
pattern (several environment tokens land at once). Its contract:

- **All-or-nothing validation.** Every placement is validated (unknown place, unaccepted
  token type → `ValueError`) **before** any journal emission or marking change; an invalid
  entry anywhere in the batch fails the whole batch with **no side effects**.
- **One `InjectionRecord` per token**, emitted in placement order — so a stream-numbering
  journal gives the batch consecutive `sequence` slots, and replay tooling built for
  per-injection records needs no batch-record variant. (A single batch record was
  considered and rejected: it would add a fourth record shape and a fourth journal
  channel for no replay benefit — the per-token stream already reproduces the batch
  deterministically.)
- Every record carries the batch's `attempt` and the unchanged single-injection
  `injectionId` format. Two same-place entries in one batch share an `injectionId`; they
  are disambiguated by the journal's `sequence` (D4 — `injectionId` is deterministic, not
  a unique key, exactly as for two `inject_token` calls with the same place and attempt).

**Sanctioned CEL over timestamp fields (single-token).** An inline CEL predicate is
evaluated against a **single** token's `data` (D6), and integer epoch-seconds
arithmetic/comparison is portable across all three CEL backends (celpy, cel-expr,
cel-rust). So a **single-token** timestamp predicate — `now - enqueued_at > 10`,
`now >= deadline_at`, both fields on one token's `data` — is blessed and backend-portable.
CEL has no implicit int/double promotion on any backend, so arithmetic over a field
that holds an int on one token and a double on another (`0` and `600.0`) is an eval
error; a failed `data cel` names the fields it reads that mix the two, each with its
type, in its error message.
A **cross-token** comparison (a clock token in one place versus a work token in another)
is **not** expressible as a single-token predicate: naming the other token's field is an
eval error (⇒ predicate false, D6). A cross-token **join** over bound tokens is written
as a `correlate` on one of the arcs (ADR 0030), and a pure cross-token gate can be too;
gates that need impure state stay a **guard** over the full input binding (which may be
impure, ADR 0002), exactly as the modeled cooldown/deadline guards are. This boundary —
single-token predicate vs correlate or guard — is the CEL-side counterpart of the seam. The **timer** (ADR 0018) is
the narrow, declarative exception to that boundary: its expression sees a **closed,
net-declared** cross-token environment — the clock token plus exactly the places named
in `timer.bind` — not an open binding, so the temporal cross-token case is expressible
declaratively while general cross-token gates stay guards.

**Native timed transitions and the advance seam (ADR 0018, ADR 0060).** A transition carrying a `timer`
declaration is enabled per the timer clause in (a): the condition must hold for the
candidate binding against the current clock token. `fire` enforces the same rule (a
direct `fire` of an unmatured timed transition yields a `failed` record with
`error.type == "NotEnabled"`, marking unchanged), and `advance` re-evaluates enablement from
the marking every step — so once a clock advance lands in the marking, timed transitions
mature with no consumer-side poll loop. The engine owns that re-evaluation via one
convenience method:

```python
def advance(self, net: Net, marking: Marking, *,
            time: tuple[str, Token] | None = None,
            attempt: int = 0, max_steps: int = 1000) -> Marking:
    """Fire to quiescence; with time=(place, token), open with one
    inject_token(replace=True) — the singleton clock-advance pattern — then
    the same run to quiescence, in one call. One advance can mature several
    deadlines; the ordinary selection loop fires them all, under the
    configured firing policy (ADR 0014) and failure budget (ADR 0015). The
    injection and the firings share one journal sequence stream, so an
    advance-driven timeline replays deterministically. (ADR 0018, ADR 0060.)"""
```

`advance`'s `time=` mode adds no new journal channel and no new primitive: it composes
`inject_token` + the selection loop. A consumer that needs append-mode injection (a
deadline token rather than a clock advance) composes `inject_token` + `advance` directly. An unmatured
timed transition is simply **not enabled**, so a quiescent net with pending deadlines
does not spin — the loop stops, and the next clock advance re-evaluates.

**Symbolic advance (`outputs=`).** On a handlerless net the maturation would
otherwise fail every firing with `HandlerNotFound`. `advance` therefore accepts a
keyword-only `outputs` provider — a pure function of `(net, reservation)` returning the
`TransitionHandlerOutput` to settle with, or `None` to skip the transition (no record,
the transition stays enabled and is excluded for the remainder of this advance, as (e)
step 1 says). The provider is probed on a live reservation — released between probes,
never more than one live at a time — and consulted afresh at settle time, never cached.
A handlerless net without `outputs=` behaves exactly as before. With an `outputs=`
provider `advance` returns an `AdvanceOutcome`: the final marking plus, per settled
firing, `(record, marking_after)` — the record the journal also received, stamped
`maturedBy` identically when `time=` opened the advance (it works with `journal=None`
too), the after-marking the firing alone produced. The deposit contract is unchanged:
the engine still evaluates the net's `data` / `data cel` templates itself, so the
provider only fills what the net leaves to a handler. `velocitron.outputs.symbolic_outputs`
is the default provider — the play matcher's shared carry rule (`velocitron/outputs.py`):
net-filled templates pass through, every other template carries the one consumed token
of its color, read tokens never carry. A transition with a `handler` fact is skipped
unless the net fills every template: its handler writes the rest, so carrying would guess.

**Feeding the seam from external state.** `inject_token` is the write primitive; a
**projection adapter** (`spec/projection-adapter.md`) is what decides *which* tokens to
inject and *when*, by deriving them from external resource state (filesystem, database,
queue, API, clock) before and outside the engine. An incremental projection routes each
arrival through this seam; a full projection builds the initial marking `advance` consumes.

## Key design decisions

The following decisions define the 0.1.0 firing contract.

- **D1 — `inputTokens` shape with arc weight.** Keyed by source place name (per
  `handler-contract.md`). Each consume-mode arc contributes exactly `weight` bound tokens
  (default `weight: 1`). When two consume arcs share a source place, their bound tokens
  are concatenated into that place's list in arc-declaration order. Arc weight is
  structurally expressible; `weight: 1` is the classical one-token case.
- **D2 — Deterministic binding selection (generalized for `weight`).** Candidate
  bindings are enumerated in a stable order: consume arcs in net declaration order; per
  arc, candidate `weight`-token selections are drawn from the source place's token list in
  insertion (index) order — the first `weight` matching tokens form the first candidate,
  and so on. The first binding for which the guard (if any) returns `true` is selected.
  This is what makes the journal replayable without recording the binding choice
  separately.
- **D3 — Produce-template deposit and violation handling.** Produce templates remain a
  declaration-ordered sequence: parallel templates sharing a destination are all
  preserved. Handler tokens validate against any matching destination/type template,
  retain handler order, and suppress literal fallbacks for their matching pair; every
  otherwise-unsupplied literal template emits in declaration order. A token with no
  destination/type template is a violation. Handling is configurable at engine
  instantiation: with **no journal**, the default is to **raise** (a programmer-bug
  signal). With a **journal attached**, the engine may be configured to
  **record-then-raise** (default — emit the violation record to the journal, then raise)
  or **record-then-drop** (emit the record, leave the marking unchanged, and continue the
  advance loop). In all cases the marking is unchanged on a violation (atomic rollback of the
  tentative consume).
- **D4 — The journal is decoupled from the engine via hooks; `sequence` is the journal
  implementation's concern.** The engine emits a `FiringRecord` through a `Journal` hook;
  it does **not** assign `sequence`, pick a storage format, or require a journal's
  presence. `firingId` keeps its `handler-contract.md` meaning (the per-attempt logical
  id, derived from `netId` + transition + `attempt`); it is **not** amended. The default
  `JsonlJournal` assigns a monotonic `sequence` and writes a timestamped `.jsonl` file;
  other implementations may key records differently.
- **D5 — Journal is the deterministic record; replay is re-run-and-compare.** The journal
  records full per-firing I/O. Replay verification = re-run the engine with identical
  handlers and an identical journal, asserting journal equality record-for-record,
  **excluding `timestamps`** (metadata-only, non-deterministic). Handler-free tape replay
  is a separate durability surface rather than part of this replay contract.
- **D6 — Strict boolean conditions; CEL compiles at parse; runtime errors degrade.**
  CEL expressions are **compiled when the net is parsed** — a syntax/compile error fails
  parsing as a `NetValidationError` (the net is malformed). Only exact boolean `true`
  satisfies a CEL predicate, named predicate handler, guard, timer condition, correlated
  inhibit, or correlated consume/read arc; implementations never coerce through host
  truthiness. A runtime evaluation error or non-boolean predicate result is treated as
  the token not matching, not an engine crash — the marking is unaffected and firing
  continues. Timer and guard non-booleans likewise degrade false/not-enabled; correlated
  inhibit and correlated consume/read errors and non-booleans fail closed per ADR 0017
  and ADR 0030. Numeric timer maturity evaluation is not a boolean condition and is
  unchanged. Validating a CEL AST against the known shape of a
  strongly typed token's `data` is not defined because the JSON schema does not type the
  payload shape.
- **D7 — Arc weight is explicit net structure.** `weight` is an optional integer `≥ 1`,
  default `1`, on consume patterns and is rejected on inhibit arcs. The produce template,
  all other net-structure fields, and the entire `handler-contract.md` are unchanged.
  `net-schema.md` defines the field in its `consumePattern` JSON Schema block and
  consume-pattern prose.
- **D8 — Arc-transform CEL is excluded.** CEL on input and output arcs filters tokens; it
  does not transform token data. Transforming arc inscriptions conflict with ADR 0001's
  net-purity rule. A transition handler performs the transformation and returns the
  resulting token as an `outputToken` (for example, a counter decrement is the handler's
  result rather than an arc inscription).
- **D9 — Guard errors degrade to not-enabled; enablement is attempt-aligned with fire.**
  A guard handler may be impure (ADR 0002) and may raise. The engine catches any
  exception or non-boolean result from the guard and treats the transition as **not
  enabled** — symmetric with D6 (a predicate handler runtime error or non-boolean ⇒
  predicate false) and an unresolved guard ref (`resolve_guard` `HandlerNotFound` ⇒ not
  enabled). In `fire` this surfaces via the
  existing not-enabled branch (a `failed` record with `error.type == "NotEnabled"`, marking
  unchanged); no new error type is introduced. Separately, `enabled_transitions` and
  `select_binding` take an optional `attempt` (default `0`); the selection loop (`advance`)
  passes its step counter as `attempt` to **both** the enablement probe and the `fire`, so
  an attempt-sensitive guard (sanctioned by `handler-contract.md` to distinguish a fresh
  fire from a net-modeled retry) sees a single consistent `attempt` across probe and fire.
  This keeps the enablement probe and firing attempt aligned.
- **D10 — An unknown transition name is an error, never a firing.** Every public engine
  entry point that takes a consumer-supplied transition name (`fire`, `select_binding`)
  **raises a typed error** (`UnknownTransitionError` in the reference implementation)
  when the name does not resolve to a transition **declared in the net**. Without the
  check, an undeclared name is indistinguishable from a declared **source transition**
  (no input arcs) inside binding selection — both have no binding arcs, so both yield
  the single empty binding — and a typo'd name would silently fire a handler. A declared
  source transition keeps firing with the empty binding, exactly as before.
  `enabled_transitions` iterates the net's declared transitions only (never a
  consumer-supplied name) and is unaffected. `advance` fires whatever transition id the
  firing-policy handler returns, so a misbehaving custom policy that returns an
  undeclared name now surfaces as this raise out of `advance` (previously a silent
  empty-binding firing); the built-in policies pick from `enabledTransitions` and are
  unaffected. Distinct from the `HandlerNotFound`
  resolve-miss rule in (b) (a *transition failure* — a `failed` record): here there is
  no declared transition to fail, so the call itself is malformed and raises.
- **D11 — Transition behavior binding is optional; execution remains explicit.** Core
  JSON omits `handler` for a handlerless transition and the parsed model uses `None`; a
  present ref remains a nonempty string. `null`, `""`, implicit same-name refs, and
  implicit no-ops are invalid. Handler absence does not affect structural enablement.
  `Engine.validate` resolves only declared refs. `Engine.fire` preserves structural
  precedence: disabled is `NotEnabled`; enabled but handlerless is an atomic
  `HandlerNotFound` failed record with a no-handler message. Runtime rejects handlerless
  nets at construction. Literal produce data is usable only after a bound handler
  completes and never creates structural firing semantics (ADR 0003 amendment).

## Surfaces outside this firing contract

- **`pending` handler status** — unsupported. This spec defines only `"completed"` and
  `"failed"`.
- **Concurrent firing** — unsupported. The firing policy returns `str | None`.
- **Handler-free tape replay** — supplied separately by the Python reference durability
  surface; it is not part of the engine/journal replay contract (D5).
- **Composition** — defined by `spec/composition.md` and its implementation-specific
  composition surfaces, not by firing semantics.
- **Implicit external transitions** — unsupported. External arrivals use the injection
  seam in (f), and side effects remain explicit handler work modeled through places.
- **CEL AST validation against strongly typed token `data` shapes** — not defined because
  the JSON schema does not type the payload shape (D6).
- **Arc-transform CEL** — excluded by net purity; handlers return transformed output
  tokens instead (D8).

## Cross-document pointers

- **Builds on `spec/net-schema.md`** — the net document: places, transitions, arcs, the
  consume pattern (with this feature's narrow additive `weight` addition, D7), and the
  produce template (the routing contract the engine deposits against). All other
  net-structure fields there are unchanged.
- **Builds on `spec/handler-contract.md`** — the runtime handler registry contract: the
  four handler kinds' I/O shapes, the `FiringContext` (closed, four fields, `timestamps`
  metadata-only), the `HandlerError` shape, the `HandlerNotFound` resolve-miss type, and
  the firing-policy handler signature (`{marking, enabledTransitions, priorities,
  consecutiveFailures}` → `str | None`). This spec consumes those shapes; it does not
  redefine them.
- **The firing journal hook contract here is authoritative.** The `FiringRecord` and
  `InjectionRecord` `TypedDict`s (no `sequence`), the `Journal` `Protocol`
  (`record_firing` + `record_deposit_violation` + `record_injection`), and the
  `JsonlJournal` (monotonic 0-based
  `sequence`, timestamped `.jsonl`) are the machine-checkable surface. The reference
  implementation in `implementations/python/src/velocitron/engine.py` and `journal.py` mirrors
  this spec; those modules are the co-evolution pressure-test that proves it coheres.
- `docs/adr/0001` — net purity (the permanent exclusion D8's arc-transform request
  conflicts with; the principle that makes replay hold).
- `docs/adr/0002` — CEL predicates, named guards (the pure/impure split the engine's
  enablement respects: predicates filter per-token and must be pure; guards gate
  transition-wide and may be impure; D9 defines the degrade-to-not-enabled semantics for
  an impure guard that raises).
- `docs/adr/0003` — handler contract: input tokens + context, side effects as places (the
  `inputTokens` shape D1 builds on; the resolve-miss-as-failure rule the engine enforces).
- `docs/adr/0005` — firing policy handler with nondeterministic default (the `first-found`
  policy the selection loop (e) calls; the runtime-level, not net-declared, scoping; the
  `priority` field, reserved there and since implemented by ADR 0014's built-in policy).
- `spec/projection-adapter.md` — the projection-adapter protocol: how external resource
  state becomes the initial marking `advance` consumes, or the per-arrival tokens the (f) seam
  injects.
- `docs/adr/0015` — the opt-in failure budget in `advance` (c) and the `consecutiveFailures`
  policy-input threading (e): a persistently failing transition stops spinning the loop
  or starving later-declared transitions; primitives stay untouched.
- `docs/adr/0018` — native timed transitions: the declarative `timer` enablement
  condition in (a) and the engine-owned `advance` `time=` re-evaluation loop in (f), built on the
  ADR 0013 injection seam with the deadline kept in the token.