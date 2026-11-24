"""Opt-in lint surface: static checks over a parsed net.

The lint surface is deliberately separate from parsing/validation: a sink
transition (consume without produce) is a legitimate Petri-net construct, so
it must NOT be a :class:`NetValidationError`. ``lint_net`` returns findings a
consumer may act on or ignore, and an ``annotations`` acknowledgement
(ADR 0011 documentation-fields carve-out) suppresses an intentional sink.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from velocitron_cli import main
from velocitron_analysis import (
    RULE_CONSUME_WITHOUT_PRODUCE,
    RULE_CORRELATE_FREE_NAME,
    RULE_PREDICATE_NAMES_COLOR_OR_PLACE,
    RULE_READ_ONLY_PRODUCER,
    LintFinding,
    lint_net,
)
from velocitron_petrinet import parse_petrinet_text
from velocitron_petrinet import parse_net

# ── Fixture nets ─────────────────────────────────────────────────────────
#
# Each net is minimal for the surface under test: every arc is either the
# consume/produce/read/inhibit shape the rule resolves or the structural
# minimum to make the net parse.


def _sink_net(annotations: dict[str, Any] | None = None) -> dict[str, Any]:
    """A sink net — one consume arc, zero produce arcs (the flagged shape) —
    with optional annotations on its ``clear_flag`` transition."""
    transition: dict[str, Any] = {"name": "clear_flag", "handler": "clear_flag"}
    if annotations is not None:
        transition["annotations"] = annotations
    return {
        "name": "sink",
        "places": [{"name": "flag", "accepts": ["flag"]}],
        "transitions": [transition],
        "arcs": [
            {
                "from": {"place": "flag"},
                "to": {"transition": "clear_flag"},
                "consume": {"type": "flag"},
            },
        ],
    }


SINK_NET: dict[str, Any] = _sink_net()

# A transition that consumes AND produces — the clean shape.
PRODUCER_NET: dict[str, Any] = {
    "name": "producer",
    "places": [
        {"name": "inbox", "accepts": ["job"]},
        {"name": "outbox", "accepts": ["job"]},
    ],
    "transitions": [{"name": "advance", "handler": "advance"}],
    "arcs": [
        {
            "from": {"place": "inbox"},
            "to": {"transition": "advance"},
            "consume": {"type": "job"},
        },
        {
            "from": {"transition": "advance"},
            "to": {"place": "outbox"},
            "produce": {"type": "job", "destination": "outbox"},
        },
    ],
}

# The motivating bug shape: an `advance_*` transition with consume+read inputs
# and zero produce arcs (a dropped produce arc), which parses clean but can
# never advance the net.
CONSUME_PLUS_READ_NET: dict[str, Any] = {
    "name": "advance-bug",
    "places": [
        {"name": "inbox", "accepts": ["job"]},
        {"name": "clock", "accepts": ["tick"]},
    ],
    "transitions": [{"name": "advance_stage", "handler": "advance_stage"}],
    "arcs": [
        {
            "from": {"place": "inbox"},
            "to": {"transition": "advance_stage"},
            "consume": {"type": "job"},
        },
        {
            "from": {"place": "clock"},
            "to": {"transition": "advance_stage"},
            "consume": {"type": "tick", "mode": "read"},
        },
    ],
}

# A transition whose only inputs are read + inhibit arcs (removes nothing) and
# no produce arc — a pure gate/observer, NOT a consumption sink.
READ_INHIBIT_ONLY_NET: dict[str, Any] = {
    "name": "observer",
    "places": [
        {"name": "config", "accepts": ["config"]},
        {"name": "lock", "accepts": ["lock"]},
    ],
    "transitions": [{"name": "observe", "handler": "observe"}],
    "arcs": [
        {
            "from": {"place": "config"},
            "to": {"transition": "observe"},
            "consume": {"type": "config", "mode": "read"},
        },
        {
            "from": {"place": "lock"},
            "to": {"transition": "observe"},
            "consume": {"type": "lock", "mode": "inhibit"},
        },
    ],
}

# Two sink transitions to pin finding order (declaration order).
TWO_SINKS_NET: dict[str, Any] = {
    "name": "two-sinks",
    "places": [
        {"name": "a", "accepts": ["t"]},
        {"name": "b", "accepts": ["t"]},
    ],
    "transitions": [
        {"name": "drop_a", "handler": "drop_a"},
        {"name": "drop_b", "handler": "drop_b"},
    ],
    "arcs": [
        {
            "from": {"place": "a"},
            "to": {"transition": "drop_a"},
            "consume": {"type": "t"},
        },
        {
            "from": {"place": "b"},
            "to": {"transition": "drop_b"},
            "consume": {"type": "t"},
        },
    ],
}


# ── The rule: consume without produce ────────────────────────────────────


class TestConsumeWithoutProduce:
    def test_sink_net_parses_without_error(self):
        # given: a sink net with NO suppression annotation
        # when: parsing it
        net = parse_net(SINK_NET)

        # then: parsing succeeds — a sink is a legitimate construct, and the
        # lint is opt-in, never a NetValidationError
        assert net.transitions[0].name == "clear_flag"

    def test_sink_transition_produces_a_finding(self):
        # given: a net with a transition that consumes but never produces
        net = parse_net(SINK_NET)

        # when: linting the net
        findings = lint_net(net)

        # then: exactly one finding is returned, naming the sink transition
        assert len(findings) == 1
        # and: the finding is a LintFinding carrying the stable rule id and
        # the transition name
        assert isinstance(findings[0], LintFinding)
        assert findings[0].rule == RULE_CONSUME_WITHOUT_PRODUCE
        assert findings[0].transition == "clear_flag"
        # and: the message names the likely cause
        assert "consumes but never produces" in findings[0].message
        assert "missing produce arc" in findings[0].message

    def test_transition_with_produce_arc_is_clean(self):
        # given: a transition that both consumes and produces
        net = parse_net(PRODUCER_NET)

        # when: linting
        findings = lint_net(net)

        # then: no finding — a produce arc is present
        assert findings == []

    def test_consume_plus_read_without_produce_is_flagged(self):
        # given: the motivating bug — consume+read inputs, zero produce arcs
        net = parse_net(CONSUME_PLUS_READ_NET)

        # when: linting
        findings = lint_net(net)

        # then: the consume-mode arc makes it a sink; the read arc is not an
        # output and does not exempt it
        assert len(findings) == 1
        assert findings[0].transition == "advance_stage"
        assert findings[0].rule == RULE_CONSUME_WITHOUT_PRODUCE

    def test_read_and_inhibit_only_transition_is_not_flagged(self):
        # given: a transition whose only inputs are read + inhibit arcs
        net = parse_net(READ_INHIBIT_ONLY_NET)

        # when: linting
        findings = lint_net(net)

        # then: no finding — read/inhibit remove nothing, so the transition is
        # not a consumption sink (a pure gate/observer, out of this rule's scope)
        assert findings == []

    def test_findings_follow_transition_declaration_order(self):
        # given: two sink transitions declared drop_a then drop_b
        net = parse_net(TWO_SINKS_NET)

        # when: linting
        findings = lint_net(net)

        # then: both are flagged, in declaration order
        assert [f.transition for f in findings] == ["drop_a", "drop_b"]


# ── Suppression via annotation (ADR 0011 carve-out) ──────────────────────


class TestSinkSuppression:
    def test_acknowledged_sink_is_suppressed(self):
        # given: a sink transition whose annotation acknowledges the rule
        net = parse_net(
            _sink_net({"lint": {"suppress": [RULE_CONSUME_WITHOUT_PRODUCE]}})
        )

        # when: linting
        findings = lint_net(net)

        # then: the intentional sink is silenced
        assert findings == []

    def test_suppression_of_another_rule_does_not_silence_this_one(self):
        # given: a suppress list naming a different (unrelated) rule id
        net = parse_net(_sink_net({"lint": {"suppress": ["some-other-rule"]}}))

        # when: linting
        findings = lint_net(net)

        # then: this rule still fires — suppression is rule-specific
        assert len(findings) == 1
        assert findings[0].rule == RULE_CONSUME_WITHOUT_PRODUCE

    def test_unrelated_annotations_do_not_suppress(self):
        # given: a sink transition with annotations that carry no lint block
        net = parse_net(_sink_net({"owner": "team-x", "note": "wip"}))

        # when: linting
        findings = lint_net(net)

        # then: the finding still fires — only a lint.suppress entry silences it
        assert len(findings) == 1

    def test_a_sink_marked_as_an_end_is_silenced(self):
        # given: a sink transition marked as an intended end
        net = parse_net(_sink_net({"end": True}))

        # when/then: nothing is flagged
        assert lint_net(net) == []

    def test_an_end_marker_other_than_true_does_not_silence(self):
        # given: end markers that are not the JSON boolean true
        nets = [parse_net(_sink_net({"end": value})) for value in ("true", 1, False)]

        # when/then: each sink is still flagged
        assert [len(lint_net(net)) for net in nets] == [1, 1, 1]


def test_validate_cli_warns_about_a_sink_until_it_is_marked_as_an_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a .petrinet with a sink, and the same net with the sink marked
    source = tmp_path / "drop.petrinet"
    text = "net drop\n\n(trash) -job-> [drop]\n"
    source.write_text(text, encoding="utf-8")
    main(["validate", str(source)])
    warned = capsys.readouterr().err

    # when: the sink is marked as an intended end
    source.write_text(text + "[drop] annotation end true\n", encoding="utf-8")
    result = main(["validate", str(source)])
    captured = capsys.readouterr()

    # then: the warning named the marker, and the marked net is silent
    assert warned.startswith(f"{source}:3:17: warning[{RULE_CONSUME_WITHOUT_PRODUCE}]")
    assert "[drop] annotation end true" in warned
    assert result == 0
    assert captured.err == ""


# ── Rule: predicate-names-color-or-place ─────────────────────────────────


def _gate_net(
    predicate: str,
    *,
    transition_annotations: dict[str, Any] | None = None,
    arc_annotations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A loan consumed under a read switch, the loan arc carrying
    ``predicate``; the transition produces, so only the predicate rule can fire."""
    transition: dict[str, Any] = {"name": "send", "handler": "send"}
    if transition_annotations is not None:
        transition["annotations"] = transition_annotations
    loan_arc: dict[str, Any] = {
        "from": {"place": "pending"},
        "to": {"transition": "send"},
        "consume": {"type": "loan", "predicate": {"cel": predicate}},
    }
    if arc_annotations is not None:
        loan_arc["annotations"] = arc_annotations
    return {
        "name": "gate",
        "places": [
            {"name": "pending", "accepts": ["loan"]},
            {"name": "branch_home", "accepts": ["switch"]},
            {"name": "sent", "accepts": ["loan"]},
        ],
        "transitions": [transition],
        "arcs": [
            loan_arc,
            {
                "from": {"place": "branch_home"},
                "to": {"transition": "send"},
                "consume": {"type": "switch", "mode": "read"},
            },
            {
                "from": {"transition": "send"},
                "to": {"place": "sent"},
                "produce": {"type": "loan", "destination": "sent"},
            },
        ],
    }


