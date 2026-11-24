# Composition keeps CEL place names with binding names

**Status:** Accepted; Decision 3 replaced by ADR 0043 (2026-10-17). (Resolves the consequence ADR 0031 recorded: `correlate`
and `data cel` expressions that name a place did not survive a merge.)

A `correlate` and a produce template's `cel` see `binding`, a map from source
place to the bound tokens' data (ADR 0017, ADR 0023, ADR 0030). Authors write
these expressions against their own net: `binding.inbox[0].region`. A
composition merge renames every place (`inbox` becomes `shipping.inbox`), and
a wired port becomes a fused place named after its source port
(`orders.accepted`). After the merge, `binding.inbox` is a missing key. The
expression fails to evaluate, and because these surfaces fail closed, the
transition is silently never enabled (a correlate) or the firing fails (a
computed fallback). A net that worked alone stopped working in a composition.

Timers did not have this problem. ADR 0018 rejected a place-keyed timer
environment for exactly this reason and chose `bind`: CEL names a variable,
the variable names a place, and the merge rewrites the place.

## Decision 1: the merge records binding names, the CEL text stays

A transition may declare `bindingNames`, a map from key to place name. When it
does, the `binding` that its CEL sees is keyed by those keys, each key holding
the data of the tokens bound from its place. When it does not, `binding` is
keyed by place name, as before.

`merge_nets` (Python) and `mergeNets` (TypeScript) write `bindingNames` on
every merged transition that has consume- or read-mode arcs. The keys are the
constituent's local place names; the values are the merged names, after alias
qualification and fusion:

```json
{"name": "shipping.pack",
 "bindingNames": {"inbox": "orders.accepted", "couriers": "shipping.couriers"}}
```

When a constituent already declares `bindingNames` (it is itself a merged
net), the merge keeps the keys and rewrites only the values. A name therefore
survives any depth of composition, and the rule is the same one the merge
applies to `timer.bind`.

The map goes from local name to merged place, not the reverse. A wire can fuse
two places of one constituent into one place (two output ports of one net
wired to the same input). Merged-to-local would then need two keys for one
value; local-to-merged stays a function, and both local names read the fused
place's tokens.

The parser requires the values to be exactly the transition's consume- and
read-mode source places. So `binding` never loses a place, and a hand-written
map cannot point at a place the transition does not bind.

**Considered options:**

- *Rewrite the CEL source during the merge* (`binding.inbox` to
  `binding["orders.accepted"]`). Rejected: it needs a CEL parser and a printer
  that round-trip every expression across the three Python backends and the
  TypeScript one. We have parsers but no printer. A text substitution would
  also rewrite string literals and comprehension variables.
- *Expose both the local and the merged names in `binding`.* Rejected: a
  local name can collide with another place's merged name, and the map would
  depend on which names happen to collide.
- *Keep the map outside the net document* (a side table returned by the merge
  and passed to the engine). Rejected: the merged net is one net, verifiable
  as one (ADR 0004). Its CEL must mean the same thing when the net is written
  to JSON and read back, or run by the other implementation.
- *Store the map in `annotations`.* Rejected: annotations are documentation
  only and never change firing (ADR 0011).

## Decision 2: only CEL sees the names

Guard and transition handlers keep receiving `inputTokens` keyed by the merged
place names, and the firing record keeps those names. Handlers are host code
and follow the composition-safe contract in `spec/handler-contract.md`: read
by token type, produce against resolved destinations. Changing their keys
would break handlers that already follow it, and journals would then hold
names that are not places of the net that ran.

## Decision 3: no `.petrinet` form

*Replaced by [ADR 0043](0043-a-merged-net-has-a-petrinet-form.md): a
`[Transition] bind Key (Place)` fact now writes each key, so a merged net
round-trips through `.petrinet`.*

`bindingNames` is merge output, not an authoring surface. The `.petrinet`
language gets no fact for it, and JSON-to-DSL conversion rejects a net that
declares it, with a message that points to the composition document. A
composition written as DSL is merged again on load, so nothing is lost.

## Consequences

- A net's `correlate` and `data cel` work unchanged inside a composition, in
  both implementations. A Python/TypeScript parity test covers a correlated
  read arc, a correlated inhibit, a computed fallback, and a timer bound to a
  fused place.
- Merged net documents grow by one map per binding transition. The schema
  change is additive: every net that was valid stays valid and behaves the
  same.
- `velocitron explain` and play diagnostics show the local names in
  failing CEL values (`binding.inbox[0].region = "eu"`), because they build
  `binding` the same way.
- The merge now also carries arc `description` and `annotations` in Python,
  as the TypeScript merge already did.
