"""Turn a list of journal records into a ``.play`` that replays them.

The consumer: a save-as-play button. A recorded run's journal — the
occurrence sequence of the net together with its environment
([ADR 0059](https://github.com/circuitmeridian/velocitron/blob/main/docs/adr/0059-velocitron-spells-its-model-words-the-way-the-petri-net-books-do.md),
item 3) — is a list of :class:`InjectionRecord` / :class:`FiringRecord`
dicts; :func:`records_to_play` writes the play that passes
:func:`check_play` and replays those records, one step per record:

- an injection of kind ``inject`` becomes an ``inject`` step, of kind
  ``update`` an ``update`` step — every arrival maps to one statement. A
  clock move is written as ``update``, the machine form (what ``velocitron
  prove`` writes too): the ``update`` statement carries no maturation, so
  the firings the move matured are then their own ``fire`` steps, in
  recorded order — a step the story picks, not one the maturation picks
  for it (ADR 0060). This is why the naive ``advance`` + ``fire`` mapping
  fails with SC301: the advance's own maturation would fire the timer
  transitions before the story's ``fire`` steps reach them.
- a completed firing becomes a ``fire`` step: `with` clauses pin the
  recorded binding when a place holds more tokens than it binds, and `->`
  clauses carry the produce tokens of every template the net does not
  fill.
- a failed firing is not an occurrence (ADR 0059, item 4 — it consumes
  nothing and changes no marking), so it is left out and kept only as a
  ``//`` comment.

The function is pure — no I/O, no clock; it runs under Pyodide. It is also
self-checking: every step it writes it replays through the real
:class:`Engine` first (`inject_token`, `reserve` + `settle`, the same seam
the checker plays through), so each step's line is written from what the
engine actually produced, and the replayed record is compared to the
journal's. A record that cannot be replayed as a step raises
:class:`RecordsToPlayError`; a play that does not check is never returned.

Known edges: a :class:`velocitron_journal.DurableJournal` decoded
row carries the channel name in ``kind`` (``injection``) where the record's
own ``inject`` / ``update`` kind sat — such records are classified by their
``replaced`` payload. The replay numbers attempts from 1 over the play's
steps, not with the recorded run's attempt counters (only attempt-branched
gates could read the difference, and the play pins those with ``assume``).

References: spec/play-language.md; ADR 0031 (plays); ADR 0059 (occurrence,
attempt record); ADR 0060 (advance is one seam and tick is deleted).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from velocitron_cel import get_default_adapter
from velocitron_engine import (
    BindingChoice,
    DepositViolation,
    Engine,
    HandlerRegistry,
    Marking,
    Net,
    Token,
    TransitionHandlerOutput,
    net_fills,
    produce_templates,
)

from .check import PlayNet
from .kept_start import KeptStartError, build_start, kept_records

__all__ = ["RecordsToPlayError", "records_to_play"]


class RecordsToPlayError(ValueError):
    """A record list :func:`records_to_play` cannot turn into a play."""


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _ident(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _token(token_dict: Token | Mapping[str, Any]) -> Token:
    if isinstance(token_dict, Token):
        return token_dict
    return Token(
        cast(str, token_dict["type"]),
        dict(cast(Mapping[str, Any], token_dict["data"])),
    )


def _token_line(token: Token) -> str:
    return f"{token.type} {_json(token.data)}"


def _token_dicts(tokens: Sequence[Any]) -> list[dict[str, Any]]:
    """Tokens, or already-serialized token dicts, as plain dicts.

    The comparison is by ``type`` and ``data`` only — the same shape
    :func:`velocitron_play_check.marking_json` writes, and the
    journal's own serialization strips everything else a :class:`Token`
    carries.
    """
    return [
        {"type": t["type"], "data": t["data"]}
        if isinstance(t, Mapping)
        else {"type": t.type, "data": t.data}
        for t in tokens
    ]


def _kind_of(record: Mapping[str, Any]) -> str:
    """Which channel a record belongs to, by its keys — the cursor's rule
    (:class:`velocitron_replay.ReplayCursor._kind_of`)."""
    if "event" in record:
        return "trace"
    if "injectionId" in record:
        return "injection"
    if "firingId" in record:
        return "firing"
    return "net_revision"


def _injection_kind(record: Mapping[str, Any]) -> str:
    """The record's ``inject`` / ``update`` kind.

    A decoded :class:`velocitron_journal.DurableJournal` row carries
    the channel name in ``kind`` (``injection``); the record's own kind is
    then read from ``replaced``, which only an ``update`` fills.
    """
    kind = record.get("kind")
    if kind in ("inject", "update"):
        return cast(str, kind)
    return "update" if record.get("replaced") else "inject"


def _same_binding(
    left: Mapping[str, Sequence[Any]], right: Mapping[str, Sequence[Any]]
) -> bool:
    """Per-place token-list equality, order-sensitive: binding enumeration
    fills each place in place order, so the recorded order is the order a
    replay binds too."""
    return {place: list(tokens) for place, tokens in left.items()} == {
        place: list(tokens) for place, tokens in right.items()
    }


def _require_net_id(record: Mapping[str, Any], net: Net) -> None:
    recorded = record.get("netId")
    if recorded is not None and recorded != net.name:
        raise RecordsToPlayError(
            f"record {record.get('firingId') or record.get('injectionId')} was "
            f"recorded against net {recorded!r}, not {net.name!r}; a play "
            "replays one net's records"
        )


def _assumption_steps(net: Net, transition: str) -> list[tuple[str, str]]:
    """The ``(step, registry ref)`` pairs a firing of ``transition`` needs.

    The checker registers no handlers, so a transition with a named `guard`
    is not enabled until the play assumes the guard's answer, and an arc
    with a named predicate filter binds nothing either. The recorded run
    answered yes to both when it fired — the answer the play assumes.

    Reference: spec/play-language.md, "Assumptions".
    """
    steps: list[tuple[str, str]] = []
    tr = next((tr for tr in net.transitions if tr.name == transition), None)
    if tr is None:
        raise RecordsToPlayError(f"the net has no transition {transition!r}")
    if tr.guard is not None:
        steps.append((f"assume [{transition}] guard true", tr.guard))
    for arc in net.arcs:
        if arc.to_transition != transition or arc.consume is None:
            continue
        predicate = arc.consume.predicate
        if predicate is not None and predicate.handler is not None:
            steps.append(
                (f"assume predicate {_json(predicate.handler)} true", predicate.handler)
            )
    return steps


def _output_clauses(
    net: Net,
    record: Mapping[str, Any],
    consumed: Mapping[str, Sequence[Token]] = {},
) -> list[str]:
    """The `->` clauses of a fire step, from the record and the net.

    Per produce template, in declaration order, over the record's
    ``outputTokens``; the tokens of one destination join into one clause
    (SC210 rejects a second for the same place), in the templates' order.
    The resolver maps a stated token to the first template of its color at
    the destination, so a color is statable only when that first template
    is open (a net-filled first is SC211); several tokens of one color —
    which a handler's own one produce arc may legitimately return — all go
    to that one template.

    An open template the record gives NO token is stated as ``nothing``
    when the carry rule could otherwise (wrongly) fill it — a consumed
    token of the template's color is in the binding — but ``nothing`` is
    only writable where the place has one open template and no net-filled
    one (SC210/SC211); a record that needs it elsewhere cannot be replayed.

    A template the net fills (``data`` / ``data cel``) is the engine's and
    is never stated.
    """
    templates = produce_templates(net, cast(str, record["transition"]))
    outputs = cast(Mapping[str, Sequence[Mapping[str, Any]]], record["outputTokens"])

    def color_of(token_dict: Token | Mapping[str, Any]) -> str:
        if isinstance(token_dict, Token):
            return token_dict.type
        return cast(str, token_dict["type"])

    first_by_color: dict[tuple[str, str], bool] = {}
    for template in templates:
        first_by_color.setdefault(
            (template.destination, template.type), not net_fills(template)
        )
    carry_by_color: dict[str, int] = {}
    for tokens in consumed.values():
        for token in tokens:
            carry_by_color[token.type] = carry_by_color.get(token.type, 0) + 1
    clauses: dict[str, list[str]] = {}
    for template in templates:
        if net_fills(template):
            continue
        key = (template.destination, template.type)
        if first_by_color[key] is False:
            # The net fills the color's first template: any stated token
            # would be SC211. The engine fills it in the replay, and
            # ``_agree_firing`` compares its value against the record.
            continue
        tokens = [
            _token(t)
            for t in outputs.get(template.destination, ())
            if color_of(t) == template.type
        ]
        if not tokens:
            if template.type not in carry_by_color:
                continue  # the carry rule has nothing to fill either
            here = [
                t for t in templates if t.destination == template.destination
            ]
            fixed = [t for t in here if net_fills(t)]
            if fixed or len(here) != 1:
                raise RecordsToPlayError(
                    f"[{record['transition']}]'s record states no "
                    f"{template.type} token into ({template.destination}), but "
                    "the carry rule would fill one; `nothing` cannot be "
                    "stated there (SC210/SC211) — the record cannot be "
                    "replayed as a play"
                )
            clauses[template.destination] = ["nothing"]
            continue
        clauses.setdefault(template.destination, []).extend(
            _token_line(token) for token in tokens
        )
    return [
        f"-> ({place}) " + ", ".join(tokens) for place, tokens in clauses.items()
    ]


def _with_clauses(
    binding: Mapping[str, Sequence[Token]], marking: Marking
) -> list[str]:
    """The `with` clauses that pin a binding when a place holds more tokens
    than it binds: one `with (p) {subset}` per bound token — a
    full-equality subset pins exactly that token, whatever shares its
    data. A place that binds its whole contents needs no clause: the first
    viable binding takes its every token in place order."""
    clauses: list[str] = []
    for place, tokens in binding.items():
        if len(list(marking.get(place, ()))) == len(tokens):
            continue
        for token in tokens:
            clauses.append(f"with ({place}) {_json(token.data)}")
    return clauses


def _contains(data: Any, subset: Any) -> bool:
    """``subset`` is a part of ``data``: objects compare key by key, all
    else by equality — the checker's own ``with {subset}`` semantics."""
    if isinstance(subset, dict) and isinstance(data, dict):
        data_map = cast(dict[str, Any], data)
        subset_map = cast(dict[str, Any], subset)
        return all(
            key in data_map and _contains(data_map[key], value)
            for key, value in subset_map.items()
        )
    return data == subset


