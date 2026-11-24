# Sequence diagrams project scenarios onto actors

**Status:** Accepted. Amended 2026-10-17 (Decision 2: only consumed tokens
trigger). Refined by [ADR 0039](0039-sequence-diagrams-draw-lived-places-as-columns.md)
(2026-10-17): lived places are columns, own steps are notes, and the
activation folding and self-arrows below are replaced. (The title keeps the
word `scenarios` this record was written with, 2026-10-17; the object it
names is the play of ADR 0059, renamed 2026-10-22 — the body's wording
tracks the rename, the title stays historical.)

A sequence diagram is the usual way to explain a process to people: who
does what, and who waits for whom. An evening shift reads "the clerk
closes the desk; a runner takes a hold; an hour later the clerk checks
the loan". Such diagrams are often drawn by hand next to the
design, and nothing tells the author when they stop matching the rules.

Velocitron already has the rules (the net) and an executable story (a
Play, ADR 0031). This record settles how a play becomes a sequence
diagram, so the diagram is a reduced view of a real firing sequence that the
checker proved against the net, and not a separate drawing. PlantUML is only
the output format.

The contracts are in [`packages/spec/petrinet-language.md`](../../packages/spec/petrinet-language.md)
("Actor facts") and [`packages/spec/play-language.md`](../../packages/spec/play-language.md)
("Sequence diagram").

## Decision 1: lifelines are actors, and an actor is a fact of the net

Who does a step is business meaning, so the net says it, not the diagram:

```text
person Clerk
system "Circulation desk"
net actor "Circulation desk"  // the default for this net's transitions
[close_desk] actor Clerk      // who fires the transition
(desk) actor Clerk            // who puts tokens into the place: its owner
```

`X actor Name` lowers to an ordinary annotation with the key `actor`, the
way `fusion` and `lint` are annotation keys with a known meaning. The engine
ignores it (ADR 0011), and the composition merge already carries place and
transition annotations. `person` and `system` lower to a new IR kind,
`actor.declare`, and resolve to the net annotation `actors`, a list in
declaration order: the lifeline order and each actor's kind.

Actors survive composition. The merge gives each transition without an
actor its constituent's default actor, and lists every constituent's
declared actors in the merged net. So one actor (an operator, a platform)
can span several nets, and a refining net's transitions keep their own
actors. A play may declare `person` and `system` lines too; they come
first in the lifeline order.

**Considered options:**

- A `decorate [t] actor` decoration. Rejected: decorations are presentation
  only and belong to no business rule; who acts is part of the model, and a
  composition should carry it.
- Actors only in the play. Rejected: every play of a net would
  repeat the same mapping, and the net's own documentation would not say
  who does what.
- A core JSON member, like `domains`. Rejected for now: the engine does not
  use actors, and an annotation key needs no schema change in either
  implementation. It can move to a member if the engine ever needs it.
- `actor Name person` as the declaration. Rejected: the grammar ignores
  line breaks, so `[t]` on one line and `actor Name` on the next would read
  as one `[t] actor Name` fact. `person` and `system` start no other
  statement.

## Decision 2: arrows are hand-offs, found by causality

The projection plays nothing: it reads the checked trace. Each token
remembers the step that produced it (a firing by its actor, or an injection
by the place's owner). A firing's sources are the producers of the tokens
it consumed or read. A source of another actor is a hand-off, and only a
hand-off draws an arrow. Consecutive steps of one actor with no hand-off
between them fold into one activation, drawn as one arrow with one line per
step.

The arrow comes from the latest hand-off source (amended below: the latest
source of a consumed token). Earlier sources are dashed
arrows labeled with the place their tokens came through: the runner
takes the hold because the desk set a shelf slot, but the runner also read
the clerk's note that the desk is closed.

**Considered options:**

- Arrows between consecutive steps of different actors. Rejected: adjacency
  is the author's ordering, not a dependency. In the evening shift the
  union catalog notes the copy between the clerk closing the desk and the
  runner taking the hold, but the clerk hands nothing to the catalog.
- One arrow per consumed token. Rejected: it repeats arrows for each token
  of one hand-off and hides the step that did the work.

### Amendment (2026-10-17): only consumed tokens trigger

On a real evening shift, the rule above drew the wrong cause. The runner
consumes its own shelf slot and reads the closed-desk note that the clerk
set an hour earlier. The latest hand-off source was the clerk, so the
diagram drew a solid arrow "Clerk → Runner: the runner takes the hold". It
reads as "the clerk told the runner to take it", which is false. A read arc
tests a long-lived record; it does not start the step.

So now only the producer of a consumed token can be the trigger: the latest
such source of another actor. A source that the step only read from is
always a dashed arrow labeled with its places. When no consumed token comes
from another actor, the solid arrow is the actor's arrow to itself.

A read-only hand-off still starts a new activation, the same as a consumed
one. Then its dashed arrow sits directly before the step it informs. If the
step joined the open activation instead, the dashed arrow would have to go
before the whole activation, next to steps it has nothing to do with.

**Considered option:** fold a read-only hand-off into the open activation
of the same actor. Rejected for the reason above. The cost is an extra
self-arrow when an actor's previous step and this one are consecutive (in
the evening shift: "Shelf slot 1", then "the runner takes the evening hold").

The same amendment drops the delay for a clock's first advance. With no earlier
`now` there is no time span to show, and "the clock reads 0" only set the
stage.

## Decision 3: labels come from the play first

A step's label is its title, then the transition's `summary` decoration,
then its `description`, then its humanized name. Play titles are the
business words for one story; the net's descriptions are the general ones.
An `advance` becomes a delay (`...1 hour 30 minutes later...`), a Markdown
heading in a step's prose becomes a divider, other prose is left out, and an
`expect` shows only when it fails, as a red note. Initial-marking tokens
have no producer, so a step that uses only them starts its actor's
activation with an arrow to itself.

## Decision 4: a sequence view is an option of the play

`show sequence` puts the diagram before a path's walkthrough, and
`show sequence only` draws it in place of the step graphs. Before any
`path` line the setting applies to every path; after one, to that path. An
unquoted `sequence` after `show` was a color name before; a color named
`sequence` is now written quoted. `velocitron play walk --sequence` and
the Obsidian plugin's `sequence=` fence option override the setting, the way
`--scope` and `scope=` override `scope`. `velocitron play sequence`
prints the PlantUML (or the projection as JSON) for GitHub, where the team's
browser extension renders PlantUML fences.

The PlantUML output pins its background (`#FEFEFE`) and its text, line and
box colors, so it reads on a dark page. A person is a PlantUML `actor`;
any other actor is a `participant`.

## Consequences

- A net change that breaks the story fails the play check, so a
  diagram cannot drift from the rules it shows.
- The diagram is as good as the actor facts and the step titles. A net
  without actors draws one lifeline (or one per composed net), which is
  still a valid, if dull, projection.
- The projection is Python only, like the checker. The TypeScript side parses
  and lowers the actor facts and carries them through its merge, with
  conformance case 24 pinning both.
- Deferred: notes from ordinary prose, grouping a branch's alternative steps
  in one diagram (`alt` blocks), and arrows for tokens a path leaves behind.
