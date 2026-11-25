# A layout fact has to be one a renderer can ignore, and DOT order follows the net

**Status:** Accepted (2026-11-25). Amends ADR 0029 (which copy sits nearest
a transition) and ADR 0035 (the order of a sibling group).

Graphviz is one renderer behind the render model (ADR 0024). A view fact
should say what the author means, not which engine knob to turn. ADR 0025
Decision 5 already limits additive v1 metadata: both implementations move
together, and the metadata stays something a consumer can ignore. The same
limit applies to layout.

## Decision 1: the test for a layout fact

A fact goes into the language only if both of these hold:

1. At least two unrelated layout families can honor it. Graphviz `dot`,
   ELK layered, dagre or Mermaid, D2, and a hand-placed SVG are the kinds
   of family that count.
2. A renderer that cannot honor the fact can ignore it and still draw a
   correct net.

A fact that fails the test stays out of the language. An engine knob that a
particular drawing really needs belongs in a renderer escape hatch outside
the source, not in a view fact.

**Rejected under this test:**

- Rank hints (`same rank`, minimum, maximum). That is Sugiyama and `dot`
  layering. ELK has rough equivalents that mean different things, and most
  other engines have none.
- Edge weights. Each engine reads a weight differently (`dot`'s `weight`,
  ELK's priorities), so the same number gives different drawings.

**Accepted, and not implemented by this record:**

- Flow direction, one fact per view: `down`, `right`, `up`, or `left`.
  Every layered engine has a main direction. A force-directed engine ignores
  it and the net is still correct. It describes how to read the net. The
  existing CLI direction flag still wins over the view fact. With
  `--no-view` the CLI default applies.
- Authored groups and lanes: named containment, view-independent in the way
  `decorate` is (ADR 0028), so a group shows in every view and under
  `--no-view`. A lane asks for a band instead of a box. Lanes are authored.
  They are not derived from `actors`. A renderer maps a group to whatever
  containment it has, and a renderer without containment ignores the group
  and still draws the net.

## Decision 2: DOT emission order comes from the net

Node and arc statements are ordered from the net's structure, not from
declaration order. The order is a walk from the initial marking:

- Rank 0 is a place that holds a token in the initial marking, a place
  nothing produces, or a transition with no input.
- Every other node is one step farther than the nearest of those, along
  consume, read, inhibit, and produce arcs.
- A component with none of those starts is walked from its alphabetically
  first node and ranked after everything already reached.
- The same rank is tied by name.

Places, transitions, fusion copies, arcs, beside rows, and the ports of a
composition diagram all use that order. Overview edges and composition wires
are sorted by the statement text, so their order does not follow the source
either. `arc_lines` still maps each arc's declaration index to its edge
line (ADR 0024): a view routes the arc the handle names, whatever order the
statement was emitted in.

The order is taken from the net's initial marking, not from the marking a
particular drawing shows. A walkthrough's two halves of one step stay the
same graph.

This replaces two places that used to follow the source. ADR 0029's nearest
beside copy is the first in this order. ADR 0035's sibling group is listed
in this order, and pairing from the left of the group is unchanged. Authors
do not pick pairs by arranging lines.

Both emitters follow it: the Python CLI (`velocitron-viz` and the net bodies
it draws) and `netToDot` in the TypeScript package (ADR 0025 Decision 5).

## Consequences

- Reordering the declarations of a net does not change its DOT. Existing
  drawings move once, because the old pictures followed source order.
- A renderer other than `dot` can use the same order as a deterministic
  tie-break and can ignore a flow fact or a group it cannot draw.
- Rank hints and edge weights are not part of the language.
