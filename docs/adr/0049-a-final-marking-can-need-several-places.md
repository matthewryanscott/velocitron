# A final marking can need several places, and a composition can say where it finishes

**Status:** Accepted (2026-10-17). Refines ADR 0036 (option to complete and
proper completion) and ADR 0037 (the `final` fact and how a merge keeps it).

A `final` fact named a set of places, and the instance was finished as soon
as any one of them held a token. That cannot say where a run finishes when
it follows two things at once. The evening shift follows the circulation
desk's loan and the union catalog's shelf together. It is finished only when both
are done: the hold is loaned, recalled, given up, or withdrawn by a newer
edition, and the catalog has shelved the copy or found it missing (and, when
the copy was both loaned and shelved, a clerk compared the two records).
`velocitron prove` reported three false findings
on it:

- **Improper completion.** The loan reached a final place while the catalog's
  copy was still in `shelved`, so the instance was "finished" with a
  token left behind.
- **A deadlock in a place that is an end.** `checkout.loaned` is final in
  the checkout lifecycle. In the evening shift the union catalog reads it to compare
  the records, so the merge dropped it from the final places (ADR 0037), and a
  loaned hold became a deadlock.
- **A deadlock in the catalog alone.** The catalog's copy waits in
  `shelved` for the comparison, and nothing in the catalog said that
  this is one of its ends.

A second problem is where to say it. Neither the lifecycle nor the catalog
can name the other's places, and a composition had no facts of its own.

## Decision 1: a final marking is a set of places that must all hold a token

`+` joins the places of one final marking; commas still separate the final
markings:

```text
final (recalled), (loaned) + (shelved)
```

A marking reaches a final marking when every place of that final marking
holds a token. A final marking of one place is the old final place, so every
existing `final` fact keeps its meaning. The **final places** are the places
of all final markings. They are never instance places, so proper completion
checks the places outside every final marking.

In JSON, `proofs.final` keeps one entry per final marking: a string for one
place, an array of two or more places otherwise:

```json
"final": ["recalled", ["loaned", "shelved"]]
```

The Contribution IR keeps one `proof.final` contribution per final marking:
the target is its first place, and `with` lists the others.

## Decision 2: a composition can declare its own final markings

```text
final lifecycle.(checkout.loaned) + catalog.(shelved),
  lifecycle.(checkout.recalled) + catalog.(missing)
```

A composition's `final` fact names places as a `share` does: `alias.(place)`,
or `alias.(inner.place)` inside a used composition. It lowers to the
composition's `final` member, a list of final markings, each a list of
`{net, place}` endpoints.

When a composition declares `final`, its final markings are the only final
markings of the merged net: they replace every final fact of its nets, and
they are kept even when an arc of the merged net reads their places. The
composition says where the whole run finishes, so the ADR 0037 rule (a final
place that the next net reads is not final) does not apply to them. Without
a composition `final`, the merge keeps its nets' final markings as before,
dropping a marking when an arc of the merged net reads or takes from one of
its places.

A composition used inside another one does not pass its own `final` up. The
outer composition says where it finishes, or the nets' own final facts apply.
The evening shift shows why: the checkout lifecycle's ends are not the
shift's ends once the catalog's side is joined to it.

## Consequences

- The evening-shift nets prove sound with the business rules unchanged. Only
  `final` facts change.
- `velocitron equiv` compares final markings too: a place is final when it
  is a final marking by itself, and the final markings of more than one place
  are one more fact. A composition that declares `final` is therefore not
  equivalent to the same composition without it.
- The schema no longer marks the entries of `proofs.final` unique: an array
  entry would need deep comparison in the generated TypeScript validators.
  The DSL still rejects a repeated final marking.
- The prover's report keeps `final` as the sorted list of final places.
