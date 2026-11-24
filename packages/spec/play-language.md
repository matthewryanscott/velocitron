# `.play` language contract

## Status and boundary

This specification defines version 1 of Velocitron's `.play` language,
the checker that plays a play against a net, and the walkthrough it
renders. The statement grammar is
[`packages/play/VelocitronPlay.g4`](../play/VelocitronPlay.g4). It parses
one statement. The line discipline in [Source text](#source-text) stays
outside that grammar. `velocitron-play` and `@velocitron/play`
(`packages/play`) parse a play in Python and TypeScript.
`velocitron-play-check` and `@velocitron/play-check`
(`packages/play-check`) check that play against a net and step a
walkthrough. The Python package is the reference for checking, the
walkthrough (including paired Graphviz graphs; [ADR 0033]), and the
sequence diagram ([ADR 0038]). TypeScript checks through
`@velocitron/engine` and steps a walkthrough document; paired Graphviz
graphs and PlantUML stay in the Python package. The conformance cases
in `spec/conformance/play/` remain the target ([ADR 0031]).

A play never changes a net. It is checked by symbolic firing through the
ordinary engine, so [`firing-semantics.md`](https://github.com/matthewryanscott/velocitron/blob/main/packages/spec/firing-semantics.md) defines
every rule of enablement, binding, timers and deposit. This document adds
only where a firing's output data comes from.

## Terms

- A **Play** is a `.play` source: an ordered list of steps against one
  net or one composition, from a chosen marking, with Markdown prose.
- A **Play step** is one statement the checker plays: `inject`, `update`,
  `advance`, `fire`, `expect` or `assume`. Every step has a marking before and
  after it; an `expect` step changes nothing, and an `assume` step changes only
  what the checker answers (below).
- A **Path** is one sequence of steps. The steps before any `path` line form
  the trunk, named `trunk`. A branch path starts from a labeled step of the
  trunk or of an earlier path and replays every step up to and including it.
- **Symbolic firing** plays a `fire` step through `Engine.reserve` and
  `Engine.settle`, with output data from the rules below in place of a handler.
- The **carry rule** fills a produce template from the one consumed token of
  its color.
- An **occurrence sequence** (the checker's result for one path) is the
  per-step record a play's check produces: the marking before and after
  each step, the engine records, the checks, and the first failed step's
  diagnostic. The books' word *trace* (G&V p. 232) names a Mazurkiewicz
  trace, a different object, so the spec does not use it here; the Python
  class `PlayTrace` keeps its name.
- A **Walkthrough** is the document rendered from one checked path.
- An **Actor** is who does a step, in business words: a transition's
  `actor`, or for an injection the `actor` (owner) of its place
  ([`petrinet-language.md`](./petrinet-language.md), "Actor facts").
- A **Hand-off** is a step that uses a token another actor produced.
- A **Lived place** is a place drawn as a column of its own: a record that
  stays, such as a branch home or a slip on a shelf
  ([`petrinet-language.md`](./petrinet-language.md), "Lived places").
- A **Sequence diagram** is the projection of one checked path onto its
  actors and columns: an arrow per hand-off and per write into or read from
  a column, and a note for an actor's own steps.

## Source text

Source is UTF-8. A statement starts at column 0. A line that starts with a
space or a tab continues the statement above it, so a token or a JSON object
may span lines; a blank line between continuation lines is allowed. A line
that starts with `///` is Markdown prose. `//` starts a comment, at column 0
or after a statement; a comment never reaches a walkthrough.

Names use the `.petrinet` forms: an `IDENT` (`[A-Za-z_][A-Za-z0-9_]*`) or a
JSON string. Inside `(…)` and `[…]` an unquoted name may also be dotted
(`lifecycle.pending`), for composed nets. JSON values follow RFC 8259:
duplicate keys and non-finite numbers are rejected.

### Prose

Consecutive `///` lines form one Markdown block, joined by single newlines;
a leading space after `///` is dropped. A `///` line with no text is an
empty line inside the block, so it starts a new Markdown paragraph. A blank
line ends a block, also a blank line right after a statement. A block
attaches as follows:

1. Directly under the `play` or a `path` line (no blank line between), it
   belongs to that header.
2. Followed by a step, it belongs to that step. Several blocks before one step
   join with a blank line.
3. Followed by a setting or a template, it belongs to the current header (the
   play's for the trunk, the path's for a branch).
4. Followed by a `path` line, it belongs to that path.
5. At the end of the source, it is appended to the last step.

## Grammar

The normative statement syntax is `packages/play/VelocitronPlay.g4`. The
block below is a reading aid for the same language. Prose, comments, and
continuation lines are not productions in that grammar; [Source text](#source-text)
defines them.

```text
Play         := Header ( Setting | Template | Prose | Step | PathDecl )*

Header       := "play" IDENT [ JsonString ]
Setting      := "net" JsonString
              | "use" JsonString "as" IDENT
              | "wire" IDENT "." "(" Name ")" "->" IDENT "." "(" Name ")"
              | "share" IDENT "." "(" Name ")" ( "~" IDENT "." "(" Name ")" )+
              | "refine" IDENT "." "[" Name "]" "by" IDENT
              | "marking" ( "initial" | "none" | Name )
              | "instance" Token
              | "scope" ( "step" | "neighbors" | "subnet" )
              | "show" Color FieldPath ( "," FieldPath )*
              | "show" "sequence" [ "only" ]
              | ( "person" | "system" | "record" ) Name
              | "box" Name Name+
FieldPath    := Name                                // keys joined by "."
Template     := "$" IDENT ":" Color JsonObject
PathDecl     := "path" IDENT [ JsonString ] "from" "@" IDENT

Step         := [ "@" IDENT ":" ] StepBody [ JsonString ]
StepBody     := "inject" "(" Name ")" "<-" Token ( "," Token )*
              | "update" "(" Name ")" "<-" Token
              | "advance" [ "(" Name ")" ] [ "+" ] Time
              | "fire" "[" Name "]" ( With | Output )*
              | "expect" Condition ( "," Condition )*
              | "assume" "[" Name "]" "guard" ( "true" | "false" )
              | "assume" "predicate" JsonString ( "true" | "false" )
With         := "with" "(" Name ")" ( JsonObject | "$" IDENT | "#" Integer )
Output       := "->" "(" Name ")" ( Token ( "," Token )* | "+" JsonObject | "nothing" )
Condition    := "(" Name ")" "==" Token ( "," Token )*
              | "(" Name ")" "empty"
              | "(" Name ")" "count" Integer
              | "(" Name ")" "has" Token
              | "enabled" ( "[" Name "]" )+
              | "not" "enabled" ( "[" Name "]" )+
              | "next" "[" Name "]"
              | "quiescent"
Token        := "$" IDENT | Color JsonObject | JsonObject
Color        := IDENT | JsonString
Time         := Number | Duration
Duration     := [ N "d" ] [ N "h" ] [ N "m" ] [ N "s" ]     // at least one part
```

`N` and `Number` are decimal numbers such as `90` or `22.5`. A duration
lowers to seconds: `90s` is 90, `90m` is 5400, `22.5h` is 81000, `1h30m` is
5400. A plain number is seconds. A whole number of seconds stays an integer.

The optional `@label:` names a step for branching; labels are unique in a
source. The optional string at the end of a step is its title, the heading
of its walkthrough section.

A bare `{json}` token takes the one color its place accepts (for `->`, the
one color of that place's produce templates); when there are several, the
color is required. `$name` names a template; a template's color is fixed.

In an `==` token list, a comma followed by `(`, `enabled`, `not`, `next` or
`quiescent` starts the next condition.

## Settings

- `net "file"` names a `.petrinet` or `.json` document, relative to the
  play file. It may be a net or a composition document (a `.petrinet`
  with a `composition` header, or composition JSON).
- `use "file" as alias`, `wire a.(p) -> b.(q)`, `share a.(p) ~ b.(q)` and
  `refine a.[t] by b` compose nets in the play itself, with the meaning
  of the same `.petrinet` facts ([`composition.md`](https://github.com/matthewryanscott/velocitron/blob/main/packages/spec/composition.md)). A
  play has `net` or `use` lines, not both. A step that names a refined
  transition fails with `SC203`, and the detail names the refining net.
- A place or transition of a composition is named by its merged name,
  `alias.name`. Inside a used composition the name has one more segment
  per level: `(lifecycle.gate.pending)`. A fused place answers to the name
  of each of its members.
- `marking initial` (the default) starts from the net's initial marking, or
  an empty marking when it declares none. `marking none` starts empty.
  `marking NAME` starts from a named marking of a single net. Together,
  `marking none` and leading `inject` steps are how a play states a
  literal start: a reader who builds a marking by hand writes `marking
  none`, injects the tokens the hand-built marking holds, and then plays.
  A kept record the hand-built marking holds is injected as its token's
  color and data; a story with no `instance` line starts without a record
  that reads `instance` and may inject it (below).
- Every starting marking also holds each **kept record** of the net
  ([`petrinet-language.md`](./petrinet-language.md), "Kept records";
  [ADR 0051](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0051-a-kept-record-is-there-from-the-start-and-only-the-net-writes-it.md)),
  with the value its `starts as` expression gives, `marking none` too. A
  start that reads `instance` is built from the token that `instance Token`
  names (`instance $u1`, or `instance hold {"branch": "main"}`); only
  its data is read. A story with no `instance` line starts without such a
  record, and may inject it as its first step. A start that cannot be built
  from the instance, or that breaks a declared domain, is `SC215`. An
  `inject` into a kept place that already holds its record, or of more than
  one token into one, fails with `SC305`; change the record with `update`.
- `$name: Color {json}` defines a template, usable before its definition.
- `scope step|neighbors|subnet` picks how much of the net each step's
  graphs draw in a walkthrough (see [Walkthrough](#walkthrough)). The
  default is `step`. A scope changes no check.
- `show Color f1, f2.sub` names the fields that a walkthrough shows for
  tokens of `Color`. A field path is keys joined by `.`; a dotted path
  reaches into a nested object (`show result outcome, hold.id`). A
  quoted path splits on `.` too, so it can name keys that are not
  identifiers. One `show` per color; it replaces the net's own
  `decorate color Color show` for that color. A color that no place takes is
  `SC214`. An unquoted `sequence` right after `show` is the setting below,
  so a color named `sequence` is written quoted: `show "sequence" id`.
- `show sequence` adds the path's [sequence diagram](#sequence-diagram) to
  its walkthrough, before the steps; `show sequence only` draws the diagram
  in place of the steps' graphs. Before any `path` line it applies to every
  path; after a `path` line it applies to that path only and wins. One per
  scope. A sequence view changes no check.
- `person Name`, `system Name` and `record Name` declare a lifeline's kind
  and put it first in the diagram, in declaration order, before the net's
  own declarations. They change no check.
- `box "Title" A B …` draws the named lifelines together in a titled box, in
  this order, where the first of them would be. A lifeline is in one box at
  most (`SC105`). A name that the diagram does not use is left out. It
  changes no check.

In a composed net every place and transition has its qualified name,
`alias.name`. A fused port place answers to the qualified name of each of
its members, so `(producer.out)` and `(consumer.in)` name the same place.

## Steps

Each step plays against the marking the previous step left.

- `inject (p) <- t1, t2` appends the tokens through `Engine.inject_tokens`:
  one injection record per token.
- `update (p) <- t` replaces the place's tokens through
  `Engine.inject_token(replace=True)`.
- `advance [(clock)] TIME` sets the clock token's `now` to `TIME`;
  `advance [(clock)] +TIME` adds `TIME` to it. The token keeps its other fields
  and its color; an empty clock place gets `{"now": TIME}` in the place's one
  color. The place may be left out when the net's timers name exactly one
  clock place. An `advance` on an empty clock place whose `TIME` is absolute
  (`advance 0` included) is update-only. Otherwise the statement carries one
  maturation: after the replace-injection, the checker plays every firing of
  a timer-gated transition on that clock the new time enabled, to quiescence,
  under the priority policy, as part of the same step — the records the
  advance already writes. A matured transition whose outputs the play cannot
  determine by the rules below (no net `data`/`data cel` and the carry rule
  does not apply) is skipped, left enabled for the author's own `fire` step:
  the checker never guesses and never emits `{}` on its own. A transition
  with a `handler` fact matures only when the net's `data`/`data cel` fills
  every output: its handler writes the rest, so a carried token would be a
  guess, and it is left for a `fire` step too. A maturation
  firing that fails (as `SC304` does) is recorded as the step's evidence and
  the pass continues without that transition — what a failed firing is to
  `Engine.advance` — and a maturation that never quiesces raises `SC315`
  instead of returning a truncated step. The statement's maturation
  deliberately narrows what `Engine.advance(time=…)` covers — only that
  clock's timer-gated transitions, priority pinned (the checker registers no
  handlers and needs determinism), chosen among those determined outputs.
- `fire [t]` plays one symbolic firing (below).
- `expect` checks conditions and changes nothing.
- `assume [t] guard true|false` scopes an assumption (below).

### Assumptions

An `assume` step tells the checker what a handler would answer, so a play
can reach a transition whose behavior is hand code
([ADR 0058](https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0058-a-net-compiles-to-a-python-base-class-and-the-journal-traces-and-replays-the-run.md),
"Open decisions"). It changes no marking; the assumption is in force from the
step to the end of its path.

- `assume [t] guard true|false` names a transition with a `guard` fact. From
  the step on, the checker answers every consult of `[t]`'s guard ref with the
  assumed value, so `fire [t]` and `expect enabled [t]` behave as if a guard
  handler had answered so. An assumption is scoped by transition: it ends with
  its path, and the next `assume [t] guard …` for the same transition replaces
  it. An `assume` for a transition without a `guard` fact is `SC308`; for a
  transition the net does not have, `SC203` (`unknown transition`, unchanged).
- `assume predicate "p" true|false` names a pure predicate handler ref. From
  the step on, the checker answers every consult of that ref on any consume
  arc with the assumed value. An `assume` for a ref no consume arc names is
  `SC310`.

An assumption stays inside its path: each path is checked on its own
registry, so the trunk's assumptions never reach a branch's steps past the
replayed prefix, and a branch replays the assumptions of the prefix it
inherits. The walkthrough draws an `assume` step as a line in its path (a
step section with no graphs, its caption stating what is assumed); a sequence
diagram draws nothing for it. The diagnostic of a transition an assumption
answers names the guard or predicate as answered (`guard "g" returned false`),
so the assumed value is visible in the occurrence sequence.

### Symbolic firing

1. **Binding.** `Engine.reserve` selects the binding: the first binding, in
   the enumeration order of [`firing-semantics.md`](https://github.com/matthewryanscott/velocitron/blob/main/packages/spec/firing-semantics.md),
   that passes every gate. `with` clauses narrow it, through `reserve`'s
   `choose` filter: `with (p) {subset}` wants a bound token from `p` whose
   data contains the subset (objects compare key by key, other values by
   equality), `with (p) $name` wants that exact token, and `with (p) #k`
   wants the token at index `k` (from 0) of `p` before the step. `p` must be
   the source of a consume or read arc of `t`.
2. **Guards.** The checker registers no handlers. A transition with a named
   guard is therefore not enabled, and the diagnostic says so — unless an
   `assume [t] guard …` step (above) is in force for it, in which case the
   guard answers the assumed value.
3. **Outputs.** For each produce template of `t`, in declaration order:
   1. A template with `data` or `data cel` is filled by the engine. A step
      may not give it (`SC211`).
   2. A `-> (p)` clause gives the template's tokens, or `nothing`.
      `-> (p) +{fields}` copies the carry token (rule 3) and sets the
      fields over it.
   3. **Carry rule:** when the binding's consume-mode tokens hold exactly
      one token of the template's color, its data is copied. Read tokens
      never carry: they are the environment, and copying one would invent a
      token.
   4. Otherwise the step fails with `SC303`, which names the template. The
      checker never guesses and never emits `{}` on its own.
4. **Settle.** `Engine.settle` deposits the tokens with the ordinary deposit
   contract and emits the firing record.

### Conditions

| Condition | Holds when |
|---|---|
| `(p) == t1, t2` | `p` holds exactly these tokens, in any order |
| `(p) empty` | `p` holds no token |
| `(p) count N` | `p` holds `N` tokens |
| `(p) has t` | some token in `p` has `t`'s color and its data contains `t`'s data |
| `enabled [a] [b]` | each listed transition is enabled (others may be too) |
| `not enabled [a] [b]` | no listed transition is enabled |
| `next [t]` | the built-in `priority` policy picks `t` from the enabled transitions |
| `quiescent` | no transition is enabled |

Enablement here is `Engine.enabled_transitions`, guards included, so a
transition with an unregistered guard is never enabled — an `assume`
statement (above) is the one way a play answers a guard.

## Paths

`path NAME ["title"] from @label` starts a branch. The label must belong to a
step of the trunk or of a path declared earlier. The branch replays its
parent's steps up to and including the labeled step, never copied, then plays
its own. Each path starts from the play's marking.

## Checking

`check_play(play, paths=None, validate_ir=True)` first resolves the whole play:
it loads the net, resolves every name, color, template and label in every
path, and raises `PlayError` with an `SC1xx` or `SC2xx` diagnostic.
Then it plays the trunk and each branch in source order, or only the named
paths. A path stops at its first failing step; the failure is part of its
occurrence sequence, never raised. The checker reads no clock and is deterministic.

A failure inside a replayed prefix is the same failure for every path that
replays it. The report gives it once, at the step's line, and lists the
blocked paths.

An occurrence sequence's steps chain: the marking after step `i` is the
marking before step `i + 1`. For a firing, a step result holds the full
binding, the consumed and read tokens, the produced tokens and the rule that
filled each output; for an injection, the injected and replaced tokens; for
an `expect`, each condition's result and values.

### Diagnostics

A diagnostic renders as `FILE:LINE:COL: error[CODE]: MESSAGE`, with indented
detail lines. The position is the step's first character.

| Code | Meaning |
|---|---|
| SC101 | syntax error: an unknown statement, a missing token, an indented first line, a play name that is not an identifier (`play step-warning`; the message names `step_warning`) |
| SC102 | invalid JSON |
| SC103 | invalid time or duration |
| SC104 | a missing or repeated `play` header, a repeated `net`, `marking`, `instance` or `scope`, two `show` lines for one color, or two `show sequence` lines in one scope |
| SC105 | a repeated label, path name, alias, template or actor; a path named `trunk` |
| SC201 | the net cannot be read, compiled or validated |
| SC202 | unknown place (with close names) |
| SC203 | unknown transition |
| SC204 | unknown template |
| SC205 | `from @label` names no step of the trunk or an earlier path |
| SC206 | unknown named marking |
| SC207 | a token color the place does not take, or a bare `{json}` where the place takes several colors |
| SC208 | `advance` without a place where the timers name zero or several clock places, or a clock place of several colors |
| SC209 | `with (p)` where `p` is not a binding place of the transition |
| SC210 | `-> (p)` where the transition produces nothing into `p`, an ambiguous `+{}` or `nothing`, or two clauses for one output |
| SC211 | `->` gives an output the net fixes with `data` or `data cel` |
| SC212 | both `net` and `use`, or neither |
| SC213 | an unknown path name in `paths` |
| SC214 | `show` names a color that no place takes |
| SC215 | a kept record's start cannot be built from the `instance` token, or breaks a declared domain |
| SC301 | the transition is not enabled |
| SC302 | no enabled binding matches the `with` clauses, or `#k` is past the end of the place |
| SC303 | an output is not determined (the carry rule does not apply) |
| SC304 | the engine rejects the deposit (for example, a `data cel` error) |
| SC305 | the engine rejects an injection, or a kept place already holds its record |
| SC306 | `advance +TIME` with no clock token, or one without a numeric `now` |
| SC307 | an `expect` condition does not hold |
| SC308 | `assume` for a transition with no `guard` fact |
| SC310 | `assume predicate` for a ref no consume arc names |
| SC315 | the advance's maturation did not quiesce within its cap |

`SC301` lists each gate that rejected the transition, from
`Engine.explain_enablement`, then `enabled now:`. The gates are
`clock-empty`, `inhibit-hit`, `arc-short` (with one line per token in the
place: wrong color, predicate false, or the predicate's eval error), 
`sub-multiset`, `correlate-miss`, `correlated-inhibit`, `timer-hold`
(with the clock and bound values), and the guard (`guard-unresolved`,
`guard-rejected`, `guard-error`). `SC302` lists the viable bindings instead.
`SC307` lists each failing condition with what the marking holds.

## Command line

```text
velocitron play check FILE [--origin DIR] [--path NAME]... [--json]
velocitron play walk  FILE [--origin DIR] [--path NAME] [--format md|json] [-o OUT]
                               [--direction tb|lr] [--scope step|neighbors|subnet]
                               [--sequence beside|only|none]
velocitron play sequence FILE [--origin DIR] [--path NAME] [--format plantuml|json] [-o OUT]
velocitron play trace FILE [--origin DIR] [--path NAME] [-o OUT]
```

`FILE` may be `-`: the source is read from stdin and named `<stdin>` in
diagnostics. `--origin DIR` is the directory that `net` and `use` paths
resolve against; without it, that is the file's directory, or the current
directory for stdin. `--scope` overrides the play's `scope` setting.

`check` exits 0 and prints one line on stdout, `FILE: OK, N paths passed`,
when every requested path passes, and 1 with the diagnostics on stderr
otherwise. `--json` prints a report object on stdout instead: `file`,
`passed`, `paths` (name, status, steps played, failure) and `diagnostics`.
An unknown `--path` is argument misuse, exit 2.

`walk` checks one path (the trunk by default) and renders it, to stdout or
`OUT`. A failing path renders up to its failure, ends with the diagnostic,
and exits 1. `--sequence` overrides the path's `show sequence` setting.

`sequence` checks one path the same way and prints its sequence diagram as
PlantUML, or as JSON with `--format json`. It exits like `walk`.

`trace` checks one path the same way and prints one JSON document of the
path's playback (the WalkthroughDocument's facts without the graphs), to
stdout or `OUT`. A failing path prints the document up to the failure,
ends with the diagnostic on stderr, and exits 1.


## Trace

`velocitron play trace` prints one JSON document per path:

- `play`, `path`, `status` (`passed` or `failed`) — the play's and path's
  names, and the path's outcome.
- `clocks` — the net's clock places, in name order.
- `initial` — the starting marking (as `walk --format json` writes one).
- `steps` — one entry per step:
  - `index` (from 0, inherited steps included), `line`, `kind`, `title`,
    `statement` — the step's fields.
  - `actor` — who does the step as the sequence view draws it: a firing's
    transition's `actor`, an injection's or update's place owner, or
    `null` (an `advance`, `expect` or `assume` has none; an untitled
    injection into an unowned place is setup on nobody's behalf).
  - `records` — the engine records, in order, each one of:
    - a `firing`: `transition`, `status`, `inputTokens`, `outputTokens`
      (each token `type` plus `data`), `matured` (`true` when the clock's
      `advance` played this firing) with the `maturedBy` injection id,
      `actor` (the transition's actor), `label` (the step's title, else
      the transition's `summary`, else its `description`, else `null`).
    - an `injection`: `place`, `injectionKind`, `tokens`, `replaced`,
      `actor`.
    - every token of a lived place also carries `column` (the lifeline it
      is drawn on) and `read` (its `reads as` text, else the place's
      label): the labels the sequence diagram resolves.
  - `afterEach` — one marking per record, the step's `after` last.
  - `after` — the marking after the step.

The document is `velocitron.play.trace_document(trace)`; the same shape
answers tools that would otherwise import checker internals.

## Walkthrough

A walkthrough has:

1. A title (the play's title, then the path's), a line of facts (net,
   path, branch point, status), and the play's and the path's prose.
2. **The starting marking**: the touched subnet drawn once with the marking
   the path starts from (for a branch, the marking after its replayed
   prefix, whose step headings are listed first).
3. One `##` section per step that changes the marking, numbered from 1 over
   the whole path: the heading `Step N — <title or statement>`, then two
   ```` ```dot ```` fences, the marking before and the marking after, a
   one-line caption of what moved, the checks of the `expect` steps that
   follow, and the step's prose. An `expect` step adds its checks and prose
   to the section before it, or to the starting marking. An `assume` step has
   its own section with no graphs (the marking does not change), and its
   caption states what is assumed from there: `From here, guard <t>'s answer
   is assumed true.` — or `predicate handler <p> is assumed false.`
4. For a failing path, the failing step's section with its before graph only
   (a firing's transition drawn in the failure style), and a last section with
   the diagnostic.

The **touched subnet** holds every transition a step fires or names in a
condition, every place on those transitions' arcs (read, inhibit and timer
clock places included), and every place a step injects into, updates,
advances or names. It keeps the arcs among them.

### Step scope

A step's graphs draw its **scope**:

- `step` (the default): a firing draws its transition and every place on
  its arcs (consume, read, inhibit, produce, and its timer's clock), and no
  other transition. An injection, update or advance draws its place alone.
- `neighbors`: the `step` scope, plus every other transition on those
  places, drawn faded (gray, dashed, name only), with only their arcs to
  those places, unlabeled. A fusion place does not add neighbors: it is drawn
  as one copy per transition, so its other transitions are not near it in
  the picture.
- `subnet`: the touched subnet, as in the starting marking.

A fusion place with no arc in the scope is drawn as one plain place.

### Before and after

The before and after graphs of a step are two graphs with one layout: they
draw the same nodes and arcs with the same ids, and each node has the same
size in both. A marking row that one half draws and the other does not is a
ghost in the other half: the same markup in transparent ink. A highlight
label that differs between the halves (`fires`, `fired`) sits in a cell of
one fixed width. `dot` lays out two such graphs the same way, so set side by
side (or stacked, with `--direction lr`) only tokens and highlights differ.
One graph holding both halves cannot promise this: `dot` lays out its parts
together, which shifts one half against the other, and its `pack` option
drops edge labels.

Graphs go through the ordinary render model ([ADR 0024]): the net's
decorations, fusion copies, `beside` and its `default` view's detail and edge
style carry over, and the starting marking also applies the default view's
positions. The net's own highlights keep their labels without their fill, so
the step's highlight is the one filled node. A firing highlights its
transition `fires` (before) and `fired` (after); an injection highlights its
place, labeled `injected`, `updated` or `clock moved` after. Token rows are
marked `consumed`, `read` and `replaced` before, and `produced`, `injected`
and `read` after. Consumed and replaced rows are pink and struck through;
produced and injected rows are light blue and bold; a read row has no fill
and a dashed outline. These differ for color-blind readers too.

### Token fields

A color named by a `show` setting, or else by the net's
`decorate color Color show` decoration, shows only those fields in its
rows, as `path=value` (a string without commas unquoted, any other value as
JSON). Any other color shows its full data. A field the step changed is
always shown, bold, underlined and amber. A token's changed fields are the
leaf paths that it adds or changes over the token it carries forward,
chosen among the tokens the step consumed (a firing) or replaced (an update
or an `advance`). That is the one such token of the same color, when there is
exactly one. Otherwise it is the token, or an object nested in one, of
which the new token keeps more than half the leaf fields unchanged, when
exactly one keeps the most: a `hold` made from a `result` that
embeds it under `hold` carries that object forward, and its new
`remindAt` is a changed field. With no such token, the token is new
and nothing is marked changed. The old token shows the same paths, under
the carried object's own path, with the old values. A place's tooltip holds the
full data of every token in it.

`--format json` emits the same content as a WalkthroughDocument:
`play`, `title`, `path`, `path_title`, `branch_from`, `net`, `status`,
`scope`, `direction` (`tb` or `lr`), `prose_md`, `sequence` (`null`, or
`mode` (`beside` or `only`) and `plantuml`), `stage` (`dot`, `checks`,
`prose_md`, `inherited`, `inherited_steps`), `steps` (each with `number`,
`heading`, `title`, `statement`, `line`, `before_dot`, `after_dot` (absent
on the failing step and on an `assume` step, which carries no graphs),
`caption`, `checks`, `prose_md`, `status`) and `failure` (`code`,
`message`, `text`, `line`). `inherited` holds the replayed prefix's step
headings; `inherited_steps` holds the same prefix as full step entries (the
fields above, minus the graphs, `status` `inherited`) so a consumer of the
JSON can retell the prefix the way the trunk walk does. With `only`,
`stage` is `null` and `steps` is empty. The Markdown form puts the diagram in a ```` ```plantuml ````
fence, under `## Sequence` for `beside`.

## Sequence diagram

A sequence diagram is a reduced view of a checked path. It draws no
structure of its own: every arrow is a fact of the path's firings, and every
label comes from the play or the net
([ADR 0038], [ADR 0039]).

**Actors.** A firing belongs to its transition's `actor`; without one, to
the net's default actor (`net actor`); without that, to the alias of a
composed net, or to the net's name. An `inject` or `update` belongs to its
place's owner (`(p) actor Name`), or to the lifeline `Outside` when the
place has no owner. A `advance` belongs to no one, but the firings it
matures belong to their transitions' actors: each draws after the advance's
delay marker, as its transition's own firing, and its outward messages —
the writes and the hand-offs into it — are marked `matured` (see `--format
json` below). A matured firing's label is its transition's label (see
Labels) with the suffix `(on time)`, so the reader sees the clock did it;
without an authored label it draws a bare arrow like any unlabeled firing.
The clock's read arc draws no hand-off (Markers).

**Lived places.** A place with a `lives` fact is drawn on a column: the
fixed name, or the string its CEL computes from the token (a failing
expression falls back to the place's label). A step that writes into a
lived place (a firing that produces into it, or an `inject` or `update`
after the path's first firing) draws a solid arrow from its actor into the
column, labeled with the step's label; several tokens into one column are
one arrow. A firing without an authored label (see Labels) labels its write
with the written place's description, else draws the arrow with no text;
never with the transition's name. A step that reads or consumes a token of
a lived place draws a dashed arrow from the column to its actor, labeled
with the value read: the place's `reads as` text, else its description,
else its humanized name. This holds whoever wrote the token, the reader's
own actor included. A step that writes into the column it reads draws one
arrow: with an authored label, only the write (a flip of a switch);
without one, only the read (the value it saw). An `inject` or `update`
before the first firing sets up the starting state and draws nothing; the
first read shows the value.

**Hand-offs.** Every other token remembers the step that produced it: a
firing, or an injection by the place's owner. Tokens of the starting
marking and tokens a `advance` writes have no producer; so do tokens an
untitled `inject` or `update` into a place with no owner produces, wherever
the step sits in the path, and tokens of a clock place. An untitled
injection into an unowned place draws nothing, and a token it produced is
no hand-off when another step consumes or reads it. An untitled `update` of
a clock place draws no hand-off either: its delay marker already says the
clock moved. A titled inject or update keeps its arrow: the author is
showing an outside event on purpose. A token that a step
consumed or read from another actor is a hand-off, drawn as an arrow from
that actor, labeled with what was handed over: the producer's step title,
else the hand-off place's read label (as above). Hand-offs from one actor
are one arrow, one line per producing step. A consumed hand-off is a solid
arrow; a read one is dashed. So an arrow follows causality, not the order
of the steps.

**Activations and notes.** A step starts a new activation when a consumed
hand-off reaches it, or when the activation before it belongs to another
actor; otherwise it joins that activation. Solid hand-off arrows come
first, then, step by step, the dashed arrows, the writes, and the notes.
There are no arrows from an actor to itself. An actor's own titled step
that writes to no lived place is a line in a note to the right of the
actor; notes of one actor in a row join into one. A step without a title
draws nothing of its own: it still runs and is checked, and its reads,
writes and hand-offs are still drawn. A titled step whose token is later
handed over shows as that arrow's label, not also as a note. Consecutive
writes of one activation into one column fold into one arrow, one line per
step that has text; a read between them keeps them apart. An activation that starts from a consumed hand-off and draws an arrow
of its own has an activation bar.

**Labels.** A step's label is its title. Without one, a firing uses its
transition's `summary` decoration, then its `description`; these three are
its authored label. A firing without an authored label uses its name, with
underscores as spaces and the first letter upper case, only in a failure
note. An injection uses its place's `description`, then its place name in
the same form.

**Markers.** A `advance` is a delay, `...1 hour 30 minutes later...`, computed
from the clock's `now` before and after. An `advance` that gives a clock its first
value draws nothing. Advances with nothing drawn between them are one delay,
the longest advance. The firings one `advance` matures draw after its delay
marker (Actors); with them drawn, the advance is no longer folded into the
next one. A `### heading` line in a step's prose opens a group
(`group First hold`) before the step; it closes at the next heading or
at the end of the path. Any other Markdown heading line (`## Cut over`) is a
divider, `== Cut over ==`. Other prose is left out. A branch path has a
divider with its title (or name) where its own steps start. An `expect`
step draws nothing, unless it fails.

**Failure.** A failing path ends with a red note: over the failing step's
actor, or across all lifelines for an `expect` or a `advance`. It holds the
step's label, the diagnostic code and message, and the diagnostic's first
detail line.

**Lifelines.** One per actor or column that the diagram uses: first the
play's `person`, `system` and `record` lines, then the net's
(`annotations.actors`), then the others in order of first appearance. A
`box` puts its members together at the place of the first one. A person is
drawn as a PlantUML `actor`, a record as a `database`, and any other
lifeline as a `participant`.

**PlantUML.** The output starts with `skinparam backgroundColor #FEFEFE` and
pins the text, line and box colors of participants, actors, databases,
notes, boxes, groups, dividers and delays, so that it reads on a dark page
too. It has the play's title (`title …`) and hides the footbox.
`--format json` emits the same view: `play`, `title`, `path`, `status`,
`lifelines` (`name`, `kind`), `boxes` (`title`, `lifelines`) and `events`,
each a `message` (`from`, `to`, `label`, `dashed`, `line`, and `matured: true`
when the firing that drew it was the clock's), a `note` (`actor`, `lines`,
`line`), an `activate` or `deactivate` (`actor`), a `group` (`text`) or
`end_group`, a `divider` or `delay` (`text`), or a
`failure` (`actor`, `label`, `code`, `message`, `line`, `detail`).

## Conformance

`spec/conformance/play/<case>/` holds `case.play`, the nets it names,
and `expected.trace.json`: one occurrence sequence per path, with for each
step its line,
kind, statement, engine records (no timestamps, which the engine takes from
the wall clock), checks and the marking after it, plus the path's failure.
Case `05-literal-start` covers a literal start: `marking none` plus leading
`inject` steps, including a kept record injected before the play's own steps.

## Not in version 1

- `run` steps, where the engine chooses the firings.
- Checking with real handlers, where a step's outputs become expectations.
- `advance until [t]` to the next timer maturity.
- A TypeScript checker.

## Turning records into a play

`velocitron.play.records_to_play(net, start, records, *, net_line, …)`
writes the `.play` source that replays a journal's recorded records, one
step per record: an injection of kind `inject` becomes an `inject` step,
of kind `update` an `update` step, and a completed firing a `fire` step
with `with` clauses pinning the recorded binding where a place holds more
tokens than it binds, and `->` clauses for the produce tokens the net does
not fill. A clock move is written as an `update`, the machine form: the
`update` statement carries no maturation (above), so the firings the move
matured are their own `fire` steps, in recorded order — the story picks
them, not the maturation (the mapping the prover's counterexample plays
write). A failed attempt is not an occurrence ([ADR 0059], item 4): it is
left out, kept only as a comment. The function is pure — it reads no file
and no clock — and it replays every record through the engine as it writes
it, so a play it returns passes `check_play` and its occurrence sequence
is the journal's record-for-record (ids, attempts and timestamps left
out). [ADR 0060]

[ADR 0024]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0024-views-are-applied-by-a-render-model.md
[ADR 0031]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0031-plays-check-firing-sequences-by-symbolic-firing.md
[ADR 0033]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0033-walkthrough-steps-draw-a-scope-as-twin-graphs.md
[ADR 0038]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0038-sequence-diagrams-project-plays-onto-actors.md
[ADR 0039]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0039-sequence-diagrams-draw-lived-places-as-columns.md
[ADR 0059]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0059-velocitron-spells-its-model-words-the-way-the-petri-net-books-do.md
[ADR 0060]: https://github.com/matthewryanscott/velocitron/blob/main/docs/adr/0060-advance-is-one-seam-and-tick-is-deleted.md
