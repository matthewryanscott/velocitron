# View application over the render model (viz.py + viz_view.py, ADR 0024).

import json
from pathlib import Path
from typing import Any

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_petrinet import parse_net
from velocitron_cli import viz_main as main
from velocitron_viz import (
    RenderModel,
    net_render_model,
    net_to_dot,
)
from velocitron_viz import (
    ViewApplicationError,
    apply_view,
    read_decorations,
    resolve_positions,
)

# Real .petrinet syntax (per spec/petrinet-language.md): arc-declared elements,
# `@handle:` arc handles, `annotation` documentation facts, `handler` bindings.
_MIXED_NET = """
net mixed

(seed) -start-> [emit] -pulse-> (out)
@shared: (out) -pulse-> [echo]

[emit] handler "emit@mixed"
[echo] handler "echo@mixed"

(out) description "Fusion place with two local instances"
(out) annotation fusion true
"""

_VIEWED_DSL_NET = (
    _MIXED_NET + '\n\nview wired position (seed) at {"x": 3, "y": 4}\n'
    'view wired route @shared orthogonal [ {"x": 1, "y": 5}, '
    '{"x": 9, "y": 5} ]\n'
)

_PLAIN_NET = """
net plain

(seed) -start-> [emit] -pulse-> (out)

[emit] handler "emit@plain"
"""

_VIEWS = "wired"


def _raw_with_payload(net_text: str, payload_fields: dict[str, Any]) -> dict[str, Any]:
    # given: a compiled net JSON carrying a hand-authored reserved payload
    document = compile_petrinet_text(net_text, "test.petrinet")
    document["annotations"] = {"petrinet.dsl/v1": payload_fields}
    return document


