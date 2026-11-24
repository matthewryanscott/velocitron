"""Project a checked play path onto a sequence diagram.

The diagram is a reduced view of the path's firings, not a separate model.
Each step belongs to an actor: a transition's ``actor`` annotation (or its
net's default actor), and for an injection the ``actor`` of the place it
fills, the place's owner. A place that ``lives`` on a column (a record such
as a branch home, or a slip on a shelf) is drawn as that column: a step
that writes into it draws an arrow into the column, and a step that reads
or consumes from it draws a dashed arrow out of it, labeled with the value
read. Every other token remembers the step that produced it; a token of
another actor is a hand-off, drawn as an arrow labeled with what was handed
over. Tokens of the starting marking, of a clock place, and of an untitled
injection into a place with no owner have no producer: they draw no
hand-off when consumed or read. A consumed hand-off starts a new activation; the actor's own titled
steps that write to no column are a note beside it.

A ``advance`` is a delay (a clock's first advance draws nothing, and ticks with no
step between them draw one), the firings it matures draw after that delay,
under their transitions' actors and marked ``(on time)``, a ``### heading`` in a
step's prose opens a group, any other heading is a divider, and an ``expect``
shows only when it fails.

:func:`sequence_view` builds the projection; :func:`render_plantuml` draws
it. PlantUML is one rendering of the view, chosen because GitHub and the
Obsidian plugin both draw it.

References: spec/play-language.md; ADR 0038.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

from velocitron_cel import get_default_adapter
from velocitron_engine import Net, Place, Token
from velocitron_play import ActorKind, FireBody, InjectBody, Step, UpdateBody

from .check import PlayTrace, StepFailure, StepResult

OUTSIDE = "Outside"
"""The lifeline of titled injections into a place with no owner: an event an
author shows on purpose. An untitled injection there draws nothing."""

SequenceFormat = Literal["plantuml", "json"]


@dataclass(frozen=True)
class Lifeline:
    name: str
    kind: ActorKind


@dataclass(frozen=True)
class Box:
    """Lifelines drawn together under a title, in the play's ``box`` line order."""

    title: str
    lifelines: tuple[str, ...]


@dataclass(frozen=True)
class Message:
    """An arrow. Dashed when the target only read what it carries.
    ``matured`` marks the outward arrows of a firing the clock matured."""

    source: str
    target: str
    label: str
    dashed: bool
    line: int
    matured: bool = False


@dataclass(frozen=True)
class Note:
    """An actor's own titled steps, one line each."""

    actor: str
    lines: tuple[str, ...]
    line: int
    steps: tuple[int, ...] = field(default=(), compare=False, repr=False)
    """The index of each line's step in the path."""


@dataclass(frozen=True)
class Activate:
    actor: str


@dataclass(frozen=True)
class Deactivate:
    actor: str


@dataclass(frozen=True)
class GroupOpen:
    text: str


@dataclass(frozen=True)
class GroupClose:
    pass


@dataclass(frozen=True)
class Divider:
    text: str


@dataclass(frozen=True)
class Delay:
    text: str


@dataclass(frozen=True)
class Failure:
    """The step a failing path stopped at; ``actor`` is None for an expect."""

    actor: str | None
    label: str
    message: str
    code: str
    line: int
    detail: str | None = None


SequenceEvent = (
    Message
    | Note
    | Activate
    | Deactivate
    | GroupOpen
    | GroupClose
    | Divider
    | Delay
    | Failure
)


@dataclass(frozen=True)
class SequenceView:
    play: str
    path: str
    status: str
    lifelines: tuple[Lifeline, ...]
    events: tuple[SequenceEvent, ...] = field(default=())
    title: str | None = None
    boxes: tuple[Box, ...] = ()


# ── Actors and columns ───────────────────────────────────────────────────


def _actor_annotation(annotations: Mapping[str, Any] | None) -> str | None:
    actor = (annotations or {}).get("actor")
    return actor if isinstance(actor, str) and actor else None


def _cel_annotation(value: Any) -> str | None:
    """The expression of an ``{"cel": "..."}`` annotation value."""
    if isinstance(value, Mapping):
        expression = cast(Mapping[str, Any], value).get("cel")
        if isinstance(expression, str):
            return expression
    return None


