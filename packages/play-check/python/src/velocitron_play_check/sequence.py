"""Project a checked play path onto a sequence diagram.

The diagram is a reduced view of the path's firings, not a separate model.
Each step belongs to an actor: a transition's ``actor`` annotation (or its
net's default actor), and for an injection the ``actor`` of the place it
fills, the place's owner. A place that ``lives`` on a column (a record such
as a branch home, or a slip on a shelf) is drawn as that column: a step
that writes into it draws an arrow into the column, and a step that reads
or consumes from it draws a dashed arrow out of it, labeled with the value
read. A place a token crosses actors through — one actor produces it and
another consumes it — is a queue lifeline. Making the token draws an arrow
into the queue, and using it draws an arrow out, each in the step that does
it. A place one actor uses stays hidden. A step's title is on its first
arrow, or a note when the step draws none; its other arrows carry the
token's colour. Tokens of the starting marking, of a clock place, and of an
untitled injection into a place with no owner have no producer: they draw
no arrow when consumed. A consumed hand-off starts a new activation; the
actor's own titled steps that draw no arrow are a note beside it.

A ``advance`` is a delay (a clock's first advance draws nothing, and ticks
with nothing drawn between them are one delay: the total time one clock
moved, or the longest when the ticks do not continue one another). The
firings it matures draw after that delay, under their transitions' actors,
labelled with the transition's own label plus ``(on time)``. A ``### heading``
in a step's prose opens a group, any other heading is a divider, and an
``expect`` shows only when it fails.

:func:`sequence_view` builds the projection; :func:`render_plantuml` draws
it. PlantUML is one rendering of the view, chosen because GitHub and the
Obsidian plugin both draw it.

References: spec/play-language.md; ADR 0038; ADR 0039; ADR 0073.
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


LifelineKind = Literal["person", "system", "record", "queue"]


@dataclass(frozen=True)
class Lifeline:
    name: str
    kind: LifelineKind


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


def _colour_text(names: Sequence[str]) -> str:
    """The token colours an arrow carries, once each, in the order seen."""
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return "\n".join(seen)


@dataclass
class _Slot:
    """One token in the path: who made it, and who took it, if anyone."""

    token: Token
    producer: str | None
    place: str
    consumer: str | None = None
    firing: bool = False
    draw_produce: bool = False
    draw_consume: bool = False


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
        # The delay the last advance drew, while nothing has been drawn after
        # it: its index, the seconds it shows, and the clock reading it ended on.
        self.delay: tuple[int, float, float] | None = None
        # The net's timer clocks: a token of a clock place has no producer,
        # so reading or consuming one never draws an arrow; the advance
        # that moved the clock drew its delay instead.
        self.clocks = {
            tr.timer.clock
            for tr in trace.subject.net.transitions
            if tr.timer is not None
        }
        self.holding: dict[str, list[_Slot]] = {}
        for place, tokens in trace.initial.items():
            self.holding[place] = [_Slot(token, None, place) for token in tokens]
        self._initial = {
            place: list(slots) for place, slots in self.holding.items()
        }
        self._planned: list[list[tuple[str, list[_Slot]]]] = []
        self._plan_i = 0
        self._phase = "record"
        self.queue_caption: dict[str, str] = {}
        self.queue_producer: dict[str, str] = {}
        self.queue_order: list[str] = []
        self.captions: set[str] = set()

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
                and event.source not in self.captions
                and event.target not in self.captions
            ):
                # One actor's writes into one lived column in a row fold into one arrow.
                # A queue arrow is one step; folding it would hide the next step.
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

    def project(self) -> None:
        """Classify hand-off places, then draw each step where it happens."""
        self._phase = "record"
        self._walk()
        self._mark_queues()
        self.holding = {
            place: list(slots) for place, slots in self._initial.items()
        }
        self._plan_i = 0
        self._phase = "replay"
        self.events = []
        self.open = None
        self.group_open = False
        self.fired = False
        self.delay = None
        self._walk()
        if self.trace.failure is not None:
            self.failed(self.trace.failure)
        self.close()
        self.close_group()

    def _walk(self) -> None:
        path = self.trace.path
        for result in self.trace.steps:
            if (
                self._phase == "replay"
                and result.index == self.trace.inherited
                and self.trace.inherited
                and path.from_label is not None
            ):
                self.divider(path.title or path.name)
            self.played(result)

    def _take(
        self,
        place: str,
        token: Token,
        *,
        remove: bool,
        consumer: str | None,
        firing: bool,
    ) -> _Slot | None:
        held = self.holding.get(place, [])
        for index, slot in enumerate(held):
            if slot.token == token:
                if (
                    self._phase == "record"
                    and consumer is not None
                    and slot.consumer is None
                ):
                    slot.consumer = consumer
                    slot.firing = firing
                if remove:
                    del held[index]
                return slot
        return None

    def _take_all(
        self,
        tokens: Mapping[str, Sequence[Token]],
        *,
        consumer: str | None,
        firing: bool,
    ) -> None:
        for place, place_tokens in tokens.items():
            for token in place_tokens:
                self._take(
                    place, token, remove=True, consumer=consumer, firing=firing
                )

    def _put(
        self, tokens: Mapping[str, Sequence[Token]], producer: str | None
    ) -> list[tuple[str, list[_Slot]]]:
        if self._phase == "record":
            batch: list[tuple[str, list[_Slot]]] = []
            for place, place_tokens in tokens.items():
                slots = [_Slot(token, producer, place) for token in place_tokens]
                self.holding.setdefault(place, []).extend(slots)
                batch.append((place, slots))
            self._planned.append(batch)
            return batch
        batch = self._planned[self._plan_i]
        self._plan_i += 1
        got = list(tokens.items())
        if len(batch) != len(got):
            raise RuntimeError("sequence projection diverged")
        for (place, slots), (got_place, got_tokens) in zip(batch, got, strict=True):
            if place != got_place or [slot.token for slot in slots] != list(got_tokens):
                raise RuntimeError(f"sequence projection diverged at ({place})")
            self.holding.setdefault(place, []).extend(slots)
        return batch

    def _mark_queues(self) -> None:
        """A place is a queue when some token crosses actors through it."""
        slots = [slot for group in self._initial.values() for slot in group]
        for batch in self._planned:
            for _, place_slots in batch:
                slots.extend(place_slots)
        crossing: list[str] = []
        first_producer: dict[str, str] = {}
        for slot in slots:
            if self.actors.lives(slot.place) or slot.place in self.clocks:
                continue
            if slot.producer and slot.place not in first_producer:
                first_producer[slot.place] = slot.producer
            crosses = bool(
                slot.firing
                and slot.producer
                and slot.consumer
                and slot.producer != slot.consumer
            )
            if crosses and slot.place not in crossing:
                crossing.append(slot.place)
        used = set(self.actors.declared)
        used.add(OUTSIDE)
        if self.actors.default:
            used.add(self.actors.default)
        used.add(self.actors.net.name)
        order: list[str] = []
        for slot in slots:
            if (
                slot.place in crossing
                and slot.place not in order
                and slot.producer
            ):
                order.append(slot.place)
        self.queue_order = order
        for place in order:
            caption = self._caption(place, used)
            self.queue_caption[place] = caption
            self.queue_producer[place] = first_producer[place]
            self.captions.add(caption)
        for slot in slots:
            if slot.place not in self.queue_caption:
                continue
            slot.draw_consume = bool(
                slot.firing
                and slot.producer
                and slot.consumer
                and slot.producer != slot.consumer
            )
            slot.draw_produce = bool(
                slot.producer
                and (
                    slot.consumer is None
                    or (slot.firing and slot.consumer != slot.producer)
                )
            )

    def _caption(self, place: str, used: set[str]) -> str:
        """The queue's caption: the place's description, else ``(place_id)``."""
        found = self.actors.place(place)
        if found is not None and found.description and found.description not in used:
            used.add(found.description)
            return found.description
        base = f"({place})"
        candidate = base
        number = 2
        while candidate in used:
            candidate = f"{base} {number}"
            number += 1
        used.add(candidate)
        return candidate

    def writes(
        self,
        actor: str,
        produced: Mapping[str, Sequence[Token]],
        line: int,
    ) -> list[tuple[Message, str]]:
        """One arrow from ``actor`` into each lived column it writes to.

        The message's label is the first written place's description, or
        nothing. The paired string is the token colour, for an arrow that
        is not the step's first.
        """
        columns: dict[str, list[str]] = {}
        descriptions: dict[str, str] = {}
        for place, place_tokens in produced.items():
            if not self.actors.lives(place):
                continue
            found = self.actors.place(place)
            text = (found.description if found is not None else None) or ""
            for token in place_tokens:
                column = self.actors.column(place, token)
                if column == actor:
                    continue
                descriptions.setdefault(column, text)
                columns.setdefault(column, []).append(token.type)
        return [
            (
                Message(actor, column, descriptions[column], False, line),
                _colour_text(colours),
            )
            for column, colours in columns.items()
        ]

    def _with_step_label(
        self,
        label: str | None,
        arrows: list[tuple[Message, str, bool]],
    ) -> list[Message]:
        """The step's label on its first arrow; other arrows carry the colour.

        ``arrows`` is ``(message, colour, is_queue)`` in the order the
        diagram draws the step's own arrows. A lived write with no step
        label keeps the place description it was given.
        """
        labelled: list[Message] = []
        for index, (message, colour, is_queue) in enumerate(arrows):
            if label and index == 0:
                text = label
            elif is_queue or label:
                text = colour
            else:
                text = message.label
            labelled.append(replace(message, label=text))
        return labelled

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
            self.fire(synthetic, transition, matured=True)

    def advance(self, result: StepResult) -> None:
        self._take_all(result.replaced, consumer=None, firing=False)
        self._put(result.produced, None)
        if self._clock_moved(result):
            self.matured_records(result)

    def _clock_moved(self, result: StepResult) -> bool:
        """Draw the delay when replaying. Return whether firings matured.

        Back-to-back moves of one clock add up, so ``advance`` 0 then 29
        then 30 says 30 seconds. Moves that do not continue that reading
        keep the longer one, so two clocks advanced together say the
        longest once.
        """
        after = _now(result.produced)
        before = _now(result.replaced)
        records = [
            record
            for record in result.records
            if "firingId" in record and record.get("status") == "completed"
        ]
        if after is None:
            if self._phase == "replay":
                self.emit(Delay("the clock moves"))
            return False
        if before is None:
            # A clock's first value: no time passes before it.
            return False
        if after < before:
            if self._phase == "replay":
                self.emit(Delay(f"the clock reads {after}"))
            return False
        if self._phase != "replay":
            return bool(records)
        return self._draw_delay(after - before, before, after, bool(records))

    def _draw_delay(
        self, seconds: float, before: float, after: float, has_records: bool
    ) -> bool:
        self.close()
        if self.delay is not None and self.delay[0] == len(self.events) - 1:
            index, drawn, last_after = self.delay
            if before == last_after:
                total = drawn + seconds
                end = after
            elif seconds > drawn:
                total = seconds
                end = after
            else:
                total = drawn
                end = last_after
            if total != drawn:
                self.events[index] = Delay(f"{_duration(total)} later")
            self.delay = (index, total, end)
            if not has_records:
                return False
        else:
            self.emit(Delay(f"{_duration(seconds)} later"))
            self.delay = (len(self.events) - 1, seconds, after)
            if not has_records:
                return False
        self.delay = None
        return True

    def _firing_label(
        self, step: Step, transition: str, *, matured: bool
    ) -> str | None:
        """A firing's label. A matured firing uses its transition, not the advance."""
        source = replace(step, title=None) if matured else step
        label = _authored_label(source, self.trace, transition)
        if matured and label is not None:
            return f"{label} (on time)"
        return label

    def fire(self, result: StepResult, transition: str, *, matured: bool = False) -> None:
        step = result.step
        line = step.position.line
        actor = self.actors.of_transition(transition)
        replaying = self._phase == "replay"
        label = (
            self._firing_label(step, transition, matured=matured)
            if replaying
            else None
        )
        write_pairs = self.writes(actor, result.produced, line) if replaying else []
        written = {message.target for message, _colour in write_pairs}
        reads: list[Message] = []
        consumes: list[tuple[str, list[str]]] = []
        for consuming, groups in ((True, result.consumed), (False, result.read)):
            for place, place_tokens in groups.items():
                colours: list[str] = []
                for token in place_tokens:
                    slot = self._take(
                        place,
                        token,
                        remove=consuming,
                        consumer=actor if consuming else None,
                        firing=consuming,
                    )
                    if not replaying:
                        continue
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
                    if consuming and slot is not None and slot.draw_consume:
                        colours.append(token.type)
                if colours:
                    consumes.append((self.queue_caption[place], colours))
        batch = self._put(result.produced, actor)
        if not replaying:
            return
        if label is None:
            # An unlabeled step that writes back into the column it reads
            # draws only the read: the value it saw is the story.
            read_from = {message.source for message in reads}
            write_pairs = [
                pair for pair in write_pairs if pair[0].target not in read_from
            ]
        produces: list[tuple[str, list[str]]] = []
        for place, slots in batch:
            colours = [slot.token.type for slot in slots if slot.draw_produce]
            if colours:
                produces.append((self.queue_caption[place], colours))
        bearing: list[tuple[Message, str, bool]] = []
        for caption, colours in consumes:
            bearing.append(
                (
                    Message(caption, actor, "", False, line, matured),
                    _colour_text(colours),
                    True,
                )
            )
        for caption, colours in produces:
            bearing.append(
                (
                    Message(actor, caption, "", False, line, matured),
                    _colour_text(colours),
                    True,
                )
            )
        for message, colour in write_pairs:
            flagged = replace(message, matured=True) if matured else message
            bearing.append((flagged, colour, False))
        labelled = self._with_step_label(label, bearing)
        n_consume = len(consumes)
        n_produce = len(produces)
        drawn: list[SequenceEvent] = [
            *labelled[n_consume : n_consume + n_produce],
            *labelled[n_consume + n_produce :],
        ]
        if not bearing:
            if matured and label:
                drawn.append(Note(actor, (label,), line, (result.index,)))
            elif not matured and step.title:
                drawn.append(Note(actor, (step.title,), line, (result.index,)))
        self.act(actor, [*labelled[:n_consume], *reads], drawn)
        self.fired = True

    def inject(self, result: StepResult) -> None:
        step = result.step
        assert isinstance(step.body, InjectBody | UpdateBody)
        actor = self.actors.owner(step.body.place.name)
        # An untitled inject/update into a place with no owner (Outside)
        # sets up state on nobody's behalf: it draws nothing, and its
        # tokens carry no producer, so a later step that consumes them
        # draws no arrow. A titled one keeps its arrow: the author shows
        # an outside event on purpose.
        silent = actor == OUTSIDE and not step.title
        self._take_all(
            result.replaced,
            consumer=None if silent else actor,
            firing=False,
        )
        batch = self._put(result.produced, None if silent else actor)
        if self._phase != "replay" or silent:
            return
        line = step.position.line
        produces: list[tuple[str, list[str]]] = []
        for place, slots in batch:
            colours = [slot.token.type for slot in slots if slot.draw_produce]
            if colours:
                produces.append((self.queue_caption[place], colours))
        lived: list[tuple[Message, str]] = []
        if self.fired:
            lived = self.writes(actor, result.produced, line)
            if not step.title:
                fallback = _step_label(step, self.trace, None)
                lived = [
                    (replace(message, label=fallback), colour)
                    for message, colour in lived
                ]
        bearing: list[tuple[Message, str, bool]] = [
            (Message(actor, caption, "", False, line), _colour_text(colours), True)
            for caption, colours in produces
        ]
        bearing.extend((message, colour, False) for message, colour in lived)
        if not bearing:
            return
        self.act(actor, [], self._with_step_label(step.title, bearing))

    def played(self, result: StepResult) -> None:
        step = result.step
        if self._phase == "replay":
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