def _choose_recorded(
    wanted: Mapping[str, Sequence[Token]],
) -> BindingChoice:
    """A ``reserve`` filter that takes only bindings that bind exactly the
    recorded tokens, per place — what the `with` clauses narrow."""

    def choose(binding: Mapping[str, Sequence[Token]]) -> bool:
        for place, tokens in wanted.items():
            bound = list(binding.get(place, ()))
            if len(bound) != len(tokens):
                return False
            pool = list(bound)
            for token in tokens:
                if not any(_contains(t.data, token.data) and t.type == token.type for t in pool):
                    return False
                for index, candidate in enumerate(pool):
                    if candidate.type == token.type and _contains(candidate.data, token.data):
                        del pool[index]
                        break
        return True

    return choose


def _start_preamble(
    net: Net,
    start: Marking,
    instance: Mapping[str, Any] | None,
) -> list[str]:
    """The ``instance`` line and leading steps that build ``start``.

    Kept records are in every starting marking (ADR 0051): the checker adds
    them from their ``starts as`` values, built against the play's
    ``instance`` line where a start reads one. Kept places therefore get no
    step; their ``starts as`` value must equal ``start``'s token, or the
    records came from a start the play cannot state. Every other held
    token is a leading ``inject`` — a kept record a run injected after
    starting without an instance included, the `marking none` + literal
    start pattern.
    """
    lines: list[str] = []
    records = kept_records(net)
    auto = Marking()
    if records and instance is not None:
        lines.append(f"instance instance {_json(dict(instance))}")
    for name in sorted(records):
        record = records[name]
        if record.reads_instance and instance is None:
            continue
        try:
            token = Token(record.color, build_start(record, instance))
        except KeptStartError as error:
            raise RecordsToPlayError(str(error)) from error
        auto = auto.set(name, [token])
    base = net.initial_marking or Marking()
    if all(
        list(start.get(place, ())) == list(base.get(place, ()))
        for place in set(start) | set(base)
    ):
        return ["marking initial", *lines]
    lines = ["marking none", *lines]
    for place in sorted(start):
        tokens = list(start.get(place, ()))
        auto_tokens = list(auto.get(place) or ())
        if tokens == auto_tokens:
            continue
        if auto_tokens:
            raise RecordsToPlayError(
                f"({place}) is a kept record and starts with "
                f"{_token_line(auto_tokens[0])}; the given start holds "
                f"{', '.join(_token_line(t) for t in tokens) or 'nothing'} — "
                "the records came from another start"
            )
        if not tokens:
            continue
        lines.append(
            f"inject ({place}) <- " + ", ".join(_token_line(t) for t in tokens)
        )
    return lines