def _cel_text(expression: str, token: Token) -> str | None:
    """A CEL expression over ``token``, as text; None when it fails."""
    adapter = get_default_adapter()
    try:
        value = adapter.eval(adapter.compile(expression), {"token": token.data})
    # A bad expression in a presentation fact falls back to the place's
    # label; it must not fail a path the checker already passed.
    except Exception:  # noqa: BLE001 - any compile or eval error => fallback
        return None
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value)


class _Actors:
    """Who does each step, where each place lives, and the lifeline order."""

    def __init__(self, trace: PlayTrace) -> None:
        subject = trace.subject
        self.net: Net = subject.net
        self.composed = subject.composed
        self.transitions = {t.name: t for t in self.net.transitions}
        self.places = {p.name: p for p in self.net.places}
        self.place_names = subject.place_names
        # A merge fills each constituent's default into its transitions, so
        # only a single net has a default left to apply here.
        self.default = _actor_annotation(self.net.annotations)
        self.declared: dict[str, ActorKind] = {}
        for actor in trace.play.actors:
            self.declared.setdefault(actor.name, actor.kind)
        raw = (self.net.annotations or {}).get("actors")
        for entry in cast(list[Any], raw) if isinstance(raw, list) else []:
            if not isinstance(entry, Mapping):
                continue
            fields = cast(Mapping[str, Any], entry)
            name = fields.get("name")
            if isinstance(name, str):
                kind = fields.get("kind")
                self.declared.setdefault(
                    name, kind if kind in ("person", "record") else "system"
                )

    def place(self, name: str) -> Place | None:
        return self.places.get(self.place_names.get(name, name))

    def of_transition(self, name: str) -> str:
        transition = self.transitions.get(name)
        actor = _actor_annotation(transition.annotations if transition else None)
        if actor is not None:
            return actor
        if self.default is not None:
            return self.default
        if self.composed and "." in name:
            return name.split(".", 1)[0]
        return self.net.name

    def owner(self, place: str) -> str:
        found = self.place(place)
        return _actor_annotation(found.annotations if found else None) or OUTSIDE

    def lives(self, place: str) -> bool:
        found = self.place(place)
        return found is not None and "lives" in (found.annotations or {})

    def column(self, place: str, token: Token) -> str:
        """The lifeline a token of a lived place is drawn on."""
        found = self.place(place)
        lives = (found.annotations or {}).get("lives") if found else None
        if isinstance(lives, str) and lives:
            return lives
        expression = _cel_annotation(lives)
        computed = _cel_text(expression, token) if expression else None
        return computed or place_label(found, place)

    def read_label(self, place: str, token: Token) -> str:
        """What a reader of the token sees: ``reads as``, else the place's label."""
        found = self.place(place)
        expression = _cel_annotation(
            (found.annotations or {}).get("reads_as") if found else None
        )
        computed = _cel_text(expression, token) if expression else None
        return computed or place_label(found, place)

    def lifelines(self, appearing: Sequence[str]) -> tuple[Lifeline, ...]:
        seen = set(appearing)
        ordered = [name for name in self.declared if name in seen]
        ordered += [name for name in dict.fromkeys(appearing) if name not in ordered]
        return tuple(
            Lifeline(name, self.declared.get(name, "system")) for name in ordered
        )


# ── Public resolution ────────────────────────────────────────────────────


def resolve_actor(
    trace: PlayTrace,
    *,
    transition: str | None = None,
    place: str | None = None,
) -> str | None:
    """Who does this step's work, as the sequence diagram draws it.

    A firing's actor is its transition's (``resolve_actor(trace,
    transition=name)``); an injection's or update's is its place's owner
    (``place=name``) — ``None`` when the place has no owner and the step is
    an untitled setup (the sequence view's ``Outside`` lifeline). A
    ``advance``, ``expect`` or ``assume`` has no actor.
    """
    actors = _Actors(trace)
    if transition is not None:
        return actors.of_transition(transition)
    if place is not None:
        return actors.owner(place)
    return None


def resolve_column(trace: PlayTrace, place: str, token: Token) -> str | None:
    """The column a token of a lived place is drawn on, else ``None``."""
    actors = _Actors(trace)
    return actors.column(place, token) if actors.lives(place) else None


def resolve_read_label(trace: PlayTrace, place: str, token: Token) -> str:
    """What a reader of the token sees: ``reads as``, else the place's label."""
    return _Actors(trace).read_label(place, token)


