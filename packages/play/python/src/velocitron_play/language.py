"""The ``.play`` source language: statements, prose, and paths.

A source is a list of statements. A statement starts at column 0; a line
that starts with whitespace continues the statement above it, so a long
token or a JSON object may span lines. ``///`` lines are Markdown prose
and ``//`` starts a comment. The statement syntax is the ANTLR grammar
``packages/play/VelocitronPlay.g4``. Parsing reports syntax errors as
``SC1xx`` diagnostics; names are resolved against a net later
(:mod:`velocitron_play_check`).

This module is the source of truth for the play lowerer. It does not import
``velocitron``. Checking a play, the walkthrough, and the sequence diagram
ship in ``velocitron_play_check`` because they use the engine.

References: spec/play-language.md.
"""

from __future__ import annotations

import json
import math
import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from antlr4 import CommonTokenStream, InputStream, Token
from antlr4.Recognizer import Recognizer
from antlr4.error.ErrorListener import ErrorListener
from antlr4.error.Errors import RecognitionException

from .generated.VelocitronPlayLexer import VelocitronPlayLexer
from .generated.VelocitronPlayParser import VelocitronPlayParser

TRUNK = "trunk"
"""The name of a play's first path, the one before any ``path`` line."""

WalkScope = Literal["step", "neighbors", "subnet"]
WALK_SCOPES: tuple[WalkScope, ...] = ("step", "neighbors", "subnet")
"""How much of the net a walkthrough draws for each step: the step's own
transition and places, those plus their other transitions faded, or the
whole touched subnet."""

SequenceMode = Literal["beside", "only"]
"""Whether a path's sequence diagram goes beside its walkthrough or replaces it."""

ActorKind = Literal["person", "system", "record"]


@dataclass(frozen=True)
class Position:
    """A 1-based line and column in the play source."""

    line: int
    column: int


@dataclass(frozen=True)
class Diagnostic:
    """One play diagnostic: ``SC1xx`` syntax, ``SC2xx`` resolution,
    ``SC3xx`` playback. ``details`` are indented lines under the message."""

    code: str
    message: str
    source: str
    position: Position
    details: tuple[str, ...] = ()

    def render(self) -> str:
        head = (
            f"{self.source}:{self.position.line}:{self.position.column}: "
            f"error[{self.code}]: {self.message}"
        )
        return "\n".join([head, *(f"  {line}" for line in self.details)])

    def as_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "source": self.source,
            "line": self.position.line,
            "column": self.position.column,
            "details": list(self.details),
        }


class PlayError(Exception):
    """A play that cannot be parsed or resolved (``SC1xx`` / ``SC2xx``)."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.render())
        self.diagnostic = diagnostic


# ── Parsed form ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NameRef:
    """A place, transition or template name as written, with its position."""

    name: str
    position: Position


@dataclass(frozen=True)
class TokenLiteral:
    """``Color {json}``, or a bare ``{json}`` whose color the place decides."""

    color: str | None
    data: dict[str, Any]
    position: Position


TokenExpr = TokenLiteral | NameRef
"""A token as written: a literal, or a ``$template`` (a :class:`NameRef`)."""


@dataclass(frozen=True)
class InjectBody:
    place: NameRef
    tokens: tuple[TokenExpr, ...]


@dataclass(frozen=True)
class UpdateBody:
    place: NameRef
    token: TokenExpr


@dataclass(frozen=True)
class AdvanceBody:
    place: NameRef | None
    seconds: int | float
    relative: bool


@dataclass(frozen=True)
class WithClause:
    """``with (p) {subset}``, ``with (p) $template`` or ``with (p) #index``."""

    place: NameRef
    subset: dict[str, Any] | None = None
    template: NameRef | None = None
    index: int | None = None


@dataclass(frozen=True)
class OutputClause:
    """``-> (p) tokens``, ``-> (p) +{merge}`` or ``-> (p) nothing``."""

    place: NameRef
    tokens: tuple[TokenExpr, ...] = ()
    merge: dict[str, Any] | None = None
    nothing: bool = False


@dataclass(frozen=True)
class FireBody:
    transition: NameRef
    withs: tuple[WithClause, ...] = ()
    outputs: tuple[OutputClause, ...] = ()


ConditionKind = Literal[
    "equals", "empty", "count", "has", "enabled", "not-enabled", "next", "quiescent"
]


@dataclass(frozen=True)
class Condition:
    """One ``expect`` condition; ``text`` is its source, whitespace collapsed."""

    kind: ConditionKind
    text: str
    position: Position
    place: NameRef | None = None
    tokens: tuple[TokenExpr, ...] = ()
    count: int | None = None
    transitions: tuple[NameRef, ...] = ()


@dataclass(frozen=True)
class ExpectBody:
    conditions: tuple[Condition, ...]


@dataclass(frozen=True)
class AssumeGuardBody:
    """``assume [t] guard true`` (or ``false``): an assumed guard answer."""

    transition: NameRef
    value: bool


