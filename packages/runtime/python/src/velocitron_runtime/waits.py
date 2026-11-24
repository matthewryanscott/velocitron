"""Intended waits: cases of a choice where the token waits on purpose.

A transition annotated ``wait`` (``[start_attempt] annotation wait {"when":
"…", "for": "…"}``, or a list of such objects) names the cases of its choice
in which no way out is enabled on purpose: the token waits for something the
outside world does. ``when`` is a CEL condition over ``binding``, the tokens
of the case keyed as the transition's own CEL sees them, plus the places it
inhibits (choice coverage passes those keys to :func:`holds`); ``for`` says in
plain words what the token waits for. Choice coverage reports a gap case as
an intended wait when one condition of a transition of the choice is true
there, and as a gap otherwise (ADR 0057).

This module reads the annotation, checks it (``velocitron validate``), and
evaluates it. The engine ignores the annotation.

References: spec/proofs.md ("Choice coverage"); ADR 0016; ADR 0032; ADR 0057.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from velocitron_cel import CelAdapter, get_default_adapter
from velocitron_engine import Net, Token, Transition

KEY = "wait"


@dataclass(frozen=True)
class Wait:
    """One intended wait of a transition: when it applies, and what for."""

    transition: str
    when: str
    reason: str


def _shape(value: Any) -> list[tuple[str, str]] | None:
    """``(when, for)`` of each entry of a well-formed ``wait``, else ``None``."""
    entries = cast(list[Any], value) if isinstance(value, list) else [value]
    if not entries:
        return None
    found: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            return None
        fields = cast(Mapping[str, Any], entry)
        when, reason = fields.get("when"), fields.get("for")
        if set(fields) != {"when", "for"}:
            return None
        if not isinstance(when, str) or not when:
            return None
        if not isinstance(reason, str) or not reason:
            return None
        found.append((when, reason))
    return found


def intended_waits(transition: Transition) -> list[Wait]:
    """The transition's intended waits; a malformed ``wait`` declares none,
    so its cases still show as gaps."""
    shape = _shape((transition.annotations or {}).get(KEY))
    return [Wait(transition.name, when, reason) for when, reason in shape or ()]


def holds(
    wait: Wait,
    keys: Mapping[str, str],
    tokens: Mapping[str, Sequence[Token]],
    *,
    adapter: CelAdapter | None = None,
) -> bool:
    """Whether the wait's condition is true for these tokens. A condition that
    fails to evaluate, or gives anything but ``true``, does not hold."""
    adapter = adapter if adapter is not None else get_default_adapter()
    binding = {
        key: [token.data for token in tokens.get(place, ())]
        for key, place in keys.items()
    }
    try:
        return adapter.eval(adapter.compile(wait.when), {"binding": binding}) is True
    except Exception:  # noqa: BLE001 - a condition that fails does not hold
        return False


def wait_problems(
    net: Net, *, adapter: CelAdapter | None = None
) -> list[tuple[str, str]]:
    """What is wrong with the ``wait`` annotations of a net, as
    ``(transition, message)`` pairs in transition order."""
    problems: list[tuple[str, str]] = []
    adapter = adapter if adapter is not None else get_default_adapter()
    for transition in net.transitions:
        value = (transition.annotations or {}).get(KEY)
        if value is None:
            continue
        shape = _shape(value)
        if shape is None:
            message = (
                f"the wait of [{transition.name}] must be "
                '{"when": "<CEL>", "for": "<what it waits for>"}, '
                "or a list of them"
            )
            problems.append((transition.name, message))
            continue
        for when, _ in shape:
            try:
                adapter.compile(when)
            except Exception as error:  # noqa: BLE001 - any parse error
                problems.append(
                    (
                        transition.name,
                        f"the wait of [{transition.name}] is not valid CEL: {error}",
                    )
                )
    return problems
