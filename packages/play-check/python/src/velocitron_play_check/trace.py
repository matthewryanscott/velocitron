"""One checked play path as JSON: per step its records, state and resolve.

:func:`trace_document` answers what the sequence view resolves — who does
each step, which column a lived place's token sits on, what a reader of it
sees — beside what :func:`velocitron_play.trace_json` records: the engine
records (with the ``matured`` mark of a firing the clock played), the
marking after each record, and the checks. The command line prints it as
``velocitron play trace``.

References: spec/play-language.md; ADR 0031; ADR 0038.
"""

from __future__ import annotations

from typing import Any

from velocitron_play import FireBody, InjectBody, UpdateBody

from .check import PlayTrace, StepResult

# `_Actors` and `_tokens` are package-internal helpers shared with the
# sequence projection. The underscore keeps them off the public surface;
# basedpyright's module-privacy check does not model that sharing.
from .sequence import OUTSIDE, _Actors, _tokens  # pyright: ignore[reportPrivateUsage]
from .walkthrough import marking_json


def _step_label(
    trace: PlayTrace, actors: _Actors, transition: str, step_title: str | None
) -> str | None:
    """A firing's authored label: the step's title, else the transition's
    summary, else its description; ``None`` when nobody wrote one."""
    if step_title:
        return step_title
    decoration = trace.subject.decorations.nodes.get(f"transition:{transition}")
    if decoration is not None and decoration.summary:
        return decoration.summary
    found = next(
        (t for t in trace.subject.net.transitions if t.name == transition), None
    )
    if found is not None and found.description:
        return found.description
    return None


def _token_view(token: Any, actors: _Actors, place: str) -> dict[str, Any]:
    """One token as JSON with its read label on a lived place."""
    view = {"type": token.type, "data": token.data}
    if actors.lives(place):
        view["column"] = actors.column(place, token)
        view["read"] = actors.read_label(place, token)
    return view


def _records_json(
    trace: PlayTrace, result: StepResult, actors: _Actors
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in result.records:
        meta = record.get("metadata") or {}
        matured = bool(meta.get("maturedBy"))
        if "firingId" in record:
            transition = record["transition"]
            records.append(
                {
                    "kind": "firing",
                    "transition": transition,
                    "status": record["status"],
                    "matured": matured,
                    "maturedBy": meta.get("maturedBy"),
                    "actor": actors.of_transition(transition),
                    "label": _step_label(
                        trace, actors, transition, result.step.title
                    ),
                    "inputTokens": {
                        place: [
                            _token_view(token, actors, place)
                            for token in _tokens(tokens)
                        ]
                        for place, tokens in record["inputTokens"].items()
                    },
                    "outputTokens": {
                        place: [
                            _token_view(token, actors, place)
                            for token in _tokens(tokens)
                        ]
                        for place, tokens in record["outputTokens"].items()
                    },
                }
            )
        else:
            place = record["place"]
            owner = actors.owner(place)
            records.append(
                {
                    "kind": "injection",
                    "place": place,
                    "injectionKind": record["kind"],
                    "tokens": [
                        _token_view(token, actors, place)
                        for token in record["tokens"]
                    ],
                    "replaced": [
                        _token_view(token, actors, place)
                        for token in record["replaced"]
                    ],
                    "actor": None if owner == OUTSIDE else owner,
                    "matured": matured,
                }
            )
    return records


def trace_document(trace: PlayTrace) -> dict[str, Any]:
    """One path's trace as JSON: per step its records (each marked when the
    clock matured it), the marking after each record, and per record the
    actor plus, on a lived place, the column and read label the sequence
    view draws."""
    actors = _Actors(trace)
    steps: list[dict[str, Any]] = []
    for result in trace.steps:
        step = result.step
        actor = None
        if isinstance(step.body, FireBody):
            actor = actors.of_transition(step.body.transition.name)
        elif isinstance(step.body, InjectBody | UpdateBody):
            owner = actors.owner(step.body.place.name)
            actor = None if owner == OUTSIDE else owner
        steps.append(
            {
                "index": result.index,
                "line": step.position.line,
                "kind": step.kind,
                "title": step.title,
                "statement": step.statement,
                "actor": actor,
                "records": _records_json(trace, result, actors),
                "afterEach": [marking_json(marking) for marking in result.markings],
                "after": marking_json(result.after),
            }
        )
    failure = trace.failure
    return {
        "play": trace.play.name,
        "path": trace.path.name,
        "status": "passed" if failure is None else "failed",
        "clocks": sorted(
            {
                timer.clock
                for timer in (
                    transition.timer
                    for transition in trace.subject.net.transitions
                )
                if timer is not None
            }
        ),
        "initial": marking_json(trace.initial),
        "steps": steps,
    }


__all__ = ["trace_document"]