class TestPredicateNamesColorOrPlace:
    def test_another_arcs_color_is_flagged_with_a_correlate_hint(self):
        # given: a loan predicate that reads the switch token's field
        net = parse_net(_gate_net("switch.owner == 'main'"))

        # when: linting
        findings = lint_net(net)

        # then: one finding names the switch and points at the bound place
        assert [f.rule for f in findings] == [RULE_PREDICATE_NAMES_COLOR_OR_PLACE]
        assert findings[0].transition == "send"
        message = findings[0].message
        assert "'switch.owner'" in message
        assert "only its own 'loan' token's fields as bare names" in message
        assert "correlate cel" in message
        assert "binding.branch_home[0].owner" in message

    def test_the_arcs_own_color_is_flagged_with_the_bare_field(self):
        # given: a loan predicate that prefixes its own color
        net = parse_net(_gate_net("loan.ready == true"))

        # when: linting
        findings = lint_net(net)

        # then: the finding suggests the bare field
        assert len(findings) == 1
        assert "write 'ready'" in findings[0].message

    def test_a_place_name_is_flagged(self):
        # given: a predicate that indexes a place name
        net = parse_net(_gate_net("branch_home[0] == 1"))

        # when: linting
        findings = lint_net(net)

        # then: the place is named as a place
        assert len(findings) == 1
        assert "'branch_home' is a place" in findings[0].message

    def test_bare_fields_strings_and_macro_variables_are_clean(self):
        # given: bare fields, a color name inside a string, a field that shares
        # a color's name used bare, and a macro variable named like a color
        net = parse_net(
            _gate_net(
                "ready && note != 'switch.owner' && switch == 'on' "
                "&& items.exists(switch, switch.on)"
            )
        )

        # when/then: nothing is flagged
        assert lint_net(net) == []

    def test_correlate_is_not_linted(self):
        # given: the cross-token test written as a correlate, not a predicate
        document = _gate_net("ready")
        document["arcs"][1]["consume"]["correlate"] = {"cel": "token.owner == 'main'"}
        net = parse_net(document)

        # when/then: nothing is flagged
        assert lint_net(net) == []

    def test_transition_suppression_silences_the_rule(self):
        # given: the transition acknowledges the rule
        net = parse_net(
            _gate_net(
                "switch.owner == 'main'",
                transition_annotations={
                    "lint": {"suppress": [RULE_PREDICATE_NAMES_COLOR_OR_PLACE]}
                },
            )
        )

        # when/then: nothing is flagged
        assert lint_net(net) == []

    def test_arc_suppression_silences_the_rule(self):
        # given: the flagged arc acknowledges the rule
        net = parse_net(
            _gate_net(
                "switch.owner == 'main'",
                arc_annotations={
                    "lint": {"suppress": [RULE_PREDICATE_NAMES_COLOR_OR_PLACE]}
                },
            )
        )

        # when/then: nothing is flagged
        assert lint_net(net) == []


