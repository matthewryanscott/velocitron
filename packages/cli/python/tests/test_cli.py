"""The packaged CLI installs the hooks that used to live on the umbrella."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from velocitron_cli import build_parser, configure, main, viz_main

_LEAF = """
net sound "One transition"

(i) -> [go] -> (o)
[go] handler "go@sound"
"""


def _leaf(tmp_path: Path) -> Path:
    path = tmp_path / "sound.petrinet"
    path.write_text(_LEAF, encoding="utf-8")
    return path


def test_validate_prints_net(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a leaf net
    path = _leaf(tmp_path)

    # when: the dispatcher validates it
    code = main(["validate", str(path)])

    # then: it reports a net and does not need the umbrella hooks
    assert code == 0
    assert capsys.readouterr().out == "net\n"


def test_check_counts_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    path = _leaf(tmp_path)

    # when
    code = main(["check", str(path)])

    # then
    assert code == 0
    assert "1 petrinet file(s)" in capsys.readouterr().out


def test_to_json_prints_a_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    path = _leaf(tmp_path)

    # when
    code = main(["to-json", str(path)])

    # then
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert '"sound"' in captured.out


def test_to_petrinet_uses_the_dsl_emitter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: main fills the emission hook from velocitron_dsl
    path = _leaf(tmp_path)

    # when
    code = main(["to-petrinet", str(path)])

    # then
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert 'net sound "One transition"' in captured.out


def test_explain_uses_the_explain_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: main fills the explain hook from velocitron_explain
    path = _leaf(tmp_path)

    # when
    code = main(["explain", str(path)])

    # then
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "sound" in captured.out


def test_explain_uses_the_injected_renderer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given
    path = _leaf(tmp_path)

    def explain_net(net: object, **_kwargs: object) -> str:
        return f"saw {getattr(net, 'name', '')}\n"

    configure(explain_net=explain_net)
    try:
        # when
        code = main(["explain", str(path)])
    finally:
        configure(explain_net=None)

    # then
    assert code == 0
    assert capsys.readouterr().out == "saw sound\n"


def test_skill_installs_from_the_skill_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # when: the dispatcher copies the packaged skill
    code = main(["skill", str(tmp_path)])

    # then: the authoring tree lands without an umbrella hook
    assert code == 0
    assert "installed velocitron skill" in capsys.readouterr().out
    assert (tmp_path / "velocitron" / "SKILL.md").is_file()


def test_skill_override_that_is_missing_is_a_pn200(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a host override that cannot find skill data
    def missing() -> Path:
        raise FileNotFoundError("bundled velocitron skill data not found")

    configure(skill_source=missing)
    try:
        # when: the command runs
        code = main(["skill", str(tmp_path)])
    finally:
        configure(skill_source=None)

    # then
    assert code == 1
    assert "bundled velocitron skill" in capsys.readouterr().err


def test_equiv_is_absent_until_configured() -> None:
    # given: the equivalence hooks are clear
    configure(equiv_add_parser=None, equiv_main=None)
    try:
        # when: the equivalence command is not registered
        with pytest.raises(SystemExit) as caught:
            build_parser().parse_args(["equiv", "a.petrinet", "b.petrinet"])
    finally:
        configure(equiv_add_parser=None, equiv_main=None)

    # then: argparse rejects the unknown command
    assert caught.value.code == 2


def test_codegen_writes_a_module(tmp_path: Path) -> None:
    # given
    path = _leaf(tmp_path)
    out = tmp_path / "sound_net.py"

    # when
    code = main(["codegen", str(path), "--out", str(out)])

    # then
    assert code == 0
    assert "class SoundNet" in out.read_text(encoding="utf-8")


def test_viz_legend_is_a_digraph(capsys: pytest.CaptureFixture[str]) -> None:
    # when
    code = viz_main(["--legend"])

    # then
    assert code == 0
    assert "digraph" in capsys.readouterr().out


def test_importing_the_package_does_not_import_the_umbrella() -> None:
    # then: the dispatcher never bound the umbrella package
    assert "velocitron" not in sys.modules
    assert "velocitron.dsl.cli" not in sys.modules
