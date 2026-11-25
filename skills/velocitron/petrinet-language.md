# `.petrinet` language contract

## Status and boundary

This specification defines version 1 of Velocitron's `.petrinet` authoring
language. It is a flat, progressive syntax which lowers ordered Contributions
into canonical JSON-shaped `net` or `composition` documents. The existing
`parse_net` and `parse_composition` functions remain the only semantic
validators. This contract does not define a second net model, JSON Schema
validator, CEL evaluator, composition merger, or firing engine.

The sole grammar is `packages/grammar/VelocitronPetriNet.g4`. It is
action-free and uses ANTLR 4.13.2. Python generation uses the matching
`antlr4-python3-runtime==4.13.2`. The TypeScript target uses the `antlr4`
4.13.2 runtime. Generated parsers and a syntax-only parse of net and
composition documents ship in `packages/grammar/python`
(`velocitron-grammar`) and `packages/grammar/typescript`
(`@velocitron/grammar`). Lowering a parse into Contribution IR ships in
`packages/dsl/python` (`velocitron-dsl`) and `packages/dsl/typescript`
(`@velocitron/dsl`). The language implementations import that lowerer.
Compiling CEL and resolving a net or composition ship in
`packages/petrinet` (`velocitron-petrinet`, `@velocitron/petrinet`).
`parse_net` and `parse_composition` in that package remain the semantic
validators.

## Source text and diagnostics

Source is strict UTF-8 without a BOM, bare CR, or isolated surrogate scalar.
LF and CRLF are accepted without normalization. Source spans identify a
portable relative source ID, half-open UTF-8 byte offsets, and 1-based
Unicode-scalar line and column positions. A diagnostic is structured as a
stable code, primary span, message, and ordered related spans. Parsing never
lowers a recovered partial tree. EOF spans are zero-width at source length.

DSL JSON values are RFC 8259 values only: double-quoted strings, lowercase
`true`, `false`, and `null`, valid JSON number syntax, arrays, and objects.
Duplicate keys, non-finite numbers, invalid escapes, raw string newlines, and
isolated escaped surrogates are rejected. Numbers must be finite IEEE-754
binary64 values; integer literals are additionally limited to
`[-9007199254740991, 9007199254740991]`.

Canonical JSON uses the project pretty profile: UTF-8; LF line endings; a
final LF; two-space indentation; object keys sorted lexicographically by
UTF-16 code units as specified by RFC 8785; semantic array order; unescaped
non-ASCII scalars; and RFC 8785 primitive string and number rendering.
Negative zero renders as `0`; exponents use
lowercase `e` without `+`. This is pretty JSON, not RFC 8785's compact
whole-document serialization.

## Names, headers, and progressive facts

`IDENT` is `[A-Za-z_][A-Za-z0-9_]*`. Every semantic name is an `IDENT`, a
bare keyword, or a JSON string. Keywords are contextual: a bare keyword is an
ordinary name wherever the grammar expects one, so `(order)`, `-view->`, and
`timer bind note` all work. Only `true`, `false`, and `null` require quoting,
and after `marking` a bare `initial` always starts the initial marking.
Canonical output quotes some keywords; quoting a name never changes it.
Parenthesized places,
bracketed transitions, `$` templates, and `@` handles use that name form;
canonical output has no whitespace after `$` or `@`. A quoted name is literal,
including dots and hyphens. Opaque handler, guard, predicate-handler, and
firing-policy references are always JSON strings and never structurally
qualified.

A composition document begins with its required header:

```text
composition Name
```

A net document may begin with `net Name [JsonStringDescription]`. If that
header is omitted, the source is a net whose effective name is `unnamed`;
headerless source and source beginning `net unnamed` have the same document
identity for aggregation. Canonical DSL always emits the explicit net header.
The net description lowers to the documentation-only top-level field.

A composition header names the DSL contribution namespace, which source
identity and cross-source merging need, and it lowers to the composition
JSON `name` ([ADR 0043](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0043-a-merged-net-has-a-petrinet-form.md)).
The merged net takes that name. JSON-to-DSL writes the header from `name`,
or `composition` for a composition JSON document without one, regardless of
its filesystem path.

Facts may precede their final declaration. Equal repeated facts are
idempotent. Unequal repeated facts conflict with both definition spans. Final
resolution rejects unresolved templates and all other required semantic
fields. A structure-only fragment may therefore parse into Contributions
without compiling.

### Same-namespace source aggregation