def records_to_play(
    net: Net | PlayNet,
    start: Marking,
    records: Sequence[Mapping[str, Any]],
    *,
    net_line: str,
    name: str = "replay",
    title: str | None = None,
    instance: Mapping[str, Any] | None = None,
) -> str:
    """Write the play that replays ``records``, given the net and its start.

    :param net: the net the records belong to — a :class:`Net`, or the
        :class:`PlayNet` a check produced (a composition too; the merged
        net's merged names name the steps).
    :param start: the marking the records replay from — a checked play's
        ``trace.initial``, typically: every kept record at its start
        value, the tokens the play injected before its steps.
    :param records: the journal records in sequence order, each an
        :class:`InjectionRecord` / :class:`FiringRecord` dict (or its
        serialized form). Trace, runtime and net-revision records are
        skipped; a failed firing is skipped (not an occurrence, ADR 0059
        item 4) and left as a ``//`` comment.
    :param net_line: the play's net setting, verbatim: ``net
        "shop.petrinet"``, or the ``use`` / ``wire`` lines of a
        composition, one line each. It must resolve — from the play's
        origin — to the same net as ``net``; the line is written, not
        checked.
    :param name: the play's name; sanitized to an ident.
    :param title: the play's title (a default names the replay).
    :param instance: the instance token's data, for kept records whose
        ``starts as`` reads it; the play carries an ``instance`` line so
        the checker reaches the same value.

    Every step is written from what the engine produced: the function
    replays each record as it writes the step — injections through
    ``inject_token``, firings through ``reserve`` + ``settle``, the same
    seam the checker plays through — and compares the replayed record to
    the journal's. The play is returned only when every record replays;
    otherwise :class:`RecordsToPlayError` names the step. The steps' own
    records are the input records' effects, so a :func:`check_play` over
    the returned play reproduces the occurrence sequence
    record-for-record (the preamble's steps are before the records, and
    ids, attempts, timestamps and metadata are not part of the
    comparison, as :func:`velocitron_play_check.trace_json`'s is
    not).

    References: spec/play-language.md; ADR 0031; ADR 0059 (items 3, 4);
    ADR 0060.
    """
    net = net.net if isinstance(net, PlayNet) else net
    if not any(_kind_of(record) in ("firing", "injection") for record in records):
        raise RecordsToPlayError("the records hold no firing or injection")
    lines = [
        f'play {_ident(name)} {_json(title or "Replay of the journal records")}',
    ]
    lines.extend(net_line.splitlines())
    lines.extend(_start_preamble(net, start, instance))

    engine = Engine(HandlerRegistry(), cel_adapter=get_default_adapter())
    assumed: dict[str, str] = {}
    marking = start
    step_index = 0
    for record in records:
        kind = _kind_of(record)
        if kind in ("trace", "net_revision"):
            continue
        _require_net_id(record, net)
        if kind == "firing" and record["status"] != "completed":
            lines.append(
                f"// skipped: a failed attempt of [{record['transition']}] — "
                "not an occurrence, no marking effect (ADR 0059, item 4)"
            )
            continue
        step_index += 1
        if kind == "injection":
            marking = _injection_step(engine, net, record, marking, lines, step_index)
        else:
            marking = _fire_step(
                engine, net, record, marking, lines, step_index, assumed
            )
    return "\n".join(lines) + "\n"