def _seat_queues(
    lifelines: tuple[Lifeline, ...], queues: list[tuple[str, str]]
) -> tuple[Lifeline, ...]:
    """Each hand-off place sits immediately after the actor that produces into it.

    ``queues`` is ``(caption, producer)`` in the order those places are first
    produced into.
    """
    by_producer: dict[str, list[Lifeline]] = {}
    for caption, producer in queues:
        by_producer.setdefault(producer, []).append(Lifeline(caption, "queue"))
    seated: list[Lifeline] = []
    placed: set[str] = set()
    for lifeline in lifelines:
        seated.append(lifeline)
        for queue in by_producer.get(lifeline.name, []):
            seated.append(queue)
            placed.add(queue.name)
    for caption, producer in queues:
        if caption in placed:
            continue
        if not any(item.name == producer for item in seated):
            seated.append(Lifeline(producer, "system"))
        index = next(i for i, item in enumerate(seated) if item.name == producer)
        seated.insert(index + 1, Lifeline(caption, "queue"))
        placed.add(caption)
    return tuple(seated)


def sequence_view(trace: PlayTrace) -> SequenceView:
    """The sequence projection of one checked path."""
    builder = _Builder(trace)
    builder.project()
    events = tuple(builder.events)
    queues = [
        (builder.queue_caption[place], builder.queue_producer[place])
        for place in builder.queue_order
    ]
    queue_names = {caption for caption, _producer in queues}
    appearing = [name for name in _appearing(events) if name not in queue_names]
    lifelines, boxes = _boxed(builder.actors.lifelines(appearing), trace)
    lifelines = _seat_queues(lifelines, queues)
    return SequenceView(
        play=trace.play.name,
        path=trace.path.name,
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
skinparam QueueBorderColor #3E7A5A
skinparam QueueBackgroundColor #F2F8F4
skinparam QueueFontColor #222222
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
    "queue": "queue",
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