def _correlate_net(correlate: str, **annotations: Any) -> dict[str, Any]:
    """The gate net with ``correlate`` on its loan arc and a clean predicate."""
    document = _gate_net("ready", **annotations)
    document["arcs"][0]["consume"]["correlate"] = {"cel": correlate}
    return document


class TestCorrelateFreeName:
    def test_an_unknown_name_is_flagged(self):
        # given: a correlate that reads a name nothing binds
        net = parse_net(_correlate_net("hold.branch == token.branch"))

        # when: linting
        findings = lint_net(net)

        # then: one finding names it and says what a correlate sees
        assert [f.rule for f in findings] == [RULE_CORRELATE_FREE_NAME]
        assert findings[0].arc == 0
        assert findings[0].inscription == "correlate"
        message = findings[0].message
        assert "uses 'hold.branch'" in message
        assert "sees only 'token' (this arc's token) and 'binding'" in message
        assert "'binding.<place>[0]'" in message

    def test_another_arcs_color_gets_its_binding_path(self):
        # given: a correlate that names the read switch's color
        net = parse_net(_correlate_net("switch.owner == token.owner"))

        # when: linting
        (finding,) = lint_net(net)

        # then: the fix reads the switch through binding
        assert "write 'binding.branch_home[0].owner'" in finding.message

    def test_the_arcs_own_color_and_a_bare_field_get_token(self):
        # given: a correlate that prefixes its own color, then uses a bare field
        net = parse_net(
            _correlate_net("loan.owner == binding.branch_home[0].owner && ready")
        )

        # when: linting
        findings = lint_net(net)

        # then: both point at token
        assert ["'token.owner'" in f.message for f in findings] == [True, False]
        assert "write 'token.ready'" in findings[1].message

    def test_token_binding_macro_variables_and_type_names_are_clean(self):
        # given: a correlate using only what a correlate may name
        net = parse_net(
            _correlate_net(
                "size(binding.branch_home) > 0 "
                "&& binding.branch_home.all(s, s.owner == token.owner) "
                "&& type(token.owner) == string"
            )
        )

        # when/then: nothing is flagged
        assert lint_net(net) == []

    def test_arc_suppression_silences_the_rule(self):
        # given: the flagged arc acknowledges the rule
        net = parse_net(
            _correlate_net(
                "hold.branch == token.branch",
                arc_annotations={"lint": {"suppress": [RULE_CORRELATE_FREE_NAME]}},
            )
        )

        # when/then: nothing is flagged
        assert lint_net(net) == []


