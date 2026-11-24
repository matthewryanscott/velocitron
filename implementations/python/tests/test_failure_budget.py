"""Failure budget + failure-aware selection (ADR 0015).

The opt-in ``Engine(max_consecutive_failures=N)`` failure budget and the
``FiringPolicyInput.consecutiveFailures`` threading, motivated by the reading hour:
a handler that keeps returning ``failed`` leaves its transition enabled
forever (atomic rollback), so ``run`` burns a step per failed fire (spin) and
under ``first-found`` every transition declared after it starves.

Covered surfaces:

* FB1 — the conservative default (``None``): a persistently failing
  transition spins to ``max_steps``, byte-for-byte today's behavior.
* FB2 — spin: with a budget, the run stops after exactly N failed firings
  (quiescence-by-exhaustion), marking unchanged.
* FB3 — starvation: with a budget, ``first-found`` moves past the exhausted
  transition to the one declared after it (the reading hour's starvation shape).
* FB4/FB5 — reset semantics: any completed firing (a sibling's, or the
  transition's own) resets the counts and re-arms the budget.
* FB6/FB7 — policy threading: ``consecutiveFailures`` is keyed by exactly
  the ``enabledTransitions`` entries (absent history = 0), and exhausted
  transitions are hidden from the policy.
* FB8/FB9 — which failure kinds count: resolve-miss (``HandlerNotFound``)
  and a deposit violation under ``record_then_drop`` both count.
* FB10 — determinism: two identically-configured runs produce identical
  journals (excluding timestamps), and failed fires still burn steps so
  firingIds stay deterministic.
* FB11 — configuration validation: a budget < 1 raises ``ValueError`` at
  construction.

ADR 0015's invariant has ONE implementation: the engine-owned selection
ledger (``Engine.selection_ledger``) counting consecutive ``failed`` firings
and clearing every count on any ``completed`` firing. ``Engine.advance`` makes one
per run; the Runtime's admission loop consults a long-lived one from the same
source and adds only its own seam rule (a failed transition is parked until an
input place changes). The Runtime-side behavior is covered through the public
Runtime surface in ``test_runtime.py`` — never by re-implementing the
invariant there.
"""

from __future__ import annotations

from typing import Any

import pytest

from velocitron_engine import (
    FiringPolicyInput,
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_runtime import Engine

from velocitron_petrinet import parse_net
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
)

from _journal_fixtures import CapturingJournal


# ── Shared helpers ───────────────────────────────────────────────────────


def _tok(t: str = "tick", **data: Any) -> Token:
    """A minimal token of type ``t`` with payload ``data``."""
    return Token(type=t, data=dict(data))


def _marking(**places: list[Token]) -> Marking:
    """A marking from ``place=tokens`` keyword pairs."""
    return Marking({place: list(toks) for place, toks in places.items()})


def _net(d: dict[str, Any]) -> Net:
    """Parse a net dict (thin alias for the parser)."""
    return parse_net(d)