def _injection_step(
    engine: Engine,
    net: Net,
    record: Mapping[str, Any],
    marking: Marking,
    lines: list[str],
    step_index: int,
) -> Marking:
    """Replay one record's injection and write it; return the next marking.

    An ``inject`` record of N tokens (an ``inject_tokens`` batch) becomes N
    steps over N consecutive indexes — one step per journal record, the
    engine's own one-record-per-token shape.
    """
    place = cast(str, record["place"])
    tokens = cast(Sequence[Mapping[str, Any]], record["tokens"])
    replace = _injection_kind(record) == "update"
    if replace and len(tokens) != 1:
        raise RecordsToPlayError(
            f"the update injection of ({place}) replaces the place with one "
            f"token; the record holds {len(tokens)}"
        )
    for token_dict in tokens:
        token = _token(token_dict)
        try:
            after, produced = engine.inject_token(
                net, marking, place, token, attempt=step_index, replace=replace
            )
        except ValueError as error:
            raise RecordsToPlayError(
                f"step {step_index}: the engine rejects the injection into "
                f"({place}): {error}"
            ) from error
        if (
            produced["place"] != place
            or produced["kind"] != _injection_kind(record)
            or _token_dicts(produced["tokens"]) != _token_dicts(record["tokens"])
            or _token_dicts(produced["replaced"])
            != _token_dicts(record["replaced"])
        ):
            raise RecordsToPlayError(
                f"step {step_index}: the replayed injection into ({place}) "
                f"differs from the record ({record.get('injectionId')})"
            )
        verb = "update" if replace else "inject"
        lines.append(f"{verb} ({place}) <- {_token_line(token)}")
        marking = after
        step_index += 1
    return marking


