# A merged net has a `.petrinet` form

**Status:** Accepted (2026-10-17).

A composition merges into one net. That net is ordinary core JSON, and the
tools that read a net also read it. But `velocitron to-petrinet` rejected
it: the merge writes `bindingNames` on every transition that binds tokens
([ADR 0032](0032-composition-keeps-cel-place-names-with-binding-names.md)),
and ADR 0032 Decision 3 gave `bindingNames` no `.petrinet` form. So a merged
net could not be read as DSL, diffed as DSL, or edited and compiled back.

## Decision 1: a `bind` fact writes one binding name

```text
[shipping.pack] bind inbox ("orders.accepted")
```

One fact per key. It lowers to the contribution kind
`transition.binding-name` `{name, place}` and resolves to
`bindingNames[name] = place`. `to-petrinet` writes one fact per key, in key
order. The resolver checks what the net validator checks: once a transition
has a bind fact, its facts must name exactly the places it consumes or
reads. Repeating a fact is idempotent; two places for one key is a
conflict.

This replaces ADR 0032 Decision 3. `bindingNames` stays merge output: an
author who writes a net by hand still names places in CEL directly, and the
`bind` fact is there so that merge output can round-trip.

**Considered options:**

- *Rewrite the CEL text to the merged place names and drop
  `bindingNames`.* Rejected for the reasons in ADR 0032: rewriting CEL is
  fragile, and the text would no longer match the constituent net.
- *An annotation that holds the map.* Rejected: annotations are
  documentation and the engine ignores them, so the compiled net would bind
  tokens under other keys.

`timer bind` stays separate: it names a variable of the timer CEL, not a key
of `binding`.

## Decision 2: the merged net takes the composition's name

Every merged net was named `composition`, so a prove report for
`library_holds.petrinet` said "net composition", and `to-petrinet` wrote
`composition composition` as the header. The `.petrinet` header did not
reach composition JSON at all.

Composition JSON gets an optional `name`. The header lowers to it, the merge
names the net after it, and `to-petrinet` writes it back as the header. A
composition JSON document without `name` still merges to a net named
`composition`, so older documents stay valid.

## Consequences

- `velocitron to-petrinet merged.json` writes DSL that compiles back to the
  same net, with the compiler's DSL payload beside it. A Python/TypeScript
  test merges a composition, writes it as DSL, and compiles it in both
  ports.
- The `bind` keyword now starts a transition fact as well as the timer fact.
- A composition compiled from DSL now has a `name` in its JSON, and reports
  and diagrams of the merged net use it.