def _fail(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    """A handler that always fails (the reading hour's failing step)."""
    return {
        "status": "failed",
        "outputTokens": {},
        "error": {"type": "SimulatedFailure", "message": "still failing"},
        "metadata": {},
    }


def _emit(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
    """Pass-through: the fixed produce-template data supplies the outputs."""
    return {"status": "completed", "outputTokens": {}, "error": None, "metadata": {}}


def _records_without_timestamps(journal: CapturingJournal) -> list[dict[str, Any]]:
    """Firing records with the non-deterministic ``timestamps`` stripped, so
    two replay runs can be compared record-for-record (D5)."""
    out: list[dict[str, Any]] = []
    for rec in journal.firings:
        copy = dict(rec)
        copy.pop("timestamps", None)
        out.append(copy)
    return out


# ── Nets ─────────────────────────────────────────────────────────────────

# Spin (FB1/FB2): one persistently failing transition. Atomic rollback keeps
# `req` populated, so `deliver` stays enabled after every failed fire.
_SPIN_NET = _net(
    {
        "name": "fb-spin",
        "places": [
            {"name": "req", "accepts": ["tick"]},
            {"name": "done", "accepts": ["tick"]},
        ],
        "transitions": [{"name": "deliver", "handler": "deliver"}],
        "arcs": [
            {
                "from": {"place": "req"},
                "to": {"transition": "deliver"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"transition": "deliver"},
                "to": {"place": "done"},
                "produce": {"type": "tick", "destination": "done", "data": {}},
            },
        ],
    }
)

# Starvation (FB3): the reading hour's shape, minimal. The failing `deliver`
# is declared FIRST, so under first-found it starves `timeout_fire` forever
# without a budget. `timeout_fire` consumes BOTH the deadline and the request
# (the terminal-consumes-the-window idiom), so once it fires, `deliver` is
# disabled and the run reaches true quiescence.
_STARVE_NET = _net(
    {
        "name": "fb-starve",
        "places": [
            {"name": "req", "accepts": ["tick"]},
            {"name": "deadline", "accepts": ["tick"]},
            {"name": "err", "accepts": ["tick"]},
        ],
        "transitions": [
            {"name": "deliver", "handler": "deliver"},
            {"name": "timeout_fire", "handler": "timeout_fire"},
        ],
        "arcs": [
            {
                "from": {"place": "req"},
                "to": {"transition": "deliver"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"place": "deadline"},
                "to": {"transition": "timeout_fire"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"place": "req"},
                "to": {"transition": "timeout_fire"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"transition": "timeout_fire"},
                "to": {"place": "err"},
                "produce": {"type": "tick", "destination": "err", "data": {}},
            },
        ],
    }
)

# Reset (FB4): failing `ta` declared first; completing `tb` on its own input.
# tb's completion resets ta's count, so ta earns a fresh budget of retries.
_RESET_NET = _net(
    {
        "name": "fb-reset",
        "places": [
            {"name": "pa", "accepts": ["tick"]},
            {"name": "pb", "accepts": ["tick"]},
            {"name": "out", "accepts": ["tick"]},
        ],
        "transitions": [
            {"name": "ta", "handler": "ta"},
            {"name": "tb", "handler": "tb"},
        ],
        "arcs": [
            {
                "from": {"place": "pa"},
                "to": {"transition": "ta"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"place": "pb"},
                "to": {"transition": "tb"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"transition": "tb"},
                "to": {"place": "out"},
                "produce": {"type": "tick", "destination": "out", "data": {}},
            },
        ],
    }
)

# Own-success reset (FB5): a self-loop that stays enabled across fires, with
# a scripted handler (fail/complete per call), so one transition can fail,
# complete (resetting its own count), then fail again on a fresh budget.
_LOOP_NET = _net(
    {
        "name": "fb-loop",
        "places": [{"name": "loop", "accepts": ["tick"]}],
        "transitions": [{"name": "step", "handler": "step"}],
        "arcs": [
            {
                "from": {"place": "loop"},
                "to": {"transition": "step"},
                "consume": {"type": "tick"},
            },
            {
                "from": {"transition": "step"},
                "to": {"place": "loop"},
                "produce": {"type": "tick", "destination": "loop", "data": {}},
            },
        ],
    }
)


def _scripted(script: list[str]) -> Any:
    """A handler that follows ``script`` ("fail"/"complete") per invocation,
    then keeps failing once the script is spent (deterministic — a pure
    function of the invocation count, never wall-clock)."""
    calls = {"n": 0}

    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        action = script[calls["n"]] if calls["n"] < len(script) else "fail"
        calls["n"] += 1
        if action == "complete":
            return _emit(inp)
        return _fail(inp)

    return handler


# ── FB1/FB2: the spin case ────────────────────────────────────────────────


class TestFailureBudgetSpin:
    """FB1/FB2: a persistently failing transition — the reading hour's spin."""

    def test_fb1_default_no_budget_spins_to_max_steps(self):
        """FB1 — the default (``max_consecutive_failures=None``) is
        conservative/backward-compatible: a persistently failing transition
        stays selectable and ``run`` burns every step on it, exactly the
        pre-ADR-0015 behavior (and the locked resolve-miss-spin contract)."""
        # given an engine with NO budget over the always-failing net
        reg = HandlerRegistry()
        reg.register_transition("deliver", _fail)
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal)
        # when running with a step cap
        final = engine.advance(_SPIN_NET, _marking(req=[_tok()]), max_steps=10)
        # then every step was burned on a failed fire of the same transition
        assert len(journal.firings) == 10
        assert all(r["status"] == "failed" for r in journal.firings)
        # and the marking is unchanged (atomic rollback kept the request)
        assert list(final.get("req", [])) == [_tok()]

    def test_fb2_budget_stops_the_spin_after_n_failures(self):
        """FB2 — with ``max_consecutive_failures=3`` the run stops after
        exactly 3 failed firings (quiescence-by-exhaustion): the transition
        is still enabled in the enablement sense, but it is exhausted and
        nothing else can fire."""
        # given an engine with a budget of 3 over the always-failing net
        reg = HandlerRegistry()
        reg.register_transition("deliver", _fail)
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal, max_consecutive_failures=3)
        # when running with a generous step cap
        final = engine.advance(_SPIN_NET, _marking(req=[_tok()]), max_steps=100)
        # then exactly 3 failed attempts were recorded, not 100
        assert [r["status"] for r in journal.firings] == ["failed"] * 3
        assert [r["transition"] for r in journal.firings] == ["deliver"] * 3
        # and the marking is unchanged (rollback; nothing was consumed)
        assert list(final.get("req", [])) == [_tok()]
        assert list(final.get("done", [])) == []