`compile_petrinet_sources(sources: Sequence[SourceInput])` is the sole
multi-source API. Each source has an explicit logical relative `sourceId` and
an effective document kind and decoded name. A composition source has exactly
one header; a net source has zero or one, with an omitted header supplying the
effective name `unnamed`. The API accepts sources only when their effective
document kind and name are identical, so headerless net sources aggregate with
sources explicitly headed `net unnamed`. Contributions append in supplied
source order and then source statement/part order. Same-file and separate-file
contributions therefore use the same idempotence, conflict, final-resolution,
and first-appearance rules. Duplicate source IDs, mismatched effective names,
mixed kinds, and reference cycles are deterministic `PN2xx` errors. The
single-path CLI uses a one-source sequence; composition `use` loads a
constituent document, not an implicit same-namespace contribution.

## Topology, order, and arc facts

Topology is chain-first and expands left to right. `-Color->` is a default
consume/produce segment, `-Color->?` is a read input, and `-Color->0` is an
inhibit input; the latter two are allowed only place-to-transition and are
longest-match lexer tokens. A bare `->` is the **Generic token** default
consume/produce syntax: its core color is exactly the ordinary string `token`
and is never inferred from adjacent places or other context. `token` is the
conventional color for classical/uncolored nets, not a wildcard or an untyped
value. Core JSON and DSL resolution retain it normally; presentation layers may
omit only its visible type label.

Referenced places/transitions and standalone `(Place)` / `[Transition]`
declarations participate in first-appearance ordering. Each topology color,
including `token` from a bare arrow, is added to each adjacent place's accepted
ordered color list. Chain expansion normally determines arc order; marking
statements determine token order.

A chain handle names one consecutive expansion run. The only order facts are
`[Transition] order PositiveInt` and `@Handle order PositiveInt`. If used, an
order class is complete and uniquely ranks `1..N`; arc-run ordering preserves
left-to-right order within the run. Canonical emission normally emits one arc
per line in core arc-array order and emits order facts only when its own layout
would otherwise change core order.

The exact statement productions are:

```text
PlaceDecl      := "(" Name ")"
TransitionDecl := "[" Name "]"
Chain          := [ "@" Name ":" ] Endpoint ( ArcSegment Endpoint )+
Endpoint       := "(" Name ")" | "[" Name "]"
ArcSegment     := "-" ( Name | JsonString ) "->"
                | "-" ( Name | JsonString ) "->?"
                | "-" ( Name | JsonString ) "->0"
                | "->"
ArcFact        := "@" Name ( "predicate" ( "cel" | "handler" ) JsonString
                           | "weight" PositiveInt
                           | "data" "cel" JsonString
                           | "data" JsonValue
                           | "correlate" "cel" JsonString
                           | "order" PositiveInt )
PlacePort      := "(" Name ")" "port" ( "input" | "output" ) Name
PlaceAccepts   := "(" Name ")" "accepts" "[" Color ( "," Color )* "]"
PlaceCapacity  := "(" Name ")" "capacityPerColorKey" JsonObject
TransitionFact := "[" Name "]" ( "handler" JsonString
                               | "guard" JsonString
                               | "order" PositiveInt
                               | "priority" NonnegativeInt )
```

`@arc_<N>` is reserved for formatter-generated identity and may appear in
source only when `N` equals the zero-based index of its uniquely targeted
core arc. An authored handle that would collide with any generated handle is
rejected. `PositiveInt` is decimal `1..`; `NonnegativeInt` is decimal `0..`.
Ports, descriptions, and annotations cannot declare an unknown semantic
object; duplicate differing facts conflict.

Arc elaborations are progressive and target a handle: `predicate cel`,
`predicate handler`, `weight`, `data`, and `correlate cel`. A predicate target
must identify exactly one place-to-transition arc. `correlate cel` must target
exactly one input arc (`->`, `->?`, or `->0`). Its string is an inline CEL
expression over two names: `token`, the data of one token, and `binding`, the
place-keyed data of the candidate binding (`binding.orders[0].account`). On an
inhibit arc it is the anti-join (ADR 0017): a source token that satisfies it
blocks the binding. On a consume or read arc it is a join (ADR 0030): every
token the arc binds must satisfy it. A `predicate cel` sees only its own
token's fields, as bare names (`status == 'ready'`); a condition between two
tokens belongs in `correlate cel`, and `velocitron validate` warns when a
predicate names a color or a place. Weight is valid only for eligible input
modes and is at least one; default weight one is omitted canonically. `data` targets a
produce arc and distinguishes absent data from literal `{}`. `data cel` is the
computed variant (ADR 0023): its string is an inline CEL expression over the
name `binding`, mutually exclusive with literal `data` on one arc, and lowers
to the template's `cel` field. Place capacity is
exactly `(Place) capacityPerColorKey JsonObject` with schema `key` and `max`;
it is checker-only, never an enablement or deposit gate.
An accepted-color fact is exactly `(Place) accepts [Color, ...]`. It declares
the place and fixes its complete, non-empty, ordered `accepts` list. Equal
repetitions are idempotent; unequal repetitions conflict. Topology-derived
colors combine idempotently with the declaration, but a topology color absent
from the declared list conflicts. Canonical emission omits these facts when
topology alone reconstructs every place and its exact accepted-color order; if
any place needs a fact, it emits facts for all places in core order so isolated
places and place-array order round-trip exactly.