def _scored_gate_net(
    predicate: str, score: Any, correlate: str | None = None
) -> dict[str, Any]:
    """The gate net with one pending loan whose ``score`` is ``score``."""
    document = _gate_net(predicate)
    if correlate is not None:
        document["arcs"][0]["consume"]["correlate"] = {"cel": correlate}
    document["initialMarking"] = {
        "pending": [{"type": "loan", "data": {"score": score}}]
    }
    return document


def test_an_int_field_compared_with_a_double_is_not_flagged():
    # given: a predicate comparing an int-valued field with a double. Ordering
    # across int and double is defined, so the comparison is not a lint.
    net = parse_net(_scored_gate_net("score > 0.01", 0))

    # when/then:
    assert lint_net(net) == []


# ── Rule: read-only-producer ─────────────────────────────────────────────

COMPARE_NET = (
    "net compare\n\n"
    "(new_file) -file->? [compare_files] -check-> (checks)\n"
    "(old_file) -file->? [compare_files]\n"
)


class TestReadOnlyProducer:
    def test_a_step_that_reads_and_produces_is_flagged(self):
        # given: a step whose inputs are all read arcs, with a produce arc
        net = parse_petrinet_text(COMPARE_NET)

        # when: linting
        findings = lint_net(net)

        # then: it is flagged, naming the step and where its tokens pile up
        assert findings == [
            LintFinding(
                rule=RULE_READ_ONLY_PRODUCER,
                transition="compare_files",
                message=(
                    "[compare_files] reads but consumes nothing, so it can fire "
                    "again and again, adding a token to (checks) each time; "
                    "consume a token, or inhibit it on its own output so it "
                    "fires once"
                ),
            )
        ]

    def test_an_inhibit_on_its_own_output_makes_it_fire_once(self):
        # given: the same step, inhibited by the place it writes
        net = parse_petrinet_text(COMPARE_NET + "(checks) -check->0 [compare_files]\n")

        # when/then: nothing is flagged
        assert lint_net(net) == []

    def test_an_inhibit_on_another_color_does_not_stop_it(self):
        # given: an inhibit from its output place, for a color it never writes
        net = parse_petrinet_text(COMPARE_NET + "(checks) -veto->0 [compare_files]\n")

        # when/then: the step is still flagged
        assert [f.rule for f in lint_net(net)] == [RULE_READ_ONLY_PRODUCER]

    def test_a_timer_does_not_stop_it(self):
        # given: the step waits for a clock it only reads
        net = parse_petrinet_text(
            COMPARE_NET
            + "(clock) -tick->? [compare_files]\n"
            + '[compare_files] timer clock (clock) cel "clock.now >= 10"\n'
        )

        # when/then: a matured timer stays matured, so it is still flagged
        assert [f.rule for f in lint_net(net)] == [RULE_READ_ONLY_PRODUCER]

    def test_a_consuming_input_or_no_input_is_clean(self):
        # given: a step that consumes one of its inputs, and a source transition
        nets = [
            parse_petrinet_text(
                COMPARE_NET.replace("(old_file) -file->?", "(old_file) -file->")
            ),
            parse_petrinet_text("net source\n\n[restock] -stock-> (inventory)\n"),
        ]

        # when/then: neither is flagged
        assert [lint_net(net) for net in nets] == [[], []]

    def test_a_suppression_silences_it(self):
        # given: the step acknowledges the rule
        net = parse_petrinet_text(
            COMPARE_NET
            + f'[compare_files] annotation lint {{"suppress": ["{RULE_READ_ONLY_PRODUCER}"]}}\n'
        )

        # when/then: nothing is flagged
        assert lint_net(net) == []