# ── FB3: the starvation case ─────────────────────────────────────────────


class TestFailureBudgetStarvation:
    """FB3: the reading hour's starvation — a failing transition declared
    first starves the deadline under first-found; the budget unblocks it."""

    def test_fb3_first_found_moves_past_the_exhausted_transition(self):
        """FB3 — ``deliver`` (declared first, always failing) fails its
        budget of 2, is exhausted, and ``first-found`` selects
        ``timeout_fire`` — the transition that starved forever without the
        budget (the reading hour's livelock). ``timeout_fire`` consumes the
        request window, so the run then reaches true quiescence."""
        # given the starve net with a failing deliver and a budget of 2
        reg = HandlerRegistry()
        reg.register_transition("deliver", _fail)
        reg.register_transition("timeout_fire", _emit)
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal, max_consecutive_failures=2)
        # when running under the DEFAULT first-found policy
        final = engine.advance(
            _STARVE_NET,
            _marking(req=[_tok()], deadline=[_tok()]),
            max_steps=100,
        )
        # then deliver failed twice, then timeout_fire fired
        assert [(r["transition"], r["status"]) for r in journal.firings] == [
            ("deliver", "failed"),
            ("deliver", "failed"),
            ("timeout_fire", "completed"),
        ]
        # and the error token landed; the request window was consumed
        assert list(final.get("err", [])) == [_tok()]
        assert list(final.get("req", [])) == []

    def test_fb3_control_without_budget_the_timeout_starves(self):
        """FB3 control — the same net and marking with NO budget livelocks:
        first-found re-selects the failing ``deliver`` every step and
        ``timeout_fire`` never fires (the control run, with no budget)."""
        # given the identical setup except no budget
        reg = HandlerRegistry()
        reg.register_transition("deliver", _fail)
        reg.register_transition("timeout_fire", _emit)
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal)
        # when running
        final = engine.advance(
            _STARVE_NET,
            _marking(req=[_tok()], deadline=[_tok()]),
            max_steps=20,
        )
        # then every step was a failed deliver; the timeout starved
        assert [r["transition"] for r in journal.firings] == ["deliver"] * 20
        assert list(final.get("err", [])) == []
        assert list(final.get("deadline", [])) == [_tok()]


# ── FB4/FB5: reset semantics ─────────────────────────────────────────────