An `arc.declare` Contribution always encodes its selected core color as
`{"kind":"explicit","value":Color}`. For bare `->`, `Color` is `token`; neither
the Contribution IR nor final resolution performs contextual color inference.
The value remains an ordinary exact-match color through parsing and core JSON,
even when visualization omits the generic label.

Standalone declarations lower to `place.declare` or `transition.declare` with
the corresponding typed target and the closed empty value `{}`. A standalone
place for which the complete aggregate supplies no explicit or topology color
resolves with `accepts: ["token"]`. Any such color evidence, including evidence
later in the same source or a later aggregate source, prevents that fallback;
the fallback never adds `token` beside evidenced colors.

A formatter reconstructing an elaborated core arc without a validated
presentation handle calls it `@arc_<zero-based-core-arc-index>`. Such a handle
is generated identity, not preserved authored metadata.

## Transition, template, marking, and timer facts

Transition facts are direct and separate: `[Transition] handler JsonString`
and `[Transition] guard JsonString`. They do not declare their target; topology
or a standalone `[Transition]` declaration must declare it first. A handler
fact supplies the transition's optional behavior binding and must contain a
nonempty JSON string. If no explicit handler fact exists at final resolution,
the core `handler` key is
omitted and parsed `Transition.handler` is `None`. No opaque same-name ref,
executable no-op, or structural firing behavior is synthesized. Handlerless
structure remains valid for parse, composition, and visualization; Engine and
Runtime execution enforce the boundaries in `spec/firing-semantics.md`.
Timer facts are exactly:

```text
[Transition] timer clock (Place) cel JsonString
[Transition] timer maturity cel JsonString
[Transition] timer bind IDENT (Place)
```

The bind name is an `IDENT` or a bare keyword, never a JSON string.

`timer maturity` is optional scheduler metadata: it evaluates in the same
closed environment as the timer CEL and returns the next future monotonic
timestamp for that binding. Runtime requires it for native timers; the
synchronous Engine ignores it. `clock` is reserved; binds retain source order
in parsed DSL and use lexical name order when reconstructed from JSON.
`priority 0` is omitted canonically. Clock/bind places must be valid timer
inputs; timer facts never synthesize topology or a scheduler.

A bind fact sets one key of a transition's `bindingNames`
([ADR 0032](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0032-composition-keeps-cel-place-names-with-binding-names.md),
[ADR 0043](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0043-a-merged-net-has-a-petrinet-form.md)):

```text
[Transition] bind Name (Place)
```

`Name` is the key under which the transition's `correlate` and produce `cel`
expressions find the tokens bound from `Place`. Authors rarely write it:
`velocitron to-petrinet` writes it for a merged net, whose keys are the
constituent nets' local place names. Once a transition has a bind fact, its
bind facts must name exactly the places it consumes or reads; otherwise the
first fact gets a `PN202` diagnostic. Repeating a fact is idempotent, and
two places for one key is a `PN202` conflict. Canonical output sorts the
keys.

Templates and markings use exactly:

```text
$Template: Color JsonValue
marking initial (Place) <- PositiveInt
marking Name (Place) <- PositiveInt
marking initial (Place) <- [ PositiveInt "*" ] $Template
marking Name (Place) <- [ PositiveInt "*" ] $Template
```

The count is mandatory in the two count-only forms and must be strictly
positive. `marking initial (Place) <- N` and `marking Name (Place) <- N`
each append exactly `N` fresh core tokens `{"type":"token","data":{}}`.
Here `token` is the exact ordinary Generic color, not a wildcard and not
untyped core data; the target place must accept `token`.

