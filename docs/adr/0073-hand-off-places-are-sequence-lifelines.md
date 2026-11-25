# Hand-off places are sequence lifelines

**Status:** Accepted (2026-11-25). Refines ADR 0038 and ADR 0039.

A sequence diagram projects a checked play onto its actors (ADR 0038) and
draws a lived place as a column (ADR 0039). A token that one actor produced
and another actor used later was not drawn when it was made. The diagram
drew one arrow at the moment the later actor consumed the token, and the
arrow carried the producer's title. Read top to bottom, the titles were out
of order. A timer made this common: a lease sits for many steps, and the
firing that ends it is drawn under the `advance` that matured it, so the
advance's title traveled with the tokens the firing produced.

The same merge of back-to-back clock moves kept the longer tick. `advance`
0, then 29, then 30 said 29 seconds, after 30 seconds had passed.

## Decision 1: a place a token crosses is a queue

A place is a hand-off place when, somewhere in the path, one actor produces
a token into it and a different actor consumes that token. The diagram
draws the place as a PlantUML `queue`. A place that only one actor uses
stays hidden, and so does a clock place. A lived place stays a column; it
is not also a queue.

The caption is the place's description. With none, it is `(place_id)`. The
queue sits immediately after the actor that first produces a token into it.

Making a token draws an arrow from the actor into the queue. Using it draws
an arrow from the queue to the actor. Both are drawn in the step that does
the moving. A token the same actor both produces and consumes draws
neither arrow, even when the place is a queue because some other token
crosses. A produce still draws when nothing later consumes the token. A
token with no producer — the starting marking, a clock, an untitled
injection into a place with no owner — draws no consume arrow.

There is no deferred label. The producer's title is not stored on the token
and replayed at the consume.

**Considered options:**

- Label the old actor-to-actor arrow with the consuming step's title, and
  keep the producer's title as a note where it happened. Rejected: the
  arrow still means "handed over for later", and a step fed by two actors
  says its title twice.
- Draw the arrow when the token is made, from the maker to the eventual
  user, and number the steps. Rejected: the arrow points at an actor who
  does nothing yet.
- A flag that falls back to the old labelling. Rejected for this record: a
  wide net can be revisited if the queues turn out to be the problem.

## Decision 2: a step's title appears once

The step's title is the label of its first arrow. When the step draws no
arrow, the title is a note, as before. Each other arrow of the step carries
the token's colour, the type string (`lease`, `job`). A read of a lived
place keeps the value read. A lived write keeps the step's title when it is
the first arrow, and carries the colour otherwise. A lived write with no
step label keeps the written place's description.

A firing a clock matures is labelled with its transition's summary, else
its description, plus `(on time)`. The `advance` step's title is not that
label. With no summary and no description, the arrow is bare.

## Decision 3: back-to-back moves of one clock show the total

Advances with nothing drawn between them are still one delay. When the next
move continues the clock reading the delay ended on, the delay shows the
sum. `advance` 0, then 29, then 30 reads `30 seconds later`. When the next
move does not continue that reading, the delay shows the longer of the two,
so two clocks advanced an hour at one moment still read `1 hour later`
once.

## Consequences

- The diagram reads in step order. A token that waits is a gap on the
  queue's line.
- A net with many crossings draws one column per crossing place. Places one
  actor uses do not.
- The projection stays Python only, as ADR 0038 left it.
