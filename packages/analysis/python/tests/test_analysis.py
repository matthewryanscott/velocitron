"""Prove, lint, and kept records run without the umbrella."""

from __future__ import annotations

from pathlib import Path

from velocitron_analysis import (
    FACTS,
    ProofReport,
    kept_records,
    lint_net,
    load,
    prove,
    read_settings,
)
from velocitron_petrinet import compile_petrinet_text, parse_net

_WORKFLOW = """
net sound_workflow "Two branches run side by side and join"

(i) -> [split] -> (p1)
[split] -> (p2)
(p1) -> [left] -> (p3)
(p2) -> [right] -> (p4)
(p3) -> [join] -> (o)
(p4) -> [join]

marking initial (i) <- 1
"""

_SINK = {
    "name": "sink",
    "places": [{"name": "flag", "accepts": ["flag"]}],
    "transitions": [{"name": "clear_flag", "handler": "clear_flag"}],
    "arcs": [
        {
            "from": {"place": "flag"},
            "to": {"transition": "clear_flag"},
            "consume": {"type": "flag"},
        }
    ],
}


def test_a_workflow_net_proves_without_the_umbrella() -> None:
    # given: a workflow net compiled by the petrinet package
    net = parse_net(compile_petrinet_text(_WORKFLOW, "sound.petrinet"))
    # when: every fact runs
    report = prove(net, facts=FACTS)
    # then: the net is sound and names its own places
    assert isinstance(report, ProofReport)
    assert report.status == "proved"
    assert report.net == "sound_workflow"
    assert kept_records(net) == {}


def test_load_reads_a_petrinet_file(tmp_path: Path) -> None:
    # given: the workflow written to a file
    path = tmp_path / "sound.petrinet"
    path.write_text(_WORKFLOW, encoding="utf-8")
    # when: load reads it
    net, composition = load(path)
    # then: a single net comes back, not a composition
    assert composition is None
    assert net.name == "sound_workflow"


def test_lint_flags_a_consume_without_produce() -> None:
    # given: a sink the parser accepts
    net = parse_net(_SINK)
    # when: lint runs
    findings = lint_net(net)
    # then: the sink is advisory, not a parse error
    assert [finding.rule for finding in findings] == ["consume-without-produce"]


def test_read_settings_reads_a_domains_file(tmp_path: Path) -> None:
    # given: a JSON5 domains file
    path = tmp_path / "domains.json5"
    path.write_text(
        '{domains: {"job.id": ["a"]}, environment: {starts: 2}}',
        encoding="utf-8",
    )
    # when: the settings are read
    settings = read_settings(path)
    # then: the override and the start count are kept
    assert list(settings.domains["job.id"]) == ["a"]
    assert settings.starts == 2