def test_validate_cli_warns_about_a_read_only_producer_in_a_composition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a composition whose checker net reads the delivered file
    (tmp_path / "loan.petrinet").write_text(
        "net loan\n\n"
        "(batch) -file-> [deliver] -file-> (delivered)\n"
        "(delivered) port output file\n",
        encoding="utf-8",
    )
    checker = tmp_path / "checker.petrinet"
    checker.write_text(
        "net checker\n\n"
        "(delivered) -file->? [compare_files] -check-> (checks)\n"
        "(delivered) port input file\n",
        encoding="utf-8",
    )
    composition = tmp_path / "rehearsal.petrinet"
    composition.write_text(
        "composition rehearsal\n\n"
        'use "loan.petrinet" as loan\n'
        'use "checker.petrinet" as checker\n'
        "wire loan.(delivered) -> checker.(delivered)\n",
        encoding="utf-8",
    )

    # when: validating the composition through the CLI
    result = main(["validate", str(composition)])
    captured = capsys.readouterr()

    # then: the warning points into the checker's file
    assert result == 0
    assert [line.split(": ")[:2] for line in captured.err.splitlines()] == [
        [f"{checker}:3:23", f"warning[{RULE_READ_ONLY_PRODUCER}]"],
    ]


def test_validate_cli_prints_findings_as_warnings_and_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a .petrinet whose predicate names another arc's color
    source = tmp_path / "gate.petrinet"
    source.write_text(
        "net gate\n\n"
        "@send_in: (pending) -loan-> [send] -loan-> (sent)\n"
        "(branch_home) -switch->? [send]\n"
        "@send_in predicate cel \"switch.owner == 'main'\"\n",
        encoding="utf-8",
    )

    # when: validating through the CLI
    result = main(["validate", str(source)])
    captured = capsys.readouterr()

    # then: the net is valid and the finding is a warning at the predicate fact
    assert result == 0
    assert captured.out == "net\n"
    (line,) = captured.err.splitlines()
    assert line.startswith(
        f"{source}:5:1: warning[{RULE_PREDICATE_NAMES_COLOR_OR_PLACE}]: "
    )


