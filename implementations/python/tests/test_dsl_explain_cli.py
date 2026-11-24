"""BDD-style contracts for the ``velocitron explain`` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

import velocitron_cli as cli
from velocitron_petrinet import compile_petrinet_text
from velocitron_explain import explain_net
from velocitron_petrinet import parse_net
from velocitron_engine import Net


_REPOSITORY_ROOT = Path(__file__).parents[3]
_MUSEUM_LOAN_FIXTURE = (
    _REPOSITORY_ROOT
    / "examples"
    / "capability-ladder"
    / "13-museum-loan"
    / "museum-loan.petrinet"
)


def _write_equivalent_museum_documents(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Net]:
    """Write one museum core Net in every supported explanation syntax."""
    petrinet = tmp_path / "museum.PETRINET"
    petrinet.write_text(
        _MUSEUM_LOAN_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    document = compile_petrinet_text(
        petrinet.read_text(encoding="utf-8"), str(petrinet)
    )

    strict_json = tmp_path / "museum.JSON"
    strict_json.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    json5 = tmp_path / "museum.JSON5"
    strict_object = json.dumps(document, ensure_ascii=False, indent=2)
    json5.write_text(
        "// JSON5 accepts this comment and the final member comma.\n"
        + strict_object.removesuffix("\n}")
        + ",\n}\n",
        encoding="utf-8",
    )
    return petrinet, strict_json, json5, parse_net(document)


def test_explain_defaults_match_the_explicit_practitioner_markdown_renderer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Given a museum Net, default selection is explicit practitioner Markdown."""
    # given: the museum Net as an authored DSL document
    petrinet, _, _, net = _write_equivalent_museum_documents(tmp_path)

    # when: the command is invoked with no rendering selectors
    assert cli.main(["explain", str(petrinet)]) == 0
    default = capsys.readouterr()

    # and: the default selectors are supplied explicitly
    assert (
        cli.main(
            [
                "explain",
                str(petrinet),
                "--format",
                "markdown",
                "--level",
                "practitioner",
            ]
        )
        == 0
    )
    explicit = capsys.readouterr()

    # then: stdout is exactly the renderer result from the initial marking,
    # and stderr remains unused
    expected = explain_net(
        net,
        format="markdown",
        level="practitioner",
        marking=net.initial_marking,
        marking_label="the initial marking",
    )
    assert default.err == explicit.err == ""
    assert default.out == explicit.out == expected


@pytest.mark.parametrize(
    ("format", "level"),
    [
        ("markdown", "newcomer"),
        ("text", "practitioner"),
        ("text", "newcomer"),
    ],
)
def test_explain_passes_each_explicit_rendering_selection_to_the_renderer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    format: Literal["markdown", "text"],
    level: Literal["practitioner", "newcomer"],
) -> None:
    """Given a museum Net, explicit format and level select that renderer output."""
    # given: one authored core Net
    petrinet, _, _, net = _write_equivalent_museum_documents(tmp_path)

    # when: both rendering selectors are explicit
    assert (
        cli.main(["explain", str(petrinet), "--format", format, "--level", level]) == 0
    )
    captured = capsys.readouterr()

    # then: the command emits the selected complete renderer document only
    assert captured.err == ""
    assert captured.out == explain_net(
        net,
        format=format,
        level=level,
        marking=net.initial_marking,
        marking_label="the initial marking",
    )


_GATE = """net gate "Send or hold on the verdict"
(pending) -request-> [send] -request-> (sent)
(pending) -request-> [hold] -request-> (held)
@send_verdict: (verdicts) -verdict->? [send]
@hold_verdict: (verdicts) -verdict->? [hold]
@send_verdict predicate cel "result == 'pass'"
@hold_verdict predicate cel "result == 'hold'"
$request: request {"id": "r1"}
$hold: verdict {"result": "hold"}
marking initial (pending) <- $request
marking held (pending) <- $request
marking held (verdicts) <- $hold
"""


def _enablement(output: str) -> list[str]:
    section = output.split("## What can happen from ", 1)[1]
    return section.split("\n\n", 1)[0].splitlines()


def test_explain_says_what_can_happen_from_the_initial_marking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a request is pending and no verdict has arrived
    source = tmp_path / "gate.petrinet"
    source.write_text(_GATE, encoding="utf-8")
    # when:
    assert cli.main(["explain", str(source)]) == 0
    # then: each step waits for the verdict, in plain words
    assert _enablement(capsys.readouterr().out) == [
        "the initial marking",
        "- [send] waits: (verdicts) is empty; it needs a verdict token there.",
        "- [hold] waits: (verdicts) is empty; it needs a verdict token there.",
    ]


