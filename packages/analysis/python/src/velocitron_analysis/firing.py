"""Fire a net through the real engine, with outputs from the data domains.

The prover never re-implements enablement. It asks the engine for every
firing a marking admits (``Engine.reservations``: each viable binding of
each enabled transition, reserved, from one walk of the enumeration), then
settles a reservation with output tokens in place of a handler, as a play
does (symbolic firing).

A produce template with ``data`` or ``data cel`` is filled by the engine.
Every other template stands for a handler, and the prover tries each output
its domains allow: the carry rule's token (or a token embedded in a consumed
one, or a fresh token of the instance) with the fields that the destination
place's readers test set to each of their values.

References: spec/proofs.md; ADR 0031 (symbolic firing); ADR 0036.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence, Set
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
from typing import Any

from velocitron_cel import CelAdapter, CelEvalError, get_default_adapter
from velocitron_engine import (
    DepositViolation,
    Engine,
    FiringReservation,
    HandlerRegistry,
    Marking,
    Net,
    ProduceTemplate,
    Token,
    TransitionHandlerOutput,
)

from .analysis import INSTANCE, NetModel


class _CachingCelAdapter(CelAdapter):
    """Keep each CEL result per expression and activation.

    A search repeats the same expression on the same token values. The
    public ``CachingCelAdapter`` lives in ``velocitron_cel``. This copy is
    private so the prover does not import that wrapper.
    """

    def __init__(self, inner: CelAdapter, limit: int = 100_000) -> None:
        self._inner = inner
        self._limit = limit
        self._results: dict[tuple[int, str], tuple[Any, bool, Any]] = {}

    def compile(self, expr: str) -> Any:
        return self._inner.compile(expr)

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        try:
            text = json.dumps(data, sort_keys=True)
        except (TypeError, ValueError):
            return self._inner.eval(compiled, data)
        key = (id(compiled), text)
        found = self._results.get(key)
        # The entry holds the compiled expression, so its id is not reused
        # while the entry lives.
        if found is None or found[0] is not compiled:
            try:
                found = (compiled, True, self._inner.eval(compiled, data))
            except CelEvalError as error:
                found = (compiled, False, str(error))
            if len(self._results) >= self._limit:
                self._results.clear()
            self._results[key] = found
        _, ok, value = found
        if not ok:
            raise CelEvalError(value)
        return deepcopy(value) if isinstance(value, (dict, list)) else value  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


def token_key(token: Token) -> str:
    return f"{token.type} {json.dumps(token.data, sort_keys=True, ensure_ascii=False)}"


class MarkingKeys:
    """Order-free keys of markings (a multiset per place).

    A fired marking shares the token lists of the places the firing did not
    touch with the marking it came from, so the key of each list is kept by
    the list's identity. The cache holds the list too, so an id is never
    reused while its entry lives. Only the lists of kept markings are
    remembered (``keep``), so a successor that turns out to be known does
    not stay in memory.
    """

    def __init__(
        self, places: Sequence[str], text: Callable[[Token], str] = token_key
    ) -> None:
        self._order = {place: i for i, place in enumerate(places)}
        self._text = text
        self._place_keys: dict[int, tuple[Sequence[Token], tuple[str, ...]]] = {}
        self._pending: list[tuple[Sequence[Token], tuple[str, ...]]] = []

    def key(
        self, marking: Marking, places: Set[str], marked: Set[str]
    ) -> tuple[Any, ...]:
        """The key of the tokens in ``places``, in the order of the places
        given to the constructor. ``marked`` names the places that hold
        tokens: the caller has it already, so the key does not walk every
        place of the marking again."""
        self._pending.clear()
        order = self._order
        tokens_of = marking.__getitem__
        tokens_key = self._tokens_key
        chosen = sorted((order[place], place) for place in marked if place in places)
        return tuple((place, tokens_key(tokens_of(place))) for _, place in chosen)

    def keep(self) -> None:
        """Remember the token lists of the marking just keyed."""
        for tokens, key in self._pending:
            self._place_keys[id(tokens)] = (tokens, key)
        self._pending.clear()

    def _tokens_key(self, tokens: Sequence[Token]) -> tuple[str, ...]:
        found = self._place_keys.get(id(tokens))
        if found is not None and found[0] is tokens:
            return found[1]
        key = tuple(sorted(self._text(token) for token in tokens))
        self._pending.append((tokens, key))
        return key


Binding = dict[str, list[Token]]
Outputs = tuple[tuple[str, tuple[Token, ...]], ...]


@dataclass(frozen=True)
class Fired:
    marking: Marking
    consumed: dict[str, list[Token]]
    error: str | None = None


class Firing:
    def __init__(self, net: Net, model: NetModel) -> None:
        self.net = net
        self.model = model
        # Most evaluations in a search repeat an earlier one: the same
        # expression on the same token values in another marking.
        self._cel = _CachingCelAdapter(get_default_adapter())
        self.engine = Engine(HandlerRegistry(), cel_adapter=self._cel)
        self._templates: dict[str, list[ProduceTemplate]] = {}
        self._outputs: dict[tuple[Any, ...], list[Outputs]] = {}
        for tr in net.transitions:
            self._templates[tr.name] = [
                arc.produce
                for arc in model.outputs.get(tr.name, ())
                if arc.produce is not None
            ]

    def enabled(self, marking: Marking) -> list[str]:
        return self.engine.enabled_transitions(self.net, marking)

    def can_fire(self, marking: Marking, transition: str) -> bool:
        return self.engine.select_binding(self.net, transition, marking) is not None

    def predicate_holds(self, cel: str, token: Token) -> bool:
        """An arc's CEL predicate on one token, as the engine reads it: on
        the token's data, an evaluation error counting as false."""
        try:
            return self._cel.eval(self._cel.compile(cel), token.data) is True
        except Exception:  # noqa: BLE001 - any eval error => predicate false, as in the engine
            return False

    def reservations(self, marking: Marking) -> dict[str, list[FiringReservation]]:
        """Every enabled transition with a reservation per binding that
        passes the engine's gates, from one walk of its enumeration."""
        return self.engine.reservations(self.net, marking)

    def handler_templates(self, transition: str) -> list[ProduceTemplate]:
        return [
            template
            for template in self._templates[transition]
            if template.data is None and template.cel is None
        ]

    def reserve(
        self, marking: Marking, transition: str, binding: Binding
    ) -> FiringReservation | None:
        return self.engine.reserve(
            self.net, marking, transition, attempt=0, choose=lambda b: _same(b, binding)
        )

    def consumed(
        self, marking: Marking, transition: str, binding: Binding
    ) -> dict[str, list[Token]]:
        reservation = self.reserve(marking, transition, binding)
        return dict(reservation.consumed_tokens) if reservation is not None else {}

    def outputs(
        self, transition: str, consumed: Mapping[str, Sequence[Token]], *, full: bool
    ) -> list[Outputs]:
        """Every output a handler of ``transition`` may give, per the domains.

        The answer depends only on the consumed tokens' data, and the same
        tokens are consumed in many markings, so it is kept per transition
        and consumed data. The kept tokens are shared, which is safe since
        tokens are never changed.
        """
        key = (
            transition,
            full,
            tuple(
                (place, tuple(token_key(token) for token in tokens))
                for place, tokens in consumed.items()
            ),
        )
        found = self._outputs.get(key)
        if found is None:
            found = self._outputs[key] = self._new_outputs(
                transition, consumed, full=full
            )
        return found

    def _new_outputs(
        self, transition: str, consumed: Mapping[str, Sequence[Token]], *, full: bool
    ) -> list[Outputs]:
        templates = self.handler_templates(transition)
        if not templates:
            return [()]
        tokens = [token for place in consumed.values() for token in place]
        by_color: dict[str, list[dict[str, Any]]] = {}
        for token in tokens:
            by_color.setdefault(token.type, []).append(token.data)
        per_template: list[list[Token]] = []
        for template in templates:
            base = _base(self.model, template.type, tokens)
            variants = self.model.token_variants(
                template.type,
                vary=self.model.tested(template.destination, template.type),
                own=INSTANCE,
                full=full,
                base=base,
                bound=by_color,
            )
            per_template.append([Token(template.type, data) for data in variants])
        result: list[Outputs] = []
        for choice in product(*per_template):
            grouped: dict[str, list[Token]] = {}
            for template, token in zip(templates, choice, strict=True):
                grouped.setdefault(template.destination, []).append(token)
            result.append(
                tuple((place, tuple(toks)) for place, toks in grouped.items())
            )
        return result

    def fire(
        self, marking: Marking, transition: str, binding: Binding, outputs: Outputs
    ) -> Fired:
        return self.settle(marking, self.reserve(marking, transition, binding), outputs)

    def settle(
        self,
        marking: Marking,
        reservation: FiringReservation | None,
        outputs: Outputs,
    ) -> Fired:
        """Fire a reserved binding with these outputs; the reservation can
        be settled again with other outputs."""
        if reservation is None:
            return Fired(marking, {}, "not enabled")
        out: TransitionHandlerOutput = {
            "status": "completed",
            "outputTokens": {place: list(tokens) for place, tokens in outputs},
            "error": None,
            "metadata": {},
        }
        try:
            committed, record = self.engine.settle(
                reservation.reserved_marking, reservation, out
            )
        except DepositViolation as error:
            return Fired(marking, dict(reservation.consumed_tokens), str(error))
        if record["status"] != "completed":
            message = (record.get("error") or {}).get("message", "failed")
            return Fired(marking, dict(reservation.consumed_tokens), str(message))
        return Fired(committed, dict(reservation.consumed_tokens))


def _same(binding: Mapping[str, Sequence[Token]], wanted: Binding) -> bool:
    if set(binding) != set(wanted):
        return False
    return all(list(binding[place]) == wanted[place] for place in wanted)


def _base(
    model: NetModel, color: str, tokens: Sequence[Token]
) -> dict[str, Any] | None:
    """The data a handler output starts from: the carry rule's token, or a
    whole token of this color embedded in a consumed token."""
    same = [token for token in tokens if token.type == color]
    if len(same) == 1:
        return dict(same[0].data)
    if same:
        return None
    embedded = [
        token.data[key]
        for token in tokens
        for key in sorted(token.data)
        if model.embeds.get((token.type, key)) == color
        and isinstance(token.data[key], dict)
    ]
    if len(embedded) == 1:
        return dict(embedded[0])
    return None