class TestFailureBudgetReset:
    """FB4/FB5: any completed firing resets every count — a sibling's
    completion (the marking changed) or the transition's own success."""

    def test_fb4_sibling_completion_resets_the_exhausted_count(self):
        """FB4 — ``ta`` (budget 2) fails twice and is exhausted; ``tb``
        completes, resetting all counts; ``ta`` earns two fresh retries; with
        ``tb`` spent, exhaustion then stops the run."""
        # given ta always failing, tb completing once, budget 2
        reg = HandlerRegistry()
        reg.register_transition("ta", _fail)
        reg.register_transition("tb", _emit)
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal, max_consecutive_failures=2)
        # when running
        engine.advance(_RESET_NET, _marking(pa=[_tok()], pb=[_tok()]), max_steps=100)
        # then the sequence shows exhaust -> sibling completes -> fresh budget
        assert [(r["transition"], r["status"]) for r in journal.firings] == [
            ("ta", "failed"),
            ("ta", "failed"),
            ("tb", "completed"),
            ("ta", "failed"),
            ("ta", "failed"),
        ]

    def test_fb5_own_completion_resets_the_count(self):
        """FB5 — a transition that fails twice (budget 3), completes, then
        keeps failing gets a FRESH budget of 3 after its own success: the
        run records 2 failures + 1 completion + 3 failures, then stops."""
        # given a scripted self-loop handler and a budget of 3
        reg = HandlerRegistry()
        reg.register_transition("step", _scripted(["fail", "fail", "complete"]))
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal, max_consecutive_failures=3)
        # when running
        engine.advance(_LOOP_NET, _marking(loop=[_tok()]), max_steps=100)
        # then the completion reset the count and re-armed the full budget
        assert [r["status"] for r in journal.firings] == [
            "failed",
            "failed",
            "completed",
            "failed",
            "failed",
            "failed",
        ]


# ── FB6/FB7: policy threading ────────────────────────────────────────────


class TestConsecutiveFailuresThreading:
    """FB6/FB7: ``FiringPolicyInput.consecutiveFailures`` — keyed by exactly
    the ``enabledTransitions`` entries, threaded to every policy (budget or
    not), with exhausted transitions hidden from the policy."""

    def test_fb6_counts_threaded_to_every_policy_without_a_budget(self):
        """FB6 — the counts thread to a custom policy even with NO budget
        configured (the failure-aware-policy seam stands alone), incrementing
        across consecutive failed fires."""
        # given a capture policy over the failing spin net, no budget
        captured: list[dict[str, int]] = []

        def capture(inp: FiringPolicyInput) -> str | None:
            captured.append(dict(inp["consecutiveFailures"]))
            assert set(inp["consecutiveFailures"]) == set(inp["enabledTransitions"])
            enabled = inp["enabledTransitions"]
            return enabled[0] if enabled else None

        reg = HandlerRegistry()
        reg.register_transition("deliver", _fail)
        reg.register_firing_policy("capture", capture)
        engine = Engine(reg, policy="capture")
        # when running three steps
        engine.advance(_SPIN_NET, _marking(req=[_tok()]), max_steps=3)
        # then the policy saw the count grow, absent history mapping to 0
        assert captured == [{"deliver": 0}, {"deliver": 1}, {"deliver": 2}]

    def test_fb7_exhausted_transition_is_hidden_from_the_policy(self):
        """FB7 — once ``deliver`` exhausts its budget of 1, the policy input
        no longer lists it: ``enabledTransitions`` (and the mirrored
        ``priorities``/``consecutiveFailures`` keys) carry only the
        still-selectable ``timeout_fire``."""
        # given a capture policy over the starve net with a budget of 1
        captured: list[FiringPolicyInput] = []

        def capture(inp: FiringPolicyInput) -> str | None:
            captured.append(inp)
            enabled = inp["enabledTransitions"]
            return enabled[0] if enabled else None

        reg = HandlerRegistry()
        reg.register_transition("deliver", _fail)
        reg.register_transition("timeout_fire", _emit)
        reg.register_firing_policy("capture", capture)
        engine = Engine(reg, policy="capture", max_consecutive_failures=1)
        # when running to quiescence
        engine.advance(
            _STARVE_NET,
            _marking(req=[_tok()], deadline=[_tok()]),
            max_steps=100,
        )
        # then step 0 offered both; step 1 hid the exhausted deliver
        assert captured[0]["enabledTransitions"] == ["deliver", "timeout_fire"]
        assert captured[1]["enabledTransitions"] == ["timeout_fire"]
        # and the sibling maps mirror the filtered list exactly
        assert captured[1]["priorities"] == {"timeout_fire": 0}
        assert captured[1]["consecutiveFailures"] == {"timeout_fire": 0}


# ── FB8/FB9: which failure kinds count ───────────────────────────────────