def test_explain_takes_a_named_marking_and_names_the_predicate_that_says_no(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the verdict says hold
    source = tmp_path / "gate.petrinet"
    source.write_text(_GATE, encoding="utf-8")
    # when:
    assert cli.main(["explain", str(source), "--marking", "held"]) == 0
    # then: [hold] can happen, and [send] says which value held it back
    assert _enablement(capsys.readouterr().out) == [
        'marking "held"',
        "- [send] waits: (verdicts) holds 1 token, but none that this step accepts:",
        """  - verdict {"result": "hold"}: predicate `result == 'pass'` is false""",
        "- [hold] can happen.",
    ]


def test_explain_takes_an_inline_marking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the verdict says pass
    source = tmp_path / "gate.petrinet"
    source.write_text(_GATE, encoding="utf-8")
    marking = {
        "pending": [{"type": "request", "data": {"id": "r1"}}],
        "verdicts": [{"type": "verdict", "data": {"result": "pass"}}],
    }
    # when:
    code = cli.main(["explain", str(source), "--marking-json", json.dumps(marking)])
    # then:
    assert code == 0
    lines = _enablement(capsys.readouterr().out)
    assert lines[0] == "the given marking"
    assert "- [send] can happen." in lines


@pytest.mark.parametrize(
    ("selector", "message"),
    [
        (["--marking", "nope"], 'unknown named marking "nope"'),
        (
            ["--marking-json", '{"nowhere": [{"type": "request", "data": {}}]}'],
            "unknown place (nowhere)",
        ),
        (
            ["--marking-json", '{"pending": [{"type": "verdict", "data": {}}]}'],
            "(pending) does not accept color verdict",
        ),
    ],
)
def test_explain_rejects_a_marking_the_net_cannot_hold(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selector: list[str],
    message: str,
) -> None:
    # given:
    source = tmp_path / "gate.petrinet"
    source.write_text(_GATE, encoding="utf-8")
    # when:
    assert cli.main(["explain", str(source), *selector]) == 1
    captured = capsys.readouterr()
    # then:
    assert captured.out == ""
    assert "error[PN200]" in captured.err and message in captured.err


def test_explain_normalizes_equivalent_museum_documents_across_all_input_formats(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Given equivalent museum documents, all supported loaders render identical bytes."""
    # given: equivalent strict JSON, comment/trailing-comma JSON5, and DSL documents
    petrinet, strict_json, json5, _ = _write_equivalent_museum_documents(tmp_path)

    # when: each input is explained through the command
    outputs: list[str] = []
    for path in (petrinet, strict_json, json5):
        assert cli.main(["explain", str(path)]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        outputs.append(captured.out)

    # then: loading syntax cannot affect the deterministic explanation bytes
    assert outputs[0] == outputs[1] == outputs[2]


@pytest.mark.parametrize(
    "contents",
    [
        "{ name: 'unterminated' ",
        "{ name: 'non-finite', annotations: { bad: NaN } }",
    ],
)
def test_explain_invalid_json5_emits_a_pn200_error_without_partial_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    contents: str,
) -> None:
    """Given malformed or non-finite JSON5, explanation fails before rendering."""
    # given: JSON5 that cannot become a finite core-Net document
    source = tmp_path / "invalid.JSON5"
    source.write_text(contents, encoding="utf-8")

    # when: the command tries to explain it
    assert cli.main(["explain", str(source)]) == 1
    captured = capsys.readouterr()

    # then: established diagnostics identify the input and stdout stayed empty
    assert captured.out == ""
    assert captured.err.startswith(f"{source}:1:1: error[PN200]: ")
    assert captured.err.endswith("\n")


def test_explain_rejects_composition_documents_without_partial_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Given a composition-shaped JSON document, explain rejects it as non-core input."""
    # given: an otherwise decodable document with the composition shape
    source = tmp_path / "composition.json"
    source.write_text('{"nets": []}\n', encoding="utf-8")

    # when: the command receives composition input
    assert cli.main(["explain", str(source)]) == 1
    captured = capsys.readouterr()

    # then: it reports PN200 and does not render a partial explanation
    assert captured.out == ""
    assert captured.err == (
        f"{source}:1:1: error[PN200]: explain accepts a core Net, not a composition\n"
    )


@pytest.mark.parametrize(
    "selector",
    [
        ["--format", "html"],
        ["--level", "expert"],
    ],
)
def test_explain_invalid_rendering_selector_remains_an_argparse_usage_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    selector: list[str],
) -> None:
    """Given an unsupported selector, argparse keeps ownership of the usage error."""
    # when: a rendering selector falls outside the command's declared choices
    with pytest.raises(SystemExit) as raised:
        cli.main(["explain", str(tmp_path / "museum.petrinet"), *selector])
    captured = capsys.readouterr()

    # then: argparse uses its normal exit status and stderr-only usage diagnostic
    assert raised.value.code == 2
    assert captured.out == ""
    assert captured.err.startswith("usage: velocitron explain")
    assert "error: argument" in captured.err
