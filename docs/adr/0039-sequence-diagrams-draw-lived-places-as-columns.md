# Sequence diagrams draw lived places as columns

**Status:** Accepted (2026-10-17). Refines ADR 0038: replaces its activation
folding, self-arrows and place-named context arrows. Amended 2026-10-17
(Decision 1: an unlabeled write-back draws the read).

ADR 0038 projects a checked play path onto its actors. On the first real
evening shift the result was correct but hard to read. Each actor's own
steps were arrows to itself, so the page was full of loops. A read of the
branch-home record was a dashed arrow from the Clerk, labeled "the title's
home branch", although the clerk recorded it an hour earlier and the reader
cares about its value. The hold the circulation desk placed for the annex
had no column to land on. A hand-drawn version of the same story was much
clearer: the branch-home record and the annex shelf were columns of their
own, arrows went into and out of them, and each arrow said what changed
hands.

This record moves the projection towards that drawing. The contracts are in
[`packages/spec/petrinet-language.md`](../../packages/spec/petrinet-language.md) ("Actor
facts") and [`packages/spec/play-language.md`](../../packages/spec/play-language.md)
("Sequence diagram").

## Decision 1: a place can live on a column

Some places are not hand-offs between two actors. They are records that
stay: a branch-home record, a copy on a shelf, the union catalog's note
that a copy was shelved or is missing. The net says where such a place lives:

```text
record "Branch home"
(branch_home) lives in "Branch home"
(loaned) lives in cel "token.branch"
```

`lives in Name` names a fixed lifeline. `lives in cel "…"` computes it from
the token, so one place can draw on many columns (each home branch, main or
annex, is its own shelf). `record` is a third actor kind beside `person` and
`system`, drawn as a PlantUML `database`. A column that is not declared is a
`system`.

Writing into a lived place (a firing that produces into it, or an `inject`
or `update` after the first firing) is an arrow from the writer into the
column, labeled with the step's label. Reading or consuming from it is a
dashed arrow out of the column, labeled with the value read. A step that
writes back into the column it reads (the clerk recording a new home
branch) draws only the
write. Injections before the first firing set up the starting state and draw
nothing; the first read shows the value.

**Syntax.** Both facts are place facts in the form of `(p) actor Name`: a
keyword phrase after the place. `lives in` reads as English, and `cel
"…"` is the form the language already uses for computed values (`predicate
cel`, `data cel`). A second keyword (`lives at`) for the computed form was
rejected: one meaning should have one spelling. Like `actor`, the facts
lower to place annotations (`lives`, and `reads_as` as `{"cel": "…"}`), so
the engine ignores them and the composition merge carries them, a fused
place by its member precedence.

**Considered options:**

- Columns declared in the play. Rejected: every play of a net would
  repeat them, and where a record lives is a fact about the net.
- One fact per step (`fire [t] -> "Partner library"`). Rejected: the same place is
  written and read by many steps; one fact per place says it once.
- Treat a lived place as an actor that owns its tokens, so the existing
  hand-off rule draws it. Rejected: a column never acts, and a hand-off
  label ("what the producer did") is the wrong label for a read.

## Decision 2: a read is labeled with the value read

`(p) reads as cel "…"` computes a short string from the token a reader sees:

```text
(branch_home) reads as cel "token.isbn + (token.confirmed ? ' confirmed at ' : ' waiting at ') + token.branch"
```

Without it, or when the expression fails, the label is the place's
description, then its humanized name. A failing expression in a
presentation fact never fails a path that the checker passed.

## Decision 3: arrows say what was handed over; own steps are notes

A hand-off arrow (a token another actor produced, not in a lived place) is
labeled with what was handed over: the producer's step title, else the
value of the place it came through (as for a read). A consumed hand-off is a
solid arrow and starts a new activation; a read one is dashed and does not.
So "Copy shelved" is an arrow from the union catalog, and the desk's
reads of the shelf note and the branch-home record sit inside the same activation.

There are no self-arrows. An actor's own titled step that writes to no
lived place is a line in a note beside it; consecutive notes of one actor
join. A step without a title draws nothing of its own: it still runs and is
checked, and its reads and writes are still drawn. A titled step whose
output is later handed over is drawn as that arrow's label, not also as a
note. Consecutive writes of one activation into one column fold into one
arrow. An activation bar is drawn on the receiver of a consumed hand-off
while its activation includes an outgoing arrow.

**Considered option:** keep the folded self-arrow of ADR 0038 and add the
columns. Rejected: a loop on a lifeline reads as a message to oneself, and
the hand-drawn diagram used notes for exactly these steps.

## Decision 4: groups, boxes, title

A `### heading` in a step's prose opens a PlantUML `group` around the
following steps, until the next heading or the path's end; other headings
stay dividers. A play line `box "circulation desk" Runner "Union catalog"` draws those
lifelines together in a titled box, in the line's order, where its first
member would be. The diagram carries the play's title. Advances with
nothing drawn between them are one delay, the longest advance, so a story
that advances two clocks at one moment reads "1 hour later" once.

The JSON form (`--format json`) carries the same view: `title`, `boxes`,
and events `message`, `note`, `activate`, `deactivate`, `group`,
`end_group`, `divider`, `delay` and `failure`. The `activation` event of
ADR 0038 is gone.

## Consequences

- A diagram is as good as its facts. A net without `lives` facts still
  draws every hand-off, now as labeled arrows and notes; adding a few
  `lives` and `reads as` facts turns records into columns.

### Amendment (2026-10-17): an unlabeled write-back draws the read

The hold's happy path drew the partner loan wrong. The circulation
desk's `[borrow]` ("request the loan") writes the loan's outcome into
the partner-library column. Then `[mark_loaned]`, with no title, summary or
description, consumes that outcome and writes the loaned copy into the
same column. Decision 1 says a step that writes into the column it reads
draws only the write. So the read "request returned" was dropped, the two
writes became neighbors, and they folded into one arrow "request the loan\nMark
loaned". The second line is the transition's name, which no author
wrote. A hold kept on the home shelf drew well, because `[wait]`
writes nothing back into the shelf column.

The read rule itself was right. A read from a column is drawn whoever wrote
the token, the reader's own actor included: the column is the source, not
the actor. Only the write-back rule hid it.

So the write-back rule now depends on whether the step has an authored
label: its title, its transition's `summary`, or its `description`.

- **With an authored label**, a step that writes into the column it reads
  draws only the write, as before. Recording a new home branch says what the
  clerk did; the old branch adds nothing.
- **Without one**, it draws only the read. The value it saw tells the
  story ("request returned"), and the write has no text worth drawing.

A firing without an authored label that writes into a column it did not
read is labeled with the written place's description, else the arrow has
no text. The transition's name is never an arrow label; it stays only in a
failure note, which must name the step. Folding skips a write without text,
and a read between two writes keeps them apart. The happy path now draws
"request the loan", then a dashed "request returned" from the partner library.

**Considered options:**

- Draw both the read and the write for every write-back. Rejected: recording
  a new home branch would draw the old branch and then the new one, which is the
  noise Decision 1 removed.
- Keep the rule and stop folding across a skipped read. Rejected: the read
  would still be missing, and an unlabeled write would still say "Mark
  loaned".
- Use the step's title alone as the test. Rejected: an untitled step whose
  transition has a description (the evening-shift fixture's `[close_desk]`)
  must still draw as a write.

Both evening shifts draw as before. Their write-backs have titles.
- Step titles now decide what is drawn: a title is a note or an arrow
  label, and a step without one is silent. Authors drop titles from
  bookkeeping steps instead of drawing them.
- The TypeScript side parses, lowers and resolves the new facts and the
  `record` kind, with conformance case 25 pinning both implementations.
  The projection stays Python only.
