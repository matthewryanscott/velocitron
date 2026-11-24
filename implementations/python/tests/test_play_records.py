"""Turning journal records into a play (``records_to_play``).

Every record the checker produces is turned back into a step, and the
step-for-step records of the replayed play are the original occurrence
sequence's: a play that plays a recorded run again.

References: spec/play-language.md; ADR 0031; ADR 0059 (occurrence, item 4);
ADR 0060 (clock moves are machine-form ``update`` steps).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_petrinet import parse_net
from velocitron_play import (
    parse_play,
    read_play,
)
from velocitron_play_check import (
    PlayTrace,
    RecordsToPlayError,
    check_play,
    records_to_play,
)
from velocitron_play_check import trace_json
from velocitron_engine import (
    Marking,
    Net,
    Token,
)

_CASES = Path(__file__).parents[3] / "packages" / "spec" / "conformance" / "play"
_FIXTURES = Path(__file__).parent / "fixtures" / "play"


def _serial(value: Any) -> Any:
    from velocitron_journal import serialize_record_value

    return serialize_record_value(value)


def _plain(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records as their JSON form, timestamps dropped — the engine takes
    them from the wall clock, so no two replays agree on them."""

    def clean(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in json.loads(json.dumps(record, default=_serial)).items()
            if key not in ("timestamps", "firingId", "injectionId", "attempt", "metadata")
        }

    return [clean(record) for record in records]


def _records(trace: PlayTrace) -> list[dict[str, Any]]:
    """The trace's plain-dict records (dict copies)."""
    return [dict(r) for step in trace.steps for r in step.records]


def _occurrence(trace: PlayTrace) -> list[dict[str, Any]]:
    """The trace's occurrence records as ``trace_json`` projects them: ids,
    attempts, timestamps and metadata left out — the replay numbers its own
    steps, so no two plays agree on those."""
    return [r for step in trace_json(trace)["steps"] for r in step["records"]]


