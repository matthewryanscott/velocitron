# A place the net only counts keeps as many tokens as its readers count

**Status:** Accepted (2026-11-02, Ada: "merge and iterate"). Refines ADR 0036 (the soundness
exploration) and ADR 0050 (firing caps).

A loop that leaves a token behind on each turn never repeats a marking.
`fixtures/prove/redelivery.petrinet` is the smallest case: each send again
puts a try into `(tries)`, nothing takes a try, and `[escalate]` reads three
of them. Without a firing cap the exploration runs into the state cap, and
every soundness fact is `unknown`. Yet the net cannot tell four tries from
forty: every step that looks at `(tries)` only asks whether it holds three.

## Decision: a counted place keeps its largest read weight of equal tokens

A place is **counted** when:

- no arc takes from it (it has read or inhibit arcs only, at least one);
- none of those arcs has a predicate or a correlate, and no other reader
  sees a token's data: no correlate or timer names it in `binding`, no
  produce `data cel` reads it, and no handler output is built from it (the
  readers of ADR 0061, Decision 2, see nothing of its tokens);
- it is not open, final or kept.

Its **count** is its largest read weight, or 1 when it has only inhibit
arcs. In every marking the exploration keeps, a counted place that holds
more than its count of tokens, all equal, holds its count of them. Places
whose tokens differ keep every token.

`Explorer` and `explore` take `saturate=False` to explore without it, so
tests can compare both.

**Why the verdicts stay the same.** Call two markings partners when they
are equal outside the counted place `p` and `p` holds its count `k` or more
in both, or the same number below `k`.

- **Every arc test gives the same answer.** A read arc of weight `w ≤ k`
  needs `w` tokens, an inhibit arc none, and both see only how many there
  are, and no reader sees their data. So the same transitions are enabled
  with the same bindings (the bound tokens of `p` are equal), and the same
  outputs come out.
- **The partners stay partners.** No arc takes from `p`, so a move adds to
  both counts or to neither, and a count at `k` or more stays there. The
  environment never writes `p` (it is not open).
- **The facts read only what partners share.** "Finished" asks which final
  places hold tokens, and `p` is not final. Proper completion asks whether
  an instance place holds a token, and `p` holds one in both partners or in
  neither (`k ≥ 1`). No dead transitions reads the firings, which are the
  same. Option to complete reads net moves, stops and environment moves,
  which are the same from partners.

So partners are bisimilar, and keeping one of them keeps every verdict.

## Consequences

- `redelivery.petrinet` ends without a cap: 3 tries at most, the same
  verdicts as with `[redeliver]` capped at 3, and no cap to assume.
- A finding's marking shows a counted place with its count of tokens; it
  stands for that many or more. A counterexample play replays the path
  from the initial marking, so its `expect` lines count every token.
- A loop that leaves tokens a step reads by their data (a predicate, a
  correlate, a copied field) still never repeats, and still needs a firing
  cap (ADR 0050).
- Choice coverage and place invariants do not explore, so they do not
  change.