In either contribution, a count-only right-hand side lowers to
`$defs.tokenLiteral` in `spec/petrinet-contribution-ir.schema.json`. An initial
fact's `marking.append` value is exactly
`{"count":N,"token":{"color":"token","data":{"type":"object","entries":[]}}}`;
a named fact puts the same `count` and `token` members in its
`metadata.named-marking` entry. Neither creates or references an implicit
template. The resolver accepts both
the existing template-reference shape and schema-valid `tokenLiteral` values
for initial and named marking entries. A literal's color must be accepted by
its target place, and its tagged `data` must resolve to an object valid as core
token data. Every marking fact appends its expanded tokens to that place;
repeated facts append in source order.

The `$Template` forms and their optional `N *` multiplicity are unchanged.
`initial` is reserved and may not name a non-initial marking. A template is an
immutable JSON-value abbreviation; use may precede definition, multiplicity
is positive, and expansion creates fresh JSON containers. Initial markings
lower to `initialMarking`; named markings preserve statement/place/token order
only below v1 metadata. Undefined templates, a non-JSON value, a missing or
nonpositive count where required, a conflicting template, a literal rejected
by its target place, invalid literal token data, and a named-marking collision
are rejected.

## Domain, final, and invariant facts

Three net facts state what the net does not show by its structure
([ADR 0037](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0037-declared-domains-are-a-runtime-contract-and-proofs-check-refinements.md)):

```text
domain Color.Field[.Field]* Value Value*
final (Place) [+ (Place)]* [, (Place) [+ (Place)]*]*
invariant [JsonString] [PositiveInt *] (Place) [+ [PositiveInt *] (Place)]* [= NonNegativeInt]
```

```text
domain verdict.result "pass" "hold"
domain attempt.delivery.tries 0 1 2
final (delivered), (gave_up)
final (recalled), (loaned) + (survey)
invariant "lock" (shelf_slot) + (lending) + (loan_ended) = 1
invariant 2 * (pending) + (done)
```

A `domain` value is a JSON string, number, `true` or `false`, listed once. The
fact lowers to the core `domains` member under the key `Color.Field.Field`
(`spec/net-schema.md`); the engine enforces it at deposit and injection, and
`velocitron prove` uses it in place of the domain it derives. Repeating a
domain fact with the same values in the same order is idempotent; another list
for the same key is a `PN202` conflict. The color must be accepted by some
place. A field key may be quoted, but may not contain a dot.

`final` and `invariant` lower to the core `proofs` member, which only the
prover reads. A `final` fact lists final markings, separated by commas; `+`
joins the places of one final marking, which the instance reaches when every
one of them holds a token
([ADR 0049](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0049-a-final-marking-can-need-several-places.md)).
Each final marking lowers to its own `proof.final` contribution, whose target
is its first place and whose `with` lists the others; it lowers to one
`proofs.final` entry, a place name, or an array of the names when there are
several. Repeated `final` facts add final markings. A place named twice in one
final marking, and a final marking named twice in one fact (in any order), are
`PN202` errors. An invariant without a weight counts a place once, and without
`= N` it claims only that no firing changes the sum. A place named twice in one
invariant, and two invariants with the same name, are `PN202` errors. Every
place must be declared. `final` takes commas so that a bare place declaration
on the next line is never read as one more final place.

Canonical output emits these facts after markings and templates, in the order
domains, `final`, invariants. `domain`, `final`, and `invariant` are keywords
that stay usable as names; `=` is a token only here.

## Actor facts

Actor facts say who does each step of the net, in business words
([ADR 0038](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0038-sequence-diagrams-project-scenarios-onto-actors.md)).
A play's sequence diagram draws one lifeline per actor, and a queue for
each place a token crosses between actors
([ADR 0073](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0073-hand-off-places-are-sequence-lifelines.md)).

```text
person Name
system Name
record Name
net actor Name
(Place) actor Name
[Transition] actor Name
```

```text
person Clerk
system Desk
net actor Desk
[close_desk] actor Clerk
(open_sign) actor Clerk
```

`[Transition] actor Name` names who fires the transition. `net actor Name` is
the default actor of every transition of this net that names none.
`(Place) actor Name` names the place's owner: who puts tokens into it from
outside the net (an injection). An actor name is an `IDENT` or a non-empty
JSON string.

These three facts lower to an ordinary `documentation.annotation`
contribution with the key `actor` and a string value, on the net, the place,
or the transition. `[t] actor Operator` and `[t] annotation actor "Operator"`
are therefore the same fact: an equal repeat is idempotent and a different
actor is a `PN202` conflict. Like every annotation, the engine ignores it.