def _roundtrip(case_dir: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    """Check a conformance case, replay its traces' records as plays, check
    those, and compare every record: the round-trip the writer promises."""
    play = read_play(case_dir / "case.play")
    report = check_play(play)
    lines = (
        [f'net "{play.net}"'] if play.net else [f'use "{u.ref}" as {u.alias}' for u in play.uses]
        + [f'wire {w.from_alias}.({w.from_place}) -> {w.to_alias}.({w.to_place})' for w in play.wires]
        + [f'share {s.members[0][0]}.({s.members[0][1]})' + "".join(f' ~ {a}.({p})' for a, p in s.members[1:]) for s in play.shares]
        + [f'refine {r.alias}.[{r.transition}] by {r.by}' for r in play.refines]
    )
    net_line = "\n".join(lines)
    replayed: list[tuple[str, list[dict[str, Any]]]] = []
    for trace in report.traces:
        records = _records(trace)
        if not records:
            continue
        text = records_to_play(
            trace.subject.net,
            trace.initial,
            records,
            net_line=net_line,
            name=f"{play.name}_{trace.path.name}_replay",
        )
        replay_play = parse_play(text, origin=case_dir)
        replay_report = check_play(replay_play)
        (replay_trace,) = replay_report.traces
        # then: the replayed play passes, and its records are the source's
        #   (its preamble's injects replay before the records, so the
        #   comparison aligns the tails)
        assert replay_trace.failure is None, (
            f"{case_dir.name}/{trace.path.name}: {replay_trace.failure}"
        )
        source_occurrence = _occurrence(trace)
        replay_occurrence = _occurrence(replay_trace)
        tail = replay_occurrence[-len(source_occurrence) :]
        assert tail == source_occurrence, (
            f"{case_dir.name}/{trace.path.name} records differ"
        )
        replayed.append((trace.path.name, records))
    return replayed


def _shop_net() -> Net:
    return parse_net(
        compile_petrinet_text(
            (_FIXTURES / "shop.petrinet").read_text(encoding="utf-8"),
            "shop.petrinet",
        )
    )


def _tok(color: str, **data: object) -> Token:
    return Token(color, dict(data))


_HEADER = 'play s\nnet "shop.petrinet"\n'


# ── The conformance cases, round-tripped ────────────────────────────────


@pytest.mark.skipif(not (_CASES / "01-symbolic-firing").is_dir(), reason="no spec tree")
def test_symbolic_firing_records_roundtrip() -> None:
    # given: a checked play whose firings state `->` outputs, carry, `nothing`
    # when: its records are turned back into plays and checked
    replayed = _roundtrip(_CASES / "01-symbolic-firing")
    # then: every trace replays, records included
    assert replayed


@pytest.mark.skipif(not (_CASES / "02-timers-and-paths").is_dir(), reason="no spec tree")
def test_clock_moves_and_matured_firings_roundtrip() -> None:
    # given: a checked play whose advances mature timer transitions, whose
    #   firing records carry `maturedBy`
    # when: its records are turned back into plays and checked
    replayed = _roundtrip(_CASES / "02-timers-and-paths")
    (deadline,) = [records for name, records in replayed if name == "deadline"]
    # then: the clock moves came back as `update` steps, not `advance`, and
    #   the matured firing as its own `fire` step — the record order holds
    assert len(deadline) >= 5
    assert [r.get("kind") for r in deadline].count("update") >= 2


@pytest.mark.skipif(not (_CASES / "03-composition").is_dir(), reason="no spec tree")
def test_composition_records_roundtrip() -> None:
    # given: a checked play against a composition (merged names, fused ports)
    # when: its records are turned back into plays and checked
    assert _roundtrip(_CASES / "03-composition")


@pytest.mark.skipif(not (_CASES / "05-literal-start").is_dir(), reason="no spec tree")
def test_literal_start_records_replay() -> None:
    # given: the checker's records of a literal start (`marking none` plus
    #   leading injects), the preamble's injections included
    # when: the records become a play — the preamble's injects are part of
    #   the records, so the new play's preamble must stay empty and every
    #   arrival becomes a step
    case_dir = _CASES / "05-literal-start"
    play = read_play(case_dir / "case.play")
    report = check_play(play)
    (trace,) = report.traces
    records = _records(trace)
    text = records_to_play(
        trace.subject.net,
        trace.initial,
        records,
        net_line=f'net "{play.net}"',
        name="literal_replay",
    )
    # then: the kept record is the marking's, and the injected arrivals are
    #   leading `inject` steps (the empty kept start and the records' start
    #   agree); the whole record stream replays in order
    body = text.split("marking initial", 1)[1]
    odd = [
        line
        for line in body.splitlines()
        if line
        and not line.startswith(("inject ", "fire ", "update ", "//", "net ", "play ", "instance "))
    ]
    assert not odd, f"unexpected preamble statement: {odd}"
    replay = check_play(parse_play(text, origin=case_dir))
    (replay_trace,) = replay.traces
    assert replay_trace.failure is None
    replay_records = _records(replay_trace)
    assert _plain(replay_records[-len(records) :]) == _plain(records)


# ── A play with a matured firing, written and replayed ──────────────────


def test_matured_firing_replays_as_explicit_fire() -> None:
    # given: the shop play, whose second advance matures [expire], its
    #   firing record carrying `maturedBy`
    play = parse_play(
        _HEADER + "fire [accept]\nadvance 60\nadvance +1m\n",
        origin=_FIXTURES,
    )
    report = check_play(play)
    (trace,) = report.traces
    records = _records(trace)
    assert any(r.get("metadata", {}).get("maturedBy") for r in records)

    # when: the records become a play
    text = records_to_play(
        trace.subject.net,
        trace.initial,
        records,
        net_line='net "shop.petrinet"',
        name="shop_replay",
    )

    # then: the clock move is an `update` and the matured [expire] an
    #   explicit `fire` — not an `advance`, whose maturation would fire it
    #   first and fail the following `fire [expire]` with SC301 (ADR 0060)
    lines = text.splitlines()
    statements = [line for line in lines if line.startswith(("inject ", "update ", "fire "))]
    assert len(statements) == 4
    assert statements[0].startswith("fire [accept]")
    assert statements[1].startswith("update (clock) <- tick ")
    assert statements[2].startswith("update (clock) <- tick ")
    assert statements[3].startswith("fire [expire]")

    # and: the replay checks and replays the same records
    replay = check_play(parse_play(text, origin=_FIXTURES))
    (replay_trace,) = replay.traces
    assert replay_trace.failure is None
    assert _plain(_records(replay_trace)[-len(records) :]) == _plain(records)


# ── The failed attempt, and the multi-token firing ──────────────────────


def test_a_failed_firing_is_a_comment_not_a_step(tmp_path: Path) -> None:
    # given: a play whose maturing `advance` writes a failed firing record —
    #   [bad]'s net `data cel` names a missing binding field, so its settle
    #   fails (the deposit violation's record-then-drop shape) — beside
    #   [ok]'s completed firing
    (tmp_path / "shop.petrinet").write_text(
        'net mat "a failing maturing firing does not stop the pass"\n'
        "(clock) -tick->? [ok]\n"
        "(clock) -tick->? [bad]\n"
        "(go) -work-> [ok]\n"
        "(go) -work-> [bad]\n"
        "@gx: [bad] -broken-> (broke)\n"
        "@gok: [ok] -done-> (done)\n"
        '[ok] timer clock (clock) cel "clock.now >= 10"\n'
        '[bad] timer clock (clock) cel "clock.now >= 10"\n'
        "[bad] priority 1\n"
        '@gok data {"k": "ok"}\n'
        "@gx data cel \"{'n': binding.missing}\"\n"
        "marking start (go) <- $w1\n"
        "marking start (go) <- $w2\n"
        "marking start (clock) <- $c\n"
        "$w1: work {}\n"
        "$w2: work {}\n"
        '$c: tick {"now": 0}\n',
        encoding="utf-8",
    )
    play = parse_play(
        'play s\nnet "shop.petrinet"\nmarking start\nadvance +50\n',
        origin=tmp_path,
    )
    report = check_play(play)
    (trace,) = report.traces
    records = _records(trace)
    assert any(r.get("status") == "failed" for r in records)

    # when: the records become a play
    text = records_to_play(
        trace.subject.net,
        trace.initial,
        records,
        net_line='net "shop.petrinet"',
        name="with_failure",
    )

    # then: the failed attempt is a comment — not an occurrence — and the
    #   completed firings replay, the occurrence sequence's tail
    assert any(
        line.startswith("// skipped: a failed attempt of [bad]")
        for line in text.splitlines()
    )
    replay = check_play(parse_play(text, origin=tmp_path))
    (replay_trace,) = replay.traces
    assert replay_trace.failure is None
    completed = [
        r
        for r in records
        if "injectionId" in r or r.get("status") == "completed"
    ]
    assert _plain(_records(replay_trace)[-len(completed) :]) == _plain(completed)


def test_a_multi_token_firing_replays_with_a_token_list() -> None:
    # given: the checker's records of a play whose firing produces two
    #   tokens into one place — a handler's two deliveries for one run
    body = (
        "$t1: purchase {\"id\": \"o-1\", \"sku\": \"a\", \"dueAt\": 100}\n"
        "$t2: purchase {\"id\": \"o-2\", \"sku\": \"b\", \"dueAt\": 100}\n"
        "inject (inbox) <- $t1, $t2\n"
        "fire [accept] -> (accepted) $t1, $t2\n"
    )
    play = parse_play(_HEADER + body, origin=_FIXTURES)
    report = check_play(play)
    (trace,) = report.traces
    assert trace.failure is None
    records = _records(trace)

    # when: the records become a play
    text = records_to_play(
        trace.subject.net, trace.initial, records,
        net_line='net "shop.petrinet"', name="multi_token",
    )

    # then: one `fire` states both tokens in its `->` clause (a handler's
    #   two deliveries for one run), and the records replay
    fire_line = next(line for line in text.splitlines() if line.startswith("fire [accept]"))
    assert fire_line.count("purchase {") == 2
    assert "with (inbox)" in fire_line
    replay = check_play(parse_play(text, origin=_FIXTURES))
    (replay_trace,) = replay.traces
    assert replay_trace.failure is None
    assert _plain(_records(replay_trace)[-len(records) :]) == _plain(records)


# ── Rejections ──────────────────────────────────────────────────────────


def test_records_of_another_net_are_refused() -> None:
    # given: one firing record naming a foreign net
    firing: dict[str, Any] = {
        "firingId": "t/f/0",
        "netId": "other",
        "transition": "accept",
        "attempt": 0,
        "status": "completed",
        "inputTokens": {"inbox": []},
        "outputTokens": {},
        "error": None,
        "metadata": {},
        "timestamps": {},
    }

    # when / then: the refusal names the net
    with pytest.raises(RecordsToPlayError, match="was recorded against net"):
        records_to_play(
            _shop_net(), Marking(), [firing], net_line='net "shop.petrinet"'
        )


def test_no_effect_records_are_refused() -> None:
    # given: records with no firing and no injection (a trace record only)
    # when / then: the refusal says so
    with pytest.raises(RecordsToPlayError, match="no firing or injection"):
        records_to_play(
            _shop_net(),
            Marking(),
            [{"event": "guard_checked", "firingId": "f", "handler": "g"}],
            net_line='net "shop.petrinet"',
        )


def test_a_firing_not_enabled_is_refused() -> None:
    # given: one firing of a transition the empty marking does not enable
    firing: dict[str, Any] = {
        "firingId": "shop/f/0",
        "netId": "shop",
        "transition": "accept",
        "attempt": 0,
        "status": "completed",
        "inputTokens": {"inbox": [{"type": "purchase", "data": {"id": "o-1"}}]},
        "outputTokens": {"accepted": [{"type": "purchase", "data": {"id": "o-1"}}]},
        "error": None,
        "metadata": {},
        "timestamps": {},
    }

    # when / then: the replay's first reserve returns None — the play would
    #   fail with SC301, so the writer refuses
    with pytest.raises(RecordsToPlayError, match="SC301"):
        records_to_play(
            _shop_net(), Marking(), [firing], net_line='net "shop.petrinet"'
        )


def test_a_durable_row_without_its_injection_kind_is_classified() -> None:
    # given: the checker's own records rewritten as decoded durable-journal
    #   rows — the channel name holds `kind` (`injection`), so the record's
    #   `inject`/`update` kind is read from its `replaced` payload
    play = parse_play(_HEADER + "fire [accept]\nadvance 60\n", origin=_FIXTURES)
    (trace,) = check_play(play).traces
    rows: list[dict[str, Any]] = []
    for step in trace.steps:
        for record in step.records:
            if "injectionId" in record:
                rows.append({**record, "kind": "injection"})
            else:
                rows.append(dict(record))

    # when: the rows become a play
    text = records_to_play(
        trace.subject.net,
        trace.initial,
        rows,
        net_line='net "shop.petrinet"',
        name="durable_rows",
    )

    # then: the clock row's kind was read from `replaced` — empty, so it
    #   replayed as an `inject` into the empty clock place, and the play
    #   checks (the same record a play's own `advance 60` on an empty
    #   clock place writes)
    assert "inject (clock) <- tick {\"now\": 60}" in text


# ── The renamed helpers, exported for the writer ────────────────────────


def test_the_writer_imports_the_checkers_own_helpers() -> None:
    # then: `net_fills` / `produce_templates` are the check module's own
    #   (one source of truth for SC211's judgement)
    import velocitron_play_check
    from velocitron_engine import net_fills, produce_templates

    assert velocitron_play_check.produce_templates is produce_templates
    assert velocitron_play_check.net_fills is net_fills
    (trace,) = check_play(
        parse_play(_HEADER + "fire [accept]\n", origin=_FIXTURES)
    ).traces
    templates = produce_templates(trace.subject.net, "accept")
    assert [t.destination for t in templates] == ["accepted"]
    assert all(not net_fills(t) for t in templates)