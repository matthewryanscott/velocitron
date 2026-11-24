"""CEL backends agree on a timer that compares an int clock with a double.

The CEL spec orders ``int``, ``uint``, and ``double`` across those types.
A deadline dated from the clock (``double(clock.now) + 120``) is a latch:
time moves to it when the latched clock time is one the domains file lists,
and stops there, so the state space is finite and the same on every backend.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from velocitron_analysis import NetModel, load, read_settings
import velocitron_analysis.firing as firing
from velocitron_analysis.firing import Firing
from velocitron_analysis.soundness import Environment, Explorer
from velocitron_cel import (
    CelAdapter,
    CelEvalError,
    CelExprAdapter,
    CelRustAdapter,
    CelpyAdapter,
)

_NET = """\
net grace "A deadline dated from the clock"

(ok) -condition-> [notice]
@notice_out: [notice] -condition-> (suspect)
@notice_clock: (clock) -tick->? [notice]
@notice_out data cel "{'brokenAt': double(binding.clock[0].now) + 120.0}"

(suspect) -condition-> [break]
@break_out: [break] -condition-> (ok)
@break_clock: (clock) -tick->? [break]
[break] timer clock (clock) cel "clock.now >= condition.brokenAt"
[break] timer bind condition (suspect)
[break] timer maturity cel "condition.brokenAt"

