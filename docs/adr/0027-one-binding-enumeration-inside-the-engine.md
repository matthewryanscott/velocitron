# One binding enumeration inside the engine (Python + TypeScript)

**Status:** Accepted. (Consolidates the binding walks that ADR 0012
(`_select_binding`'s cartesian product), ADR 0017 (correlated-inhibit
anti-join), and ADR 0018 (native timers) each extended in place; keeps their
public semantics frozen.)

The binding walk was forked: `Engine._select_binding` and
`Engine.timer_maturities` each enumerated candidate bindings privately, and
`Runtime._footprint` re-derived arc classification from `net.arcs` again. Three
enumerations of the same structure meant three places to keep in lockstep
across the two implementations — and the forked walks could drift silently.

This record settles: ONE lazy enumeration primitive per implementation yields
each candidate binding plus *why* it was rejected; both binding consumers
consume it; the Runtime consumes the topology index the primitive implies; the
public surfaces (`selectBinding`, `timerMaturities`) keep exactly their
spec-blessed shape.

## Decision 1: one lazy enumeration primitive

`Engine._binding_candidates` (Python) / `Engine.#candidateBindings`
(TypeScript) yield one candidate binding at a time — `tokens` (the full
consume- and read-mode bound multiset keyed by source place), `consumed` (the
consume-only subset `fire` removes), and `rejected`: **why** the candidate was
turned away, from the one rejection vocabulary `BindingRejection` /
`BindingRejection`:

- **`per-arc-miss`** — walk-level: a pre-binding gate failed the whole
  transition (uncorrelated inhibit zero-test matched; a binding arc had fewer
  matching tokens than its `weight`; or a timer's clock place was empty). The
  single last yield of a walk that produced no binding.
- **`product-miss`** — walk-level: the cartesian product was walked to its end
  without one surviving binding.
- **`sub-multiset`** — candidate-level: the bound tokens would bind one token
  to two arcs (D1's sub-multiset rule, also the read/consume disjointness
  rule).
- **`correlated-inhibit`** — candidate-level: an anti-join blocked the binding
  (eval error or non-boolean fails closed, ADR 0017).
- **`timer-hold`** — candidate-level: `timer.cel` did not evaluate to exact
  `true`, so the binding is unmatured (ADR 0018).

**Considered options:**

- Keep the private forks and add tests pinning each walk separately. Rejected:
  the fork is the defect — every new pure gate must then be threaded through
  two walks per implementation and mirrored across both implementations.
- Make the primitive eagerly materialize all candidates and let consumers
  post-filter. Rejected: consumers stop early by design (below); eager
  materialization would pay full-product cost on every enablement probe.
- Include the guard in the enumeration. Rejected: the guard is possibly impure
  (ADR 0002); it belongs to the first-success consumer, which may abandon the
  walk mid-product — it must never run inside the walk it stops.

## Decision 2: the consumption contract

- **First-success consumer** — `select_binding` / `fire` (via
  `_select_binding` / `#selectBinding`): resolve the guard once (an unresolved
  guard ref ⇒ not enabled before any enumeration), then consume the walk until
  the first viable binding the guard accepts; guard-rejected bindings and
  annotated rejections advance the walk in the same enumeration order, so
  first-surviving selection and replay determinism (D2/D5) are unchanged.
- **First-failure consumer** — `timer_maturities` / `timerMaturities`: per
  timed transition, consume the walk until the FIRST `timer-hold` rejection —
  the first structurally valid binding whose `timer.cel` fails — evaluate that
  binding's `timer.maturity` scheduling expression, and stop there (lazy). One
  wake candidate per timed transition is all the Runtime's `min`-wake
  consumption can act on; a skipped behind-the-clock maturity stays silent.
  Note: a walk that previously appended a `TimerMaturity` for *every*
  cel-failing binding now records only the first — the enumeration order puts
  the earliest candidate first, the Runtime recomputes on every marking
  mutation, and any later-bound token's wake is re-found then.
- **Footprint consumer** — `Runtime._footprint` classifies consumed / read /
  written places from `Engine.topology_index` (Python) — the immutable
  declaration-ordered topology tables the enumeration already implies —
  instead of re-deriving arc classification from `net.arcs`. (The TypeScript
  implementation has no async Runtime seam; its topology is already private to
  the engine.)

Both implementations mirror the primitive and its contract one-to-one
(`BindingStep` ↔ `_CandidateBinding`, the rejection vocabulary, the
evaluation-order comments); the conformance corpus and parity tests remain the
cross-implementation oracle.

**Considered options:**

- Let `timer_maturities` keep appending a wake candidate per cel-failing
  binding. Rejected (as the consolidation): the full-product scan was the
  eager part of the fork; a single first-failure walk per transition is the
  consumption contract the shared walk is FOR — and the two implementations'
  primitive semantics must be identical, so the lazy contract is pinned on
  both sides.
- Expose the enumeration publicly (a third public surface alongside
  `selectBinding`/`timerMaturities`). Rejected: public interface is frozen;
  the rejection vocabulary is an internal audit seam, exercised only through
  the two consumers.

## Consequences

- Adding a pure, structural enablement gate is a one-place change per
  implementation: extend the walk's gate order, and every consumer inherits
  it.
- Enumeration order is the walk's — declaration-order arcs, lexicographic
  per-arc combinations — pinned by public-surface tests on both sides
  (order stability across calls and attempts; correlated-inhibit skips;
  first-failure timer consumption; footprint equality with the old per-arc
  derivation on every conformance-corpus net).
- `selectBinding`, `timerMaturities`, `fire`, `enabled_transitions`, and the
  injection/reservation surfaces are unchanged; guards, predicates, timers'
  `cel`, and correlated inhibits keep their decided postures (D6/D9, ADR
  0017, ADR 0018).