def test_validate_cli_points_each_finding_at_its_source_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a sink transition, and a flagged predicate on a handled arc that
    # an arc-run order moves ahead of the arcs declared before it
    source = tmp_path / "gate.petrinet"
    source.write_text(
        "net gate\n\n"
        "@drop: (trash) -loan-> [discard]\n"
        "@send_in: (pending) -loan-> [send] -loan-> (sent)\n"
        "@gate: (branch_home) -switch->? [send]\n"
        "@send_in order 1\n"
        "@gate order 2\n"
        "@drop order 3\n"
        "@send_in predicate cel \"switch.owner == 'main'\"\n"
        '@send_in correlate cel "hold.id == token.id"\n',
        encoding="utf-8",
    )

    # when: validating through the CLI
    result = main(["validate", str(source)])
    captured = capsys.readouterr()

    # then: the sink points at its transition name, the predicate and
    # correlate findings at their facts
    assert result == 0
    assert [line.split(" warning")[0] for line in captured.err.splitlines()] == [
        f"{source}:3:25:",
        f"{source}:9:1:",
        f"{source}:10:1:",
    ]


def test_validate_cli_reports_a_json_finding_at_1_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a JSON net, which has no source positions
    source = tmp_path / "sink.json"
    source.write_text(json.dumps(SINK_NET), encoding="utf-8")

    # when: validating through the CLI
    result = main(["validate", str(source)])
    captured = capsys.readouterr()

    # then: the warning falls back to 1:1
    assert result == 0
    (line,) = captured.err.splitlines()
    assert line.startswith(f"{source}:1:1: warning[{RULE_CONSUME_WITHOUT_PRODUCE}]")


