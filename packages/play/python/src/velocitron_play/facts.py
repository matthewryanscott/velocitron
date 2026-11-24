"""Project a parsed play to the cross-language agreement object.

``packages/play/typescript`` builds the same object. Keep the keys and the
omitted-empty rules aligned with ``playFacts``.
"""

from __future__ import annotations

import math
from typing import Any, cast

from .language import (
    AdvanceBody,
    AssumeGuardBody,
    Condition,
    ExpectBody,
    FireBody,
    InjectBody,
    NameRef,
    OutputClause,
    Play,
    PlayError,
    PlayPath,
    Step,
    StepBody,
    TokenExpr,
    UpdateBody,
    WithClause,
    parse_play,
)


def _canon(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        pairs = cast(dict[Any, Any], value)
        return {str(key): _canon(item) for key, item in pairs.items()}
    if isinstance(value, list):
        items = cast(list[Any], value)
        return [_canon(item) for item in items]
    if isinstance(value, tuple):
        items = cast(tuple[Any, ...], value)
        return [_canon(item) for item in items]
    raise TypeError("play fact is not JSON")


def _token(token: TokenExpr) -> dict[str, Any]:
    if isinstance(token, NameRef):
        return {"template": token.name}
    return {"color": token.color, "data": _canon(token.data)}


def _condition(condition: Condition) -> dict[str, Any]:
    fact: dict[str, Any] = {"kind": condition.kind, "text": condition.text}
    if condition.place is not None:
        fact["place"] = condition.place.name
    if condition.tokens:
        fact["tokens"] = [_token(token) for token in condition.tokens]
    if condition.count is not None:
        fact["count"] = condition.count
    if condition.transitions:
        fact["transitions"] = [item.name for item in condition.transitions]
    return fact


def _with_clause(clause: WithClause) -> dict[str, Any]:
    fact: dict[str, Any] = {"place": clause.place.name}
    if clause.template is not None:
        fact["template"] = clause.template.name
    elif clause.index is not None:
        fact["index"] = clause.index
    elif clause.subset is not None:
        fact["subset"] = _canon(clause.subset)
    return fact


def _output(clause: OutputClause) -> dict[str, Any]:
    fact: dict[str, Any] = {"place": clause.place.name}
    if clause.nothing:
        fact["nothing"] = True
    elif clause.merge is not None:
        fact["merge"] = _canon(clause.merge)
    else:
        fact["tokens"] = [_token(token) for token in clause.tokens]
    return fact


def _body(body: StepBody) -> dict[str, Any]:
    if isinstance(body, InjectBody):
        return {
            "place": body.place.name,
            "tokens": [_token(token) for token in body.tokens],
        }
    if isinstance(body, UpdateBody):
        return {"place": body.place.name, "token": _token(body.token)}
    if isinstance(body, AdvanceBody):
        return {
            "place": None if body.place is None else body.place.name,
            "seconds": _canon(body.seconds),
            "relative": body.relative,
        }
    if isinstance(body, FireBody):
        return {
            "transition": body.transition.name,
            "with": [_with_clause(clause) for clause in body.withs],
            "output": [_output(clause) for clause in body.outputs],
        }
    if isinstance(body, ExpectBody):
        return {"conditions": [_condition(item) for item in body.conditions]}
    if isinstance(body, AssumeGuardBody):
        return {
            "assume": "guard",
            "transition": body.transition.name,
            "value": body.value,
        }
    return {
        "assume": "predicate",
        "predicate": body.predicate,
        "value": body.value,
    }


def _step(step: Step) -> dict[str, Any]:
    return {
        "kind": step.kind,
        "label": step.label,
        "title": step.title,
        "prose": step.prose,
        "statement": step.statement,
        "line": step.position.line,
        "column": step.position.column,
        "body": _body(step.body),
    }


def _path(path: PlayPath) -> dict[str, Any]:
    from_label = path.from_label
    return {
        "name": path.name,
        "title": path.title,
        "prose": path.prose,
        "from": None
        if from_label is None
        else {
            "name": from_label.name,
            "line": from_label.position.line,
            "column": from_label.position.column,
        },
        "sequence": path.sequence,
        "steps": [_step(step) for step in path.steps],
    }


def play_facts(play: Play) -> dict[str, Any]:
    """Return the agreement projection of one parsed play."""
    return {
        "name": play.name,
        "title": play.title,
        "prose": play.prose,
        "line": play.position.line,
        "column": play.position.column,
        "net": play.net,
        "marking": play.marking,
        "scope": play.scope,
        "sequence": play.sequence,
        "instance": None if play.instance is None else _token(play.instance),
        "uses": [{"ref": use.ref, "alias": use.alias} for use in play.uses],
        "wires": [
            {
                "from_alias": wire.from_alias,
                "from_place": wire.from_place,
                "to_alias": wire.to_alias,
                "to_place": wire.to_place,
            }
            for wire in play.wires
        ],
        "refines": [
            {"alias": refine.alias, "transition": refine.transition, "by": refine.by}
            for refine in play.refines
        ],
        "shares": [
            [{"alias": alias, "place": place} for alias, place in share.members]
            for share in play.shares
        ],
        "shows": [
            {"color": show.color, "fields": list(show.fields)} for show in play.shows
        ],
        "actors": [{"name": actor.name, "kind": actor.kind} for actor in play.actors],
        "boxes": [
            {"title": box.title, "members": list(box.members)} for box in play.boxes
        ],
        "templates": [
            {"name": name, "color": literal.color, "data": _canon(literal.data)}
            for name, literal in play.templates.items()
        ],
        "paths": [_path(path) for path in play.paths],
    }


def project_source(text: str, source: str = "<memory>") -> dict[str, Any]:
    """Project source text, or the first ``SC1xx`` position when it fails."""
    try:
        play = parse_play(text, source)
    except PlayError as error:
        diagnostic = error.diagnostic
        return {
            "ok": False,
            "code": diagnostic.code,
            "line": diagnostic.position.line,
            "column": diagnostic.position.column,
        }
    return {"ok": True, **play_facts(play)}
