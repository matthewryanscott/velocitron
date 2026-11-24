# Decorations are view-independent presentation facts drawn inside labels

**Status:** Accepted.

ADR 0024 left decorations (labels, colors, highlights) for later, to ride the
render model "when their channel decision lands". ADR 0025 fixed the channel
for presentation facts: the compiler-owned payload
`annotations["petrinet.dsl/v1"]`, extended additively. This record settles the
decoration vocabulary, where it lives in that payload, and how a renderer
draws it.

## Decision 1: `decorate` facts, stored beside views, not inside them

The language gains one statement family:

```text
decorate (Place)|[Transition]|@Handle highlight [ "label" ]
decorate (Place)|[Transition]|@Handle note "text"
decorate [Transition]|@Handle summary "text"
decorate color Color quiet
```

They lower to the closed IR kinds `decoration.highlight`, `decoration.note`,
`decoration.summary` and `decoration.quiet`, and resolve into an optional
payload member `decorations`, keyed by `place:`, `transition:`, `arc:` and
`color:` subjects.

**Considered options:**

- Decorations as members of a view (`view v highlight [t]`). Rejected: the
  facts that prompted this work mark an element itself, for example "changed
  in round R2.11". They must show in every render, including `--no-view`, and
  repeating them per view would make the author keep copies in step.
- Ordinary element annotations (`[t] annotation highlight "R2.11"`). Rejected
  for the reason ADR 0025 Decision 1 gives: annotations are freeform and
  merge-propagated, so one presentation fact would have two homes and no
  shape check.
- A top-level `decorations` member (chosen). It is optional, so documents
  without decorations keep their exact payload.

Arc decorations stay handle-keyed (ADR 0025 Decision 4) and use the same
"exactly one arc" rule as routes.

## Decision 2: notes and highlight labels are lines inside the label

A note and a highlight label are drawn as extra small lines inside the node or
edge label: the highlight label in bold amber, the note in italic teal.

**Considered options:**

- Graphviz `xlabel`. Rejected: Graphviz places external labels after layout,
  so they can overlap other nodes, and it may move or drop them. The text the
  author asked for would then be missing with no sign of it.
- A separate note node joined by a dotted edge. Rejected: the extra node takes
  part in layout and moves the nodes around it, and it would need its own
  position in every view.
- Lines inside the label (chosen). The layout engine sizes the node or edge
  label to fit the text, so nothing overlaps and nothing is lost. Pinned
  nodes keep their positions; only the decorated label grows.

A highlighted node fills `#FFE08A` with an amber border; a highlighted arc
draws with an amber, wider pen. The highlight styles override port tints and
the guard border, because a highlight is the author's explicit request for
attention.

## Decision 3: `summary` belongs to the detail levels

`summary` text shows only at the `summary` detail level, where it replaces a
transition's guard and timer, or an arc's predicate, correlation, or data
template. Without an authored summary, that level cuts each expression to one
line. `full` never shows the summary, and `structure` hides the expression and
the summary alike. A place has no expression to summarize, so the language
rejects a place summary.

## Decision 4: `quiet` is a color fact, also available as a flag

`decorate color C quiet` hides the type label on consume and produce arcs of
color `C`, as the renderer always does for the Generic `token` color. Read and
inhibit arcs keep their labels, because there the label carries the arc's
mode. A source-level fact lets a Markdown fence render without flags;
`velocitron-viz --quiet-color C` does the same for a single render.

## Consequences

- Both implementations, the IR schema, the payload validator, emission, and a
  `19-decorations` conformance case move in lockstep, per ADR 0025 Decision 5.
- Decorations stay inert: no engine, property, or composition code reads them.
- Composition renders draw no decorations, as they draw no views.