def resolve_step_title(trace: PlayTrace, transition: str) -> str:
    """The firing's business label: the step's title, else the transition's
    summary, else its description — ``None`` (as ``""``-free ``None``) when
    the net gives none."""
    decoration = trace.subject.decorations.nodes.get(f"transition:{transition}")
    if decoration is not None and decoration.summary:
        return decoration.summary
    found = next(
        (t for t in trace.subject.net.transitions if t.name == transition), None
    )
    if found is not None and found.description:
        return found.description
    return humanize(transition)


# ── Labels ───────────────────────────────────────────────────────────────


def humanize(name: str) -> str:
    """``alias.start_attempt`` → ``Start attempt``."""
    words = name.rsplit(".", 1)[-1].replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else name


def place_label(place: Place | None, name: str) -> str:
    if place is not None and place.description:
        return place.description
    return humanize(name)


def _authored_label(
    step: Step, trace: PlayTrace, transition: str | None
) -> str | None:
    """A label someone wrote: the step's title, else its transition's summary or description."""
    if step.title:
        return step.title
    if transition is None:
        return None
    decoration = trace.subject.decorations.nodes.get(f"transition:{transition}")
    if decoration is not None and decoration.summary:
        return decoration.summary
    found = next(
        (t for t in trace.subject.net.transitions if t.name == transition), None
    )
    if found is not None and found.description:
        return found.description
    return None


def _step_label(step: Step, trace: PlayTrace, transition: str | None) -> str:
    authored = _authored_label(step, trace, transition)
    if authored is not None:
        return authored
    if transition is not None:
        return humanize(transition)
    assert isinstance(step.body, InjectBody | UpdateBody)
    name = step.body.place.name
    found = next(
        (
            p
            for p in trace.subject.net.places
            if p.name == trace.subject.place_names.get(name, name)
        ),
        None,
    )
    return place_label(found, name)


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _headings(prose: str) -> list[tuple[int, str]]:
    """Each Markdown heading in ``prose``: its level and text."""
    return [
        (len(match.group(1)), match.group(2))
        for line in prose.splitlines()
        if (match := _HEADING.match(line.strip()))
    ]


