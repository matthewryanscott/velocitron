"""Lower one ``.petrinet`` document into contribution IR.

``lower_petrinet_text`` is the portable lowering step. This module is the
source of truth. CEL compilation and contribution resolution ship in
``velocitron_petrinet``. Canonical emission stays in ``velocitron_dsl``.
The CLI ships in ``velocitron_cli``. This module does not import ``velocitron`` or the
package root.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any, Final, NoReturn, cast

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext, Token
from antlr4.Recognizer import Recognizer
from antlr4.error.ErrorListener import ErrorListener
from antlr4.error.Errors import RecognitionException

from .diagnostics import (
    Diagnostic,
    PetrinetDslError,
    SourcePosition,
    SourceSpan,
)

# TODO: this lowerer vendors a second copy of the ANTLR parser that
# packages/grammar already generates. Layer lint forbids importing
# velocitron_grammar.generated, and grammar's public parse_petrinet returns
# a tree without the token types and visitor base this module subclasses.
# Teach grammar to export that surface, then import it here.
# packages/petrinet calls lower_petrinet_text and does not vendor another copy.
from .generated.VelocitronPetriNetLexer import VelocitronPetriNetLexer
from .generated.VelocitronPetriNetParser import VelocitronPetriNetParser
from .generated.VelocitronPetriNetVisitor import VelocitronPetriNetVisitor

__all__ = [
    "VIEW_DETAILS",
    "VIEW_SPLINES",
    "json_values_equal",
    "lower_petrinet_text",
    "valid_field_path",
]

_FORMAT = "velocitron.petrinet/contribution-ir"
_VERSION = 1

_JSON_NUMBER = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
VIEW_SPLINES: Final[tuple[str, ...]] = ("ortho", "spline", "curved", "polyline", "line")
VIEW_DETAILS: Final[tuple[str, ...]] = ("full", "summary", "structure")


class _SourceMap:
    def __init__(self, source_id: str, text: str) -> None:
        self.source_id = source_id
        self.text = text
        self._line_starts = [0]
        for index, character in enumerate(text):
            if character == "\n":
                self._line_starts.append(index + 1)

    def position(self, index: int) -> SourcePosition:
        index = max(0, min(index, len(self.text)))
        line_index = 0
        for candidate, start in enumerate(self._line_starts):
            if start > index:
                break
            line_index = candidate
        start = self._line_starts[line_index]
        return SourcePosition(
            byte_offset=len(self.text[:index].encode("utf-8")),
            line=line_index + 1,
            column=index - start + 1,
        )

    def span(self, start: int, end: int) -> SourceSpan:
        return SourceSpan(self.source_id, self.position(start), self.position(end))


_JSON_PRIMITIVE_TOKENS: Final = frozenset(
    {
        VelocitronPetriNetParser.STRING,
        VelocitronPetriNetParser.NUMBER,
        VelocitronPetriNetParser.POSITIVE_INTEGER,
        VelocitronPetriNetParser.ZERO,
        VelocitronPetriNetParser.TRUE,
        VelocitronPetriNetParser.FALSE,
        VelocitronPetriNetParser.NULL,
    }
)


def _has_prior_net_body(context: ParserRuleContext | None) -> bool:
    # Keep the header-only grammar probe; only after a net body is a complete
    # JSON value read as a non-object extensions value.
    extensions_context = None if context is None else context.parentCtx
    document_context = (
        None if extensions_context is None else extensions_context.parentCtx
    )
    if (
        context is None
        or context.getRuleIndex() != VelocitronPetriNetParser.RULE_jsonObject
        or extensions_context is None
        or extensions_context.getRuleIndex() != VelocitronPetriNetParser.RULE_extensions
        or not isinstance(document_context, ParserRuleContext)
        or document_context.getRuleIndex() != VelocitronPetriNetParser.RULE_document
    ):
        return False
    children = cast(list[object], document_context.children or [])
    return any(
        isinstance(child, ParserRuleContext)
        and child.getRuleIndex()
        not in (
            VelocitronPetriNetParser.RULE_netHeader,
            VelocitronPetriNetParser.RULE_extensions,
        )
        for child in children
    )


def _non_object_extensions_end(
    recognizer: Recognizer, offending: Token, text: str
) -> int | None:
    """End index of a non-object JSON value given to ``extensions``, if it is one."""
    if not isinstance(recognizer, VelocitronPetriNetParser) or not _has_prior_net_body(
        recognizer._ctx
    ):
        return None
    end = offending.stop + 1 if offending.type in _JSON_PRIMITIVE_TOKENS else None
    if offending.type == VelocitronPetriNetParser.LBRACK:
        stream = recognizer.getTokenStream()
        if not isinstance(stream, CommonTokenStream):
            return None
        stream.fill()
        depth = 0
        for token in stream.tokens[offending.tokenIndex :]:
            if token.channel != Token.DEFAULT_CHANNEL:
                continue
            if token.type == VelocitronPetriNetParser.LBRACK:
                depth += 1
            elif token.type == VelocitronPetriNetParser.RBRACK:
                depth -= 1
                if depth == 0:
                    end = token.stop + 1
                    break
            elif token.type == Token.EOF:
                break
    if end is None:
        return None
    try:
        value = json.loads(
            text[offending.start : end], parse_constant=_reject_json_constant
        )
    except ValueError:
        return None
    return None if isinstance(value, dict) else end


def _reject_json_constant(constant: str) -> NoReturn:
    raise ValueError(f"not JSON: {constant}")


class _SyntaxListener(ErrorListener):
    def __init__(self, source: _SourceMap) -> None:
        self.source = source
        self.diagnostics: list[Diagnostic] = []

    def syntaxError(
        self,
        recognizer: Recognizer,
        offendingSymbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: RecognitionException | None,
    ) -> None:
        del line, column, e
        start = (
            len(self.source.text) if offendingSymbol is None else offendingSymbol.start
        )
        end = start if offendingSymbol is None else max(start, offendingSymbol.stop + 1)
        if offendingSymbol is not None and offendingSymbol.type == Token.EOF:
            start = end = len(self.source.text)
        help_text: str | None = None
        extensions_end = (
            None
            if offendingSymbol is None
            else _non_object_extensions_end(
                recognizer, offendingSymbol, self.source.text
            )
        )
        if extensions_end is not None:
            msg = "extensions requires a JSON object"
            help_text = "replace the value with a JSON object"
            end = extensions_end
        elif "expecting IDENT" in msg or msg.startswith("missing IDENT at "):
            if msg.startswith("missing IDENT at ") and offendingSymbol is not None:
                msg = f"mismatched input {offendingSymbol.text!r} expecting identifier"
            else:
                msg = msg.replace("expecting IDENT", "expecting identifier")
            help_text = "add a mandatory identifier alias after as"
        self.diagnostics.append(
            Diagnostic("PN101", msg, self.source.span(start, end), help_text)
        )


def contains_isolated_surrogate(value: str) -> bool:
    """Whether ``value`` holds a UTF-16 surrogate code point on its own."""
    return _contains_surrogate(value)


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _valid_capacity_key(value: object) -> bool:
    if isinstance(value, str):
        return bool(value)
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(item, str) and bool(item) for item in cast(list[object], value)
    )


def valid_capacity_key(value: object) -> bool:
    """Whether ``value`` is a capacity key the lowerer accepts."""
    return _valid_capacity_key(value)


def _decode_name(text: str) -> str:
    return json.loads(text) if text.startswith('"') else text


def _composition_path(ctx: Any) -> str:
    """The dotted name inside ``(...)`` or ``[...]`` of a composition fact."""
    return ".".join(_decode_name(name.getText()) for name in ctx.name())


def _tag(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, (int, float)):
        return {"type": "number", "lexeme": str(value).lower()}
    if isinstance(value, list):
        items = cast(list[Any], value)
        return {"type": "array", "items": [_tag(item) for item in items]}
    if isinstance(value, dict):
        entries = cast(dict[str, Any], value)
        return {
            "type": "object",
            "entries": [
                {"key": key, "value": _tag(item)} for key, item in entries.items()
            ],
        }
    raise TypeError(f"not a JSON value: {value!r}")


def _untag(value: Mapping[str, Any]) -> Any:
    kind = value.get("type")
    if kind == "null":
        if set(value) != {"type"}:
            raise ValueError("null has unexpected members")
        return None
    if kind == "boolean":
        if set(value) != {"type", "value"} or not isinstance(value["value"], bool):
            raise ValueError("invalid boolean")
        return value["value"]
    if kind == "string":
        if set(value) != {"type", "value"} or not isinstance(value["value"], str):
            raise ValueError("invalid string")
        if _contains_surrogate(value["value"]):
            raise ValueError("string contains an isolated surrogate")
        return value["value"]
    if kind == "number":
        lexeme = value.get("lexeme")
        if (
            set(value) != {"type", "lexeme"}
            or not isinstance(lexeme, str)
            or _JSON_NUMBER.fullmatch(lexeme) is None
        ):
            raise ValueError("invalid number")
        parsed = float(lexeme)
        if not math.isfinite(parsed):
            raise ValueError("number must be finite")
        if (
            all(marker not in lexeme for marker in ".eE")
            and abs(int(lexeme)) > 9007199254740991
        ):
            raise ValueError("integer exceeds the safe IEEE-754 range")
        return int(lexeme) if all(marker not in lexeme for marker in ".eE") else parsed
    if kind == "array":
        items = value.get("items")
        if set(value) != {"type", "items"} or not isinstance(items, list):
            raise ValueError("invalid array")
        typed_items = cast(list[Any], items)
        if not all(isinstance(item, Mapping) for item in typed_items):
            raise ValueError("invalid array")
        return [_untag(cast(Mapping[str, Any], item)) for item in typed_items]
    if kind == "object":
        entries = value.get("entries")
        if set(value) != {"type", "entries"} or not isinstance(entries, list):
            raise ValueError("invalid object")
        result: dict[str, Any] = {}
        for raw_entry in cast(list[Any], entries):
            if not isinstance(raw_entry, Mapping):
                raise ValueError("invalid object entry")
            entry = cast(Mapping[str, Any], raw_entry)
            if set(entry) != {"key", "value"}:
                raise ValueError("invalid object entry")
            key = entry["key"]
            raw_value = entry["value"]
            if (
                not isinstance(key, str)
                or key in result
                or not isinstance(raw_value, Mapping)
            ):
                raise ValueError("invalid or duplicate object key")
            result[key] = _untag(cast(Mapping[str, Any], raw_value))
        return result
    raise ValueError("unknown tagged JSON value")


def untag_json_value(value: Mapping[str, Any]) -> Any:
    """Unwrap one tagged JSON value produced by the lowerer."""
    return _untag(value)


def json_values_equal(left: Any, right: Any) -> bool:
    """Compare decoded JSON values using JSON, rather than Python, scalar types."""
    left_is_number = isinstance(left, (int, float)) and not isinstance(left, bool)
    right_is_number = isinstance(right, (int, float)) and not isinstance(right, bool)
    if left_is_number or right_is_number:
        return left_is_number and right_is_number and bool(left == right)
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        typed_left = cast(list[Any], left)
        typed_right = cast(list[Any], right)
        return len(typed_left) == len(typed_right) and all(
            json_values_equal(left_item, right_item)
            for left_item, right_item in zip(typed_left, typed_right, strict=True)
        )
    if isinstance(left, dict):
        typed_left = cast(dict[str, Any], left)
        typed_right = cast(dict[str, Any], right)
        return len(typed_left) == len(typed_right) and all(
            key in typed_right and json_values_equal(value, typed_right[key])
            for key, value in typed_left.items()
        )
    return bool(left == right)


class _LoweringVisitor(VelocitronPetriNetVisitor):
    def __init__(self, source: _SourceMap) -> None:
        super().__init__()
        self.source = source
        self.contributions: list[dict[str, Any]] = []
        self.document_kind: str | None = None
        self._statement = 0

    def _json_error(self, message: str, ctx: Any) -> None:
        raise PetrinetDslError(
            Diagnostic(
                "PN101",
                message,
                self.source.span(ctx.start.start, ctx.stop.stop + 1),
            )
        )

    def _semantic_error(self, message: str, ctx: Any) -> None:
        raise PetrinetDslError(
            Diagnostic(
                "PN202",
                message,
                self.source.span(ctx.start.start, ctx.stop.stop + 1),
            )
        )

    def _lower_json_value(self, ctx: Any) -> dict[str, Any]:
        # A domainValue is a jsonValue without objects, arrays and null.
        if hasattr(ctx, "jsonObject") and ctx.jsonObject() is not None:
            return self._lower_json_object(ctx.jsonObject())
        if hasattr(ctx, "jsonArray") and ctx.jsonArray() is not None:
            return {
                "type": "array",
                "items": [
                    self._lower_json_value(item) for item in ctx.jsonArray().jsonValue()
                ],
            }
        string = ctx.STRING()
        if string is not None:
            value = json.loads(string.getText())
            if _contains_surrogate(value):
                self._json_error("JSON string contains an isolated surrogate", ctx)
            return {"type": "string", "value": value}
        number = ctx.NUMBER()
        if number is None and hasattr(ctx, "POSITIVE_INTEGER"):
            number = ctx.POSITIVE_INTEGER()
        if number is None and hasattr(ctx, "ZERO"):
            number = ctx.ZERO()
        if number is not None:
            lexeme = number.getText()
            parsed = float(lexeme)
            if not math.isfinite(parsed):
                self._json_error("JSON number must be finite IEEE-754 binary64", ctx)
            if (
                all(marker not in lexeme for marker in ".eE")
                and abs(int(lexeme)) > 9007199254740991
            ):
                self._json_error("JSON integer exceeds the safe IEEE-754 range", ctx)
            return {"type": "number", "lexeme": lexeme}
        if ctx.TRUE() is not None:
            return {"type": "boolean", "value": True}
        if ctx.FALSE() is not None:
            return {"type": "boolean", "value": False}
        return {"type": "null"}

    def _lower_json_object(self, ctx: Any) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        keys: set[str] = set()
        for key_token, value_ctx in zip(ctx.STRING(), ctx.jsonValue(), strict=True):
            key = json.loads(key_token.getText())
            if _contains_surrogate(key):
                self._json_error("JSON object key contains an isolated surrogate", ctx)
            if key in keys:
                self._json_error(f"duplicate JSON object key {key!r}", ctx)
            keys.add(key)
            entries.append({"key": key, "value": self._lower_json_value(value_ctx)})
        return {"type": "object", "entries": entries}

    def _span(self, start: int, end: int) -> dict[str, Any]:
        return self.source.span(start, end).as_dict()

    def _contribution(
        self,
        *,
        kind: str,
        target: dict[str, Any],
        value: dict[str, Any],
        start: int,
        end: int,
        part: int = 0,
    ) -> None:
        statement = self._statement
        self.contributions.append(
            {
                "id": {
                    "source": self.source.source_id,
                    "statement": statement,
                    "part": part,
                },
                "kind": kind,
                "ordinal": len(self.contributions),
                "span": self._span(start, end),
                "target": target,
                "value": value,
            }
        )

    def visitDocument(self, ctx: Any) -> None:
        wrapper_accessors = {
            VelocitronPetriNetParser.AdditionalChainContext: "chain",
            VelocitronPetriNetParser.AdditionalTransitionHandlerContext: (
                "transitionHandler"
            ),
            VelocitronPetriNetParser.AdditionalInitialMarkingContext: (
                "initialMarking"
            ),
            VelocitronPetriNetParser.AdditionalTemplateDefinitionContext: (
                "templateDefinition"
            ),
        }
        statement_types = (
            VelocitronPetriNetParser.NetHeaderContext,
            VelocitronPetriNetParser.CompositionHeaderContext,
            VelocitronPetriNetParser.CompositionUseContext,
            VelocitronPetriNetParser.CompositionWireContext,
            VelocitronPetriNetParser.CompositionShareContext,
            VelocitronPetriNetParser.CompositionRefineContext,
            VelocitronPetriNetParser.CompositionFinalContext,
            VelocitronPetriNetParser.ChainContext,
            VelocitronPetriNetParser.PlaceDeclarationContext,
            VelocitronPetriNetParser.TransitionDeclarationContext,
            VelocitronPetriNetParser.TransitionHandlerContext,
            VelocitronPetriNetParser.TransitionGuardContext,
            VelocitronPetriNetParser.TransitionTimerContext,
            VelocitronPetriNetParser.TransitionTimerMaturityContext,
            VelocitronPetriNetParser.TransitionTimerBindContext,
            VelocitronPetriNetParser.TransitionBindingNameContext,
            VelocitronPetriNetParser.TransitionPriorityContext,
            VelocitronPetriNetParser.TransitionOrderContext,
            VelocitronPetriNetParser.ChainOrderContext,
            VelocitronPetriNetParser.PlacePortContext,
            VelocitronPetriNetParser.PlaceAcceptsContext,
            VelocitronPetriNetParser.PlaceCapacityContext,
            VelocitronPetriNetParser.ArcWeightContext,
            VelocitronPetriNetParser.ArcDataContext,
            VelocitronPetriNetParser.ArcPredicateContext,
            VelocitronPetriNetParser.ArcCorrelateContext,
            VelocitronPetriNetParser.InitialMarkingContext,
            VelocitronPetriNetParser.TemplateDefinitionContext,
            VelocitronPetriNetParser.NamedMarkingContext,
            VelocitronPetriNetParser.MetadataDescriptionContext,
            VelocitronPetriNetParser.MetadataAnnotationContext,
            VelocitronPetriNetParser.ViewPositionContext,
            VelocitronPetriNetParser.ViewRouteContext,
            VelocitronPetriNetParser.ViewSplinesContext,
            VelocitronPetriNetParser.ViewDetailContext,
            VelocitronPetriNetParser.DecorationContext,
            VelocitronPetriNetParser.ExtensionsContext,
            VelocitronPetriNetParser.DomainDeclarationContext,
            VelocitronPetriNetParser.FinalDeclarationContext,
            VelocitronPetriNetParser.InvariantDeclarationContext,
            VelocitronPetriNetParser.ActorAssignmentContext,
            VelocitronPetriNetParser.ActorDeclarationContext,
            VelocitronPetriNetParser.PlaceLivesContext,
            VelocitronPetriNetParser.PlaceReadsAsContext,
            VelocitronPetriNetParser.PlaceKeptContext,
        )
        for child in ctx.children:
            accessor = next(
                (
                    name
                    for wrapper_type, name in wrapper_accessors.items()
                    if isinstance(child, wrapper_type)
                ),
                None,
            )
            if accessor is not None:
                child = getattr(child, accessor)()
            if isinstance(child, statement_types):
                self.visit(child)
                self._statement += 1

    def visitNetHeader(self, ctx: Any) -> None:
        description = ctx.STRING()
        self._contribution(
            kind="document.net-header",
            target={"type": "document"},
            value={
                "name": _decode_name(ctx.name().getText()),
                **(
                    {"description": json.loads(description.getText())}
                    if description
                    else {}
                ),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitCompositionHeader(self, ctx: Any) -> None:
        self.document_kind = "composition"
        self._contribution(
            kind="document.composition-header",
            target={"type": "document"},
            value={"namespace": _decode_name(ctx.name().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitCompositionUse(self, ctx: Any) -> None:
        self._contribution(
            kind="composition.use",
            target={"type": "document"},
            value={
                "ref": json.loads(ctx.STRING().getText()),
                "alias": ctx.IDENT().getText(),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitCompositionWire(self, ctx: Any) -> None:
        aliases = ctx.IDENT()
        places = ctx.compositionPlace()
        self._contribution(
            kind="composition.wire",
            target={"type": "document"},
            value={
                "from": self._composition_endpoint(aliases[0], places[0]),
                "to": self._composition_endpoint(aliases[1], places[1]),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitCompositionShare(self, ctx: Any) -> None:
        self._contribution(
            kind="composition.share",
            target={"type": "document"},
            value={
                "places": [
                    self._composition_endpoint(alias, place)
                    for alias, place in zip(
                        ctx.IDENT(), ctx.compositionPlace(), strict=True
                    )
                ]
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitCompositionFinal(self, ctx: Any) -> None:
        markings: list[list[dict[str, Any]]] = []
        for marking_ctx in ctx.compositionFinalMarking():
            markings.append(
                [
                    self._composition_endpoint(alias, place)
                    for alias, place in zip(
                        marking_ctx.IDENT(), marking_ctx.compositionPlace(), strict=True
                    )
                ]
            )
        self._contribution(
            kind="composition.final",
            target={"type": "document"},
            value={"markings": markings},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def _composition_endpoint(self, alias: Any, place: Any) -> dict[str, Any]:
        """``alias.(name)``, or ``alias.(inner.name)`` inside a composition."""
        return {
            "alias": alias.getText(),
            "place": _composition_path(place),
            "span": self._span(alias.getSymbol().start, place.stop.stop + 1),
        }

    def visitCompositionRefine(self, ctx: Any) -> None:
        aliases = ctx.IDENT()
        transition = ctx.compositionTransition()
        self._contribution(
            kind="composition.refine",
            target={"type": "document"},
            value={
                "transition": {
                    "alias": aliases[0].getText(),
                    "name": _composition_path(transition),
                    "span": self._span(
                        aliases[0].getSymbol().start, transition.stop.stop + 1
                    ),
                },
                "by": {
                    "alias": aliases[1].getText(),
                    "span": self._span(
                        aliases[1].getSymbol().start, aliases[1].getSymbol().stop + 1
                    ),
                },
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitChain(self, ctx: Any) -> None:
        nodes = ctx.chainNode()
        segments = ctx.arcSegment()
        handle_ctx = ctx.chainHandle()
        arc_specs: list[
            tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, int, int, Any]
        ] = []
        for index, segment in enumerate(segments):
            left = nodes[index]
            right = nodes[index + 1]
            left_place = left.place()
            right_place = right.place()
            if (left_place is None) == (right_place is None):
                raise PetrinetDslError(
                    Diagnostic(
                        "PN101",
                        "a chain segment must connect a place and a transition",
                        self.source.span(left.start.start, right.stop.stop + 1),
                    )
                )
            operator = segment.arcOperator().getText()
            color_ctx = segment.color()
            if color_ctx is None:
                color = {"kind": "explicit", "value": "token"}
            else:
                color = {
                    "kind": "explicit",
                    "value": _decode_name(color_ctx.name().getText()),
                }
            if left_place is not None:
                mode = {
                    "->": "consume",
                    "->?": "read",
                    "->0": "inhibit",
                }.get(operator)
                if mode is None:
                    self._json_error("invalid input arc operator", segment)
                assert mode is not None
                source = {
                    "type": "place",
                    "name": _decode_name(left_place.name().getText()),
                }
                destination = {
                    "type": "transition",
                    "name": _decode_name(right.transition().name().getText()),
                }
                transition_ctx = right.transition()
            else:
                if operator != "->":
                    arc_operator = segment.arcOperator()
                    raise PetrinetDslError(
                        Diagnostic(
                            "PN101",
                            f"{operator} is only allowed on place-to-transition arcs",
                            self.source.span(
                                arc_operator.start.start,
                                arc_operator.stop.stop + 1,
                            ),
                        )
                    )
                mode = "produce"
                source = {
                    "type": "transition",
                    "name": _decode_name(left.transition().name().getText()),
                }
                destination = {
                    "type": "place",
                    "name": _decode_name(right_place.name().getText()),
                }
                transition_ctx = None
            arc_specs.append(
                (
                    source,
                    destination,
                    color,
                    mode,
                    left.start.start,
                    right.stop.stop + 1,
                    transition_ctx,
                )
            )
        part_offset = 1 if handle_ctx is not None else 0
        arc_ids = [
            {
                "document": self.source.source_id,
                "statement": self._statement,
                "part": part_offset + index,
            }
            for index in range(len(arc_specs))
        ]
        if handle_ctx is not None:
            handle = _decode_name(handle_ctx.name().getText())
            self._contribution(
                kind="arc.handle",
                target={"type": "arcHandle", "name": handle},
                value={"arcIds": arc_ids},
                start=ctx.start.start,
                end=ctx.stop.stop + 1,
            )
        for index, (
            source,
            destination,
            color,
            mode,
            start,
            end,
            transition_ctx,
        ) in enumerate(arc_specs):
            value: dict[str, Any] = {
                "from": source,
                "to": destination,
                "color": color,
                "mode": mode,
            }
            if mode == "consume":
                value["transitionNameSpan"] = self._span(
                    transition_ctx.name().start.start,
                    transition_ctx.name().stop.stop + 1,
                )
            self._contribution(
                kind="arc.declare",
                target={"type": "arc", "id": arc_ids[index]},
                value=value,
                start=start,
                end=end,
                part=part_offset + index,
            )

    def visitPlaceDeclaration(self, ctx: Any) -> None:
        place = ctx.place()
        self._contribution(
            kind="place.declare",
            target={"type": "place", "name": _decode_name(place.name().getText())},
            value={},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionDeclaration(self, ctx: Any) -> None:
        transition = ctx.transition()
        self._contribution(
            kind="transition.declare",
            target={
                "type": "transition",
                "name": _decode_name(transition.name().getText()),
            },
            value={},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitPlacePort(self, ctx: Any) -> None:
        self._contribution(
            kind="place.port",
            target={
                "type": "place",
                "name": _decode_name(ctx.place().name().getText()),
            },
            value={
                "direction": ctx.portDirection().getText(),
                "color": _decode_name(ctx.color().name().getText()),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionHandler(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        self._contribution(
            kind="transition.handler",
            target={"type": "transition", "name": name},
            value={"handler": json.loads(ctx.STRING().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionGuard(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        self._contribution(
            kind="transition.guard",
            target={"type": "transition", "name": name},
            value={"guard": json.loads(ctx.STRING().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionTimer(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        clock = _decode_name(ctx.place().name().getText())
        self._contribution(
            kind="transition.timer",
            target={"type": "transition", "name": name},
            value={
                "clock": {"type": "place", "name": clock},
                "cel": json.loads(ctx.STRING().getText()),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionTimerMaturity(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        self._contribution(
            kind="transition.timer-maturity",
            target={"type": "transition", "name": name},
            value={"maturity": json.loads(ctx.STRING().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionTimerBind(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        bind_name = ctx.timerBindName().getText()
        place = _decode_name(ctx.place().name().getText())
        self._contribution(
            kind="transition.timer-bind",
            target={"type": "transition", "name": name},
            value={
                "name": bind_name,
                "place": {"type": "place", "name": place},
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionBindingName(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        place = _decode_name(ctx.place().name().getText())
        self._contribution(
            kind="transition.binding-name",
            target={"type": "transition", "name": name},
            value={
                "name": _decode_name(ctx.name().getText()),
                "place": {"type": "place", "name": place},
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def _safe_integer(self, ctx: Any) -> int:
        value = int(ctx.getText())
        if value > 9007199254740991:
            self._json_error("integer exceeds the safe IEEE-754 range", ctx)
        return value

    def visitTransitionPriority(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        self._contribution(
            kind="transition.priority",
            target={"type": "transition", "name": name},
            value={"priority": self._safe_integer(ctx.nonnegativeInteger())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTransitionOrder(self, ctx: Any) -> None:
        name = _decode_name(ctx.transition().name().getText())
        self._contribution(
            kind="order.transition",
            target={"type": "transition", "name": name},
            value={"rank": self._safe_integer(ctx.positiveInteger())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitChainOrder(self, ctx: Any) -> None:
        name = _decode_name(ctx.name().getText())
        self._contribution(
            kind="order.arc-run",
            target={"type": "arcHandle", "name": name},
            value={"rank": self._safe_integer(ctx.positiveInteger())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitPlaceAccepts(self, ctx: Any) -> None:
        place = _decode_name(ctx.place().name().getText())
        colors = [_decode_name(color.getText()) for color in ctx.color()]
        if len(colors) != len(set(colors)):
            self._semantic_error(
                f"accepted colors for ({place}) must not contain duplicates",
                ctx,
            )
        self._contribution(
            kind="place.accepts",
            target={"type": "place", "name": place},
            value={"colors": colors},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitPlaceCapacity(self, ctx: Any) -> None:
        place = _decode_name(ctx.place().name().getText())
        object_ctx = ctx.jsonObject()
        tagged = self._lower_json_object(object_ctx)
        value = cast(dict[str, Any], _untag(tagged))
        value_contexts = {
            json.loads(key.getText()): item
            for key, item in zip(
                object_ctx.STRING(), object_ctx.jsonValue(), strict=True
            )
        }
        if set(value) != {"key", "max"}:
            self._semantic_error(
                f"capacityPerColorKey for ({place}) must contain exactly key and max",
                object_ctx,
            )
        key = value["key"]
        if not _valid_capacity_key(key):
            self._semantic_error(
                "capacityPerColorKey key must be a non-empty string or non-empty "
                f"array of non-empty strings for ({place})",
                value_contexts["key"],
            )
        maximum = value["max"]
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
            self._semantic_error(
                "capacityPerColorKey max must be an integer greater than or equal "
                f"to 1; got {maximum!r} for ({place})",
                value_contexts["max"],
            )
        self._contribution(
            kind="place.capacity-per-color-key",
            target={"type": "place", "name": place},
            value=value,
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitArcWeight(self, ctx: Any) -> None:
        handle = _decode_name(ctx.name().getText())
        value_ctx = ctx.jsonValue()
        tagged = self._lower_json_value(value_ctx)
        weight = _untag(tagged)
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
            self._semantic_error(
                "arc weight must be an integer greater than or equal to 1; "
                f"got {weight!r} for @{handle}",
                value_ctx,
            )
        self._contribution(
            kind="arc.weight",
            target={"type": "arcHandle", "name": handle},
            value={"weight": weight},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitArcData(self, ctx: Any) -> None:
        handle = _decode_name(ctx.name().getText())
        if ctx.CEL() is not None:
            # The computed variant (ADR 0023): `data cel JsonString` lowers
            # to the produce template's `cel` field, not literal data.
            self._contribution(
                kind="arc.produce-cel",
                target={"type": "arcHandle", "name": handle},
                value={"cel": json.loads(ctx.STRING().getText())},
                start=ctx.start.start,
                end=ctx.stop.stop + 1,
            )
            return
        self._contribution(
            kind="arc.produce-data",
            target={"type": "arcHandle", "name": handle},
            value={"data": self._lower_json_value(ctx.jsonValue())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitArcPredicate(self, ctx: Any) -> None:
        handle = _decode_name(ctx.name().getText())
        kind = ctx.predicateKind().getText()
        self._contribution(
            kind="arc.predicate",
            target={"type": "arcHandle", "name": handle},
            value={"kind": kind, kind: json.loads(ctx.STRING().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitArcCorrelate(self, ctx: Any) -> None:
        handle = _decode_name(ctx.name().getText())
        self._contribution(
            kind="arc.correlate",
            target={"type": "arcHandle", "name": handle},
            value={"cel": json.loads(ctx.STRING().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def _lower_marking_value(self, ctx: Any) -> tuple[int, dict[str, Any]]:
        count_ctx = ctx.positiveInteger()
        count = self._safe_integer(count_ctx) if count_ctx is not None else 1
        template_ctx = ctx.templateReference()
        if template_ctx is not None:
            return count, {
                "template": {
                    "type": "template",
                    "name": _decode_name(template_ctx.name().getText()),
                }
            }
        return count, {
            "color": "token",
            "data": {"type": "object", "entries": []},
        }

    def visitInitialMarking(self, ctx: Any) -> None:
        count, token = self._lower_marking_value(ctx.markingValue())
        self._contribution(
            kind="marking.append",
            target={
                "type": "place",
                "name": _decode_name(ctx.place().name().getText()),
            },
            value={"count": count, "token": token},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitTemplateDefinition(self, ctx: Any) -> None:
        template = _decode_name(ctx.templateReference().name().getText())
        value = self._lower_json_value(ctx.jsonValue())
        self._contribution(
            kind="template.define",
            target={"type": "template", "name": template},
            value={"value": value},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    @staticmethod
    def _metadata_target(ctx: Any) -> dict[str, Any]:
        if ctx.NET() is not None:
            return {"type": "document"}
        if ctx.place() is not None:
            return {
                "type": "place",
                "name": _decode_name(ctx.place().name().getText()),
            }
        if ctx.transition() is not None:
            return {
                "type": "transition",
                "name": _decode_name(ctx.transition().name().getText()),
            }
        return {"type": "arcHandle", "name": _decode_name(ctx.name().getText())}

    def visitNamedMarking(self, ctx: Any) -> None:
        count, token = self._lower_marking_value(ctx.markingValue())
        self._contribution(
            kind="metadata.named-marking",
            target={"type": "document"},
            value={
                "name": _decode_name(ctx.markingName().getText()),
                "entries": [
                    {
                        "place": {
                            "type": "place",
                            "name": _decode_name(ctx.place().name().getText()),
                        },
                        "count": count,
                        "token": token,
                    }
                ],
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitMetadataDescription(self, ctx: Any) -> None:
        self._contribution(
            kind="documentation.description",
            target=self._metadata_target(ctx.metadataTarget()),
            value={"text": json.loads(ctx.STRING().getText())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitMetadataAnnotation(self, ctx: Any) -> None:
        self._contribution(
            kind="documentation.annotation",
            target=self._metadata_target(ctx.metadataTarget()),
            value={
                "key": _decode_name(ctx.name().getText()),
                "value": self._lower_json_value(ctx.jsonValue()),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    @staticmethod
    def _view_target(target: Any) -> dict[str, str]:
        place = target.place()
        if place is not None:
            place_name = _decode_name(place.name().getText())
            copy = target.transition()
            if copy is not None:
                return {
                    "type": "placeCopy",
                    "place": place_name,
                    "transition": _decode_name(copy.name().getText()),
                }
            return {"type": "place", "name": place_name}
        transition = target.transition()
        if transition is None:
            raise ValueError("view target must be a place, place copy, or transition")
        return {
            "type": "transition",
            "name": _decode_name(transition.name().getText()),
        }

    def visitViewPosition(self, ctx: Any) -> None:
        targets = ctx.viewTarget()
        subject = self._view_target(targets[0])
        base = self._view_target(targets[1]) if len(targets) > 1 else None
        delta = self._lower_json_object(ctx.jsonObject())
        position = {"from": base, "delta": delta} if base is not None else delta
        self._contribution(
            kind="view.position",
            target={"type": "view", "name": _decode_name(ctx.name().getText())},
            value={"subject": subject, "position": position},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitViewRoute(self, ctx: Any) -> None:
        names = ctx.name()
        self._contribution(
            kind="view.route",
            target={"type": "arcHandle", "name": _decode_name(names[1].getText())},
            value={
                "view": {"type": "view", "name": _decode_name(names[0].getText())},
                "points": [
                    self._lower_json_value(point)
                    for point in ctx.jsonArray().jsonValue()
                ],
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def _view_style(self, ctx: Any, member: str, allowed: tuple[str, ...]) -> None:
        view_name, raw_value = (_decode_name(name.getText()) for name in ctx.name())
        if raw_value not in allowed:
            self._semantic_error(
                f"unknown {member} value {raw_value!r} for view {view_name!r}; "
                f"expected one of {', '.join(allowed)}",
                ctx,
            )
        self._contribution(
            kind=f"view.{member}",
            target={"type": "view", "name": view_name},
            value={member: raw_value},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitViewSplines(self, ctx: Any) -> None:
        self._view_style(ctx, "splines", VIEW_SPLINES)

    def visitViewDetail(self, ctx: Any) -> None:
        self._view_style(ctx, "detail", VIEW_DETAILS)

    def visitDecoration(self, ctx: Any) -> None:
        if ctx.COLOR_KEYWORD() is not None:
            target: dict[str, Any] = {
                "type": "color",
                "name": _decode_name(ctx.color().getText()),
            }
            if ctx.SHOW() is None:
                kind, value = "decoration.quiet", {}
            else:
                fields: list[str] = []
                for string in ctx.STRING():
                    path = json.loads(string.getText())
                    if not valid_field_path(path):
                        self._semantic_error(
                            f"show field path {string.getText()} has an empty key; "
                            "write keys separated by single dots",
                            ctx,
                        )
                    if path in fields:
                        self._semantic_error(
                            f"show decoration for color {target['name']} repeats "
                            f"field path {string.getText()}",
                            ctx,
                        )
                    fields.append(path)
                kind, value = "decoration.show", {"fields": fields}
        else:
            target_ctx = ctx.decorationTarget()
            if target_ctx.place() is not None:
                target = {
                    "type": "place",
                    "name": _decode_name(target_ctx.place().name().getText()),
                }
            elif target_ctx.transition() is not None:
                target = {
                    "type": "transition",
                    "name": _decode_name(target_ctx.transition().name().getText()),
                }
            else:
                target = {
                    "type": "arcHandle",
                    "name": _decode_name(target_ctx.name().getText()),
                }
            strings = ctx.STRING()
            text = json.loads(strings[0].getText()) if strings else None
            if ctx.HIGHLIGHT() is not None:
                kind, value = (
                    "decoration.highlight",
                    {} if text is None else {"label": text},
                )
            elif ctx.NOTE() is not None:
                kind, value = "decoration.note", {"text": text}
            elif ctx.BESIDE() is not None:
                if target["type"] != "place":
                    self._semantic_error(
                        "beside decorations apply to fusion places; "
                        f"{target_ctx.getText()} has no local copies to place",
                        ctx,
                    )
                side = (
                    "left"
                    if ctx.LEFT() is not None
                    else "right"
                    if ctx.RIGHT() is not None
                    else None
                )
                kind, value = (
                    "decoration.beside",
                    {} if side is None else {"side": side},
                )
            else:
                if target["type"] == "place":
                    self._semantic_error(
                        "summary decorations apply to transitions and arcs; "
                        f"place ({target['name']}) has no expression to summarize",
                        ctx,
                    )
                kind, value = "decoration.summary", {"text": text}
        self._contribution(
            kind=kind,
            target=target,
            value=value,
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitExtensions(self, ctx: Any) -> None:
        self._contribution(
            kind="document.extensions",
            target={"type": "document"},
            value={"extensions": self._lower_json_object(ctx.jsonObject())},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitDomainDeclaration(self, ctx: Any) -> None:
        color = _decode_name(ctx.color().getText())
        keys = [_decode_name(name.getText()) for name in ctx.fieldPath().name()]
        path = ".".join(keys)
        if not all(keys) or any("." in key for key in keys):
            self._semantic_error(
                f"domain field path {path!r} for color {color} needs non-empty "
                "keys without dots",
                ctx.fieldPath(),
            )
        values: list[dict[str, Any]] = []
        seen: list[Any] = []
        for value_ctx in ctx.domainValue():
            tagged = self._lower_json_value(value_ctx)
            value = _untag(tagged)
            if any(json_values_equal(value, old) for old in seen):
                self._semantic_error(
                    f"domain {color}.{path} repeats the value {value_ctx.getText()}",
                    value_ctx,
                )
            seen.append(value)
            values.append(tagged)
        self._contribution(
            kind="domain.values",
            target={"type": "color", "name": color},
            value={"path": path, "values": values},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitFinalDeclaration(self, ctx: Any) -> None:
        seen: list[frozenset[str]] = []
        for part, marking_ctx in enumerate(ctx.finalMarking()):
            names: list[str] = []
            for place_ctx in marking_ctx.place():
                name = _decode_name(place_ctx.name().getText())
                if name in names:
                    self._semantic_error(
                        f"final names ({name}) more than once in one marking",
                        place_ctx,
                    )
                names.append(name)
            if frozenset(names) in seen:
                self._semantic_error(
                    "final names "
                    + " + ".join(f"({name})" for name in names)
                    + " more than once",
                    marking_ctx,
                )
            seen.append(frozenset(names))
            self._contribution(
                kind="proof.final",
                target={"type": "place", "name": names[0]},
                value={"with": names[1:]} if len(names) > 1 else {},
                start=marking_ctx.start.start,
                end=marking_ctx.stop.stop + 1,
                part=part,
            )

    def visitInvariantDeclaration(self, ctx: Any) -> None:
        terms: list[dict[str, Any]] = []
        for term_ctx in ctx.invariantTerm():
            name = _decode_name(term_ctx.place().name().getText())
            if any(term["place"] == name for term in terms):
                self._semantic_error(
                    f"invariant names ({name}) more than once", term_ctx
                )
            weight_ctx = term_ctx.positiveInteger()
            weight = self._safe_integer(weight_ctx) if weight_ctx is not None else 1
            terms.append({"place": name, "weight": weight})
        value: dict[str, Any] = {"terms": terms}
        string = ctx.STRING()
        if string is not None:
            name = json.loads(string.getText())
            if not name:
                self._semantic_error("an invariant name must not be empty", ctx)
            value["name"] = name
        constant_ctx = ctx.nonnegativeInteger()
        if constant_ctx is not None:
            value["constant"] = self._safe_integer(constant_ctx)
        self._contribution(
            kind="proof.invariant",
            target={"type": "document", "kind": "net"},
            value=value,
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def _actor_name(self, ctx: Any) -> str:
        actor = _decode_name(ctx.getText())
        if not actor:
            self._semantic_error("an actor name must not be empty", ctx)
        return actor

    def visitActorAssignment(self, ctx: Any) -> None:
        # The actor is an ordinary annotation under the well-known key
        # `actor`, as `fusion` is: the engine ignores it, the merge carries it.
        self._contribution(
            kind="documentation.annotation",
            target=self._metadata_target(ctx.actorTarget()),
            value={
                "key": "actor",
                "value": {"type": "string", "value": self._actor_name(ctx.name())},
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def visitActorDeclaration(self, ctx: Any) -> None:
        self._contribution(
            kind="actor.declare",
            target={"type": "document", "kind": "net"},
            value={
                "name": self._actor_name(ctx.name()),
                "kind": (
                    "person"
                    if ctx.PERSON() is not None
                    else "record"
                    if ctx.RECORD() is not None
                    else "system"
                ),
            },
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    def _place_annotation(self, ctx: Any, key: str, value: dict[str, Any]) -> None:
        self._contribution(
            kind="documentation.annotation",
            target={
                "type": "place",
                "name": _decode_name(ctx.place().name().getText()),
            },
            value={"key": key, "value": value},
            start=ctx.start.start,
            end=ctx.stop.stop + 1,
        )

    @staticmethod
    def _cel_object(ctx: Any) -> dict[str, Any]:
        return {
            "type": "object",
            "entries": [
                {
                    "key": "cel",
                    "value": {"type": "string", "value": _decode_name(ctx.getText())},
                }
            ],
        }

    def visitPlaceLives(self, ctx: Any) -> None:
        # Where a place lives in a sequence diagram: a lifeline name, or CEL
        # over the token that computes one. An annotation, as `actor` is.
        if ctx.CEL() is not None:
            value = self._cel_object(ctx.STRING())
        else:
            value = {"type": "string", "value": self._actor_name(ctx.name())}
        self._place_annotation(ctx, "lives", value)

    def visitPlaceReadsAs(self, ctx: Any) -> None:
        self._place_annotation(ctx, "reads_as", self._cel_object(ctx.STRING()))

    def visitPlaceKept(self, ctx: Any) -> None:
        # A record this net keeps, there from the start (ADR 0051). An
        # annotation, as `lives` is: the engine ignores it.
        value = {
            "type": "object",
            "entries": [
                {
                    "key": "by",
                    "value": {"type": "string", "value": self._actor_name(ctx.name())},
                },
                {"key": "start", "value": self._cel_object(ctx.STRING())},
            ],
        }
        self._place_annotation(ctx, "kept", value)


def lower_petrinet_text(text: str, source_name: str = "<memory>") -> dict[str, Any]:
    """Parse one complete ``.petrinet`` document into portable Contribution IR.

    Syntax-only parsing of the same grammar lives in ``velocitron_grammar``
    (``packages/grammar/python``). This function is the lowering step.
    ``python3 tools/dsl_package.py`` copies it into ``velocitron_dsl``
    (``packages/dsl/python``). It does not re-export either package. CEL
    compilation and contribution resolution ship in ``velocitron_petrinet``.
    Composition merge ships in ``packages/merge``.
    """
    source = _SourceMap(source_name, text)
    if (
        text.startswith("\ufeff")
        or "\r" in text.replace("\r\n", "")
        or any(0xD800 <= ord(character) <= 0xDFFF for character in text)
    ):
        raise PetrinetDslError(
            Diagnostic(
                "PN100",
                "source must be strict UTF-8 text without a BOM or bare CR",
                source.span(0, 0),
            )
        )
    lexer = VelocitronPetriNetLexer(InputStream(text))
    listener = _SyntaxListener(source)
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    stream = CommonTokenStream(lexer)
    parser = VelocitronPetriNetParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.document()
    stream.fill()
    if listener.diagnostics:
        raise PetrinetDslError(listener.diagnostics[0])
    visitor = _LoweringVisitor(source)
    visitor.visit(tree)
    return {
        "format": _FORMAT,
        "version": _VERSION,
        "documentKind": visitor.document_kind or "net",
        "document": {"id": source_name},
        "contributions": visitor.contributions,
    }


def valid_field_path(path: object) -> bool:
    """Whether ``path`` names a token field: non-empty keys joined by dots."""
    return isinstance(path, str) and all(path.split("."))


def petrinet_lexer_literals() -> tuple[str, ...]:
    """Quoted lexer literals, including JSON constants the grammar reserves."""
    from .generated.VelocitronPetriNetLexer import VelocitronPetriNetLexer

    return tuple(
        literal
        for literal in VelocitronPetriNetLexer.literalNames
        if isinstance(literal, str)  # pyright: ignore[reportUnnecessaryIsInstance]
    )