def _payload(
    positions: dict[str, Any],
    routes: dict[str, Any],
    handles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # given: a complete reserved payload with one view
    return {
        "arcHandles": dict(handles or {}),
        "markings": {},
        "views": {_VIEWS: {"positions": positions, "routes": routes}},
        "extensions": {},
    }


def test_net_render_model_matches_net_to_dot():
    # given: fixtures with and without fusion places, named and unnamed
    for net_text in (_MIXED_NET, _PLAIN_NET):
        net = parse_net(compile_petrinet_text(net_text, "test.petrinet"))
        # when: rendering through the model and through net_to_dot
        model = net_render_model(net)
        # then: the dot text is identical and the index covers every element
        assert model.dot == net_to_dot(net)
        assert len(model.arc_lines) == len(net.arcs)
    model = net_render_model(
        parse_net(compile_petrinet_text(_MIXED_NET, "test.petrinet"))
    )
    assert set(model.node_lines) == {
        "place:seed",
        "place:out",
        "transition:emit",
        "transition:echo",
    }
    # a fusion place renders as local instances only — one per transition here
    assert len(model.node_lines["place:out"]) == 2


def test_absolute_position_hits_place_and_its_fusion_instances():
    # given: the mixed net and a view positioning the fusion place
    net = parse_net(compile_petrinet_text(_MIXED_NET, "test.petrinet"))
    raw = _raw_with_payload(_MIXED_NET, _payload({"place:out": {"x": 10, "y": 20}}, {}))
    model = net_render_model(net)
    # when: the view is applied
    dot = apply_view(model, raw, _VIEWS)
    # then: every fusion instance line carries the pinned position
    lines = dot.splitlines()
    positioned = [line for line in lines if 'pos="10,20!"' in line]
    assert len(positioned) == len(model.node_lines["place:out"]) == 2
    assert "    splines=ortho;" in lines


def test_route_targets_the_handled_arcs_edge_only():
    # given: the plain net, an arcHandle for arc 1, and a route on that handle
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    raw = _raw_with_payload(
        _PLAIN_NET,
        _payload(
            {"place:seed": {"x": 0, "y": 0}},
            {
                "pulse": {
                    "style": "orthogonal",
                    "points": [{"x": 1, "y": 5}, {"x": 9, "y": 5}],
                }
            },
            handles={
                "pulse": {
                    "index": 1,
                    "fingerprint": {
                        "from": "emit",
                        "to": "out",
                        "type": "pulse",
                        "mode": "produce",
                    },
                }
            },
        ),
    )
    model = net_render_model(net)
    # when: the view is applied
    dot = apply_view(model, raw, _VIEWS)
    # then: exactly the arc-1 edge line carries the route points (line
    # indexes shift once splines=ortho inserts, so assert by content)
    lines = dot.splitlines()

    def line_with(needle: str) -> str:
        matches = [line for line in lines if needle in line]
        assert len(matches) == 1, (needle, matches)
        return matches[0]

    assert 'pos="1,5 9,5"' in line_with('"emit" -> "out"')
    assert "pos=" not in line_with('"seed" -> "emit"')


def test_route_on_an_attr_less_edge_statement():
    # given: a model whose edge statement carries no attribute block
    model = RenderModel(
        dot='digraph net {\n    "p1" -> "go";\n}',
        node_lines={"place:p1": (1,)},
        arc_lines=(1,),
        graph_attr_line=1,
    )
    raw = _raw_with_payload(
        _PLAIN_NET,
        _payload(
            {},
            {"pulse": {"style": "orthogonal", "points": [{"x": 2, "y": 3}]}},
            handles={"pulse": {"index": 0}},
        ),
    )
    # when: the route is applied
    dot = apply_view(model, raw, _VIEWS)
    # then: the attribute block is created around the route, not mangled
    assert dot.splitlines()[1] == "    splines=ortho;"
    assert '    "p1" -> "go" [pos="2,3"];' in dot.splitlines()


def test_unknown_view_rejects_with_the_established_message():
    # given: a payload without the requested view
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    raw = _raw_with_payload(_PLAIN_NET, _payload({}, {}))
    # when: applying a view that does not exist
    # then: the established unknown-view error surfaces
    with pytest.raises(ViewApplicationError) as error:
        apply_view(model, raw, "nope")
    assert "unknown view 'nope'" in str(error.value)


def test_unknown_subject_rejects_by_name():
    # given: a view positioning a subject the net does not declare
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    raw = _raw_with_payload(_PLAIN_NET, _payload({"place:ghost": {"x": 1, "y": 2}}, {}))
    # when: the view is applied
    # then: the unknown subject is named, not silently dropped
    with pytest.raises(ViewApplicationError) as error:
        apply_view(model, raw, _VIEWS)
    assert "unknown subject 'place:ghost'" in str(error.value)


def test_malformed_subject_key_rejects():
    # given: a position entry whose subject key has no kind prefix
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    raw = _raw_with_payload(_PLAIN_NET, _payload({"ghost": {"x": 1, "y": 2}}, {}))
    # when: the view is applied
    # then: the malformed subject is rejected with a named error
    with pytest.raises(ViewApplicationError) as error:
        apply_view(model, raw, _VIEWS)
    assert "invalid view subject 'ghost'" in str(error.value)


def test_invalid_position_shape_rejects():
    # given: a position whose value is not a finite {x, y} pair
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    for bad in ({"x": 1}, {"x": True, "y": 2}, {"x": "1", "y": 2}):
        raw = _raw_with_payload(_PLAIN_NET, _payload({"place:seed": bad}, {}))
        # when: the view is applied
        # then: the invalid position error surfaces
        with pytest.raises(ViewApplicationError, match="invalid position"):
            apply_view(model, raw, _VIEWS)


def test_stale_route_index_rejects():
    # given: a route whose arc index lies beyond the rendered arcs
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    raw = _raw_with_payload(
        _PLAIN_NET,
        _payload(
            {},
            {"pulse": {"style": "orthogonal", "points": [{"x": 1, "y": 1}]}},
            handles={"pulse": {"index": 9}},
        ),
    )
    # when: the view is applied
    # then: the stale index is rejected instead of silently skipped
    with pytest.raises(ViewApplicationError, match="beyond the rendered arcs"):
        apply_view(model, raw, _VIEWS)


def test_unknown_route_handle_rejects_with_the_established_message():
    # given: a route naming a handle the payload does not carry
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    raw = _raw_with_payload(
        _PLAIN_NET,
        _payload(
            {},
            {"ghost": {"style": "orthogonal", "points": [{"x": 1, "y": 1}]}},
        ),
    )
    # when: the view is applied
    # then: the unknown-handle error surfaces (the handle map is empty)
    with pytest.raises(ViewApplicationError, match="unknown arc handle 'ghost'"):
        apply_view(model, raw, _VIEWS)


def test_invalid_route_shape_rejects():
    # given: a route with the wrong style
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    model = net_render_model(net)
    raw = _raw_with_payload(
        _PLAIN_NET,
        _payload(
            {},
            {"pulse": {"style": "spline", "points": [{"x": 1, "y": 1}]}},
            handles={"pulse": {"index": 0}},
        ),
    )
    # when: the view is applied
    # then: the invalid route error surfaces before any text mutates
    with pytest.raises(ViewApplicationError, match="invalid route"):
        apply_view(model, raw, _VIEWS)


def test_relative_chain_resolves_in_dependency_order():
    # given: A absolutely positioned, B and C chained relative to it
    positions = {
        "place:a": {"x": 100, "y": 50},
        "place:b": {"from": "place:a", "delta": {"x": 10, "y": -5}},
        "place:c": {"from": "place:b", "delta": {"x": 0, "y": 25}},
    }
    # when: the positions resolve
    resolved = resolve_positions(_VIEWS, positions)
    # then: the chain resolves by arithmetic against the resolved base
    assert resolved["place:a"] == (100, 50)
    assert resolved["place:b"] == (110, 45)
    assert resolved["place:c"] == (110, 70)


def test_relative_cycle_rejects():
    # given: two relative entries referencing each other
    positions = {
        "place:a": {"from": "place:b", "delta": {"x": 1, "y": 1}},
        "place:b": {"from": "place:a", "delta": {"x": 1, "y": 1}},
    }
    # when: the positions resolve
    # then: the cycle is rejected
    with pytest.raises(ViewApplicationError, match="cycle"):
        resolve_positions(_VIEWS, positions)


def test_relative_unknown_base_rejects():
    # given: a relative entry whose base carries no position in this view
    positions = {"place:b": {"from": "place:a", "delta": {"x": 1, "y": 1}}}
    # when: the positions resolve
    # then: the unpositioned base is named
    with pytest.raises(ViewApplicationError, match="unpositioned subject"):
        resolve_positions(_VIEWS, positions)


_RELATIVE_DSL_NET = (
    _PLAIN_NET + '\nview wired position (seed) at {"x": 3, "y": 4}\n'
    'view wired position (out) relative (seed) + {"x": 1, "y": 0}\n'
)


def test_dsl_relative_positions_apply_end_to_end():
    # given: a DSL net whose relative entry rides the real compile pipeline
    document = compile_petrinet_text(_RELATIVE_DSL_NET, "test.petrinet")
    net = parse_net(document)
    model = net_render_model(net)
    # when: the view applies to the model
    dot = apply_view(model, document, _VIEWS)
    # then: the chain resolves seed's absolute plus out's authored delta
    lines = dot.splitlines()

    def line_with(needle: str) -> str:
        matches = [line for line in lines if needle in line]
        assert len(matches) == 1, (needle, matches)
        return matches[0]

    assert 'pos="3,4!"' in line_with('"seed" [shape=ellipse')
    assert 'pos="4,4!"' in line_with('"out" [shape=ellipse')


def test_cli_renders_relative_dsl_source_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a .petrinet source carrying relative and absolute view facts, on disk
    source = tmp_path / "relative.petrinet"
    source.write_text(
        _VIEWED_DSL_NET + '\nview wired position (seed) at {"x": 3, "y": 4}\n'
        'view wired position (out) relative (seed) + {"x": 1, "y": 0}\n',
        encoding="utf-8",
    )

    # when: the viz CLI renders the source with the view applied
    # then: resolved relative coordinates reach the pinned dot output
    assert main([str(source), "--view", "wired"]) == 0
    out = capsys.readouterr().out
    assert 'pos="3,4!"' in out
    assert 'pos="4,4!"' in out


def test_cli_applies_a_view_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a net JSON whose payload positions one place, on disk
    document = compile_petrinet_text(_PLAIN_NET, "test.petrinet")
    document["annotations"] = {
        "petrinet.dsl/v1": {
            "arcHandles": {},
            "markings": {},
            "views": {
                "wired": {
                    "positions": {"place:seed": {"x": 3, "y": 4}},
                    "routes": {},
                }
            },
            "extensions": {},
        }
    }
    source = tmp_path / "plain.json"
    source.write_text(json.dumps(document), encoding="utf-8")

    # when: the CLI renders the document with that view selected
    exit_code = main([str(source), "--view", "wired"])
    # then: the pinned position and the view attribute render to stdout
    assert exit_code == 0
    out = capsys.readouterr().out
    assert 'pos="3,4!"' in out
    assert "splines=ortho;" in out


def test_cli_renders_dsl_source_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a .petrinet source whose view facts carry the payload, on disk
    source = tmp_path / "mixed.petrinet"
    source.write_text(_VIEWED_DSL_NET, encoding="utf-8")

    # when: the viz CLI renders the DSL source with that view selected
    # then: the authored facts carry through the assembled payload
    assert main([str(source), "--view", "wired"]) == 0
    out = capsys.readouterr().out
    assert 'pos="3,4!"' in out
    assert 'pos="1,5 9,5"' in out
    assert "splines=ortho;" in out
    # and: the fusion place renders as two local instances
    assert out.count("label=<<b>out</b>") == 2


def test_cli_dsl_source_matches_document_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the same net as DSL source and as canonical document JSON
    source_dsl = tmp_path / "mixed.petrinet"
    source_dsl.write_text(_VIEWED_DSL_NET, encoding="utf-8")
    document = compile_petrinet_text(_VIEWED_DSL_NET, "mixed.petrinet")
    source_json = tmp_path / "mixed.json"
    source_json.write_text(json.dumps(document), encoding="utf-8")

    # when: both inputs render with the view applied
    assert main([str(source_dsl), "--view", "wired"]) == 0
    dot_dsl = capsys.readouterr().out
    assert main([str(source_json), "--view", "wired"]) == 0
    dot_json = capsys.readouterr().out

    # then: the author sees the same diagram from either input
    assert dot_dsl == dot_json


def test_positioned_view_selects_neato_with_point_coordinates():
    # given: a view that pins one node
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    raw = _raw_with_payload(_PLAIN_NET, _payload({"place:seed": {"x": 3, "y": 4}}, {}))
    # when: the view is applied
    lines = apply_view(net_render_model(net), raw, _VIEWS).splitlines()
    # then: the graph asks for an engine that honors pos, read in points
    for attribute in ("layout=neato;", "inputscale=72;", "overlap=scale;"):
        assert f"    {attribute}" in lines


def test_view_without_positions_keeps_the_dot_engine():
    # given: a view with no positions
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    raw = _raw_with_payload(_PLAIN_NET, _payload({}, {}))
    # when: the view is applied
    dot = apply_view(net_render_model(net), raw, _VIEWS)
    # then: no layout engine is forced
    assert "layout=" not in dot
    assert "    splines=ortho;" in dot.splitlines()


_DEFAULT_VIEWED_NET = (
    _PLAIN_NET + '\nview default position (seed) at {"x": 3, "y": 4}\n'
)


def test_cli_applies_the_default_view_without_a_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a source with a view named default
    source = tmp_path / "plain.petrinet"
    source.write_text(_DEFAULT_VIEWED_NET, encoding="utf-8")
    # when: the CLI renders it with no view flag
    assert main([str(source)]) == 0
    # then: the default view applies
    out = capsys.readouterr().out
    assert 'pos="3,4!"' in out
    assert "layout=neato;" in out


def test_cli_no_view_skips_the_default_view(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a source with a view named default
    source = tmp_path / "plain.petrinet"
    source.write_text(_DEFAULT_VIEWED_NET, encoding="utf-8")
    # when: the CLI renders it with --no-view
    assert main([str(source), "--no-view"]) == 0
    # then: the plain layout renders
    out = capsys.readouterr().out
    assert "pos=" not in out
    assert "layout=" not in out
    assert "splines=" not in out


def test_cli_rejects_view_with_no_view(tmp_path: Path) -> None:
    # given: any source
    source = tmp_path / "plain.petrinet"
    source.write_text(_DEFAULT_VIEWED_NET, encoding="utf-8")
    # when: both view flags are given
    # then: argparse rejects the combination
    with pytest.raises(SystemExit) as exit_info:
        main([str(source), "--view", "default", "--no-view"])
    assert exit_info.value.code == 2


_STYLED_NET = (
    _PLAIN_NET + "\nview default splines curved\nview default detail structure\n"
)


def test_view_splines_replaces_the_ortho_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a default view that picks curved edges
    source = tmp_path / "plain.petrinet"
    source.write_text(_STYLED_NET, encoding="utf-8")
    # when: the CLI renders it
    assert main([str(source)]) == 0
    # then: the view's style replaces ortho
    out = capsys.readouterr().out
    assert "    splines=curved;" in out
    assert "ortho" not in out


def test_view_detail_applies_unless_the_cli_overrides_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a default view at structure detail
    source = tmp_path / "plain.petrinet"
    source.write_text(_STYLED_NET, encoding="utf-8")
    # when: rendered without and with --detail
    assert main([str(source)]) == 0
    view_out = capsys.readouterr().out
    assert main([str(source), "--detail", "full"]) == 0
    flag_out = capsys.readouterr().out
    # then: the view hides the handler; the flag brings it back
    assert "emit@plain" not in view_out
    assert "emit@plain" in flag_out


def test_invalid_view_splines_in_hand_written_json_rejects():
    # given: a payload whose view names an unknown edge style
    net = parse_net(compile_petrinet_text(_PLAIN_NET, "test.petrinet"))
    payload = _payload({}, {})
    payload["views"][_VIEWS]["splines"] = "wavy"
    raw = _raw_with_payload(_PLAIN_NET, payload)
    # when: the view is applied
    # then: the error names the view and the value
    with pytest.raises(ViewApplicationError, match="invalid splines 'wavy'"):
        apply_view(net_render_model(net), raw, _VIEWS)


_DECORATED_NET = """
net decorated

(queued) -job-> [start] -job-> (running)
@done_in: (running) -job-> [finish]
[finish] -receipt-> (done)
(gate) -job->? [finish]
@done_in predicate cel "job.exitCode == 0"
[start] timer clock (queued) cel "clock.now >= job.dueAt"

decorate [start] highlight "R2.11"
decorate (running) note "one worker at a time"
decorate @done_in highlight
decorate @done_in summary "succeeded"
decorate [start] summary "due now"
"""


def _decorated_dot(
    *args: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> str:
    source = tmp_path / "decorated.petrinet"
    source.write_text(_DECORATED_NET, encoding="utf-8")
    assert main([str(source), "--plain-labels", *args]) == 0
    return capsys.readouterr().out


def _line_with(dot: str, needle: str) -> str:
    matches = [line for line in dot.splitlines() if line.startswith(f"    {needle}")]
    assert len(matches) == 1, (needle, matches)
    return matches[0]


def test_highlight_fills_nodes_and_bolds_arcs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a transition and an arc decorated with highlight
    # when: the CLI renders the source
    dot = _decorated_dot(tmp_path=tmp_path, capsys=capsys)
    # then: the node fills amber and shows its label; the arc pen turns amber
    start = _line_with(dot, '"start" [')
    assert 'fillcolor="#FFE08A"' in start
    assert "R2.11" in start
    assert 'color="#D97706", penwidth=2.5' in _line_with(dot, '"running" -> "finish"')
    assert "#D97706" not in _line_with(dot, '"queued" -> "start"')


def test_note_shows_at_every_detail_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a place with a note
    for detail in ("full", "summary", "structure"):
        # when: rendered at each detail level
        dot = _decorated_dot("--detail", detail, tmp_path=tmp_path, capsys=capsys)
        # then: the note is in the place label
        assert "one worker at a time" in _line_with(dot, '"running" [')


def test_summary_replaces_expressions_only_at_summary_detail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: an arc and a transition with authored summaries
    # when: rendered at full and at summary detail
    full = _decorated_dot(tmp_path=tmp_path, capsys=capsys)
    summary = _decorated_dot("--detail", "summary", tmp_path=tmp_path, capsys=capsys)
    # then: full shows the CEL, summary shows the authored text instead
    assert "job.exitCode == 0" in full and "succeeded" not in full
    assert "succeeded" in summary and "job.exitCode" not in summary
    assert "clock.now" in full and "due now" not in full
    assert "due now" in summary and "clock.now" not in summary


_PRIORITIZED_NET = """
net prioritized

(queued) -job-> [start] -job-> (running)
(queued) -job-> [skip] -job-> (skipped)
[start] priority 5
[skip] priority 1
decorate [start] summary "first choice"
"""


def test_summary_hides_the_priority_only_at_summary_detail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: two prioritized transitions, one with an authored summary
    source = tmp_path / "prioritized.petrinet"
    source.write_text(_PRIORITIZED_NET, encoding="utf-8")
    # when: rendered at full and at summary detail
    assert main([str(source), "--plain-labels"]) == 0
    full = capsys.readouterr().out
    assert main([str(source), "--plain-labels", "--detail", "summary"]) == 0
    summary = capsys.readouterr().out
    # then: the summary replaces the priority; the transition without one keeps it
    assert "priority 5" in _line_with(full, '"start" [')
    start = _line_with(summary, '"start" [')
    assert "first choice" in start and "priority" not in start
    assert "priority 1" in _line_with(summary, '"skip" [')


_CORRELATED_NET = """
net correlated

(queued) -job-> [start] -job-> (running)
@cfg_in: (settings) -setting->? [start]
@cfg_in correlate cel "token.account == binding.queued[0].account"
decorate @cfg_in summary "own account"
"""


def test_read_arc_correlate_draws_like_an_inhibit_correlate_and_takes_a_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a read arc with a correlate and an authored summary
    source = tmp_path / "correlated.petrinet"
    source.write_text(_CORRELATED_NET, encoding="utf-8")
    # when: rendered at full and at summary detail
    assert main([str(source), "--plain-labels"]) == 0
    full = _line_with(capsys.readouterr().out, '"settings" -> "start"')
    assert main([str(source), "--plain-labels", "--detail", "summary"]) == 0
    summary = _line_with(capsys.readouterr().out, '"settings" -> "start"')
    # then: full shows the correlate CEL; summary shows the authored text instead
    assert "binding.queued[0].account" in full and "own account" not in full
    assert "own account" in summary and "binding.queued" not in summary


def test_quiet_color_hides_consume_and_produce_labels_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: the decorated net, with job quieted from the command line
    # when: rendered
    dot = _decorated_dot("--quiet-color", "job", tmp_path=tmp_path, capsys=capsys)
    # then: consume and produce arcs of job lose the type label
    assert "label=" not in _line_with(dot, '"queued" -> "start"')
    assert "label=" not in _line_with(dot, '"start" -> "running"')
    # and: the read arc and other colors keep theirs
    assert "read job" in _line_with(dot, '"gate" -> "finish"')
    assert "receipt" in _line_with(dot, '"finish" -> "done"')


def test_decorate_color_quiet_needs_no_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a source that quiets job itself
    source = tmp_path / "quiet.petrinet"
    source.write_text(_DECORATED_NET + "decorate color job quiet\n", encoding="utf-8")
    # when: rendered with no flags
    assert main([str(source), "--plain-labels"]) == 0
    # then: the consume arc carries no type label
    assert "label=" not in _line_with(capsys.readouterr().out, '"queued" -> "start"')


def test_read_decorations_collects_shown_fields_per_color() -> None:
    # given: a net that shows two job fields and also quiets job
    net = compile_petrinet_text(
        _DECORATED_NET
        + "decorate color job quiet\n"
        + 'decorate color job show "id" "owner.name"\n',
        "shown.petrinet",
    )
    # when: its decorations are read
    decorations = read_decorations(net)
    # then: job maps to its field paths in source order, beside the quiet flag
    assert decorations.shown_fields == {"job": ("id", "owner.name")}
    assert decorations.quiet_colors == frozenset({"job"})


def test_read_decorations_without_show_has_no_shown_fields() -> None:
    # given: a net that only quiets job
    net = compile_petrinet_text(
        _DECORATED_NET + "decorate color job quiet\n", "quiet.petrinet"
    )
    # when: its decorations are read
    decorations = read_decorations(net)
    # then: no color names fields to show
    assert decorations.shown_fields == {}


_BESIDE_NET = """
net beside

(queued) -job-> [start] -job-> (running)
(switch) -flag->? [start]
(budget) -credit->? [start]
(owner) -flag->? [start]
(switch) -flag->? [finish]
(running) -job-> [finish]
(switch) annotation fusion true
(budget) annotation fusion true
(owner) annotation fusion true
"""


def _beside_dot(
    decorations: str, *args: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> str:
    source = tmp_path / "beside.petrinet"
    source.write_text(_BESIDE_NET + decorations, encoding="utf-8")
    assert main([str(source), "--plain-labels", *args]) == 0
    return capsys.readouterr().out


def test_beside_keeps_copies_on_their_transitions_rank_in_side_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: switch beside left, budget beside right
    decorations = "decorate (switch) beside left\ndecorate (budget) beside right\n"
    # when: rendered
    dot = _beside_dot(decorations, tmp_path=tmp_path, capsys=capsys)
    # then: each transition and its beside copies share one ranked cluster
    assert "    newrank=true;" in dot.splitlines()
    assert _line_with(dot, 'subgraph "cluster_beside_0"') == (
        '    subgraph "cluster_beside_0" { label=""; peripheries=0; margin=0; '
        '{ rank=same; "switch@start"; "start"; "budget@start"; } }'
    )
    # and: an invisible chain fixes the order; a copy without beside stays out
    assert '    "switch@start" -> "start" -> "budget@start" [style=invis];' in dot
    assert '    "switch@finish" -> "finish" [style=invis];' in dot
    assert "owner@start" not in _line_with(dot, 'subgraph "cluster_beside_0"')


def test_beside_without_a_side_balances_copies_starting_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: three copies at start with no side, in arc order switch, budget, owner
    decorations = (
        "decorate (switch) beside\ndecorate (budget) beside\ndecorate (owner) beside\n"
    )
    # when: rendered
    dot = _beside_dot(decorations, tmp_path=tmp_path, capsys=capsys)
    # then: switch goes left, budget right, owner left again and farther out
    assert (
        '    "owner@start" -> "switch@start" -> "start" -> "budget@start" '
        "[style=invis];"
    ) in dot


def test_beside_leaves_the_order_of_a_written_copy_to_its_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: finish writes switch, whose copies go beside on the left
    decorations = "[finish] -flag-> (switch)\ndecorate (switch) beside left\n"
    # when: rendered
    dot = _beside_dot(decorations, tmp_path=tmp_path, capsys=capsys)
    # then: the write runs against the row, so it takes no part in the layout
    assert '    "switch@finish" -> "finish" [style=invis];' in dot
    assert "constraint=false" in _line_with(dot, '"finish" -> "switch@finish"')
    # and: so does every other arc to a beside copy; arcs to other copies keep theirs
    assert "constraint=false" in _line_with(dot, '"switch@start" -> "start" [label')
    assert "constraint=false" not in _line_with(dot, '"owner@start" -> "start"')


def test_beside_is_dropped_by_a_positioned_view_and_by_no_fusion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a beside copy and a view that pins start
    decorations = (
        "decorate (switch) beside left\n"
        'view pinned position [start] at {"x": 0, "y": 0}\n'
    )
    # when: rendered with that view, and with fusion off
    pinned = _beside_dot(
        decorations, "--view", "pinned", tmp_path=tmp_path, capsys=capsys
    )
    unfused = _beside_dot(decorations, "--no-fusion", tmp_path=tmp_path, capsys=capsys)
    # then: neato gets no beside statements, and without copies there are none
    assert "layout=neato;" in pinned
    for dot in (pinned, unfused):
        assert "newrank" not in dot
        assert "cluster_beside" not in dot
        assert "style=invis" not in dot


def test_decorate_color_show_picks_the_fields_a_render_shows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a marked job, and a source that shows only its id
    source = tmp_path / "shown.petrinet"
    source.write_text(
        _DECORATED_NET
        + "marking initial (queued) <- $j1\n"
        + '$j1: job {"id": "j-1", "n": 7}\n'
        + 'decorate color job show "id"\n',
        encoding="utf-8",
    )
    # when: rendered with no flags
    assert main([str(source)]) == 0
    # then: the row shows the id alone, and the tooltip the full data
    line = _line_with(capsys.readouterr().out, '"queued" [')
    assert "● job id=j-1</font>" in line
    assert 'tooltip="job {\\"id\\":\\"j-1\\",\\"n\\":7}"' in line
