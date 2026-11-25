"""``velocitron-viz --metrics`` runs Graphviz or reads its JSON."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from velocitron_cli import viz_main

_LEAF = """
net sample "One step"

(src) -> [go] -> (dst)
[go] handler "go@sample"

view placed position (src) at {"x": 0, "y": 0}
view placed position [go] at {"x": 120, "y": 0}
view placed position (dst) at {"x": 240, "y": 0}
"""

# Two straight diagonals. Graphviz would draw this the same way.
_CROSSED = {
    "layout": "neato",
    "objects": [
        {"_gvid": 0, "name": "a", "pos": "0,0"},
        {"_gvid": 1, "name": "b", "pos": "2,2"},
        {"_gvid": 2, "name": "c", "pos": "0,2"},
        {"_gvid": 3, "name": "d", "pos": "2,0"},
    ],
    "edges": [
        {"tail": 0, "head": 1, "id": "arc:0", "pos": "e,2,2 0,0 0,0 2,2 2,2"},
        {"tail": 2, "head": 3, "id": "arc:1", "pos": "e,2,0 0,2 0,2 2,0 2,0"},
    ],
}

_COMPOSITION = (
    Path(__file__).resolve().parents[4]
    / "examples/capability-ladder/10-wired-pulse/wired_pulse.petrinet"
)


def test_metrics_reads_piped_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: Graphviz JSON on stdin, including the engine that wrote it
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_CROSSED)))
    # when: the command measures it
    code = viz_main(["--metrics", "-"])
    # then: the crossing is named and the engine is the one in the JSON
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["crossings"] == 1
    assert report["engine"] == "neato"
    assert report["pairs"][0]["drawn"] == "a→b × c→d"
    assert "graphviz_version" in report
    if shutil.which("dot") is None:
        assert report["graphviz_version"] is None
    else:
        assert isinstance(report["graphviz_version"], str)


def test_metrics_rejects_text_that_is_not_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: stdin that is not Graphviz JSON
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    # when: the command tries to measure it
    code = viz_main(["--metrics", "-"])
    # then: it fails before printing a report
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert (
        "velocitron-viz: error: layout metrics expected Graphviz JSON" in captured.err
    )


def test_a_rendered_net_stamps_arc_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a standalone net
    path = tmp_path / "sample.petrinet"
    path.write_text(_LEAF, encoding="utf-8")
    # when: the command renders DOT
    code = viz_main([str(path)])
    # then: each arc edge carries an id a later metrics pass can read
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert 'id="arc:0"' in captured.out
    assert 'id="arc:1"' in captured.out


def test_metrics_reports_a_missing_graphviz(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given: Graphviz is not on PATH
    path = tmp_path / "sample.petrinet"
    path.write_text(_LEAF, encoding="utf-8")
    monkeypatch.setattr("velocitron_cli.viz.shutil.which", lambda _engine: None)
    # when: the command is asked to measure the net
    code = viz_main([str(path), "--metrics"])
    # then: the error names the missing engine
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "Graphviz is required for --metrics" in captured.err
    assert "'dot' was not found on PATH" in captured.err


def test_metrics_rejects_a_composition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given: a composition document
    # when: metrics is requested
    code = viz_main([str(_COMPOSITION), "--metrics"])
    # then: the command asks for a standalone net
    captured = capsys.readouterr()
    assert code == 1
    assert "--metrics applies to a standalone net" in captured.err


@pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz is not installed")
@pytest.mark.skipif(
    shutil.which("neato") is None, reason="Graphviz neato is not installed"
)
def test_metrics_runs_the_engine_named_in_the_dot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a net whose placed view pins positions, so the DOT names neato
    path = tmp_path / "sample.petrinet"
    path.write_text(_LEAF, encoding="utf-8")
    # when: metrics runs with no view, then with the pinned view
    plain = viz_main([str(path), "--metrics"])
    plain_out = capsys.readouterr()
    viewed = viz_main([str(path), "--metrics", "--view", "placed"])
    viewed_out = capsys.readouterr()
    # then: each report names the engine that drew it
    assert plain == 0, plain_out.err
    assert viewed == 0, viewed_out.err
    plain_report = json.loads(plain_out.out)
    viewed_report = json.loads(viewed_out.out)
    assert plain_report["engine"] == "dot"
    assert viewed_report["engine"] == "neato"
    assert isinstance(plain_report["crossings"], int)
    assert isinstance(viewed_report["crossings"], int)
    assert plain_report["graphviz_version"]
    for key in (
        "crossings",
        "pairs",
        "overlaps",
        "edge_node_overlaps",
        "edge_length",
        "bends",
        "graphviz_version",
        "engine",
    ):
        assert key in plain_report
