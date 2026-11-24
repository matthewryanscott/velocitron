# A kept record is there from the start, and only the net writes it

**Status:** Accepted (2026-10-19). Refines ADR 0036 (the environment model
and the soundness facts), ADR 0040 (shares) and ADR 0047 (records the
outside world keeps).

The circulation desk keeps one record of a copy's condition for each hold.
The record starts undamaged. The desk's own steps read it and
write it back: they take it and give it again. Nobody outside the circulation
desk writes it. `velocitron prove` had no good way to say "a record this
system keeps, there from the start, clean":

- **As a token in the initial marking**, proper completion counted it as
  work that the instance left behind, so it was refuted. Its isbn was
  a literal (`"9780306406157"`), and the check gives its instance an isbn
  of its own (`own-isbn`). The steps that correlate the record with
  the hold on the isbn never fired.
- **As a fused place**, the environment supplied it. The check put it into
  the net at any moment, with any value of its domains and at any time.
  That multiplies the states: a check of the evening shift that ended at
  344 000 states before passed 1 500 000.

ADR 0047 covers records that the outside world keeps and changes at any
time. This record is the opposite: the system keeps it, and only the
system's own steps change it.

## Decision 1: a place fact says that the net keeps the record, and how it starts

```text
system "circulation desk"
(condition) kept by "circulation desk" starts as cel
    "{'isbn': instance.isbn, 'damaged': false}"
```

(The fact is one line in a `.petrinet` file.)

`kept by NAME` names who keeps the record, in the words of the actor facts
(ADR 0038). `starts as cel` gives the start value: a CEL map of the record's
fields. It may read one name, `instance`, the data of the instance token
that a check or a story follows. A kept record is a **kept place**. The
fact lowers to the place annotation `kept: {"by": NAME, "start": {"cel":
"…"}}`, as `lives in` lowers to `lives`. The engine ignores it, and the
merge carries it.

## Decision 2: the prover starts with the record and never lets the environment write it

- **Start.** The exploration starts with one token in each kept place: the
  start value, built against the check's instance token. That token takes
  its own value for each key, ordered and free field (`own-isbn`), as
  the start token does, so a step that correlates the record with the
  instance on the isbn can fire. A field that the start copies from
  the instance joins the instance's field, so both get the same domain.
- **No arrivals or updates.** A kept place is never open: not a start
  place, a fact, a resource, a record (ADR 0047) or a clock, whatever
  produces into it, fuses it or shares it. A domains file that names it
  under `injections` or `updates` is an error.
- **Not instance work.** A kept place is never an instance place, a sink or
  a final place. Proper completion does not look at it, and a final marking
  is reached whatever it holds. A `final` fact or domains file that names it
  is an error.
- **Not a choice.** Several steps that take the record and give it back
  rewrite it; they do not choose between themselves by it. Choice coverage
  skips a kept place, as it skips a resource.
- **Domains still apply.** The values that the net writes into the record
  come from the arcs' `data cel`, as before. A start that breaks a declared
  domain is an error. The report lists kept places under `roles.kept`. A
  place invariant counts the start token in the initial marking.

## Decision 3: `velocitron validate` checks a kept place

It is an error when a kept place:

- has `annotation fusion true`, is a port, or lives in a `record` column
  (the outside world supplies those places);
- has tokens in the initial marking;
- accepts more than one color;
- has a start that is not a map with literal keys, that reads a name other
  than `instance`, that leaves out or breaks a declared domain of the
  record's color, or that leaves out a field that the net reads from the
  place.

In a composition, each net's kept places are checked in that net, and a
share that joins a kept place must join only places that are kept the
same way (the same `by` and the same start). A kept place cannot be a
port, so a wire never joins one.

## Decision 4: a story starts with the record when it can build it

A play starts with each kept record whose start reads no `instance`.
A start that reads `instance` needs the story's instance:

```text
instance $u1
```

The `instance` setting names a token (a template or a literal). The story
then starts with the record built from that token's data, as prove does.
A story that names no instance starts without that record, so a story
that injects the record itself keeps working. Injecting into a kept place
that already holds its record is an error that says to use `update`. A
start that cannot be built from the instance is an `SC215` error. A
counterexample that `prove` writes has an `instance` line, so the story
starts from the same record as the check.

## Considered options

- **A token in the initial marking.** It is already in the language, but
  the token is instance work for proper completion, and its literal values
  do not match the instance the check invents.
- **A fused or open place that the environment supplies.** It matches the
  instance, but the record can arrive at any moment with any value. The
  state space grows, and the check tries starts that never happen.
- **A record column (ADR 0047).** It says the opposite: the outside world
  keeps the record and changes it at any time.
- **Pin the record's fields in the domains file.** The check still injects
  the record at any moment, and the pins also hide states the net reaches
  (a pinned `damaged: [false]` hides the damaged copy the desk records).
- **A start in the domains file.** Rejected for the reason ADR 0040 and ADR
  0047 give: it moves a fact about the net into a file next to it.
- **Seed every story with the record.** A story has no instance to build
  it from, and the existing stories inject the record themselves.

## Consequences

- The circulation desk can keep its condition record without
  a domains file. The evening-shift check no longer tries every arrival time and
  value of the record.
- A check follows one instance, so a kept record always starts undamaged in
  it. A step that needs an earlier history of the record (damage from
  earlier loans of the same title) is dead unless the net can reach
  that history in one instance.
- A lock that the system keeps (the shelf slot: one loan at a time per
  home branch) can be a kept place too. The check then no longer explores a
  lock that another instance frees later.
- The TypeScript implementation parses the fact and gives the same JSON;
  like `prove` and `play check`, the checks of Decision 3 are in the
  Python implementation only.
- The contract is in [`packages/spec/proofs.md`](../../packages/spec/proofs.md) ("Roles of
  places"), [`packages/spec/petrinet-language.md`](../../packages/spec/petrinet-language.md)
  ("Kept records") and
  [`packages/spec/play-language.md`](../../packages/spec/play-language.md).