`person Name`, `system Name` and `record Name` declare an actor's kind and
the order of the lifelines. A `record` is a column that a lived place is
drawn on (below), not someone who acts. Each lowers to an `actor.declare` contribution (target the net
document, value `{name, kind}`), and resolves to the net annotation
`actors: [{"name", "kind"}, ...]` in declaration order. An equal repeat is
idempotent; the same name with two kinds is a `PN202` conflict,
and so is a `net annotation actors` fact beside a declaration. A net need not
declare its actors: an undeclared actor is a system, in order of first
appearance.

Canonical output emits an `actor` annotation with a string value as an
`actor` fact, and a well-formed `actors` annotation as `person`, `system`
and `record` lines, among the documentation facts. `actor`, `person`,
`system` and `record` are keywords that stay usable as names.

### Lived places

A lived place is a record that stays, such as a branch home or a file on a
host. A sequence diagram draws it as a column of its own
([ADR 0039](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0039-sequence-diagrams-draw-lived-places-as-columns.md)).

```text
(Place) lives in Name
(Place) lives in cel "CEL"
(Place) reads as cel "CEL"
```

```text
record "Branch home"
(branch_home) lives in "Branch home"
(branch_home) reads as cel "token.isbn + ' at ' + token.branch"
(loaned) lives in cel "token.branch"
```

`lives in Name` names the column. `lives in cel "…"` computes it: a CEL
expression over `token`, the token's data, whose string result is the
column name. `reads as cel "…"` computes what a reader of a token sees, the
label of a read arrow. Each lowers to a `documentation.annotation`
contribution on the place: the key `lives` with a string value or
`{"cel": "…"}`, and the key `reads_as` with `{"cel": "…"}`. The engine
ignores them; canonical output emits them back as these facts. `lives`,
`in` and `reads` are keywords that stay usable as names.

### Kept records

A kept record is a record this system keeps: it is there from the start,
and only the net's own steps change it
([ADR 0051](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0051-a-kept-record-is-there-from-the-start-and-only-the-net-writes-it.md)).

```text
(Place) kept by Name starts as cel "CEL"
```

```text
system "circulation desk"
(condition) kept by "circulation desk" starts as cel "{'isbn': instance.isbn, 'damaged': false}"
```

`kept by Name` names who keeps the record, as an actor name. `starts as cel
"…"` is the start value: a CEL map of the record's fields, with literal
keys. It may read one name, `instance`, the data of the instance token that
`velocitron prove` or a play follows (`spec/proofs.md`, "Kept records";
`spec/play-language.md`). The fact lowers to a `documentation.annotation`
contribution on the place with the key `kept` and the value `{"by": Name,
"start": {"cel": "…"}}`. The engine ignores it; canonical output emits it
back as this fact. `kept` and `starts` are keywords that stay usable as
names.

`velocitron validate` reports a `PN202` error at the fact when the kept
place has `annotation fusion true`, is a port, lives in a `record` column,
has tokens in the initial marking, or accepts more than one color; and when
the start is not a map with literal keys, reads a name other than
`instance`, leaves out or breaks a declared domain of the record's color,
or leaves out a field that the net reads from the place. In a composition,
each net is checked on its own, and a `share` that joins a kept place must
join only places kept the same way (the same `by` and start); the error is
at the `share` fact. A wire never joins a kept place, because it is never a
port. These checks are in the Python implementation; the TypeScript
implementation lowers the fact to the same JSON.

## Composition

The only composition inclusion fact is `use JsonStringRef as IDENT`; aliases
are mandatory and unique. The referenced file may be a net or another
composition ([ADR 0041](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0041-a-composition-can-use-a-composition.md)).
A wire is `wire Alias.(Place) -> Alias.(Place)`. Paths are retained verbatim and
resolved relative to the containing composition source. Wires connect an output
port to an equal-typed input port; they fuse existing places and never add
transitions, token copies, polling, handlers, or ref rewriting. Each constituent
transition's optional behavior binding is preserved unchanged, including
absence.

A share is `share Alias.(Place) ~ Alias.(Place) [~ Alias.(Place) ...]`
([ADR 0040](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0040-a-share-fuses-places-without-a-direction.md)). It
lowers to one `shares[]` entry `{places: [{net, place}, ...]}` and fuses the
places into one place without a direction: the places need not be ports, and
they must accept the same colors. Use it for a record or a lock that several
nets read, take, or give back, and for a final place more than one net ends
in. Every alias must be declared by a `use` fact; repeating the same fact is
idempotent. An unknown place, different colors, or a place shared with itself
is a `PN202` diagnostic at the share fact. `share` is a keyword and `~` a
token; `share` cannot be an alias but stays valid as a place, transition, or
color name.

