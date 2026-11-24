# Composition

**Status:** Public alpha — the composition schema, structural validation rules, and place-fusion merge engine are implemented in Python (`implementations/python/src/velocitron/composition.py`) and TypeScript (`implementations/typescript/src/schema/composition.ts` and `composition-merge.ts`). A merged net uses the ordinary firing semantics; dynamic transport and subscription semantics are not part of this structural composition contract (see [Out of scope](#out-of-scope)).

## Purpose

A **composition** merges one or more nets into a single larger net by aliasing them and adding **wires** between their **ports**. Ports are the composition interface; wires are the cross-net arcs. A **share** fuses places of several nets that are one record, with no direction ([Shares](#shares)), and a composition may use another composition as one constituent ([Compositions as constituents](#compositions-as-constituents)). Per [ADR 0004], composition is *merging net schemas and adding wires*, and the composed system is a single Petri net, verifiable as one.

This document defines the composition semantics and structural validation rules. The canonical machine-readable shape is [`spec/composition.schema.json`](./composition.schema.json). Core net semantics — `Place`, `Transition`, `Arc`, `Token`, `Marking`, and the `Port` facet — live in [`spec/net-schema.md`](./net-schema.md), with their machine-readable shape in [`spec/net.schema.json`](./net.schema.json). Ports are restated briefly below for orientation.

## Canonical JSON Schema

The authoritative machine-readable composition schema is
[`spec/composition.schema.json`](./composition.schema.json), a
[JSON Schema draft 2020-12](https://json-schema.org/draft/2020-12/schema)
document. Its `$id` identifier is
`https://awesome-petri.dev/schemas/composition.json`.

The Python validator loads a byte-identical packaged copy from
`velocitron/schemas/composition.schema.json` through `importlib.resources`; it
never reaches outside the installed wheel at runtime. Focused schema-resource
tests validate the canonical document itself and fail on any
canonical/package byte drift. The complete schema lives only in the standalone
artifact rather than being duplicated in this prose.

`parse_composition(source, *, net_loader=None, origin=None)` resolves the
retained literal `ref`. A filesystem source supplies its parent as `origin`.
For a mapping or raw text source, a relative reference is rejected unless the
caller supplies an explicit `origin: Path` or a `net_loader` closure; absolute
filesystem paths need no origin. The optional
`net_loader(ref: str) -> Mapping | Path | str` returns source material only,
and the parser still validates every result by calling `parse_net`.

The default loader accepts source-relative filesystem `.json` net documents.
The DSL loader accepts `.json` or `.petrinet`: it compiles the latter to a
JSON-shaped dictionary before `parse_composition` calls `parse_net`. Load
cycles, missing files, unsupported extensions, originless relative refs, and
loader failures are deterministic reference-loading diagnostics. A loader
never returns a prevalidated `Net` or bypasses net validation.


The parser loads each `nets[].ref` and validates it against [`spec/net.schema.json`](./net.schema.json) before applying the composition-level validation rules below.

## Ports (recap)

A **port** is a place that declares a `port` facet: `port: {direction: "input" | "output", type: "<token type>"}`. Ports are **boundary places** — the composition interface of a net. Non-port places are **internal**. The semantic definition lives in [`spec/net-schema.md`](./net-schema.md), and the machine-readable shape lives in [`spec/net.schema.json`](./net.schema.json); this document relies on both and does not redefine `Place`.

- `direction: "output"` — the net may emit tokens of `type` through this port.
- `direction: "input"` — the net may receive tokens of `type` through this port.

A port's `type` must be one of the place's `accepts` token types (enforced by the net schema/parser).

## Wires

A **wire** is a unidirectional cross-net arc joining an **output** port to an **input** port. It is a special form of an `Arc` — formed by joining two nets rather than within one ([ADR 0004]; see `Wire` in [`CONTEXT.md`](../../CONTEXT.md)).

- **Direction:** `from` must be an output port; `to` must be an input port. Tokens flow source → sink.
- **Why unidirectional.** Bidirectional coupling is modeled as two separate unidirectional wires, keeping the topology explicit and statically checkable. A wire is a single directed edge, never a pair ([ADR 0004]).
- **Type compatibility.** The output port's `type` and the input port's `type` must be equal ([ADR 0004]).
- **Structural scope.** A wire declares a structural link between two compatible ports. The merge engine realizes that link by place fusion, so the merged net uses ordinary token and firing semantics. Transport or subscription concerns such as backpressure, buffering, overflow, retry, and dynamic discovery are not defined by this contract ([ADR 0004]).

## Shares

A **share** says that places of several nets are one place:
`share outcome.(destination_free) ~ gate.(destination_free) ~ again.(destination_free)`
in `.petrinet`, `{"shares": [{"places": [{"net": "outcome", "place": "destination_free"}, ...]}]}` in JSON ([ADR 0040](../../docs/adr/0040-a-share-fuses-places-without-a-direction.md)). Use it for a record or a lock that several nets read, take or give back, and for a final place that more than one net ends in.

- **No direction.** The places need not be ports, and no direction is checked. A share has at least two places.
- **Same colors.** The places must accept the same colors (as sets), because they become one place.
- **One relation with wires.** The merge puts a share's places into the same equivalence relation as wired ports, so a place that is both wired and shared ends up in one fused place.
- **Proofs.** A shared place keeps the role its members had: when a member is annotated `fusion: true`, `velocitron prove` still lets the environment supply it ([`spec/proofs.md`](./proofs.md#compositions)). A wired place is always closed. A kept place ([ADR 0051](../../docs/adr/0051-a-kept-record-is-there-from-the-start-and-only-the-net-writes-it.md)) is never supplied, and a share that joins one joins only places kept the same way.

## Aliasing

Each referenced net gets an **alias** — the local name under which the net's places and transitions are known inside the composition.

- **Derivation.** `alias` is optional in `nets[]`. If omitted, the alias defaults to the referenced net's `name` field.
- **Qualified naming.** In the composed net, every place and transition is referred to as `<alias>.<name>` (e.g. `prod.out`, `cons.in`). This namespaces each net's symbols so identically-named places or transitions in different nets do not collide.
- **Why dotted.** The dotted form mirrors the JSON wire shape `{net, port}` where `net` is the alias and `port` the local name — `<alias>.<portName>` is the same pair, serialized as one string. It is conventional in JSON/URI contexts and avoids the heavier `::` separator. Aliases are restricted to simple identifiers (schema `pattern`) so the `.` is an unambiguous delimiter.

## Compositions as constituents

A `nets[].ref` may name another composition document ([ADR 0041](../../docs/adr/0041-a-composition-can-use-a-composition.md)). It needs an explicit `alias`.

- **Flattening.** The parser parses the inner composition and flattens it into the outer one. Its nets become `<alias>.<inner alias>` (`lifecycle.gate`), at the position of the `use`, and its wires, shares and refinements carry over under those names. The merge then runs once, over nets only, so every rule of this document applies unchanged. The merged names have one more segment per level: `lifecycle.gate.pending`.
- **Paths.** An endpoint names a place or transition inside the composition by its dotted path, the name it has in that composition's merged net: `{"net": "lifecycle", "port": "gate.sending"}` (`.petrinet` `lifecycle.(gate.sending)`), `{"net": "lifecycle", "transition": "outcome.attempt", "by": "attempt"}` (`refine lifecycle.[outcome.attempt] by attempt`), and `{"net": "lifecycle", "place": "gate.signals"}` in a share. The path names a member place, so a wire checks that member's own direction and color, and it joins the inner fused place.
- **References.** A nested composition's relative references are relative to its own file. The parser rebases them onto the outer composition before it calls the loader (`pair/take.petrinet` for `take.petrinet` inside `pair/pair.petrinet`). A composition that uses itself, directly or through others, is rejected: `composition reference cycle: a.petrinet -> a.petrinet`.
- **Parsed form.** `Composition.nets` keeps the references as written; `parsed_nets`, `wires`, `shares` and `refinements` are flattened, refinements in their flattened form (`net: "lifecycle.outcome"`, `transition: "attempt"`); `sources` maps each flattened alias to its rebased reference.
- **Refinement.** A refined transition may sit inside a used composition. The refining net (`by`) must be a net, not a composition.

## Composition = merge + wires

Merging net schemas under aliases and adding wires yields **one larger net**. The composed net is itself a valid net, verifiable as a single Petri net ([ADR 0004]). It takes the composition's optional `name` (the `.petrinet` header), so reports and diagrams name it as the author did; a composition without a `name` merges to a net named `composition` ([ADR 0043](../../docs/adr/0043-a-merged-net-has-a-petrinet-form.md)).

Conceptually, the merge:

1. Qualifies every place, transition, and arc endpoint in each referenced net by its alias (`<alias>.<name>`), producing a disjoint union of namespaced nets.
2. For each wire, **identifies** (fuses) the named output port and input port into a single shared place in the composed net — the port place through which tokens flow from the source net's output to the sink net's input. A wire is thus the declarative link that, when merged, becomes structure. Each share fuses its places the same way, with no direction.
3. Re-exposes any **unwired** ports of the constituent nets as the composition's own boundary ports (under their `<alias>.<portName>` names). This is what makes a composition itself composable — a chip ([`CONTEXT.md`](../../CONTEXT.md)) whose boundary is its set of unwired ports.

The merge engine — producing the combined net (resolving aliases, fusing port-places, rewriting arc endpoints, re-exposing unwired ports) — is implemented in Python (`merge_nets` / `merge_composition` in `implementations/python/src/velocitron/composition.py`) and TypeScript (`mergeNets` / `mergeComposition` in `implementations/typescript/src/schema/composition-merge.ts`); the composed net is verifiable as a single Petri net regardless of realization ([ADR 0004]).

Because the merge **rewrites place names** (alias qualification plus port fusion), handlers must not key on literal place names — they read inputs by token type and produce against resolved destinations. That contract is defined in ["Composition-safe handlers" in `spec/handler-contract.md`](./handler-contract.md#composition-safe-handlers).

The chosen `[impl]` realization is **place fusion**. For each wire, the output port-place and input port-place fuse into a single shared place — named by the sorted `__`-concatenation of the equivalence class's output (source) port qualified names — through which tokens flow from the source net's output to the sink net's input. A class with no output port among its members (only shares) is named by the sorted `__`-concatenation of all its members. Unwired ports re-expose as the composition's own boundary ports (under their `<alias>.<portName>` names). The merged net is structurally valid and runnable by `Engine`. A **routing-transition** realization — inserting a synthetic transition mediating each wire — was rejected: it introduces a transition not present in the constituents and adds firing overhead per token transfer, for no structural benefit (the composed net is verifiable as a single net either way).

### Fused-place annotations

Every fused place the merge creates carries documentation-only annotations ([ADR 0011](../../docs/adr/0011-documentation-fields.md)) built from its equivalence class:

- **Fusion tag.** The merge tags the fused place `annotations: {"fusion": true}` — a fused place is exactly the hub-and-spoke shape the fusion-place rendering convention exists for ([`CONTEXT.md`](../../CONTEXT.md) "Fusion place"), so tooling (e.g. `velocitron-viz`) styles it without any manual tagging. `velocitron-viz` labels each local copy with the qualified name of the member in its transition's net, the name that transition's CEL reads the place by, and a single node with the first member's name in the order below; walkthrough captions name places the same way, so the `__` name does not show.
- **Member carry-through.** The member port-places' own `description` and `annotations` (an `actor` owner among them) carry through onto the fused place. Conflicting keys resolve deterministically: **output (source) ports merge before input ports** — the fused place is named after its sources, and their annotations take the same precedence — each group in **sorted qualified-name order**, and the earliest member wins each conflicting key. The fused place's `description` is the first member's non-empty `description` in the same order. The order is a property of the equivalence class, not of wire ordering — the same rule that makes the fused place's *name* deterministic.
- **Tag precedence.** The `fusion` key is set last and always wins, overriding any member-supplied `fusion` value.

Annotations remain documentation-only ([ADR 0011](../../docs/adr/0011-documentation-fields.md)): the tag and carried keys never influence enablement, firing, or token flow on the merged net.

Every other place, transition, and arc keeps its own `description` and `annotations` through the merge.

### Actors

Actors ([ADR 0038](../../docs/adr/0038-sequence-diagrams-project-scenarios-onto-actors.md)) survive the merge, so one actor can span several nets. A transition with no `actor` annotation takes its constituent net's default actor (that net's own `annotations.actor`). The merged net's `annotations.actors` lists every constituent's declared actors, the first declaration first; an actor declared a `person` in one net and a `system` in another is an error. A place keeps its own `actor` (its owner) and its `lives` and `reads_as` facts ([ADR 0039](../../docs/adr/0039-sequence-diagrams-draw-lived-places-as-columns.md)), and a fused place carries its members' as above, key by key: an output port's `lives` wins, and an input port's `reads_as` still carries when the output port has none. A `record` declaration merges like `person` and `system`.

### CEL keeps its local place names

A constituent net's CEL can name its own places: `binding.inbox[0].region` in a `correlate`, or `binding.pending[0].id` in a produce template's `cel`. The merge renames those places, so the merge also records, on every merged transition that binds tokens, a **`bindingNames`** map from the constituent's local place name to the merged place name ([ADR 0032](../../docs/adr/0032-composition-keeps-cel-place-names-with-binding-names.md)):

```json
{"name": "shipping.pack", "bindingNames": {"inbox": "orders.accepted", "couriers": "shipping.couriers"}}
```

The engine keys that transition's `binding` by these names ([`spec/firing-semantics.md`](./firing-semantics.md) (a)), so the expression means in the merged net what it meant in the constituent, and the CEL text is never rewritten. When the constituent already declares `bindingNames` (it is itself a merge), the merge keeps the keys and rewrites only the place values, so names survive any depth of composition. The keys are a transition's own scope: two transitions may use the same key for different places.

A wire can fuse two places of one constituent into one place (a net that binds tokens from two of its own output ports, both wired to one input). Both local names then map to the fused place and see the same list of bound tokens. Timers need no names: their `bind` variables already name places, and the merge rewrites those places like arc endpoints ([ADR 0018](../../docs/adr/0018-native-timed-transitions.md)). Handlers and guards still see place-keyed `inputTokens` under the merged names; they follow the composition-safe contract above.

### Domains and proof facts

The merged net keeps every constituent's `domains` ([`spec/net-schema.md`](./net-schema.md), [ADR 0037](../../docs/adr/0037-declared-domains-are-a-runtime-contract-and-proofs-check-refinements.md)). Domains are keyed by color, not by place, so they need no renaming. Two constituents that give one key different value sets are an error: `domain <key> differs between <alias> and <alias>` (TypeScript issue code `composition.domain_conflict`). The same values in another order are one value set.

The merged net also keeps the constituents' `proofs`, under the merged place names. A declared invariant's weights name the merged places (a fused place sums the weights of its members), and its `name` gets the alias: `lifecycle.lock`. A final marking stays final only while no arc of the merged net reads or takes from any of its places, because a place one net ends in may be where the next net starts.

### Final markings

A composition can say where the merged net finishes with its own `final` member: a list of final markings, each a list of `{net, place}` endpoints whose places must all hold a token ([ADR 0049](../../docs/adr/0049-a-final-marking-can-need-several-places.md)). In `.petrinet`, `final lifecycle.(checkout.loaned) + catalog.(shelved), lifecycle.(shelf.recalled) + catalog.(missing)`. An endpoint names a place as a share member does, with a dotted path inside a used composition. The composition's final markings become the merged net's only final markings: they replace every constituent's `final` fact, and they stay final even when an arc of the merged net reads their places. A composition used inside another one does not pass its own `final` up; the outer composition declares its own, or the constituents' facts apply as above. An unknown alias, an unknown place, or a place named twice in one final marking is an error (TypeScript issue codes `composition.final.alias_unknown`, `composition.final.place_unknown`, `composition.final.duplicate_member`).

## Refinement

A net can keep one step abstract: a single transition that stands for work another net describes in detail. A **refinement** replaces that transition with the other net during the merge ([ADR 0034](../../docs/adr/0034-composition-refines-a-transition-by-a-wired-net.md)):

```json
{"refinements": [{"net": "lifecycle", "transition": "attempt", "by": "attempt"}]}
```

`net` is the alias of the net that declares the transition, `transition` its name, and `by` the alias of the **refining net**. In `.petrinet` the fact is `refine lifecycle.[attempt] by attempt`.

The merge removes the refined transition and every arc to or from it. Nothing else changes: the transition's places stay, and the wires that join them to the refining net's ports fuse them as usual. Without the refinement, the abstract transition and the refining net's first transition both consume from the fused place, so a run can skip the detailed steps.

A refinement does not add wires. The author writes them, and the merge checks that the refining net fits:

- Every place the transition consumes from or reads must be wired, directly or through other wires or shares to the same fused place, to an **input** port of the refining net whose `type` is the arc's color.
- Every place the transition produces into must be wired from an **output** port of the refining net whose `type` is the arc's color.
- The refining net may have other ports (an output that goes elsewhere, an input from a third net).
- The refined transition may not have an inhibit arc or a timer. These test for an absence or a time, and no port direction carries such a test into the refining net.

The handler, guard, priority, and arc inscriptions (predicates, correlates, `data`) of the refined transition go away with it; the refining net's own transitions decide when and how tokens move. Every remaining place, transition, and arc keeps its `description`, `annotations`, and `bindingNames` as above. A standalone net is unchanged: its abstract transition stays in its own document and diagram.

## Overview diagram

`velocitron-viz COMPOSITION --overview` (Python only) draws a composition for a reader who wants to know what each part is for, not how it works. It reads only facts the documents already state:

- Each constituent net is one box, labeled by its `description`, else its `name`. No transition is drawn.
- The places of a wired class are one node, with an arrow from each net that produces into it and an arrow to each net that consumes from it; a net that only reads it gets a dashed arrow labeled `reads`. A net that both fills and empties the place draws only one arrow: from the net when no other net fills it, else to the net.
- The **case colors** are the colors of the wired places. A place that holds a case color, that a net produces into and no net consumes from, is an **end**, drawn as a double circle.
- Another place of a share is a **shared record**, drawn as a cylinder with a dashed line to each net that uses it. The line is labeled by what the net does to it: `takes` (consumes), `gives back` (produces into a record some net takes), `writes` (produces into a record no net takes), `reads`. A record that no net takes or reads is a signal, and its lines have no label.
- A place that lives in a column of kind `record` (`(switch) lives in "Branch home"` with `record "Branch home"`, [ADR 0039](../../docs/adr/0039-sequence-diagrams-draw-lived-places-as-columns.md)) is a record the outside world keeps. It is drawn with a dashed border, even when only one net uses it.
- Any other place used by only one net is left out.
- An end is labeled by the first member's name with `_` read as a space (`gave up`). Any other node's label is the `description` of a member place, else that name. A place's description often serves another view (a sequence column's file, for example) and is too long for a small end marker.
- A nested composition is a dashed cluster titled by its alias; a place used only inside it is drawn inside it. A refining net sits in a dashed cluster titled `refines:` and the refined transition's `description` (else its name), joined by a dotted line to the net it refines. The refined transition's arcs are not counted.

A composition document has no name or description of its own, so the CLI titles the diagram by the file's stem (`hold-lifecycle`). A source without an extension, such as `/dev/stdin`, gives no title.

## Validation rules

These are the structural checks the JSON Schema cannot express; the Python parser implements them (see `velocitron.parser.parse_composition`). Each raises a `NetValidationError`.

1. **No dangling ports.** Every wire endpoint `(net, port)` must resolve to a declared port on the referenced net. Concretely: `net` must equal some `nets[].alias` (or a derived default), the referenced net must be loadable and valid, and `port` must be the name of a place on that net that declares a `port` facet.

2. **Direction compatibility.** The wire's `from` port must declare `direction: "output"`; the `to` port must declare `direction: "input"`. A wire from an input port or to an output port is rejected.

3. **Type compatibility.** The `from` (output) port's `type` and the `to` (input) port's `type` must be **equal** ([ADR 0004]). Tokens flowing across a wire keep their color.

4. **Alias uniqueness.** No two `nets[]` entries may resolve to the same alias — whether supplied explicitly or derived from `name`. Duplicate aliases are rejected.

5. **Net validity.** Each `nets[].ref` must parse and validate against [`spec/net.schema.json`](./net.schema.json). A composition is only as valid as its constituents.

6. **Shares fit.** Each share names known aliases and existing places, no place twice, and every place accepts the same colors. Each failure message starts with `share a.(p) ~ b.(q):` (the places as written).

7. **Nested references.** A referenced composition has an explicit alias and no reference cycle, and every dotted path names a place or transition of one of its nets (`net 'lifecycle' has no port named 'gate.nothing'`). A refining net is a net, not a composition.

8. **Refinements fit.** Each refinement's `net` and `by` must be known, different aliases; `transition` must be a transition of `net`; no transition is refined twice; and the refining net must fit as [Refinement](#refinement) states. Each failure message starts with `refine <net>.[<transition>] by <by>:` and names the place, color, or arc that does not fit.

### Out of scope

The **runtime merge engine** produces the combined net by resolving aliases, fusing port-places, rewriting arc endpoints, and re-exposing unwired ports. Both implementations provide it: Python as `merge_nets` and `merge_composition`, TypeScript as `mergeNets` and `mergeComposition`. The resulting net uses the ordinary firing semantics. This composition contract does not define a separate dynamic transport or subscription layer, including backpressure, buffering, overflow, retry, or dynamic discovery ([ADR 0004]).

## Worked example

Adapted from `TestComposition.test_parse_composition` in [`implementations/python/tests/test_parser.py`](../../implementations/python/tests/test_parser.py). A **producer** net emits `task` tokens at its `out` output port; a **consumer** net absorbs `task` tokens at its `in` input port. One wire joins them.

### `producer.json`

```json
{
  "name": "producer",
  "places": [
    {"name": "work", "accepts": ["task"]},
    {"name": "out", "accepts": ["task"], "port": {"direction": "output", "type": "task"}}
  ],
  "transitions": [{"name": "produce", "handler": "produce_handler"}],
  "arcs": [
    {"from": {"place": "work"}, "to": {"transition": "produce"}, "consume": {"type": "task"}},
    {"from": {"transition": "produce"}, "to": {"place": "out"}, "produce": {"type": "task", "destination": "out"}}
  ]
}
```

### `consumer.json`

```json
{
  "name": "consumer",
  "places": [
    {"name": "in", "accepts": ["task"], "port": {"direction": "input", "type": "task"}},
    {"name": "done", "accepts": ["task"]}
  ],
  "transitions": [{"name": "consume", "handler": "consume_handler"}],
  "arcs": [
    {"from": {"place": "in"}, "to": {"transition": "consume"}, "consume": {"type": "task"}},
    {"from": {"transition": "consume"}, "to": {"place": "done"}, "produce": {"type": "task", "destination": "done"}}
  ]
}
```

### `composition.json`

```json
{
  "nets": [
    {"ref": "producer.json", "alias": "prod"},
    {"ref": "consumer.json", "alias": "cons"}
  ],
  "wires": [
    {"from": {"net": "prod", "port": "out"}, "to": {"net": "cons", "port": "in"}}
  ]
}
```

### The merge

Validation passes: `prod.out` is an output port of type `task`; `cons.in` is an input port of type `task`; aliases `prod` and `cons` are unique. The merge (conceptually) produces one net:

- Places: `prod.work`, `cons.done`, and the **fused** port place `prod.out` ≡ `cons.in` (a single shared place holding `task` tokens).
- Transitions: `prod.produce`, `cons.consume`.
- Arcs: `prod.work → prod.produce` (consume `task`), `prod.produce → <fused port>` (produce `task`), `<fused port> → cons.consume` (consume `task`), `cons.consume → cons.done` (produce `task`).

A `task` token deposited by `prod.produce` lands in the fused port place, where `cons.consume` can take it — one connected net, verifiable as a single Petri net ([ADR 0004]).

## References

- [`spec/net.schema.json`](./net.schema.json) and [`spec/net-schema.md`](./net-schema.md) — canonical machine-readable shape and semantic definition of `Net`, `Place`, `Transition`, `Arc`, `Token`, `Marking`, and the `Port` facet. This document restates `Port` only for orientation.
- [ADR 0004 — Structural ports and unidirectional wires](../../docs/adr/0004-structural-ports-unidirectional-wires.md) — the composition decision: structural ports only, unidirectional wires, dynamic transport/subscription semantics outside the composition contract, and the composed system verifiable as one net.
- [ADR 0032 — Composition keeps CEL place names with binding names](../../docs/adr/0032-composition-keeps-cel-place-names-with-binding-names.md) — why the merge records `bindingNames` instead of rewriting CEL text.
- [ADR 0034 — A composition refines a transition by a wired net](../../docs/adr/0034-composition-refines-a-transition-by-a-wired-net.md) — why refinement removes the transition and checks explicit wires instead of adding them.
- [ADR 0040 — A share fuses places without a direction](../../docs/adr/0040-a-share-fuses-places-without-a-direction.md) — why shared records get their own fact and keep their proof role.
- [ADR 0041 — A composition can use a composition](../../docs/adr/0041-a-composition-can-use-a-composition.md) — why a used composition is flattened and named by dotted paths.
- [ADR 0042 — `velocitron equiv` compares merged nets up to renaming](../../docs/adr/0042-equiv-compares-merged-nets-up-to-renaming.md) — how to check that a composition is the same net as another.

[ADR 0004]: ../docs/adr/0004-structural-ports-unidirectional-wires.md