def _duration(seconds: float) -> str:
    """``5400`` → ``1 hour 30 minutes``."""
    parts: list[str] = []
    remaining = seconds
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        count = int(remaining // size)
        if count:
            parts.append(f"{count} {unit}{'s' if count != 1 else ''}")
            remaining -= count * size
    if remaining or not parts:
        value = int(remaining) if float(remaining).is_integer() else remaining
        parts.append(f"{value} second{'s' if value != 1 else ''}")
    return " ".join(parts)


def _now(tokens: Mapping[str, Sequence[Token]]) -> float | None:
    for place_tokens in tokens.values():
        for token in place_tokens:
            now = token.data.get("now")
            if isinstance(now, int | float) and not isinstance(now, bool):
                return now
    return None


# ── Projection ───────────────────────────────────────────────────────────


def _tokens(value: Any) -> list[Token]:
    """The tokens of a record field: plain or already :class:`Token`."""
    return [t if isinstance(t, Token) else Token(t["type"], t["data"]) for t in value]


@dataclass(frozen=True)
class _Source:
    """The step that made a token: its actor, and what it handed over."""

    actor: str
    index: int
    label: str


@dataclass
class _Activation:
    actor: str
    triggers: list[Message]
    events: list[SequenceEvent]


class _Builder:
    def __init__(self, trace: PlayTrace) -> None:
        self.trace = trace
        self.actors = _Actors(trace)
        self.events: list[SequenceEvent] = []
        self.open: _Activation | None = None
        self.group_open = False
        self.fired = False
        # Steps whose title labels a hand-off: the arrow says it, not a note.
        self.handed: set[int] = set()
        # The delay the last advance drew, while nothing has been drawn after it.
        self.delay: tuple[int, float] | None = None
        self.drawn_matured = False
        # The net's timer clocks: a token of a clock place has no producer,
        # so reading or consuming one never draws a hand-off; the advance
        # that moved the clock drew its delay instead.
        self.clocks = {
            tr.timer.clock
            for tr in trace.subject.net.transitions
            if tr.timer is not None
        }
        self.tokens: dict[str, list[tuple[Token, _Source | None]]] = {}
        for place, tokens in trace.initial.items():
            self.tokens[place] = [(token, None) for token in tokens]

    # Events

    def close(self) -> None:
        activation, self.open = self.open, None
        if activation is None or not (activation.triggers or activation.events):
            return
        self.events.extend(activation.triggers)
        outgoing = any(
            isinstance(event, Message) and event.source == activation.actor
            for event in activation.events
        )
        bar = bool(activation.triggers) and outgoing
        if bar:
            self.events.append(Activate(activation.actor))
        self.events.extend(activation.events)
        if bar:
            self.events.append(Deactivate(activation.actor))
        self.delay = None

    def emit(self, event: SequenceEvent) -> None:
        self.close()
        self.events.append(event)
        self.delay = None

    def close_group(self) -> None:
        if self.group_open:
            self.emit(GroupClose())
            self.group_open = False

    def headings(self, step: Step) -> None:
        for level, text in _headings(step.prose):
            self.close_group()
            if level == 3:
                self.emit(GroupOpen(text))
                self.group_open = True
            else:
                self.emit(Divider(text))

    def divider(self, text: str) -> None:
        self.close_group()
        self.emit(Divider(text))

    def act(
        self,
        actor: str,
        hand_offs: Sequence[Message],
        drawn: Sequence[SequenceEvent],
    ) -> None:
        """Add one step by ``actor``: the arrows into it, then what it drew."""
        solid = [message for message in hand_offs if not message.dashed]
        context = [message for message in hand_offs if message.dashed]
        if solid or self.open is None or self.open.actor != actor:
            self.close()
            self.open = _Activation(actor, solid, [])
        assert self.open is not None
        for event in [*context, *drawn]:
            last = self.open.events[-1] if self.open.events else None
            if (
                isinstance(event, Note)
                and isinstance(last, Note)
                and last.actor == event.actor
            ):
                self.open.events[-1] = Note(
                    last.actor,
                    last.lines + event.lines,
                    last.line,
                    last.steps + event.steps,
                )
            elif (
                isinstance(event, Message)
                and isinstance(last, Message)
                and not event.dashed
                and not last.dashed
                and (event.source, event.target) == (last.source, last.target)
            ):
                # One actor's writes into one column in a row fold into one arrow.
                self.open.events[-1] = Message(
                    last.source,
                    last.target,
                    "\n".join(text for text in (last.label, event.label) if text),
                    False,
                    last.line,
                )
            else:
                self.open.events.append(event)

    # Tokens

    def take(self, place: str, token: Token, *, remove: bool) -> _Source | None:
        held = self.tokens.get(place, [])
        for index, (candidate, source) in enumerate(held):
            if candidate == token:
                if remove:
                    del held[index]
                return source
        return None

    def take_all(self, tokens: Mapping[str, Sequence[Token]]) -> None:
        for place, place_tokens in tokens.items():
            for token in place_tokens:
                self.take(place, token, remove=True)

    def put(
        self, tokens: Mapping[str, Sequence[Token]], source: _Source | None
    ) -> None:
        for place, place_tokens in tokens.items():
            self.tokens.setdefault(place, []).extend((t, source) for t in place_tokens)

    def writes(
        self,
        actor: str,
        produced: Mapping[str, Sequence[Token]],
        label: str | None,
        line: int,
    ) -> list[Message]:
        """One arrow from ``actor`` into each column it writes to.

        Without a ``label``, an arrow says the description of the first place it writes, or nothing.
        """
        columns: dict[str, str] = {}
        for place, place_tokens in produced.items():
            if not self.actors.lives(place):
                continue
            found = self.actors.place(place)
            for token in place_tokens:
                column = self.actors.column(place, token)
                if column != actor and column not in columns:
                    columns[column] = (found.description if found else None) or ""
        return [
            Message(actor, column, label if label is not None else text, False, line)
            for column, text in columns.items()
        ]

    # Steps

    def matured_records(self, result: StepResult) -> None:
        """The firings one ``advance`` matured: each drawn like a firing of
        its own transition, under the firing's actor, after the advance's
        delay marker, marked ``matured`` (spec: "on time"). The firing's
        data comes from its record — the checker already played it, so the
        consumed/read/produced tokens are the record's own.
        """
        net = self.trace.subject.net
        consume_places: dict[str, set[str]] = {}
        for arc in net.arcs:
            if (
                arc.to_transition is not None
                and arc.from_place is not None
                and arc.consume is not None
                and arc.consume.mode == "consume"
            ):
                consume_places.setdefault(arc.to_transition, set()).add(
                    arc.from_place
                )
        for record in result.records:
            if "firingId" not in record:
                continue
            if record.get("status") != "completed":
                continue
            transition = record["transition"]
            binding = {
                place: _tokens(record["inputTokens"][place])
                for place in record["inputTokens"]
            }
            sources = consume_places.get(transition, set())
            consumed = {place: binding[place] for place in sources if place in binding}
            read = {
                place: tokens
                for place, tokens in binding.items()
                if place not in consumed
            }
            produced = {
                place: _tokens(record["outputTokens"][place])
                for place in record["outputTokens"]
            }
            synthetic = replace(
                result,
                records=(cast(Any, record),),
                produced=produced,
                consumed=consumed,
                read=read,
            )
            self.drawn_matured = True
            self.fire(synthetic, transition, matured=True)
        if self.drawn_matured:
            self.fired = True
            self.drawn_matured = False

    def advance(self, result: StepResult) -> None:
        self.take_all(result.replaced)
        self.put(result.produced, None)
        after, before = _now(result.produced), _now(result.replaced)
        if after is None:
            self.emit(Delay("the clock moves"))
            return
        if before is None:
            # A clock's first value: no time passes before it.
            return
        if after < before:
            self.emit(Delay(f"the clock reads {after}"))
            return
        seconds = after - before
        records = [
            record
            for record in result.records
            if "firingId" in record and record.get("status") == "completed"
        ]
        self.close()
        if self.delay is not None and self.delay[0] == len(self.events) - 1:
            # Ticks with nothing drawn between them are one delay: the longest.
            index, drawn = self.delay
            if seconds > drawn:
                self.events[index] = Delay(f"{_duration(seconds)} later")
                self.delay = (index, seconds)
            if not records:
                return
        else:
            self.emit(Delay(f"{_duration(seconds)} later"))
            self.delay = (len(self.events) - 1, seconds)
            if not records:
                return
        # The delay drew; now the firings the new time matured.
        self.delay = None
        self.matured_records(result)

    def fire(self, result: StepResult, transition: str, *, matured: bool = False) -> None:
        step = result.step
        line = step.position.line
        actor = self.actors.of_transition(transition)
        label = _authored_label(step, self.trace, transition)
        if matured and label is not None:
            label = f"{label} (on time)"
        writes = self.writes(actor, result.produced, label, line)
        written = {message.target for message in writes}
        reads: list[Message] = []
        by_source: dict[str, tuple[bool, list[str]]] = {}
        for consumed, tokens in ((True, result.consumed), (False, result.read)):
            for place, place_tokens in tokens.items():
                for token in place_tokens:
                    source = self.take(place, token, remove=consumed)
                    if self.actors.lives(place):
                        column = self.actors.column(place, token)
                        # A labeled step that writes back into the column it
                        # reads (a flip of a switch) draws only the write.
                        if column == actor or (column in written and label is not None):
                            continue
                        read = self.actors.read_label(place, token)
                        message = Message(column, actor, read, True, line)
                        if message not in reads:
                            reads.append(message)
                        continue
                    if source is None or source.actor == actor:
                        continue
                    if place in self.clocks:
                        # A clock token a `update` placed has no producer:
                        # the advance that moved the clock drew its delay.
                        continue
                    self.handed.add(source.index)
                    solid, labels = by_source.get(source.actor, (False, []))
                    if source.label not in labels:
                        labels.append(source.label)
                    by_source[source.actor] = (solid or consumed, labels)
        hand_offs = [
            Message(
                source_actor,
                actor,
                "\n".join(
                    label if label.endswith(" (on time)") else label + " (on time)"
                    for label in labels
                )
                if matured
                else "\n".join(labels),
                not solid,
                line,
            )
            for source_actor, (solid, labels) in by_source.items()
        ]
        if label is None:
            # An unlabeled step that writes back into the column it reads
            # draws only the read: the value it saw is the story.
            read_from = {message.source for message in reads}
            writes = [message for message in writes if message.target not in read_from]
        if matured:
            writes = [replace(message, matured=True) for message in writes]
            hand_offs = [replace(message, matured=True) for message in hand_offs]
        drawn: list[SequenceEvent] = [*reads, *writes]
        if not writes and step.title:
            drawn.append(Note(actor, (step.title,), line, (result.index,)))
        self.act(actor, hand_offs, drawn)
        handed = step.title or None
        for place, place_tokens in result.produced.items():
            self.put(
                {place: place_tokens},
                _Source(
                    actor,
                    result.index,
                    handed or self.actors.read_label(place, place_tokens[0]),
                ),
            )
        self.fired = True

    def inject(self, result: StepResult) -> None:
        step = result.step
        assert isinstance(step.body, InjectBody | UpdateBody)
        place = step.body.place.name
        actor = self.actors.owner(place)
        # An untitled inject/update into a place with no owner (Outside)
        # sets up state on nobody's behalf: it draws nothing, and its
        # tokens carry no producer, so a later step that consumes or reads
        # them draws no hand-off. A titled one keeps its arrow: the author
        # shows an outside event on purpose.
        silent = actor == OUTSIDE and not step.title
        self.take_all(result.replaced)
        if self.fired and not silent:
            label = _step_label(step, self.trace, None)
            writes = self.writes(actor, result.produced, label, step.position.line)
            if writes:
                self.act(actor, [], writes)
        for produced_place, place_tokens in result.produced.items():
            producer = (
                None
                if silent
                else _Source(
                    actor,
                    result.index,
                    step.title
                    or self.actors.read_label(produced_place, place_tokens[0]),
                )
            )
            self.put({produced_place: place_tokens}, producer)

    def played(self, result: StepResult) -> None:
        step = result.step
        self.headings(step)
        if step.kind in ("expect", "assume"):
            return
        if step.kind == "advance":
            self.advance(result)
        elif isinstance(step.body, FireBody):
            self.fire(result, step.body.transition.name)
        else:
            self.inject(result)

    def failed(self, failure: StepFailure) -> None:
        step = failure.step
        self.headings(step)
        actor: str | None = None
        transition: str | None = None
        if isinstance(step.body, FireBody):
            transition = step.body.transition.name
            actor = self.actors.of_transition(transition)
        elif isinstance(step.body, InjectBody | UpdateBody):
            actor = self.actors.owner(step.body.place.name)
        if step.kind in ("expect", "advance", "assume"):
            label = step.title or step.statement
            actor = None
        else:
            label = _step_label(step, self.trace, transition)
        self.emit(
            Failure(
                actor,
                label,
                failure.diagnostic.message,
                failure.diagnostic.code,
                step.position.line,
                failure.diagnostic.details[0] if failure.diagnostic.details else None,
            )
        )


def _without_handed_notes(
    events: Sequence[SequenceEvent], handed: set[int]
) -> list[SequenceEvent]:
    kept: list[SequenceEvent] = []
    for event in events:
        if isinstance(event, Note) and handed & set(event.steps):
            pairs = [
                (text, index)
                for text, index in zip(event.lines, event.steps, strict=True)
                if index not in handed
            ]
            if not pairs:
                continue
            event = Note(
                event.actor,
                tuple(text for text, _ in pairs),
                event.line,
                tuple(index for _, index in pairs),
            )
        kept.append(event)
    return kept


def _appearing(events: Sequence[SequenceEvent]) -> list[str]:
    appearing: list[str] = []
    for event in events:
        if isinstance(event, Message):
            names = [event.source, event.target]
        elif isinstance(event, Note | Activate | Deactivate):
            names = [event.actor]
        elif isinstance(event, Failure) and event.actor is not None:
            names = [event.actor]
        else:
            names = []
        appearing += [name for name in names if name not in appearing]
    return appearing


def _boxed(
    lifelines: tuple[Lifeline, ...], trace: PlayTrace
) -> tuple[tuple[Lifeline, ...], tuple[Box, ...]]:
    """Lifelines with each box's members together, at its first member's place."""
    present = {lifeline.name: lifeline for lifeline in lifelines}
    boxes = [
        Box(box.title, members)
        for box in trace.play.boxes
        if (members := tuple(name for name in box.members if name in present))
    ]
    box_of = {name: box for box in boxes for name in box.lifelines}
    ordered: list[Lifeline] = []
    placed: list[Box] = []
    for lifeline in lifelines:
        box = box_of.get(lifeline.name)
        if box is None:
            ordered.append(lifeline)
        elif box not in placed:
            placed.append(box)
            ordered += [present[name] for name in box.lifelines]
    return tuple(ordered), tuple(placed)


def sequence_view(trace: PlayTrace) -> SequenceView:
    """The sequence projection of one checked path."""
    builder = _Builder(trace)
    path = trace.path
    for result in trace.steps:
        if (
            result.index == trace.inherited
            and trace.inherited
            and path.from_label is not None
        ):
            builder.divider(path.title or path.name)
        builder.played(result)
    if trace.failure is not None:
        builder.failed(trace.failure)
    builder.close()
    builder.close_group()
    events = tuple(_without_handed_notes(builder.events, builder.handed))
    lifelines, boxes = _boxed(builder.actors.lifelines(_appearing(events)), trace)
    return SequenceView(
        play=trace.play.name,
        path=path.name,
        status="passed" if trace.failure is None else "failed",
        lifelines=lifelines,
        events=events,
        title=trace.play.title,
        boxes=boxes,
    )


# ── Rendering ────────────────────────────────────────────────────────────

_PREAMBLE = """\
skinparam backgroundColor #FEFEFE
skinparam defaultFontColor #222222
skinparam shadowing false
skinparam ArrowColor #555555
skinparam ArrowFontColor #222222
skinparam sequenceMessageAlign left
skinparam SequenceLifeLineBorderColor #999999
skinparam SequenceLifeLineBackgroundColor #FFFFFF
skinparam ParticipantBorderColor #5B7DB1
skinparam ParticipantBackgroundColor #EEF3FA
skinparam ParticipantFontColor #222222
skinparam ActorBorderColor #8A6D1F
skinparam ActorBackgroundColor #FFF6E0
skinparam ActorFontColor #222222
skinparam DatabaseBorderColor #B08A2E
skinparam DatabaseBackgroundColor #FFF6E0
skinparam DatabaseFontColor #222222
skinparam NoteBorderColor #C9B458
skinparam NoteBackgroundColor #FFFBEA
skinparam NoteFontColor #222222
skinparam BoxBorderColor #BBBBBB
skinparam BoxFontColor #444444
skinparam SequenceGroupBorderColor #888888
skinparam SequenceGroupBackgroundColor #F0F0F0
skinparam SequenceGroupHeaderFontColor #222222
skinparam SequenceGroupFontColor #222222
skinparam SequenceDividerBorderColor #888888
skinparam SequenceDividerBackgroundColor #EEEEEE
skinparam SequenceDividerFontColor #222222
skinparam SequenceDelayFontColor #555555
skinparam TitleFontColor #222222
hide footbox"""

_FAILURE_COLOR = "#FDE2E2"
_BOX_COLOR = "#F4F4F4"

_KEYWORDS: Mapping[str, str] = {
    "person": "actor",
    "record": "database",
    "system": "participant",
}


def _text(value: str) -> str:
    """One line of PlantUML text."""
    return " ".join(value.split()).replace("\\", "\\\\")


def _lines(value: str) -> str:
    """PlantUML message text, one ``\\n`` per line of ``value``."""
    return "\\n".join(_text(line) for line in value.split("\n"))


def _aliases(lifelines: Sequence[Lifeline]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for lifeline in lifelines:
        base = re.sub(r"[^A-Za-z0-9]+", "_", lifeline.name).strip("_").lower() or "l"
        if base[0].isdigit():
            base = f"l_{base}"
        alias, n = base, 2
        while alias in aliases.values():
            alias, n = f"{base}_{n}", n + 1
        aliases[lifeline.name] = alias
    return aliases


def render_plantuml(view: SequenceView) -> str:
    """The view as one PlantUML sequence diagram, readable on a dark page."""
    alias = _aliases(view.lifelines)
    lines = ["@startuml", _PREAMBLE]
    if view.title:
        lines.append(f"title {_text(view.title)}")
    box_of = {name: box for box in view.boxes for name in box.lifelines}
    for lifeline in view.lifelines:
        box = box_of.get(lifeline.name)
        if box is not None and box.lifelines[0] == lifeline.name:
            lines.append(f"box {json.dumps(box.title)} {_BOX_COLOR}")
        lines.append(
            f"{_KEYWORDS[lifeline.kind]} {json.dumps(lifeline.name)}"
            f" as {alias[lifeline.name]}"
        )
        if box is not None and box.lifelines[-1] == lifeline.name:
            lines.append("end box")
    for event in view.events:
        if isinstance(event, Message):
            arrow = "-->" if event.dashed else "->"
            text = f" : {_lines(event.label)}" if event.label else ""
            lines.append(f"{alias[event.source]} {arrow} {alias[event.target]}{text}")
        elif isinstance(event, Note):
            target = alias[event.actor]
            if len(event.lines) == 1:
                lines.append(f"note right of {target} : {_text(event.lines[0])}")
            else:
                lines += [
                    f"note right of {target}",
                    *(_text(text) for text in event.lines),
                    "end note",
                ]
        elif isinstance(event, Activate):
            lines.append(f"activate {alias[event.actor]}")
        elif isinstance(event, Deactivate):
            lines.append(f"deactivate {alias[event.actor]}")
        elif isinstance(event, GroupOpen):
            lines.append(f"group {_text(event.text)}")
        elif isinstance(event, GroupClose):
            lines.append("end")
        elif isinstance(event, Divider):
            lines.append(f"== {_text(event.text)} ==")
        elif isinstance(event, Delay):
            lines.append(f"...{_text(event.text)}...")
        else:
            where = f"over {alias[event.actor]}" if event.actor else "across"
            lines += [
                f"note {where} {_FAILURE_COLOR}",
                f"✗ {_text(event.label)}",
                f"{event.code}: {_text(event.message)}",
                *([_text(event.detail)] if event.detail else []),
                "end note",
            ]
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _event_json(event: SequenceEvent) -> dict[str, Any]:
    if isinstance(event, Message):
        out = {
            "kind": "message",
            "from": event.source,
            "to": event.target,
            "label": event.label,
            "dashed": event.dashed,
            "line": event.line,
        }
        if event.matured:
            out["matured"] = True
        return out
    if isinstance(event, Note):
        return {
            "kind": "note",
            "actor": event.actor,
            "lines": list(event.lines),
            "line": event.line,
        }
    if isinstance(event, Activate):
        return {"kind": "activate", "actor": event.actor}
    if isinstance(event, Deactivate):
        return {"kind": "deactivate", "actor": event.actor}
    if isinstance(event, GroupOpen):
        return {"kind": "group", "text": event.text}
    if isinstance(event, GroupClose):
        return {"kind": "end_group"}
    if isinstance(event, Divider):
        return {"kind": "divider", "text": event.text}
    if isinstance(event, Delay):
        return {"kind": "delay", "text": event.text}
    return {
        "kind": "failure",
        "actor": event.actor,
        "label": event.label,
        "code": event.code,
        "message": event.message,
        "line": event.line,
        "detail": event.detail,
    }


def sequence_json(view: SequenceView) -> dict[str, Any]:
    """The view as JSON: lifelines and boxes, then events in order."""
    return {
        "play": view.play,
        "title": view.title,
        "path": view.path,
        "status": view.status,
        "lifelines": [
            {"name": lifeline.name, "kind": lifeline.kind}
            for lifeline in view.lifelines
        ],
        "boxes": [
            {"title": box.title, "lifelines": list(box.lifelines)} for box in view.boxes
        ],
        "events": [_event_json(event) for event in view.events],
    }


def render_sequence(
    trace: PlayTrace, *, format: SequenceFormat = "plantuml"
) -> str:
    view = sequence_view(trace)
    if format == "json":
        return json.dumps(sequence_json(view), ensure_ascii=False, indent=2) + "\n"
    return render_plantuml(view)


__all__ = [
    "OUTSIDE",
    "Activate",
    "Box",
    "Deactivate",
    "Delay",
    "Divider",
    "Failure",
    "GroupClose",
    "GroupOpen",
    "Lifeline",
    "Message",
    "Note",
    "SequenceView",
    "humanize",
    "render_plantuml",
    "render_sequence",
    "resolve_actor",
    "resolve_column",
    "resolve_read_label",
    "resolve_step_title",
    "sequence_json",
    "sequence_view",
]