When an alias names a composition, the parentheses or brackets hold a dotted
path inside it: `lifecycle.(gate.sending)` is the place `sending` of the net
`gate` inside the composition `lifecycle`, and `lifecycle.[outcome.attempt]` a
transition. The path is the name the place or transition has in that
composition's merged net, so it works at any depth. A path that names nothing
is a `PN202` diagnostic at the endpoint.

A composition's own final markings are
`final Alias.(Place) [+ Alias.(Place)]* [, Alias.(Place) [+ Alias.(Place)]*]*`
([ADR 0049](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0049-a-final-marking-can-need-several-places.md)).
One fact lowers to one `composition.final` contribution and to the
composition's `final` member: a list of final markings, each a list of
`{net, place}` endpoints. They replace the final facts of the composition's
nets in the merged net (see "Final markings" in `spec/composition.md`). Every
alias must be declared by a `use` fact; repeating a final marking is
idempotent. A place named twice in one final marking, or a place the net does
not declare, is a `PN202` diagnostic at the `final` fact.

A refinement is `refine Alias.[Transition] by Alias`. It lowers to one
`refinements[]` entry `{net, transition, by}`: the merge removes the refined
transition and its arcs, and the `by` net takes its part through ordinary wires
that the author writes (see "Refinement" in `spec/composition.md`). Both aliases
must be declared by `use` facts and differ; repeating the same fact is
idempotent, and refining one transition by two nets is a `PN202` conflict.
Fit failures found after the nets load (unknown transition, an unwired place, a
port of another color, an inhibit arc or a timer) are `PN202` diagnostics at the
refined `Alias.[Transition]`. `refine` and `by` are keywords, so they cannot be
aliases; as place, transition, or color names they stay valid. The refined
transition may sit inside a used composition (`refine lifecycle.[outcome.attempt]
by attempt`); the `by` alias must name a net, and a composition there is a
`PN202` diagnostic at the refined `Alias.[Transition]`.

`parse_composition(source, *, net_loader=None, origin=None)` uses
`origin: Path | None` solely to resolve relative default-loader references.
For a filesystem path, the parser supplies that path's parent automatically.
For in-memory mapping/raw text, a relative ref is rejected unless the caller
supplies `origin` or a `net_loader` closure that resolves it. Absolute paths
need no origin. `net_loader` is
`Callable[[str], Mapping | Path | str]`: a DSL loader accepts a
source-relative `.petrinet`, compiles it to JSON-shaped data, returns that
data, and the parser calls `parse_net` itself. JSON refs return JSON source
material to the same validator. Missing files, unsupported extensions, cycles,
and loader failure are stable `PN5xx` diagnostics; a loader may never return a
`Net`, `Composition`, or bypassed validation result.

Compiling a composition source loads its nets only when the caller passes a
loader or an origin: Python `compile_petrinet_text(..., net_loader=,
origin=)` and TypeScript `compilePetrinetText(source, sourceId, {loadRef,
origin})`. Both ports then report a wire, share, or refine that does not fit
the loaded nets as the same `PN202` diagnostic at the fact.

## Full-document metadata and presentation

The exact metadata facts are:

```text
MetadataTarget description JsonString
MetadataTarget annotation Name JsonValue
extensions JsonObject
view Name position ViewTarget at {"x": Number, "y": Number}
view Name position ViewTarget relative ViewTarget + {"x": Number, "y": Number}
view Name route @Handle orthogonal [ {"x": Number, "y": Number}, ... ]
view Name splines ( ortho | spline | curved | polyline | line )
view Name detail ( full | summary | structure )
decorate DecorationTarget highlight [ JsonString ]
decorate DecorationTarget note JsonString
decorate ( [Transition] | @Handle ) summary JsonString
decorate (Place) beside [ left | right ]
decorate color Color quiet
decorate color Color show JsonString ...
```