class TestCountedFailureKinds:
    """FB8/FB9: every ``failed`` record ``run`` receives from ``fire``
    counts toward the budget — resolve-miss and deposit-violation-drop
    included, not just handler-``failed``."""

    def test_fb8_resolve_miss_counts_toward_the_budget(self):
        """FB8 — an unregistered handler (``HandlerNotFound`` -> ``failed``
        record) exhausts the budget like a handler-``failed``: 2 failed
        records, then the run stops instead of spinning to ``max_steps``.
        (The locked no-budget resolve-miss spin is untouched — FB1 covers
        the default.)"""
        # given the spin net with NO handler registered and a budget of 2
        reg = HandlerRegistry()
        journal = CapturingJournal()
        engine = Engine(reg, journal=journal, max_consecutive_failures=2)
        # when running
        engine.advance(_SPIN_NET, _marking(req=[_tok()]), max_steps=100)
        # then both failures were resolve-misses and the run stopped at 2
        assert [r["status"] for r in journal.firings] == ["failed", "failed"]
        assert all(
            r["error"] is not None and r["error"]["type"] == "HandlerNotFound"
            for r in journal.firings
        )

    def test_fb9_deposit_violation_drop_counts_toward_the_budget(self):
        """FB9 — under ``deposit_violation="record_then_drop"`` a violating
        fire returns a ``failed`` record (routed through the violation hook)
        and counts: 2 violation records, then the run stops."""

        # given a handler that deposits to a place with no produce template
        def violate(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
            return {
                "status": "completed",
                "outputTokens": {"nowhere": [_tok()]},
                "error": None,
                "metadata": {},
            }

        reg = HandlerRegistry()
        reg.register_transition("deliver", violate)
        journal = CapturingJournal()
        engine = Engine(
            reg,
            journal=journal,
            deposit_violation="record_then_drop",
            max_consecutive_failures=2,
        )
        # when running
        final = engine.advance(_SPIN_NET, _marking(req=[_tok()]), max_steps=100)
        # then exactly 2 violations were recorded (the violation hook, not
        # record_firing) and the run stopped by exhaustion
        assert len(journal.violations) == 2
        assert len(journal.firings) == 0
        assert list(final.get("req", [])) == [_tok()]


# ── FB10: determinism / replay ───────────────────────────────────────────


class TestFailureBudgetDeterminism:
    """FB10: the budget is step/attempt-based and deterministic — two
    identically-configured runs replay record-for-record (D5)."""

    def test_fb10_two_runs_replay_identically_and_attempts_advance(self):
        """FB10 — same net + same handlers + same budget => identical
        journals (excluding timestamps). Failed fires still advance the step
        counter (``attempt`` 0,1,2,...), so firingIds stay deterministic and
        collision-free across the failure/reset sequence."""
        # given two identically-configured engines over the reset net
        journals: list[CapturingJournal] = []
        for _ in range(2):
            reg = HandlerRegistry()
            reg.register_transition("ta", _fail)
            reg.register_transition("tb", _emit)
            journal = CapturingJournal()
            journals.append(journal)
            engine = Engine(reg, journal=journal, max_consecutive_failures=2)
            # when each runs over an equal marking
            engine.advance(_RESET_NET, _marking(pa=[_tok()], pb=[_tok()]), max_steps=100)
        j1, j2 = journals
        # then the journals are equal record-for-record (excluding timestamps)
        assert _records_without_timestamps(j1) == _records_without_timestamps(j2)
        # and attempts advanced monotonically through failures and resets
        assert [r["attempt"] for r in j1.firings] == [0, 1, 2, 3, 4]
        assert len({r["firingId"] for r in j1.firings}) == 5


# ── FB11: configuration validation ───────────────────────────────────────


class TestFailureBudgetValidation:
    """FB11: the budget is engine config, validated at construction like the
    firing-policy ref and ``deposit_violation`` mode."""

    @pytest.mark.parametrize("bad", [0, -1])
    def test_fb11_budget_below_one_raises_at_init(self, bad: int):
        """FB11 — a budget of 0 would exhaust every transition before its
        first fire; negative is nonsense. Both raise ``ValueError`` at
        ``Engine.__init__``, never surfacing out of ``run``."""
        # given / when / then a sub-1 budget raises at construction
        with pytest.raises(ValueError):
            Engine(HandlerRegistry(), max_consecutive_failures=bad)

    def test_fb11_budget_of_one_and_none_construct(self):
        """FB11 — the smallest legal budget (1) and the default (``None``)
        both construct."""
        # given / when / then the legal values construct without raising
        Engine(HandlerRegistry(), max_consecutive_failures=1)
        Engine(HandlerRegistry(), max_consecutive_failures=None)