@dataclass(frozen=True)
class AssumePredicateBody:
    """``assume predicate "p" true`` (or ``false``): an assumed predicate
    answer, on every consume arc whose predicate names the ref."""

    predicate: str
    value: bool
    position: Position


StepBody = (
    InjectBody
    | UpdateBody
    | AdvanceBody
    | FireBody
    | ExpectBody
    | AssumeGuardBody
    | AssumePredicateBody
)
StepKind = Literal["inject", "update", "advance", "fire", "expect", "assume"]


@dataclass(frozen=True)
class Step:
    """One play step. ``statement`` is the step's source without its
    label and title, whitespace collapsed."""

    kind: StepKind
    body: StepBody
    statement: str
    position: Position
    label: str | None = None
    title: str | None = None
    prose: str = ""


@dataclass(frozen=True)
class PlayPath:
    """A path: the trunk, or a branch from a labeled step of an earlier path."""

    name: str
    position: Position
    title: str | None = None
    prose: str = ""
    from_label: NameRef | None = None
    steps: tuple[Step, ...] = ()
    sequence: SequenceMode | None = None


@dataclass(frozen=True)
class ActorDecl:
    """``person Name``, ``system Name`` or ``record Name``: a lifeline's kind and order."""

    name: str
    kind: ActorKind
    position: Position


@dataclass(frozen=True)
class BoxDecl:
    """``box "Title" A B``: lifelines drawn together in a titled box."""

    title: str
    members: tuple[str, ...]
    position: Position


@dataclass(frozen=True)
class UseDecl:
    ref: str
    alias: str
    position: Position


@dataclass(frozen=True)
class WireDecl:
    from_alias: str
    from_place: str
    to_alias: str
    to_place: str
    position: Position


@dataclass(frozen=True)
class RefineDecl:
    """``refine a.[t] by b``: net ``b`` replaces transition ``t`` of net ``a``."""

    alias: str
    transition: str
    by: str
    position: Position


@dataclass(frozen=True)
class ShareDecl:
    """``share a.(p) ~ b.(q)``: places of several nets that are one place."""

    members: tuple[tuple[str, str], ...]
    position: Position


@dataclass(frozen=True)
class ShowDecl:
    """``show Color field, field.sub``: the fields a walkthrough shows."""

    color: str
    fields: tuple[str, ...]
    position: Position


@dataclass(frozen=True)
class Play:
    """A parsed ``.play`` source."""

    name: str
    source: str
    position: Position
    title: str | None = None
    prose: str = ""
    origin: Path | None = None
    net: str | None = None
    net_position: Position | None = None
    uses: tuple[UseDecl, ...] = ()
    wires: tuple[WireDecl, ...] = ()
    refines: tuple[RefineDecl, ...] = ()
    shares: tuple[ShareDecl, ...] = ()
    marking: str = "initial"
    marking_position: Position | None = None
    # The instance a kept record's start is built from (ADR 0051).
    instance: TokenExpr | None = None
    instance_position: Position | None = None
    templates: dict[str, TokenLiteral] = field(default_factory=dict[str, TokenLiteral])
    paths: tuple[PlayPath, ...] = ()
    scope: WalkScope | None = None
    shows: tuple[ShowDecl, ...] = ()
    sequence: SequenceMode | None = None
    actors: tuple[ActorDecl, ...] = ()
    boxes: tuple[BoxDecl, ...] = ()

    def path(self, name: str) -> PlayPath | None:
        return next((path for path in self.paths if path.name == name), None)


# ── Layout and statement grammar ─────────────────────────────────────────

_PLAIN_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_INTEGER = re.compile(r"[0-9]+")
_DURATION = re.compile(
    r"(?:(?P<d>[0-9]+(?:\.[0-9]+)?)d)?"
    r"(?:(?P<h>[0-9]+(?:\.[0-9]+)?)h)?"
    r"(?:(?P<m>[0-9]+(?:\.[0-9]+)?)m)?"
    r"(?:(?P<s>[0-9]+(?:\.[0-9]+)?)s)?"
)