`MetadataTarget` is `net`, `(Place)`, `[Transition]`, or `@Handle`.
`ViewTarget` is `(Place)`, `(Place)@[Transition]`, or `[Transition]`; views
cannot position the document or an arc. `(Place)@[Transition]` names one
drawn copy of a fusion place at that transition (ADR 0068). The place must be annotated
`fusion true`, and the transition must use it. Two targets that draw the same
shared copy (ADR 0035: neighbor transitions, `beside` with no side) must carry
the same position; equal positions are idempotent and different ones conflict.
The stored key is `place:<place>@transition:<transition>`. The entry is
stored on the view. A renderer places that copy at the entry's resolved
point (ADR 0072). An ADR 0035 shared copy is one node, so the one agreed
entry places it.
A `relative`
position names two targets: the subject it positions and the base it offsets
from; the delta is added to the base's rendered position. The base may be any
positionable target. Relative entries never resolve into the stored payload:
they lower verbatim (positions stay `{"from", "delta"}` facts). The resolver
checks shape and that each target names a declared place or transition. A bare
`(Place)` base is that place entry's point, so the view must position the
place. A `(Place)@[Transition]` base must itself be positioned in the view,
and applying the view adds the delta to the point where that copy is drawn. A
transition base is only checked as declared; applying the view rejects one
that carries no position. Applying a view resolves relative entries at render
time against the other positions in the same view — chains resolve in
dependency order, a base that carries no position in that view is rejected,
and a relative chain that never becomes grounded is rejected.
`splines` picks the Graphviz edge style a renderer uses when it applies the
view; without it the style is `ortho`. `detail` picks how much behavior the
labels show when the view applies: `full` shows every expression whole,
`summary` shortens expressions, and `structure` drops handler refs, guards,
timers, priorities, predicates, correlations and data templates. A caller's
explicit detail choice wins over the view's. Each value is a `Name`; any other
value is rejected while lowering, and two different values for one view
conflict. A view needs no positions: style facts alone declare it.

`DecorationTarget` is `(Place)`, `[Transition]`, or `@Handle`, where the
handle must identify exactly one arc. Decorations are inert presentation
facts, like views, but they belong to no view: a renderer draws them with any
view or with none. `highlight` marks an element; its optional string is a
short label drawn with it. `note` is a short text drawn with the element.
`summary` is the text that the `summary` detail level shows in place of a
transition's guard, timer and priority, or an arc's predicate, correlation, or data
template; a place carries no such expression, so a place summary is rejected
while lowering. `beside` applies to a fusion place, one annotated
`fusion true`, which a renderer draws as one local copy per transition that
uses it: it asks the renderer to draw each copy on the same rank as its
transition, next to it. `left` and `right` pick the side; without a side the
renderer picks one. When a view positions nodes, a copy is placed by the
first of these that applies (ADR 0072). A `(P)@[T]` entry places that copy.
A whole-place `(P)` entry places every copy of `P` that has no copy entry.
`beside` places a copy only when neither entry does, at a horizontal offset
from its transition on the side `beside` chooses, when that transition is
positioned (ADR 0067). The offset is computed from the label widths. A
whole-place entry still anchors `relative (P)`. A transition or a
handle has no copies, so `beside` on
one is rejected while lowering, and `beside` on a place that is not annotated
`fusion true` is rejected. `decorate color Color quiet` asks a renderer to hide the type
label on consume and produce arcs of that color, as it always does for the
Generic `token` color; read and inhibit arcs keep their labels.
`decorate color Color show "id" "owner.name"` names the token fields a
renderer shows for that color, in the given order. It takes one or more
strings. Each string is a field path: keys joined by dots, so `owner.name`
reaches the `name` key inside the `owner` object. An empty path, an empty key
(`a..b`, `.a`, `a.`), or a path given twice in one fact is rejected while
lowering. A color may be both `quiet` and `show`. Each target
holds at most one value per decoration kind: an equal repeat is idempotent
and a different one conflicts. A decoration of an undeclared place,
transition, or handle, or of a color that no place accepts, is rejected.
`net description` and `net annotation` lower directly to
top-level core documentation fields, so arbitrary ordinary net annotation keys
survive JSON→DSL→JSON. `extensions` is net-scope only. Annotation keys use
`Name`; the reserved `"petrinet.dsl/v1"` key is rejected in ordinary annotation
facts. An unknown target, non-object extension, malformed/non-finite position,
unsupported view style/member, route or decoration to an unknown or stale
handle, or a
metadata fact trying to declare a semantic object is rejected.

Descriptions and ordinary annotations lower directly to their core
non-behavioral fields. Named markings, geometry, routes, decorations, authored
arc handles, and opaque extensions lower only below net
`annotations["petrinet.dsl/v1"]`. Version 1 has exactly these shapes:

```text
arcHandles: { Handle: { index: NonnegativeInt,
                        fingerprint: { from, to, type, mode } } }
markings:   { Name: { Place: [Token, ...] } }
views:      { Name: { positions: { Target: Point }
                      | { Target: { from: Target, delta: { x, y } } },
                      routes: { Handle: { style: "orthogonal",
                                          points: [Point, ...] } },
                      splines?: "ortho" | "spline" | "curved"
                                | "polyline" | "line",
                      detail?: "full" | "summary" | "structure" } }
extensions: JsonObject
decorations?: { Subject: { highlight?: { label?: String },
                           note?: String,
                           summary?: String,
                           beside?: { side?: "left" | "right" } }
              | { "color:" Color: { quiet?: true,
                                    show?: [FieldPath, ...] } } }
```

A position `Target` is `place:<name>`, `transition:<name>`, or
`place:<name>@transition:<name>` for one drawn copy. A decoration `Subject` is `place:<name>`, `transition:<name>`, or
`arc:<handle>`; a place subject carries no `summary`, and only a place subject
carries `beside`. A color subject carries at least one of `quiet` and `show`;
`show` keeps the source order of its field paths. The `decorations` member
is present only when the source has at least one decoration.

Formatting validates handle index first and exact fingerprint second. Only
`extensions` may contain unknown future fields. Metadata cannot change Engine,
property, or composition behavior; `view row` is not syntax. A view named
`default` is the one exception to opt-in presentation: a renderer applies it
when the caller selects no view, and `velocitron-viz --no-view` turns it off.

## Portable Contribution IR

Contribution IR has `format: "velocitron.petrinet/contribution-ir"` and
`version: 1`. Its machine-readable schema is
`spec/petrinet-contribution-ir.schema.json`. It contains a document kind and
an ordered contribution array. Every contribution has a source-derived unique
identity, contiguous source ordinal, closed kind, explicit typed target,
JSON-only value, and portable source span. It represents progressive facts;
source metadata never reaches resolved canonical JSON. Unsupported format or
version is rejected before resolution.

## Canonical output and CLI

Canonical DSL is LF-terminated, explicit, deterministic, and a fixed point. It
always emits a net header and explicit arc colors (including `-token->`).
For each transition that has no incident topology arc, canonical output emits
a standalone `[Transition]` declaration before that transition's optional
facts. It emits a transition handler fact exactly when the core transition has
a behavior binding and omits the fact when the core `handler` key is absent.
Header omission, bare arrows, and place-color fallback remain authoring sugar;
handler absence remains absence. Canonical output emits topology in core order;
standalone isolated-transition declarations; present handlers/guards; timer and
priority facts; place facts; arc elaborations; markings/templates; domain,
final, and invariant facts; then documentation and full-document metadata.

For markings, every maximal consecutive run of
`{"type":"token","data":{}}` emits `marking initial (Place) <- N` or
`marking Name (Place) <- N` with the integer run length substituted for `N`,
including `1`; canonical output does not generate a template for that run. All
other tokens retain generated
`$token_<zero-based-distinct-token-ordinal>` template facts, and only
consecutive structurally equal tokens coalesce. Generic-empty runs do not
consume a generated-template ordinal.

Compact output is separately requested and may replace eligible default
`-token->` consume/produce segments with bare `->`; bare arrows never
abbreviate another color.

The `velocitron` console script provides exactly:

```text
velocitron validate INPUT
velocitron to-json INPUT [--semantic-only]
velocitron to-petrinet INPUT [--compact]
```

Successful commands write only UTF-8 output to stdout and no stderr; `validate`
writes `net\n` or `composition\n`. The one exception: `validate` of a net (or of
each net a composition uses) also runs the advisory lint rules (`spec/net-schema.md`) and writes each finding to
stderr as `PATH:LINE:COLUMN: warning[RULE]: MESSAGE` at the source of what it flags (`1:1` for JSON input), still exiting 0. A transition that consumes and produces nothing is warned about (`consume-without-produce`); when that end is intended, mark it with `[t] annotation end true`, which silences the warning for that transition, in a net and in a composition that uses it. `validate` also reports a `PN202` error at a malformed `[t] annotation wait {"when": "<CEL>", "for": "<text>"}`, the intended wait of a choice (`spec/net-schema.md`, ADR 0057). User errors exit 1 with deterministic
`PATH:LINE:COLUMN: error[CODE]: MESSAGE` stderr and no traceback. Argument
misuse exits 2. `to-json` preserves full net metadata by default;
`--semantic-only` is the only removal path.

## Contract amendments

The former Slice 03 requirement to canonically recover `@vend_signal` is
replaced by generated `@arc_3`: core JSON has no source-only handle field.
Slice 02 authored return-first topology remains a valid parse/resolution case,
not required canonical JSON-to-DSL text. Composition headers remain
DSL-local namespaces and do not add core JSON metadata.