def _fire_step(
    engine: Engine,
    net: Net,
    record: Mapping[str, Any],
    marking: Marking,
    lines: list[str],
    step_index: int,
    assumed: dict[str, str],
) -> Marking:
    """Replay one completed firing and write it; return the next marking."""
    transition = cast(str, record["transition"])
    for step, ref in _assumption_steps(net, transition):
        if step in assumed:
            continue
        assumed[step] = transition
        if step.startswith(f"assume [{transition}]"):
            engine.registry.register_guard(ref, _yes)
        else:
            engine.registry.register_predicate(ref, _yes)
        lines.append(step)
    reservation = engine.reserve(net, marking, transition, attempt=step_index)
    recorded_input = cast(
        Mapping[str, Sequence[Mapping[str, Any]]], record["inputTokens"]
    )
    wanted = dict(_tokens_by_place(recorded_input))
    if reservation is None or not _same_binding(reservation.input_tokens, wanted):
        # The recorded binding is not the first viable one (SC302's
        # narrowing): re-reserve through a filter over the recorded tokens,
        # which is what the step's `with` clauses say.
        reservation = engine.reserve(
            net,
            marking,
            transition,
            attempt=step_index,
            choose=_choose_recorded(wanted),
        )
        if reservation is None:
            raise RecordsToPlayError(
                f"step {step_index}: no binding of [{transition}] matches the "
                "recorded tokens where the records place it; the play would "
                f"fail with SC301/SC302 ({record.get('firingId')})"
            )
        if not _same_binding(reservation.input_tokens, wanted):
            raise RecordsToPlayError(
                f"step {step_index}: [{transition}]'s recorded binding cannot "
                "be pinned by token subsets; the record cannot be replayed as "
                f"a play with `with` clauses ({record.get('firingId')})"
            )
    outputs = cast(
        Mapping[str, Sequence[Token | Mapping[str, Any]]], record["outputTokens"]
    )
    # The handler tokens the replay states: the open templates' tokens, the
    # record's. Templates the net fills (``data`` / ``data cel``) are left
    # to the engine — it computes them from the binding, the same values a
    # play's symbolic firing reaches. A record whose tokens there came from
    # a REAL handler, differing from the net's own fill, fails the
    # comparison below: those records cannot be replayed as a play, which
    # checks with no handlers (SC211's boundary, ADR 0058's seams).
    handler_tokens = {
        place: [_token(t) for t in _open_template_tokens(net, transition, place, outputs)]
        for place in outputs
    }
    handler_tokens = {
        place: tokens for place, tokens in handler_tokens.items() if tokens
    }
    out = TransitionHandlerOutput(
        status="completed",
        outputTokens=handler_tokens,
        error=None,
        metadata={},
    )
    try:
        after, produced = engine.settle(
            reservation.reserved_marking, reservation, out
        )
    except DepositViolation as error:
        raise RecordsToPlayError(
            f"step {step_index}: the engine rejects the deposit of "
            f"[{transition}]: {error}"
        ) from error
    if produced["status"] != "completed":
        raise RecordsToPlayError(
            f"step {step_index}: [{transition}] replayed as "
            f"{produced['status']}, not completed"
        )
    _agree_firing(record, produced, transition, step_index)
    parts = [f"fire [{transition}]", *_with_clauses(reservation.input_tokens, marking)]
    parts.extend(_output_clauses(net, record, reservation.consumed_tokens))
    lines.append(" ".join(parts))
    return after