class _Source:
    """The whole file: offsets to 1-based line and column."""

    def __init__(self, text: str, source: str) -> None:
        self.text = text
        self.source = source
        self.line_starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self.line_starts.append(index + 1)

    def position(self, offset: int) -> Position:
        bounded = min(max(offset, 0), len(self.text))
        line = bisect_right(self.line_starts, bounded)
        return Position(line, bounded - self.line_starts[line - 1] + 1)

    def error(self, code: str, message: str, offset: int) -> PlayError:
        return PlayError(Diagnostic(code, message, self.source, self.position(offset)))


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite number {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {json.dumps(key)}")
        result[key] = value
    return result


def _seconds(value: float) -> int | float:
    if not math.isfinite(value):
        raise ValueError("non-finite time")
    return int(value) if value.is_integer() else value


def _duration_seconds(text: str) -> int | float:
    match = _DURATION.fullmatch(text)
    if match is None or not any(match.groupdict().values()):
        raise ValueError("invalid duration")
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    total = sum(
        float(value) * units[unit]
        for unit, value in match.groupdict().items()
        if value is not None
    )
    return _seconds(total)


def _collapsed(text: str, start: int, stop: int) -> str:
    return " ".join(text[start:stop].split())


def _prose_text(line: str) -> str:
    return line[3:].removeprefix(" ")


def _statements(source: _Source) -> list[tuple[str, int, int]]:
    """Split the source into ``("prose" | "blank" | "statement", start, end)``.

    A statement runs from a column-0 line through every following line that
    is blank or starts with whitespace. Its trailing blank lines are not part
    of it. A blank line between continuation lines stays inside the statement.
    """
    text = source.text
    items: list[tuple[str, int, int]] = []
    current: list[int] | None = None
    blank_after: tuple[int, int] | None = None
    for line_start in source.line_starts:
        if line_start >= len(text) and line_start > 0:
            break
        newline = text.find("\n", line_start)
        line_end = len(text) if newline < 0 else newline
        line = text[line_start:line_end]
        if not line.strip():
            if current is None:
                items.append(("blank", line_start, line_end))
            elif blank_after is None:
                blank_after = (line_start, line_end)
            continue
        if line[0] in " \t":
            if current is not None:
                current[1] = line_end
                blank_after = None
                continue
            raise source.error(
                "SC101", "a statement must start at column 0", line_start
            )
        if current is not None:
            items.append(("statement", current[0], current[1]))
            current = None
            if blank_after is not None:
                items.append(("blank", *blank_after))
                blank_after = None
        if line.startswith("///"):
            items.append(("prose", line_start, line_end))
        elif line.startswith("//"):
            continue
        else:
            current = [line_start, line_end]
    if current is not None:
        items.append(("statement", current[0], current[1]))
    return items


class _CollectingListener(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[tuple[int, int, str, Any]] = []

    def syntaxError(
        self,
        recognizer: Recognizer,
        offendingSymbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: RecognitionException | None,
    ) -> None:
        del recognizer, e
        self.errors.append((line, column, msg, offendingSymbol))


def _symbol_start(symbol: Any) -> int | None:
    start = getattr(symbol, "start", None)
    if isinstance(start, int) and start >= 0:
        return start
    return None


def _chunk_offset(chunk: str, line: int, column: int) -> int:
    offset = 0
    current = 1
    while current < line:
        newline = chunk.find("\n", offset)
        if newline < 0:
            return len(chunk)
        offset = newline + 1
        current += 1
    return min(len(chunk), offset + column)


def _node_start(node: Any) -> int:
    symbol = getattr(node, "symbol", None)
    if symbol is not None:
        start = _symbol_start(symbol)
        if start is not None:
            return start
    start = _symbol_start(getattr(node, "start", None))
    if start is not None:
        return start
    return int(node.start.start)


def _many(nodes: Any) -> list[Any]:
    if not nodes:
        return []
    return list(nodes)


def _channel_tokens(chunk: str) -> list[Any]:
    lexer = VelocitronPlayLexer(InputStream(chunk))
    lexer.removeErrorListeners()
    stream = CommonTokenStream(lexer)
    stream.fill()
    return [
        token
        for token in stream.tokens
        if token.channel == Token.DEFAULT_CHANNEL and token.type != Token.EOF
    ]


def _bad_advance_offset(chunk: str) -> int | None:
    """Offset of an advance's bad time, when the statement is an advance.

    A trailing token after a real time is a syntax error (``SC101``), so this
    returns ``None`` then. A missing time, a word, or a number that is not
    seconds (``1e2``, ``-1``) is ``SC103``.
    """
    tokens = _channel_tokens(chunk)
    if not tokens or tokens[0].type != VelocitronPlayParser.ADVANCE:
        return None
    index = 1
    if index < len(tokens) and tokens[index].type == VelocitronPlayParser.LPAREN:
        index += 1
        while index < len(tokens) and tokens[index].type != VelocitronPlayParser.RPAREN:
            index += 1
        if index >= len(tokens):
            return None
        index += 1
    if index < len(tokens) and tokens[index].type == VelocitronPlayParser.PLUS:
        index += 1
    if index >= len(tokens):
        return int(tokens[-1].start)
    token = tokens[index]
    if token.type == VelocitronPlayParser.DURATION:
        return None
    if token.type == VelocitronPlayParser.NUMBER and _PLAIN_NUMBER.fullmatch(
        token.text or ""
    ):
        return None
    return int(token.start)


_PLAY_HEADER_NAME = re.compile(r"play[ \t]+([^\s\"]\S*)")
_NOT_IDENT = re.compile(r"[^A-Za-z0-9_]")


def _bad_play_name(chunk: str) -> tuple[int, str] | None:
    """The offset of the first character a header's play name may not hold,
    and the identifier to write instead; ``None`` for any other statement.

    Play files are kebab-case, so ``play step-warning`` is the likely slip.
    """
    match = _PLAY_HEADER_NAME.match(chunk)
    if match is None:
        return None
    name = match.group(1).split("//", 1)[0]
    if not name:
        return None
    bad = _NOT_IDENT.search(name)
    if bad is not None:
        index = bad.start()
    elif name[0].isdigit():
        index = 0
    else:
        return None
    suggestion = _NOT_IDENT.sub("_", name)
    if suggestion[0].isdigit():
        suggestion = f"_{suggestion}"
    return match.start(1) + index, suggestion


@dataclass
class _PathBuilder:
    name: str
    position: Position
    title: str | None = None
    prose: list[str] = field(default_factory=list[str])
    from_label: NameRef | None = None
    steps: list[Step] = field(default_factory=list[Step])
    sequence: SequenceMode | None = None

    def build(self) -> PlayPath:
        return PlayPath(
            name=self.name,
            position=self.position,
            title=self.title,
            prose="\n\n".join(self.prose),
            from_label=self.from_label,
            steps=tuple(self.steps),
            sequence=self.sequence,
        )


class _Statement:
    """One statement's grammar tree, lowered against the original source."""

    def __init__(self, source: _Source, start: int, end: int) -> None:
        self.source = source
        self.base = start
        self.chunk = source.text[start:end]
        listener = _CollectingListener()
        lexer = VelocitronPlayLexer(InputStream(self.chunk))
        lexer.removeErrorListeners()
        lexer.addErrorListener(listener)
        stream = CommonTokenStream(lexer)
        parser = VelocitronPlayParser(stream)
        parser.removeErrorListeners()
        parser.addErrorListener(listener)
        tree = parser.statement()
        if listener.errors:
            line, column, message, symbol = listener.errors[0]
            advance = _bad_advance_offset(self.chunk)
            if advance is not None:
                raise self._error(
                    "SC103",
                    "expected seconds or a duration such as `90m`",
                    advance,
                )
            named = _bad_play_name(self.chunk)
            if named is not None:
                raise self._error(
                    "SC101",
                    "a play name is an identifier (letters, digits, `_`): "
                    f"write `{named[1]}`",
                    named[0],
                )
            offset = _symbol_start(symbol)
            if offset is None:
                offset = _chunk_offset(self.chunk, line, column)
            raise self._error("SC101", message, offset)
        self.tree = tree

    def _error(self, code: str, message: str, chunk_offset: int) -> PlayError:
        return self.source.error(code, message, self.base + chunk_offset)

    def _pos(self, chunk_offset: int) -> Position:
        return self.source.position(self.base + chunk_offset)

    def _at(self, node: Any) -> int:
        return _node_start(node)

    def _string(self, node: Any, what: str) -> str:
        offset = self._at(node)
        try:
            value = json.loads(node.getText())
        except ValueError as error:
            message = getattr(error, "msg", str(error))
            raise self._error(
                "SC102", f"invalid JSON in {what}: {message}", offset
            ) from error
        if not isinstance(value, str):
            raise self._error("SC101", f"{what} must be a string", offset)
        return value

    def _json_object(self, ctx: Any, what: str) -> dict[str, Any]:
        offset = int(ctx.start.start)
        raw = self.chunk[offset : int(ctx.stop.stop) + 1]
        try:
            value = json.loads(
                raw,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except ValueError as error:
            message = getattr(error, "msg", str(error))
            raise self._error(
                "SC102", f"invalid JSON in {what}: {message}", offset
            ) from error
        if not isinstance(value, dict):
            raise self._error("SC102", f"{what} must be a JSON object", offset)
        return cast(dict[str, Any], value)

    def _tight(self, ctx: Any) -> str:
        raw = self.chunk[int(ctx.start.start) : int(ctx.stop.stop) + 1]
        if any(character.isspace() for character in raw) or "//" in raw:
            raise self._error(
                "SC101", "a name cannot contain whitespace", int(ctx.start.start)
            )
        return raw

    def _single(self, ctx: Any) -> str:
        return str(ctx.getText())

    def _name_text(self, ctx: Any, what: str) -> str:
        if ctx.STRING() is not None:
            return self._string(ctx.STRING(), what)
        return self._tight(ctx.qualifiedName())

    def _name_ref(self, ctx: Any, what: str) -> NameRef:
        return NameRef(self._name_text(ctx, what), self._pos(int(ctx.start.start)))

    def _place(self, ctx: Any) -> NameRef:
        qualified = ctx.qualifiedName()
        return NameRef(self._tight(qualified), self._pos(int(qualified.start.start)))

    def _transition(self, ctx: Any) -> NameRef:
        qualified = ctx.qualifiedName()
        return NameRef(self._tight(qualified), self._pos(int(qualified.start.start)))

    def _color(self, ctx: Any, what: str) -> str:
        if ctx.STRING() is not None:
            return self._string(ctx.STRING(), what)
        unquoted = getattr(ctx, "singleNameNotSequence", None)
        if unquoted is not None and unquoted() is not None:
            return self._single(unquoted())
        return self._single(ctx.singleName())

    def _field(self, ctx: Any) -> str:
        if ctx.STRING() is not None:
            path = self._string(ctx.STRING(), "a field name")
            offset = self._at(ctx.STRING())
        else:
            path = self._tight(ctx.qualifiedName())
            offset = int(ctx.start.start)
        if not path or any(not key for key in path.split(".")):
            raise self._error("SC101", f"invalid field path {json.dumps(path)}", offset)
        return path

    def _integer(self, node: Any, what: str) -> int:
        text = str(node.getText())
        if _INTEGER.fullmatch(text) is None:
            raise self._error("SC101", f"expected {what}", self._at(node))
        return int(text)

    def _time(self, ctx: Any | None) -> int | float:
        if ctx is None or ctx.singleName() is not None:
            offset = 0 if ctx is None else int(ctx.start.start)
            raise self._error(
                "SC103",
                "expected seconds or a duration such as `90m`",
                offset,
            )
        number = ctx.NUMBER()
        if number is not None:
            text = str(number.getText())
            if _PLAIN_NUMBER.fullmatch(text) is None:
                raise self._error(
                    "SC103",
                    "expected seconds or a duration such as `90m`",
                    self._at(number),
                )
            return _seconds(float(text))
        try:
            return _duration_seconds(str(ctx.DURATION().getText()))
        except ValueError as error:
            raise self._error(
                "SC103",
                "expected seconds or a duration such as `90m`",
                int(ctx.start.start),
            ) from error

    def _token(self, ctx: Any, what: str) -> TokenExpr:
        position = self._pos(int(ctx.start.start))
        if ctx.DOLLAR() is not None:
            return NameRef(self._single(ctx.singleName()), position)
        data = self._json_object(ctx.jsonObject(), what)
        if ctx.color() is None:
            return TokenLiteral(None, data, position)
        return TokenLiteral(self._color(ctx.color(), "a color"), data, position)

    def _tokens(self, ctx: Any, what: str) -> tuple[TokenExpr, ...]:
        return tuple(self._token(token, what) for token in _many(ctx.tokenExpr()))

    def _wire_end(self, ctx: Any) -> tuple[str, str]:
        return self._single(ctx.singleName()), self._place(ctx.place()).name

    def _condition(self, ctx: Any) -> Condition:
        position = self._pos(int(ctx.start.start))
        text = _collapsed(self.chunk, int(ctx.start.start), int(ctx.stop.stop) + 1)
        if ctx.EQ() is not None:
            return Condition(
                "equals",
                text,
                position,
                place=self._place(ctx.place()),
                tokens=self._tokens(ctx.tokenList(), "token data"),
            )
        if ctx.EMPTY() is not None:
            return Condition("empty", text, position, place=self._place(ctx.place()))
        if ctx.COUNT() is not None:
            return Condition(
                "count",
                text,
                position,
                place=self._place(ctx.place()),
                count=self._integer(ctx.NUMBER(), "a token count"),
            )
        if ctx.HAS() is not None:
            return Condition(
                "has",
                text,
                position,
                place=self._place(ctx.place()),
                tokens=(self._token(ctx.tokenExpr(), "token data"),),
            )
        transitions = tuple(self._transition(item) for item in _many(ctx.transition()))
        if ctx.NOT() is not None:
            kind: ConditionKind = "not-enabled"
        elif ctx.ENABLED() is not None:
            kind = "enabled"
        elif ctx.NEXT() is not None:
            kind = "next"
        else:
            kind = "quiescent"
        return Condition(kind, text, position, transitions=transitions)

    def _with_clause(self, ctx: Any) -> WithClause:
        place = self._place(ctx.place())
        if ctx.DOLLAR() is not None:
            name = ctx.singleName()
            return WithClause(
                place,
                template=NameRef(self._single(name), self._pos(int(name.start.start))),
            )
        if ctx.HASH() is not None:
            return WithClause(place, index=self._integer(ctx.NUMBER(), "a token index"))
        return WithClause(place, subset=self._json_object(ctx.jsonObject(), "a subset"))

    def _output(self, ctx: Any) -> OutputClause:
        place = self._place(ctx.place())
        if ctx.NOTHING() is not None:
            return OutputClause(place, nothing=True)
        if ctx.PLUS() is not None:
            return OutputClause(
                place, merge=self._json_object(ctx.jsonObject(), "the merged fields")
            )
        return OutputClause(place, tokens=self._tokens(ctx.tokenList(), "token data"))

    def _truth(self, ctx: Any) -> bool:
        word = str(ctx.getText())
        if word in ("true", "false"):
            return word == "true"
        raise self._error(
            "SC101",
            "expected `true` or `false`",
            int(ctx.start.start),
        )

    def _step(self, ctx: Any) -> Step:
        body_ctx = ctx.stepBody()
        label_ctx = ctx.label()
        label = None if label_ctx is None else self._single(label_ctx.singleName())
        title = None
        if ctx.STRING() is not None:
            title = self._string(ctx.STRING(), "the step title")
            body_end = self._at(ctx.STRING())
        else:
            body_end = len(self.chunk)
        body_start = int(body_ctx.start.start)
        if body_ctx.injectBody() is not None:
            inject = body_ctx.injectBody()
            body: StepBody = InjectBody(
                self._place(inject.place()),
                self._tokens(inject.tokenList(), "token data"),
            )
            kind: StepKind = "inject"
        elif body_ctx.updateBody() is not None:
            update = body_ctx.updateBody()
            body = UpdateBody(
                self._place(update.place()),
                self._token(update.tokenExpr(), "token data"),
            )
            kind = "update"
        elif body_ctx.advanceBody() is not None:
            advance = body_ctx.advanceBody()
            place = None if advance.place() is None else self._place(advance.place())
            body = AdvanceBody(
                place,
                self._time(advance.timeValue()),
                advance.PLUS() is not None,
            )
            kind = "advance"
        elif body_ctx.fireBody() is not None:
            fire = body_ctx.fireBody()
            body = FireBody(
                self._transition(fire.transition()),
                tuple(self._with_clause(item) for item in _many(fire.withClause())),
                tuple(self._output(item) for item in _many(fire.outputClause())),
            )
            kind = "fire"
        elif body_ctx.expectBody() is not None:
            expect = body_ctx.expectBody()
            body = ExpectBody(
                tuple(self._condition(item) for item in _many(expect.condition()))
            )
            kind = "expect"
        else:
            assume = body_ctx.assumeBody()
            if assume is None:
                raise self._error("SC101", "expected an assume statement", body_start)
            if assume.PREDICATE() is not None:
                body = AssumePredicateBody(
                    self._string(assume.STRING(), "a predicate handler ref"),
                    self._truth(assume.truthValue()),
                    self._pos(self._at(assume.STRING())),
                )
            else:
                body = AssumeGuardBody(
                    self._transition(assume.transition()),
                    self._truth(assume.truthValue()),
                )
            kind = "assume"
        return Step(
            kind=kind,
            body=body,
            statement=_collapsed(self.chunk, body_start, body_end),
            position=self._pos(0),
            label=label,
            title=title,
        )

    def string(self, node: Any, what: str) -> str:
        return self._string(node, what)

    def single(self, ctx: Any) -> str:
        return self._single(ctx)

    def name_text(self, ctx: Any, what: str) -> str:
        return self._name_text(ctx, what)

    def wire_end(self, ctx: Any) -> tuple[str, str]:
        return self._wire_end(ctx)

    def token(self, ctx: Any, what: str) -> TokenExpr:
        return self._token(ctx, what)

    def transition(self, ctx: Any) -> NameRef:
        return self._transition(ctx)

    def color(self, ctx: Any, what: str) -> str:
        return self._color(ctx, what)

    def field(self, ctx: Any) -> str:
        return self._field(ctx)

    def json_object(self, ctx: Any, what: str) -> dict[str, Any]:
        return self._json_object(ctx, what)

    def pos(self, chunk_offset: int) -> Position:
        return self._pos(chunk_offset)

    def step(self, ctx: Any) -> Step:
        return self._step(ctx)


def _with_prose(step: Step, prose: str) -> Step:
    return Step(
        kind=step.kind,
        body=step.body,
        statement=step.statement,
        position=step.position,
        label=step.label,
        title=step.title,
        prose=prose,
    )


def parse_play(
    text: str, source: str = "<memory>", *, origin: Path | None = None
) -> Play:
    """Parse ``.play`` source text. Raises :class:`PlayError` (SC1xx).

    ``origin`` is the directory that ``net`` and ``use`` paths resolve
    against; ``source`` names the file in diagnostics. The statement syntax
    is ``VelocitronPlay.g4``; this function also applies the line discipline
    and the ``SC104`` / ``SC105`` rules.
    """
    src = _Source(text, source)
    header: dict[str, Any] = {}
    header_prose: list[str] = []
    uses: list[UseDecl] = []
    wires: list[WireDecl] = []
    refines: list[RefineDecl] = []
    shares: list[ShareDecl] = []
    shows: list[ShowDecl] = []
    actors: list[ActorDecl] = []
    boxes: list[BoxDecl] = []
    templates: dict[str, TokenLiteral] = {}
    paths: list[_PathBuilder] = []
    labels: dict[str, Position] = {}
    pending: list[list[str]] = []
    block_open = False
    after_header_line = False

    def take_pending() -> str:
        text_ = "\n\n".join("\n".join(block) for block in pending)
        pending.clear()
        return text_

    def scope_prose() -> list[str]:
        if not paths or paths[-1].name == TRUNK:
            return header_prose
        return paths[-1].prose

    def attach_setting_prose() -> None:
        if pending:
            scope_prose().append(take_pending())

    for kind, start, end in _statements(src):
        if kind == "blank":
            block_open = False
            after_header_line = False
            continue
        line_text = src.text[start:end]
        if kind == "prose":
            if after_header_line:
                blocks = scope_prose()
                if block_open:
                    blocks[-1] += "\n" + _prose_text(line_text)
                else:
                    blocks.append(_prose_text(line_text))
                block_open = True
                continue
            if not block_open:
                pending.append([])
            pending[-1].append(_prose_text(line_text))
            block_open = True
            continue
        block_open = False
        after_header_line = False
        parsed = _Statement(src, start, end)
        tree = parsed.tree
        if not header:
            header_ctx = tree.header()
            if header_ctx is None:
                raise src.error(
                    "SC104",
                    'a play starts with `play NAME ["title"]`',
                    start,
                )
            position = src.position(start)
            title = (
                None
                if header_ctx.STRING() is None
                else parsed.string(header_ctx.STRING(), "the title")
            )
            header["name"] = parsed.single(header_ctx.singleName())
            header["title"] = title
            header["position"] = position
            header_prose.extend(filter(None, [take_pending()]))
            paths.append(_PathBuilder(TRUNK, position))
            after_header_line = True
            continue
        if tree.header() is not None:
            raise src.error("SC104", "a source holds one `play` header", start)
        sequence = tree.sequenceShow()
        if sequence is not None:
            mode: SequenceMode = "only" if sequence.ONLY() is not None else "beside"
            branch = paths[-1] if paths[-1].name != TRUNK else None
            current_sequence = (
                branch.sequence if branch is not None else header.get("sequence")
            )
            if current_sequence is not None:
                scope_name = "the play" if branch is None else f"path {branch.name}"
                raise src.error(
                    "SC104",
                    f"{scope_name} names its sequence view twice",
                    start,
                )
            if branch is not None:
                branch.sequence = mode
            else:
                header["sequence"] = mode
            attach_setting_prose()
            continue
        box = tree.boxSetting()
        if box is not None:
            names = _many(box.name())
            title = parsed.name_text(names[0], "the box title")
            members = [parsed.name_text(name, "a lifeline name") for name in names[1:]]
            boxed = {member for declared in boxes for member in declared.members}
            for member in members:
                if member in boxed or members.count(member) > 1:
                    raise src.error(
                        "SC105", f"lifeline {member} is in two boxes", start
                    )
            boxes.append(BoxDecl(title, tuple(members), src.position(start)))
            attach_setting_prose()
            continue
        actor = tree.actorSetting()
        if actor is not None:
            kind_ctx = actor.actorKind()
            if kind_ctx is None:
                raise src.error("SC101", "expected an actor kind", start)
            if kind_ctx.PERSON() is not None:
                actor_kind: ActorKind = "person"
            elif kind_ctx.SYSTEM() is not None:
                actor_kind = "system"
            else:
                actor_kind = "record"
            actor_name = parsed.name_text(actor.name(), "an actor name")
            if not actor_name:
                raise src.error("SC101", "an actor name must not be empty", start)
            if any(declared.name == actor_name for declared in actors):
                raise src.error("SC105", f"actor {actor_name} is declared twice", start)
            actors.append(ActorDecl(actor_name, actor_kind, src.position(start)))
            attach_setting_prose()
            continue
        net = tree.netSetting()
        if net is not None:
            if "net" in header:
                raise src.error("SC104", "the play names its net twice", start)
            header["net"] = parsed.string(net.STRING(), "the net file")
            header["net_position"] = src.position(start)
            attach_setting_prose()
            continue
        use = tree.useSetting()
        if use is not None:
            alias = parsed.single(use.singleName())
            if any(declared.alias == alias for declared in uses):
                raise src.error("SC105", f"alias {alias} is used twice", start)
            uses.append(
                UseDecl(
                    parsed.string(use.STRING(), "the net file"),
                    alias,
                    src.position(start),
                )
            )
            attach_setting_prose()
            continue
        wire = tree.wireSetting()
        if wire is not None:
            ends = _many(wire.wireEnd())
            from_alias, from_place = parsed.wire_end(ends[0])
            to_alias, to_place = parsed.wire_end(ends[1])
            wires.append(
                WireDecl(
                    from_alias, from_place, to_alias, to_place, src.position(start)
                )
            )
            attach_setting_prose()
            continue
        share = tree.shareSetting()
        if share is not None:
            members_share = tuple(
                parsed.wire_end(end) for end in _many(share.wireEnd())
            )
            shares.append(ShareDecl(members_share, src.position(start)))
            attach_setting_prose()
            continue
        refine = tree.refineSetting()
        if refine is not None:
            aliases = _many(refine.singleName())
            refines.append(
                RefineDecl(
                    parsed.single(aliases[0]),
                    parsed.transition(refine.transition()).name,
                    parsed.single(aliases[1]),
                    src.position(start),
                )
            )
            attach_setting_prose()
            continue
        instance = tree.instanceSetting()
        if instance is not None:
            if "instance" in header:
                raise src.error("SC104", "the play names its instance twice", start)
            header["instance"] = parsed.token(instance.tokenExpr(), "token data")
            header["instance_position"] = src.position(start)
            attach_setting_prose()
            continue
        scope_ctx = tree.scopeSetting()
        if scope_ctx is not None:
            if "scope" in header:
                raise src.error("SC104", "the play names its scope twice", start)
            if scope_ctx.STEP() is not None:
                header["scope"] = "step"
            elif scope_ctx.NEIGHBORS() is not None:
                header["scope"] = "neighbors"
            else:
                header["scope"] = "subnet"
            attach_setting_prose()
            continue
        show = tree.colorShow()
        if show is not None:
            color = parsed.color(show.colorNotSequence(), "a color")
            if any(declared.color == color for declared in shows):
                raise src.error("SC104", f"the play shows color {color} twice", start)
            fields = [
                parsed.field(field_path) for field_path in _many(show.fieldPath())
            ]
            if len(set(fields)) != len(fields):
                raise src.error("SC101", f"`show {color}` repeats a field", start)
            shows.append(ShowDecl(color, tuple(fields), src.position(start)))
            attach_setting_prose()
            continue
        marking = tree.markingSetting()
        if marking is not None:
            if "marking" in header:
                raise src.error("SC104", "the play names its marking twice", start)
            header["marking"] = parsed.name_text(
                marking.name(), "`initial`, `none` or a marking name"
            )
            header["marking_position"] = src.position(start)
            attach_setting_prose()
            continue
        template = tree.templateDecl()
        if template is not None:
            name_node = template.singleName()
            color_ctx = template.color()
            data_ctx = template.jsonObject()
            if (
                name_node is None
                or color_ctx is None
                or data_ctx is None
                or color_ctx.start is None
            ):
                raise src.error("SC101", "expected a template", start)
            name = parsed.single(name_node)
            if name in templates:
                raise src.error("SC105", f"template ${name} is defined twice", start)
            templates[name] = TokenLiteral(
                parsed.color(color_ctx, "a color"),
                parsed.json_object(data_ctx, "template data"),
                parsed.pos(int(color_ctx.start.start)),
            )
            attach_setting_prose()
            continue
        path_ctx = tree.pathDecl()
        if path_ctx is not None:
            names = _many(path_ctx.singleName())
            name = parsed.single(names[0])
            if name == TRUNK or any(path.name == name for path in paths):
                raise src.error(
                    "SC105",
                    f"path name {name} is already taken"
                    + (" (the first path is the trunk)" if name == TRUNK else ""),
                    parsed.base + _node_start(names[0]),
                )
            title = (
                None
                if path_ctx.STRING() is None
                else parsed.string(path_ctx.STRING(), "the title")
            )
            label_at = path_ctx.AT()
            label = NameRef(
                parsed.single(names[1]),
                parsed.pos(_node_start(label_at)),
            )
            builder = _PathBuilder(name, src.position(start), title, from_label=label)
            prose = take_pending()
            if prose:
                builder.prose.append(prose)
            paths.append(builder)
            after_header_line = True
            continue
        step_ctx = tree.step()
        if step_ctx is None:
            raise src.error("SC101", "expected a play statement", start)
        step = parsed.step(step_ctx)
        if step.label is not None:
            if step.label in labels:
                raise src.error("SC105", f"label @{step.label} is used twice", start)
            labels[step.label] = step.position
        prose = take_pending()
        if prose:
            step = _with_prose(step, prose)
        paths[-1].steps.append(step)

    if not header:
        raise src.error("SC104", "a play starts with `play NAME`", 0)
    if pending:
        trailing = take_pending()
        scope = paths[-1]
        if scope.steps:
            last = scope.steps[-1]
            scope.steps[-1] = _with_prose(
                last, f"{last.prose}\n\n{trailing}" if last.prose else trailing
            )
        else:
            scope_prose().append(trailing)
    return Play(
        name=header["name"],
        source=source,
        position=header["position"],
        title=header["title"],
        prose="\n\n".join(header_prose),
        origin=origin,
        net=header.get("net"),
        net_position=header.get("net_position"),
        uses=tuple(uses),
        wires=tuple(wires),
        refines=tuple(refines),
        shares=tuple(shares),
        marking=header.get("marking", "initial"),
        marking_position=header.get("marking_position"),
        instance=header.get("instance"),
        instance_position=header.get("instance_position"),
        templates=templates,
        paths=tuple(path.build() for path in paths),
        scope=header.get("scope"),
        shows=tuple(shows),
        sequence=header.get("sequence"),
        actors=tuple(actors),
        boxes=tuple(boxes),
    )


def read_play(path: Path | str) -> Play:
    """Read and parse a ``.play`` file; its directory is the origin."""
    file = Path(path)
    with file.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    return parse_play(text, str(path), origin=file.parent)


def step_label_names(paths: Sequence[PlayPath]) -> dict[str, tuple[int, int]]:
    """Each label → (path index, step index) of the step that carries it."""
    found: dict[str, tuple[int, int]] = {}
    for path_index, path in enumerate(paths):
        for step_index, step in enumerate(path.steps):
            if step.label is not None:
                found[step.label] = (path_index, step_index)
    return found