(clock) annotation fusion true
marking initial (ok) <- $start
$start: condition {"brokenAt": 0}
marking initial (clock) <- $tick
$tick: tick {"now": 0}
"""

_DOMAINS = '{domains: {"tick.now": [0, 120, 240]}}\n'


def _adapters() -> list[tuple[str, type[CelAdapter]]]:
    found: list[tuple[str, type[CelAdapter]]] = [("celpy", CelpyAdapter)]
    if importlib.util.find_spec("cel") is not None:
        found.append(("rust", CelRustAdapter))
    if importlib.util.find_spec("cel_expr_python") is not None:
        found.append(("cpp", CelExprAdapter))
    return found


def _explore(adapter: type[CelAdapter], path: Path) -> Explorer:
    # given the adapter Firing will bind. It is restored by the caller.
    firing.get_default_adapter = lambda: adapter()
    net, _composition = load(path)
    settings = read_settings(path.with_suffix(".domains.json5"))
    declared = net.proofs
    model = NetModel(
        net,
        overrides=settings.domains,
        instance_color=settings.instance_color,
        final=settings.final
        if settings.final is not None
        else (declared.final if declared is not None else None),
    )
    model.kept_marking()
    environment = Environment(
        settings.injections, settings.updates, settings.firings, settings.starts
    )
    explorer = Explorer(
        net,
        model,
        Firing(net, model),
        environment=environment,
        max_states=2_000,
    )
    explorer.explore()
    return explorer


def test_every_backend_finishes_the_same_deadline(tmp_path: Path) -> None:
    # given: a net whose timer compares an int clock with a double deadline
    # dated from that clock, and every CEL backend this process has
    net = tmp_path / "grace.petrinet"
    net.write_text(_NET, encoding="utf-8")
    net.with_suffix(".domains.json5").write_text(_DOMAINS, encoding="utf-8")
    adapters = _adapters()
    previous = firing.get_default_adapter

    # when: each backend explores it
    try:
        runs = [(name, _explore(adapter, net)) for name, adapter in adapters]
    finally:
        firing.get_default_adapter = previous

    # then: every backend finishes, on the same graph, and time moves to the
    # deadline dated from the last listed clock time and no further
    sizes = []
    for name, explorer in runs:
        clocks = {
            token.data.get("now")
            for state in explorer.states
            for token in state.marking.get("clock", ())
        }
        assert not explorer.capped, name
        assert clocks == {0, 120, 240, 360}, (name, clocks)
        assert any(move.transition == "break" for move in explorer.moves), name
        sizes.append(explorer.size())
    assert len(set(sizes)) == 1


# ``ERROR`` is an evaluation error. A result is the Python value CEL returns.
_ERROR = object()

# One table for every installed backend. Expectations are the CEL conformance
# suite: numeric types share one number line, equality past 2**53 converts the
# integer to double (the ``*_lossy_double`` cases), ``NaN`` equals nothing,
# ``-0.0`` equals ``0``, and map keys use that same equality.
#
# This table is the gate for a later ``common-expression-language`` bump.
# 0.6.0, the version CI installs, fails the scalar rows (``1 == 1.0`` is
# false). 0.10.0 passes those rows and still fails the map-key rows
# (``{1: 'a'}[1u]``, ``1u in {1: 'a'}``, ``{1: 'a'} == {1u: 'a'}``,
# ``{1: 'a'}[1.0]``). Deleting the adapter rewrite after a bump, or a bump
# that changes these results, fails here.
_NUMERIC_EQUALITY: tuple[tuple[str, dict[str, object] | None, object], ...] = (
    ("1 == 1.0", None, True),
    ("1 != 1.0", None, False),
    ("1u == 1.0", None, True),
    ("1u != 1.0", None, False),
    ("1 == 1u", None, True),
    ("1 != 1u", None, False),
    ("1.0 == 1u", None, True),
    ("-0.0 == 0", None, True),
    ("-0.0 == 0.0", None, True),
    ("-0.0 == 0u", None, True),
    ("0 == -0.0", None, True),
    ("double('NaN') == double('NaN')", None, False),
    ("double('NaN') != double('NaN')", None, True),
    ("double('NaN') == 1", None, False),
    ("1 == double('NaN')", None, False),
    ("double('NaN') in [double('NaN')]", None, False),
    ("-1 == 1u", None, False),
    ("-1 == 18446744073709551615u", None, False),
    ("-1 < 0u", None, True),
    ("9007199254740992 == 9007199254740992.0", None, True),
    ("9007199254740993 == 9007199254740992.0", None, True),
    ("9007199254740993 > 9007199254740992.0", None, False),
    ("9007199254740994 == 9007199254740994.0", None, True),
    ("9223372036854775807 == 9223372036854775808.0", None, True),
    ("9223372036854775807 < 9223372036854775808.0", None, False),
    ("9223372036854775807 >= 9223372036854775808.0", None, True),
    ("-9223372036854775808 == -9223372036854775808.0", None, True),
    ("18446744073709551615u == 18446744073709551615.0", None, True),
    ("18446744073709551615u < 18446744073709551616.0", None, False),
    ("[1] == [1.0]", None, True),
    ("[1] != [1.0]", None, False),
    ("[1] == [1u]", None, True),
    ("[1.0, 2.0, 3] == [1u, 2, 3u]", None, True),
    ("[[1]] == [[1.0]]", None, True),
    ("[9007199254740993] == [9007199254740992.0]", None, True),
    ("{'k': 1} == {'k': 1.0}", None, True),
    ("1.0 in [1, 2]", None, True),
    ("1u in [1.0]", None, True),
    ("1.5 in [1, 2]", None, False),
    ("-0.0 in [0]", None, True),
    ("0 in [-0.0]", None, True),
    ("{1: 'a'} == {1u: 'a'}", None, True),
    ("{1: 'a'} != {1u: 'b'}", None, True),
    ("{1: 1.0, 2u: 3u} == {1u: 1, 2: 3.0}", None, True),
    ("{1: 'a', 2u: 'b'} == {2: 'b', 1u: 'a'}", None, True),
    ("{'k': {1: 'a'}} == {'k': {1u: 'a'}}", None, True),
    ("[{1: 'a'}] == [{1u: 'a'}]", None, True),
    ("{1: 'a'}[1u]", None, "a"),
    ("{1: 'a'}[1.0]", None, "a"),
    ("{1u: 'a'}[1]", None, "a"),
    ("{0: 'a'}[-0.0]", None, "a"),
    ("1u in {1: 'a'}", None, True),
    ("1.0 in {1: 'a'}", None, True),
    ("1 in {1u: 'a'}", None, True),
    ("2.0 in {1: 'a'}", None, False),
    ("double('NaN') in {1: 'a'}", None, False),
    ("-0.0 in {0: 'a', 1u: 'b'}", None, True),
    ("1 + 1.0", None, _ERROR),
    ("{1: 'a'}[2]", None, _ERROR),
    ("x == 1.0", {"x": 1}, True),
    ("x == y", {"x": 1, "y": 1.0}, True),
    ("[x] == [1.0]", {"x": 1}, True),
    ("m[k]", {"m": {1: "a"}, "k": 1.0}, "a"),
    ("k in m", {"m": {1: "a"}, "k": 1.0}, True),
    ("k in m", {"m": {1: "a"}, "k": 2.0}, False),
)


def test_every_backend_agrees_on_cross_type_numeric_equality() -> None:
    # given: the conformance cases for equality, inequality, list membership,
    # and map keys across int, uint, and double, on every installed backend
    for name, adapter_type in _adapters():
        adapter = adapter_type()
        for expr, data, expected in _NUMERIC_EQUALITY:
            activation = {} if data is None else data
            # when: the expression is evaluated
            if expected is _ERROR:
                with pytest.raises(CelEvalError):
                    adapter.eval(adapter.compile(expr), activation)
                continue
            got = adapter.eval(adapter.compile(expr), activation)
            # then: the backend matches the spec, and a bool is a real bool
            assert got == expected, (name, expr, got)
            if isinstance(expected, bool):
                assert got is expected, (name, expr)