def _open_template_tokens(
    net: Net,
    transition: str,
    place: str,
    outputs: Mapping[str, Sequence[Token | Mapping[str, Any]]],
) -> list[Token]:
    """The record's tokens into ``place`` whose color matches an OPEN
    produce template (the net does not fill it) — the tokens a play may
    state. Net-filled templates' tokens are left out for the engine to
    compute."""
    open_colors = {
        template.type
        for template in produce_templates(net, transition)
        if template.destination == place and not net_fills(template)
    }
    return [
        _token(t)
        for t in outputs.get(place, ())
        if (
            t.type if isinstance(t, Token) else cast(str, t["type"])
        ) in open_colors
    ]


def _tokens_by_place(
    place_keyed: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[Token]]:
    return {place: [_token(t) for t in tokens] for place, tokens in place_keyed.items()}


def _agree_firing(
    record: Mapping[str, Any],
    produced: Mapping[str, Any],
    transition: str,
    step_index: int,
) -> None:
    """The comparison the writer guarantees: the replayed firing's binding
    and outputs are the record's. Attempts, ids, timestamps and metadata
    are not compared — the play renumbers attempts, and its own records
    carry none of the recorded run's metadata."""
    if produced["transition"] != transition:
        raise RecordsToPlayError(
            f"step {step_index}: the reserved transition "
            f"{produced['transition']!r} is not the record's "
            f"{transition!r} ({record.get('firingId')})"
        )
    if not _same_binding(
        produced["inputTokens"],
        dict(_tokens_by_place(cast(Mapping[str, Sequence[Mapping[str, Any]]], record["inputTokens"]))),
    ):
        raise RecordsToPlayError(
            f"step {step_index}: [{transition}]'s replayed binding differs "
            f"from the record's ({record.get('firingId')})"
        )
    recorded_outputs = {
        place: _token_dicts(list(tokens))
        for place, tokens in cast(
            Mapping[str, Sequence[Mapping[str, Any]]], record["outputTokens"]
        ).items()
        if tokens
    }
    replayed_outputs = {
        place: _token_dicts(list(tokens))
        for place, tokens in produced["outputTokens"].items()
        if tokens
    }
    if recorded_outputs != replayed_outputs:
        raise RecordsToPlayError(
            f"step {step_index}: [{transition}]'s replayed outputs differ "
            f"from the record's ({record.get('firingId')})"
        )


def _yes(inp: Any) -> bool:
    del inp
    return True