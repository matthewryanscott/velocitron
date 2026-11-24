# The presentation vocabulary is compiler-owned and v1 extends additively

**Status:** Accepted. (ADR 0024's "relative entry wire shape is provisional"
paragraph points here; this record fulfills it.)

Card 1 (ADR 0024) moved view application onto a render model and left the
relative-position wire shape provisional: `viz_view.py` already resolves
relative entries at render time, but canonical documents rejected them at
`_reserved_payload`. The remaining slice was to make the presentation
vocabulary real end to end — language syntax, Contribution IR, resolver,
canonical payload, emission, both implementations, and conformance fixtures —
and to settle the four questions the provisional shape was waiting on.

## Decision 1: the compiler owns presentation facts in the reserved payload

`annotations["petrinet.dsl/v1"].views` remains the single vocabulary for view
facts (positions, routes). Presentation data is not blessed into
element-level ordinary annotations: annotations stay semantic, shape
validation stays centralized, and `apply_view` keeps reading exactly one
channel. Net-scope payload still drops from composition merge, so merged and
composed renders stay unviewed by design.

**Considered options:**

- Bless a convention where presentation facts ride element-level ordinary
  annotations (e.g. `(out) annotation petrinet.view {...}`). Rejected:
  element annotations are freeform and merge-propagated, so the same
  presentation fact would have two homes depending on whether the author
  wanted merge survival; shape guarding splits across two channels; the
  reserved-payload validator would stop being the single shape authority for
  exactly the facts it was built (ADR 0020) to own.
- Keep the payload channel (chosen): one validator, one consumer, inert by
  construction.

## Decision 2: relative entries lower verbatim; the shape is decided now

A relative position is a view-position fact whose payload entry is
`{"from": "<kind>:<name>", "delta": {"x", "y"}}` (kind `place`/`transition`
— the string form is the payload's; the IR keeps a plain `{type, name}`
target for `from` and the tagged `coordinatePoint` for `delta`, matching the
"IR is typed, payload is wire" split the arcHandles fingerprint already
uses). DSL syntax: `view <name> position <target> relative <base> + {"x",
"y"}`. `relative` becomes a lexer keyword and, alongside `at`, stays usable
as a bare name.

## Decision 3: the resolver validates references, never resolves geometry

Relative chains resolve at render time (ADR 0024 Decision 2). The resolver
checks the entry's shape and that both the subject and the base name declared
places/transitions, then stores the fact verbatim; emission re-renders the
relative fact as authored. Base placement inside the view, dependency-order
resolution, and cycle rejection remain `apply_view` errors.

## Decision 4: arc decoration stays handle-keyed

Routes address arcs by declared `@handle` (index + fingerprint guarding
staleness). Ordinal- or identity-keyed arc decoration would reintroduce
exactly the fragile source-position coupling card 1 deleted; arcs stay
unroutable until the author names them.

## Decision 5: v1 extends in place; the key stays `petrinet.dsl/v1`

This is a public 0.1.0 alpha with no compatibility scaffolding and no
external consumers of the exact shapes; a `v2` key would double the
validate/emit/mirror surface for no user. This record therefore also fixes
the standing policy for inert presentation metadata: widening an existing
v1 member's accepted shape additively is fine, provided both implementations,
the schemas, and the conformance fixtures move in lockstep. Additive
extension does not license changing existing member shapes incompatibly,
removing members, or making the metadata behaviorally load-bearing.

## Consequences

- `to-json` → `to-petrinet` round trips preserve relative facts; emission
  renders absolute positions first (sorted by `x`, `y`, subject), then
  relative positions (sorted by `from`, subject), then routes — deterministic
  and independent of authored statement order.
- Cross-kind offsets are legal: any positionable target can base on any other
  target's rendered position, because views apply in one rendered coordinate
  space.
- The 11-speaks-window conformance corpus gains a `17-relative-views` case
  pinning the language, the IR oneOf, and the diagnostics byte-for-byte on
  both implementations.
- The `dot -Tplain` (layout-relative) positioning idea from ADR 0024 remains
  out of scope until the render-inspect loop owns the `dot` boundary; the
  skill-side loop (card 3) composes with any DOT renderer, so that boundary
  can arrive later without breaking this vocabulary.