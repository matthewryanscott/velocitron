"""``velocitron play check`` and ``velocitron play walk``.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

import velocitron_cli as cli
from velocitron_skill import skill_root

_FIXTURES = Path(__file__).parent / "fixtures" / "play"


def _copy_fixtures(tmp_path: Path) -> Path:
    for name in ("shop.petrinet", "shop.play"):
        shutil.copy(_FIXTURES / name, tmp_path / name)
    return tmp_path / "shop.play"


def test_check_of_passing_paths_prints_one_ok_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    play = _copy_fixtures(tmp_path)

    # when
    code = cli.main(["play", "check", str(play), "--path", "trunk", "--path", "late"])

    # then: one line on stdout says which file passed and how much was played
    assert code == 0
    assert capsys.readouterr() == (f"{play}: OK, 2 paths passed\n", "")


def test_check_reports_a_failure_with_its_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the held path fails
    play = _copy_fixtures(tmp_path)

    # when
    code = cli.main(["play", "check", str(play)])

    # then
    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith(f"{play}:26:1: error[SC301]: [ship] is not enabled\n")
    assert "  inhibit arc (holds) -hold->0 [ship] forbids" in err
    assert "  enabled now: [split], [copy]" in err


def test_check_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # given
    play = _copy_fixtures(tmp_path)

    # when
    code = cli.main(["play", "check", str(play), "--json"])

    # then
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert [(p["name"], p["status"]) for p in payload["paths"]] == [
        ("trunk", "passed"),
        ("late", "passed"),
        ("held", "failed"),
    ]
    assert payload["diagnostics"][0]["code"] == "SC301"


def test_a_syntax_error_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.play").write_text("play s\nlaunch [t]\n")
    assert cli.main(["play", "check", str(tmp_path / "bad.play")]) == 1
    assert "error[SC101]" in capsys.readouterr().err


def test_an_unknown_path_is_misuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    play = _copy_fixtures(tmp_path)
    assert cli.main(["play", "check", str(play), "--path", "nope"]) == 2
    assert "unknown path nope" in capsys.readouterr().err


def test_the_skill_example_checks_and_its_reference_matches_the_spec() -> None:
    # given: the bundled skill, read as the installed package ships it
    skill = skill_root()

    # when / then: the example play passes against the kitchen sink
    assert cli.main(["play", "check", str(skill / "kitchen-sink.play")]) == 0
    # and: the bundled reference is the spec, byte for byte
    spec = Path(__file__).parents[3] / "packages" / "spec" / "play-language.md"
    if spec.is_file():
        assert (skill / "play-language.md").read_bytes() == spec.read_bytes()


def test_walk_writes_the_walkthrough(tmp_path: Path) -> None:
    # given
    play = _copy_fixtures(tmp_path)
    out = tmp_path / "late.md"

    # when
    code = cli.main(["play", "walk", str(play), "--path", "late", "-o", str(out)])

    # then
    assert code == 0
    text = out.read_text()
    assert text.startswith(
        "# One purchase through the shop — The purchase is not shipped in time\n"
    )
    assert "## Step 2 — past the deadline" in text


def test_walk_of_a_failing_path_renders_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    play = _copy_fixtures(tmp_path)

    # when
    code = cli.main(["play", "walk", str(play), "--path", "held", "--format", "json"])

    # then
    assert code == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "failed"
    assert "error[SC301]" in captured.err


def test_walk_and_check_read_stdin_with_an_origin(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given: the play text on stdin; its net beside it in tmp_path
    play = _copy_fixtures(tmp_path)
    text = play.read_text()

    # when
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    walked = cli.main(
        ["play", "walk", "-", "--origin", str(tmp_path), "--format", "json"]
    )
    walk_out = capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    checked = cli.main(["play", "check", "-", "--origin", str(tmp_path)])

    # then: the held path fails, and stdin is named in the diagnostic
    assert walked == 0
    assert json.loads(walk_out)["status"] == "passed"
    assert checked == 1
    assert capsys.readouterr().err.startswith("<stdin>:26:1: error[SC301]")


def test_walk_scope_flag_overrides_the_play(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    play = _copy_fixtures(tmp_path)

    # when
    code = cli.main(
        ["play", "walk", str(play), "--format", "json", "--scope", "neighbors"]
    )

    # then
    assert code == 0
    assert json.loads(capsys.readouterr().out)["scope"] == "neighbors"
