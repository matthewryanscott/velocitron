"""The symbolic-output rule: one home shared by the play checker and the
engine's ``advance(outputs=...)`` seam.

A handlerless net fired symbolically still needs output data for each
produce template. The rule settled by ADR 0031 — the net fills the
template itself (``data`` / ``data cel``), or the one consumed token of
the template's color is carried — lives here, so the play checker's
``fire`` and the engine's symbolic advance read the same judgement and
cannot drift.

References: spec/firing-semantics.md (e, f); ADR 0031 (the carry rule);
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from .contract import TransitionHandlerOutput
from .schema import Token

if TYPE_CHECKING:
    from .engine import FiringReservation
    from .schema import Net, ProduceTemplate

__all__ = [
    "carry_rule",
    "net_fills",
    "produce_templates",
    "symbolic_outputs",
]


def produce_templates(net: Net, transition: str) -> list[ProduceTemplate]:
    """The transition's produce templates, in declaration order."""
    return [
        arc.produce
        for arc in net.arcs
        if arc.produce is not None and arc.from_transition == transition
    ]


def net_fills(template: ProduceTemplate) -> bool:
    """Whether the net fills ``template`` itself — literal ``data`` or a
    ``data cel`` — so a play may not state its tokens (SC211)."""
    return template.data is not None or template.cel is not None


def carry_rule(
    templates: list[ProduceTemplate],
    consumed_tokens: dict[str, list[Token]],
) -> dict[str, list[Token]] | None:
    """The carry rule over the templates the net does not fill.

    For each non-net-filled template: when the consumed tokens hold
    *exactly one* token of the template's color, its data is copied
    (deepcopy — the consumed token is never aliased) into a new token at
    the template's destination. ``consumed_tokens`` is keyed by place (a
    :class:`FiringReservation`'s ``consumed_tokens``); the rule groups
    the tokens by color. ``None`` when the rule cannot fill some
    template — zero candidates, or several. Read tokens never carry
    (they are the environment), so the caller must pass consume-mode
    tokens only.

    References: ADR 0031 (SC303's own line).
    """
    carried: dict[str, list[Token]] = {}
    carried_by_color: dict[str, list[Token]] = {}
    for token in (tok for tokens in consumed_tokens.values() for tok in tokens):
        carried_by_color.setdefault(token.type, []).append(token)
    for template in templates:
        if net_fills(template):
            continue
        candidates = carried_by_color.get(template.type, [])
        if len(candidates) != 1:
            return None
        carried.setdefault(template.destination, []).append(
            Token(template.type, deepcopy(candidates[0].data))
        )
    return carried


def symbolic_outputs(
    net: Net, reservation: FiringReservation
) -> TransitionHandlerOutput | None:
    """The default :class:`~velocitron_engine.OutputProvider`: the net's
    ``data`` / ``data cel`` templates are left to the engine's deposit
    (which evaluates them over the binding), and every remaining template
    is filled by the carry rule over the reservation's consumed tokens.

    ``None`` means the firing cannot be determined — the caller skips the
    transition, exactly as the play checker's SC303 rule does. A transition
    with a ``handler`` fact is determined only when the net fills every
    template: its handler writes the rest, and a carried token would be a
    guess.
    """
    del net  # the templates come from the reservation's own net
    templates = [
        template
        for template in produce_templates(reservation.net, reservation.transition)
        if not net_fills(template)
    ]
    if not templates:
        return {"status": "completed", "outputTokens": {}, "error": None, "metadata": {}}
    if any(
        transition.name == reservation.transition and transition.handler is not None
        for transition in reservation.net.transitions
    ):
        return None
    carried = carry_rule(templates, reservation.consumed_tokens)
    if carried is None:
        return None
    return {
        "status": "completed",
        "outputTokens": carried,
        "error": None,
        "metadata": {},
    }
