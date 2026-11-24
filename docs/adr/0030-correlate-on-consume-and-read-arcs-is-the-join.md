# `correlate` on consume and read arcs is the join

**Status:** Accepted. (Amends the scope of ADR 0017: `correlate` was valid
only on inhibit arcs. It is now valid on every input arc. The inhibit
semantics of ADR 0017 do not change.)

An inline `predicate cel` sees one token's `data` as bare fields (D6). A net
therefore had no declarative way to say "bind the branch-home record of THIS
hold's isbn" or "the shelf note for THIS title". The only way
was a named guard handler over the whole binding. Real nets then wrote
predicates such as `branch_home.confirmed == true` on an arc that carries a
`hold` token. That expression reads a field called `branch_home` of the
hold token: it is an eval error, so the predicate is false and the arc
never matches. The net parses, and the mistake shows up only at run time.

ADR 0017 rejected `correlate` on consume and read arcs with the words
"cross-token conditions over bound tokens are guard territory". This record
reverses that one sentence. A join over bound tokens is pure and structural,
like the anti-join, and the `{token, binding}` environment already names both
sides. A guard stays the place for impure or transition-wide logic.

## Decision 1: the same inscription and the same environment

A consume or read arc may carry `correlate: {cel: "<expr>"}`. For a candidate
binding B, the arc passes only if **every** token it binds makes the
expression exactly `true`, evaluated over:

- `token` — the data of that one bound token;
- `binding` — B as a map of source-place name → list of bound tokens' data,
  over every consume- and read-mode arc, the correlated arc's own tokens
  included. It is the ADR 0017 shape, and the guard's `inputTokens` shape
  projected to data.

With `weight: N` each of the N tokens is tested. The DSL fact is unchanged:
`@h correlate cel "..."` may target any one input arc (`->`, `->?`, `->0`); a
produce arc is still rejected (PN202).

**Considered options:**

- A new field name (`join`) for the positive case. Rejected: the environment,
  the compile rule and the failure posture are the same as the inhibit
  `correlate`; the arc's mode already says whether a match passes or blocks.
  Two names for one test would be two things to learn.
- Let `predicate cel` see `binding`. Rejected for the reason ADR 0017 gives:
  bare fields and a `binding` name in one environment are ambiguous, and
  detecting which one an expression means needs AST inspection across three
  CEL backends.
- Let a correlate see only the arcs declared before it. Rejected: the result
  would depend on arc order in the source, which authors do not think of as
  meaningful, and a join between two arcs would have to be written on the
  later one.

## Decision 2: evaluation order inside the one enumeration

The check is one more pure gate in the ADR 0027 binding walk. Per candidate
binding the order is:

1. sub-multiset validity (D1);
2. **consume/read correlates** — arcs in declaration order, each arc's
   tokens in bound order;
3. correlated inhibits (ADR 0017);
4. the timer (ADR 0018);
5. the guard, in the first-success consumer (ADR 0002, ADR 0027).

Single-token predicates run before all of these, when each arc's candidates
are built. Because `binding` is assembled before any correlate runs, the order
in step 2 decides only which failing check stops first, never whether the
binding survives. A rejected binding is skipped, not reordered, so
first-surviving selection and replay stay deterministic (D2, D5).

The enumeration names this rejection `correlate-miss`, next to
`correlated-inhibit`, in both implementations.

## Decision 3: errors and non-booleans fail closed

An eval error (a missing field, a type mismatch, a backend raise) or a
non-boolean result rejects the candidate binding. The join is unproven, so the
token may not be bound. This is D6's degrade-toward-not-enabled posture, and
it matches the correlated inhibit's fail-closed rule. It never crashes the
engine.

## Decision 4: a lint names the predicate mistake

`velocitron validate` runs the ADR 0016 lint surface on a net and prints each
finding as a warning on stderr; the exit code stays 0. A new rule,
`predicate-names-color-or-place`, flags an inline `predicate cel` that selects
a field of, or indexes, a name that is a color or a place of the net
(`branch_home.confirmed`, `loan.outcome` on a `loan` arc). The message says that
a predicate sees only its own token's fields as bare names and points to
`correlate cel`, or to the bare field when the name is the arc's own color.

The rule reads identifiers from the pure-Python celpy parse tree. celpy is a
core dependency, so the rule works whatever backend evaluates the net. Names
inside string literals and names bound by a comprehension macro are not
flagged. A bare name (`isbn == 'x'`) is not flagged, because a token
field may share a name with a color. It is suppressed by
`annotations.lint.suppress` on the transition, as ADR 0016 defines, or on
the flagged arc.

**Considered options:**

- Reject such predicates at parse. Rejected: a token may really have a field
  named like a color, and ADR 0016 keeps lint advisory.
- Flag every free name that matches a color or place. Rejected: bare fields
  that share a color's name are common in real nets (`isbn` on a
  hold token), and the mistake this rule targets is always a selection.

## Consequences

- A join is declarative and visible in the net, the viz and `explain`, so
  fewer nets need a named guard for key equality.
- `correlate` is drawn on a read or consume arc the way it is drawn on an
  inhibit arc, and `decorate @h summary` replaces it at `detail summary`.
- The cost of a join grows with the cartesian product, because the check runs
  per candidate binding after the product is formed. Nets with large places
  and several correlated arcs pay for every combination they try.
- `velocitron validate` now also prints `consume-without-produce` warnings
  for sink transitions, since it runs the whole lint surface.
- The schema change is a relaxation: every net that was valid stays valid and
  behaves the same.