def test_validate_cli_lints_each_net_of_a_composition_in_its_own_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a composition that uses a sender with a sink twice, and a
    # receiver whose correlate names a place of the sender
    sender = tmp_path / "sender.petrinet"
    sender.write_text(
        "net sender\n\n"
        "(seed) -job-> [emit] -job-> (job_out)\n"
        "(trash) -job-> [drop]\n"
        "(job_out) port output job\n",
        encoding="utf-8",
    )
    receiver = tmp_path / "receiver.petrinet"
    receiver.write_text(
        "net receiver\n\n"
        "@take: (job_in) -job-> [receive] -job-> (done)\n"
        "(job_in) port input job\n"
        '@take correlate cel "job_out.id == token.id"\n',
        encoding="utf-8",
    )
    composition = tmp_path / "pipeline.petrinet"
    composition.write_text(
        "composition pipeline\n\n"
        'use "sender.petrinet" as first\n'
        'use "sender.petrinet" as second\n'
        'use "receiver.petrinet" as receiver\n'
        "wire first.(job_out) -> receiver.(job_in)\n"
        "wire second.(job_out) -> receiver.(job_in)\n",
        encoding="utf-8",
    )

    # when: validating the composition through the CLI
    result = main(["validate", str(composition)])
    captured = capsys.readouterr()

    # then: each finding points into its net's own file, once
    assert result == 0
    assert captured.out == "composition\n"
    assert [line.split(": ")[:2] for line in captured.err.splitlines()] == [
        [f"{sender}:4:17", f"warning[{RULE_CONSUME_WITHOUT_PRODUCE}]"],
        [f"{receiver}:5:1", f"warning[{RULE_CORRELATE_FREE_NAME}]"],
    ]


def test_validate_cli_silences_a_composition_nets_sink_marked_as_an_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a composition whose sender has a sink
    sender = tmp_path / "sender.petrinet"
    text = (
        "net sender\n\n"
        "(seed) -job-> [emit] -job-> (job_out)\n"
        "(trash) -job-> [drop]\n"
        "(job_out) port output job\n"
    )
    sender.write_text(text, encoding="utf-8")
    (tmp_path / "receiver.petrinet").write_text(
        "net receiver\n\n"
        "(job_in) -job-> [receive] -job-> (done)\n"
        "(job_in) port input job\n",
        encoding="utf-8",
    )
    composition = tmp_path / "pipeline.petrinet"
    composition.write_text(
        "composition pipeline\n\n"
        'use "sender.petrinet" as sender\n'
        'use "receiver.petrinet" as receiver\n'
        "wire sender.(job_out) -> receiver.(job_in)\n",
        encoding="utf-8",
    )
    main(["validate", str(composition)])
    warned = capsys.readouterr().err

    # when: the sender marks the sink as an intended end
    sender.write_text(text + "[drop] annotation end true\n", encoding="utf-8")
    result = main(["validate", str(composition)])
    captured = capsys.readouterr()

    # then: the sink warned in the sender's file, and the marked one is silent
    assert warned.startswith(f"{sender}:4:17: warning[{RULE_CONSUME_WITHOUT_PRODUCE}]")
    assert result == 0
    assert captured.err == ""
