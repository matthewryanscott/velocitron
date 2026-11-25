"""Render a built net without the umbrella package."""

from __future__ import annotations

import velocitron_viz
from velocitron_viz import (
    Arc,
    ConsumePattern,
    Decoration,
    Decorations,
    Marking,
    Net,
    NetRef,
    Place,
    Port,
    Predicate,
    ProduceTemplate,
    RenderStyle,
    Token,
    Transition,
    ViewApplicationError,
    Wire,
    NAME_POINT,
    SMALL_POINT,
    apply_view,
    beside_gap,
    node_width,
    composition_to_dot,
    fusion_layout,
    legend_dot,
    net_render_model,
    net_to_dot,
    sibling_groups,
)
from velocitron_viz import Composition
from velocitron_viz import render as render_mod


def _feature_net() -> Net:
    return Net(
        name="feature-net",
        places=[
            Place("in_port", ["job"], port=Port("input", "job")),
            Place("out_port", ["job"], port=Port("output", "job")),
            Place("buffer", ["job", "flag"], description="a buffer of jobs"),
        ],
        transitions=[
            Transition("work", handler="work_handler"),
            Transition(
                "gated", handler="gated_handler", guard="gate_guard", priority=7
            ),
        ],
        arcs=[
            Arc(
                from_place="in_port",
                to_transition="work",
                consume=ConsumePattern(
                    "job",
                    Predicate('kind == "batch"', None),
                    "consume",
                    weight=2,
                ),
            ),
            Arc(
                from_place="buffer",
                to_transition="work",
                consume=ConsumePattern("flag", None, "inhibit"),
            ),
            Arc(
                from_place="buffer",
                to_transition="gated",
                consume=ConsumePattern("job", Predicate(None, "job_ready"), "read"),
            ),
            Arc(
                from_transition="work",
                to_place="out_port",
                produce=ProduceTemplate("job", "out_port", data={"fixed": True}),
            ),
            Arc(
                from_transition="gated",
                to_place="buffer",
                produce=ProduceTemplate(
                    "flag",
                    "buffer",
                    cel='{"count": binding.buffer[0].count - 1}',
                ),
            ),
        ],
        initial_marking=Marking(
            {"buffer": [Token("job", {}), Token("job", {})]},
        ),
    )


def _choice(extra_arcs: list[Arc], places: list[Place], names: list[str]) -> Net:
    pending = Place("pending", ["job"])
    return Net(
        name="choice",
        places=[pending, *places],
        transitions=[Transition(name) for name in names],
        arcs=[
            *[
                Arc(
                    from_place="pending",
                    to_transition=name,
                    consume=ConsumePattern("job", None, "consume"),
                )
                for name in names
            ],
            *extra_arcs,
        ],
    )


def test_a_built_net_renders_ports_marks_guards_and_arc_modes() -> None:
    # given: a net that exercises the structural drawing, already built
    net = _feature_net()
    # when: the library renders it
    dot = net_to_dot(net)
    plain = net_to_dot(net, style=RenderStyle(html_labels=False))
    # then: the drawing names every feature the renderer distinguishes
    assert "label=<<b>feature-net</b>>; labelloc=t;" in dot
    assert "port input &#183; job" in dot
    assert "port output &#183; job" in dot
    assert dot.count("peripheries=2") == 2
    assert "&#10216;job, flag&#10217;" in dot
    assert "● × 2 job" in dot
    assert "work_handler()" in dot
    assert "guard: gate_guard?" in dot
    assert "priority 7" in dot
    assert "arrowhead=odot" in dot
    assert "no flag" in dot
    assert "read job" in dot
    assert 'color="#1f6feb", style=dashed' in dot
    assert "2 &#215; job" in dot
    assert 'kind == "batch"' in dot
    assert "pred: job_ready" in dot
    assert '+ data {"fixed": true}' in dot
    assert '+ data cel {"count": binding.buffer[0].count - 1}' in dot
    assert "label=<" not in plain
    assert "⟨job, flag⟩" in plain
    assert "●" not in net_to_dot(net, include_marking=False)


def test_a_fusion_place_is_one_local_copy_per_transition() -> None:
    # given: one fusion place touched by three transitions
    net = Net(
        name="fusion-net",
        places=[
            Place("window", ["tok"], annotations={"fusion": True}),
            Place("src", ["job"]),
            Place("dst", ["job"]),
        ],
        transitions=[
            Transition("open", handler="open_h"),
            Transition("close", handler="close_h"),
            Transition("idle", handler="idle_h"),
        ],
        arcs=[
            Arc(
                from_place="src",
                to_transition="open",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="open",
                to_place="window",
                produce=ProduceTemplate("tok", "window"),
            ),
            Arc(
                from_place="window",
                to_transition="close",
                consume=ConsumePattern("tok", None, "consume"),
            ),
            Arc(
                from_place="window",
                to_transition="idle",
                consume=ConsumePattern("tok", None, "inhibit"),
            ),
            Arc(
                from_transition="close",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
        initial_marking=Marking({"window": [Token("tok", {})]}),
    )
    # when: rendered with fusion copies, and again as one node
    dot = net_to_dot(net)
    flat = net_to_dot(net, render_fusion=False)
    # then: each transition has a dashed local copy and the hub is absent
    assert '"window@open"' in dot
    assert '"window@close"' in dot
    assert '"window@idle"' in dot
    assert '"window" [' not in dot
    assert dot.count('style=dashed, color="gray40"') == 3
    assert "<b>window</b>" in dot
    assert '"open" -> "window@open"' in dot
    assert "arrowhead=odot" in dot
    assert dot.count("● tok") == 3
    assert '"window" [' in flat
    assert "window@" not in flat


def _read_switch(name: str) -> Arc:
    return Arc(
        from_place="switch",
        to_transition=name,
        consume=ConsumePattern("job", None, "read"),
    )


def test_neighbor_siblings_share_one_fusion_copy() -> None:
    # given: hold and skip are one choice, and both read a beside fusion place
    switch = Place("switch", ["job"], annotations={"fusion": True})
    read = _read_switch
    pair = _choice([read("hold"), read("skip")], [switch], ["hold", "skip"])
    trio = _choice(
        [read("hold"), read("skip"), read("send")],
        [switch],
        ["hold", "skip", "send"],
    )
    decorations = Decorations(nodes={"place:switch": Decoration(beside=True)})
    # when: the layout places the copies
    paired = fusion_layout(pair, {"switch"}, decorations)
    three = fusion_layout(trio, {"switch"}, decorations)
    groups = sibling_groups(trio, {"switch"})
    # then: two neighbors share the copy between them, and a run of three
    # pairs from the left
    assert groups == [("hold", "skip", "send")]
    assert dict(paired.copies) == {
        ("switch", "hold"): "switch@hold+skip",
        ("switch", "skip"): "switch@hold+skip",
    }
    assert paired.rows == (("hold", "switch@hold+skip", "skip"),)
    assert three.rows == (("hold", "switch@hold+skip", "skip", "send", "switch@send"),)


def test_an_unshared_run_pushes_copies_outside_the_row() -> None:
    # given: the same choice, with the fusion place opted out of sharing
    switch = Place("switch", ["job"], annotations={"fusion": True})
    read = _read_switch
    pair = _choice([read("hold"), read("skip")], [switch], ["hold", "skip"])
    trio = _choice(
        [read("hold"), read("skip"), read("send")],
        [switch],
        ["hold", "skip", "send"],
    )
    decorations = Decorations(
        nodes={"place:switch": Decoration(beside=True, beside_share=False)}
    )
    # when: the layout places the copies
    paired = fusion_layout(pair, {"switch"}, decorations)
    three = fusion_layout(trio, {"switch"}, decorations)
    # then: a run of two is the copy, the siblings, the copy, and the middle
    # of a run of three balances to the left
    assert paired.rows == (("switch@hold", "hold", "skip", "switch@skip"),)
    assert "hold+skip" not in "".join(paired.copies.values())
    assert three.rows == (
        ("switch@hold", "hold", "switch@skip", "skip", "send", "switch@send"),
    )


def _lease_choice() -> Net:
    # given: commit and expire are one choice on working; acquire is not
    clock = Place("clock", ["now"], annotations={"fusion": True})
    return Net(
        name="lease_choice",
        places=[
            Place("idle", ["job"]),
            Place("lease", ["permit"]),
            Place("working", ["job"]),
            Place("done", ["job"]),
            clock,
        ],
        transitions=[
            Transition("acquire"),
            Transition("commit"),
            Transition("expire"),
        ],
        arcs=[
            Arc(
                from_place="idle",
                to_transition="acquire",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="lease",
                to_transition="acquire",
                consume=ConsumePattern("permit", None, "consume"),
            ),
            Arc(
                from_transition="acquire",
                to_place="working",
                produce=ProduceTemplate("job", "working"),
            ),
            Arc(
                from_place="working",
                to_transition="commit",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="commit",
                to_place="done",
                produce=ProduceTemplate("job", "done"),
            ),
            Arc(
                from_transition="commit",
                to_place="lease",
                produce=ProduceTemplate("permit", "lease"),
            ),
            Arc(
                from_place="working",
                to_transition="expire",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="expire",
                to_place="idle",
                produce=ProduceTemplate("job", "idle"),
            ),
            Arc(
                from_transition="expire",
                to_place="lease",
                produce=ProduceTemplate("permit", "lease"),
            ),
            Arc(
                from_place="clock",
                to_transition="acquire",
                consume=ConsumePattern("now", None, "read"),
            ),
            Arc(
                from_place="clock",
                to_transition="commit",
                consume=ConsumePattern("now", None, "read"),
            ),
            Arc(
                from_place="clock",
                to_transition="expire",
                consume=ConsumePattern("now", None, "read"),
            ),
        ],
    )


def test_lease_choice_unshared_draws_two_clock_copies_outside_the_row() -> None:
    # given: the clock is beside unshared
    net = _lease_choice()
    decorations = Decorations(
        nodes={"place:clock": Decoration(beside=True, beside_share=False)}
    )
    # when: the layout and the drawing place the copies
    layout = fusion_layout(net, {"clock"}, decorations)
    dot = net_to_dot(net, decorations=decorations)
    # then: commit and expire keep one row, with a clock copy on each outside
    assert layout.rows == (
        ("clock@acquire", "acquire"),
        ("clock@commit", "commit", "expire", "clock@expire"),
    )
    assert "clock@commit+expire" not in dot
    assert dot.count('"clock@commit" [shape=ellipse') == 1
    assert dot.count('"clock@expire" [shape=ellipse') == 1
    assert (
        '    "clock@commit" -> "commit" -> "expire" -> "clock@expire" [style=invis];'
        in dot
    )


def _coord(value: float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def _place_width(name: str, color: str) -> float:
    return node_width([(name, NAME_POINT), (f"⟨{color}⟩", SMALL_POINT)])


def _transition_width(name: str) -> float:
    return node_width([(name, NAME_POINT)])


def _gap(transition: str, place: str, color: str) -> float:
    return beside_gap(_transition_width(transition), _place_width(place, color))


def _lanes(positions: dict[str, object]) -> dict[str, object]:
    return {
        "annotations": {
            "petrinet.dsl/v1": {
                "views": {"lanes": {"positions": positions, "routes": {}}},
                "arcHandles": {},
            }
        }
    }


def _node(dot: str, name: str) -> str:
    matches = [line for line in dot.splitlines() if line.startswith(f'    "{name}" [')]
    assert len(matches) == 1, (name, matches)
    return matches[0]


def _lease_lock() -> Net:
    # given: one fusion lock, used by two workers' acquire and release
    arcs: list[Arc] = []
    places = [Place("lock", ["permit"], annotations={"fusion": True})]
    transitions: list[Transition] = []
    for worker in ("a", "b"):
        places.extend(
            [
                Place(f"ready_{worker}", ["job"]),
                Place(f"held_{worker}", ["job"]),
                Place(f"done_{worker}", ["job"]),
            ]
        )
        transitions.extend(
            [Transition(f"acquire_{worker}"), Transition(f"release_{worker}")]
        )
        arcs.extend(
            [
                Arc(
                    from_place=f"ready_{worker}",
                    to_transition=f"acquire_{worker}",
                    consume=ConsumePattern("job", None, "consume"),
                ),
                Arc(
                    from_place="lock",
                    to_transition=f"acquire_{worker}",
                    consume=ConsumePattern("permit", None, "consume"),
                ),
                Arc(
                    from_transition=f"acquire_{worker}",
                    to_place=f"held_{worker}",
                    produce=ProduceTemplate("job", f"held_{worker}"),
                ),
                Arc(
                    from_place=f"held_{worker}",
                    to_transition=f"release_{worker}",
                    consume=ConsumePattern("job", None, "consume"),
                ),
                Arc(
                    from_transition=f"release_{worker}",
                    to_place=f"done_{worker}",
                    produce=ProduceTemplate("job", f"done_{worker}"),
                ),
                Arc(
                    from_transition=f"release_{worker}",
                    to_place="lock",
                    produce=ProduceTemplate("permit", "lock"),
                ),
            ]
        )
    return Net(name="lease_lock", places=places, transitions=transitions, arcs=arcs)


def test_a_pinned_view_places_each_lease_lock_copy_beside_its_transition() -> None:
    # given: the lock is beside left, and the view pins the four transitions
    net = _lease_lock()
    decorations = Decorations(
        nodes={"place:lock": Decoration(beside=True, beside_side="left")}
    )
    model = net_render_model(net, decorations=decorations)
    gap = _gap("acquire_a", "lock", "permit")
    # when: the view is applied
    dot = apply_view(
        model,
        _lanes(
            {
                "transition:acquire_a": {"x": 0, "y": 300},
                "transition:release_a": {"x": 0, "y": 100},
                "transition:acquire_b": {
                    "from": "transition:acquire_a",
                    "delta": {"x": 300, "y": 0},
                },
                "transition:release_b": {
                    "from": "transition:release_a",
                    "delta": {"x": 300, "y": 0},
                },
            }
        ),
        "lanes",
    )
    # then: each copy sits one gap to the left of its own transition
    assert f'pos="-{_coord(gap)},300!"' in _node(dot, "lock@acquire_a")
    assert f'pos="-{_coord(gap)},100!"' in _node(dot, "lock@release_a")
    assert f'pos="{_coord(300 - gap)},300!"' in _node(dot, "lock@acquire_b")
    assert f'pos="{_coord(300 - gap)},100!"' in _node(dot, "lock@release_b")
    assert "layout=neato;" in dot
    assert "cluster_beside" not in dot
    assert "style=invis" not in dot


def test_beside_copies_on_one_side_step_out_by_one_gap() -> None:
    # given: two left copies at one transition, switch first in arc order
    switch = Place("switch", ["job"], annotations={"fusion": True})
    budget = Place("budget", ["job"], annotations={"fusion": True})
    net = Net(
        name="stacked",
        places=[
            Place("queued", ["job"]),
            switch,
            budget,
        ],
        transitions=[Transition("start")],
        arcs=[
            Arc(
                from_place="queued",
                to_transition="start",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="switch",
                to_transition="start",
                consume=ConsumePattern("job", None, "read"),
            ),
            Arc(
                from_place="budget",
                to_transition="start",
                consume=ConsumePattern("job", None, "read"),
            ),
        ],
    )
    decorations = Decorations(
        nodes={
            "place:switch": Decoration(beside=True, beside_side="left"),
            "place:budget": Decoration(beside=True, beside_side="left"),
        }
    )
    # when: the view pins start
    dot = apply_view(
        net_render_model(net, decorations=decorations),
        _lanes({"transition:start": {"x": 0, "y": 0}}),
        "lanes",
    )
    # then: the first copy is nearest, and the second is one gap farther
    gap = _gap("start", "switch", "job")
    assert f'pos="-{_coord(gap)},0!"' in _node(dot, "switch@start")
    assert f'pos="-{_coord(2 * gap)},0!"' in _node(dot, "budget@start")


def test_a_shared_beside_copy_sits_between_two_pinned_transitions() -> None:
    # given: hold and skip share one beside copy
    switch = Place("switch", ["job"], annotations={"fusion": True})
    net = _choice(
        [_read_switch("hold"), _read_switch("skip")], [switch], ["hold", "skip"]
    )
    decorations = Decorations(nodes={"place:switch": Decoration(beside=True)})
    model = net_render_model(net, decorations=decorations)
    # when: both transitions are pinned, and when only the left one is
    both = apply_view(
        model,
        _lanes(
            {
                "transition:hold": {"x": 0, "y": 0},
                "transition:skip": {"x": 300, "y": 0},
            }
        ),
        "lanes",
    )
    one = apply_view(
        model,
        _lanes({"transition:hold": {"x": 0, "y": 0}}),
        "lanes",
    )
    # then: both pins put the copy at the midpoint, and one pin puts it one gap right
    assert 'pos="150,0!"' in _node(both, "switch@hold+skip")
    assert f'pos="{_coord(_gap("hold", "switch", "job"))},0!"' in _node(
        one, "switch@hold+skip"
    )


def test_beside_wins_for_copies_and_the_place_position_stays_an_anchor() -> None:
    # given: the lease lock, with a position on the place and on one transition
    net = _lease_lock()
    decorations = Decorations(
        nodes={"place:lock": Decoration(beside=True, beside_side="left")}
    )
    # when: the view is applied
    dot = apply_view(
        net_render_model(net, decorations=decorations),
        _lanes(
            {
                "transition:acquire_a": {"x": 0, "y": 0},
                "place:lock": {"x": 10, "y": 20},
                "place:ready_a": {"from": "place:lock", "delta": {"x": 10, "y": 0}},
            }
        ),
        "lanes",
    )
    # then: the pinned transition's copy sits beside it, and ready_a uses the place
    gap = _gap("acquire_a", "lock", "permit")
    assert f'pos="-{_coord(gap)},0!"' in _node(dot, "lock@acquire_a")
    assert 'pos="10,20!"' not in _node(dot, "lock@acquire_a")
    assert "pos=" not in _node(dot, "lock@release_a")
    assert 'pos="20,20!"' in _node(dot, "ready_a")


def test_a_view_pins_positions_without_parsing_dot_text() -> None:
    # given: a rendered net and a view that positions one place
    net = Net(
        name="placed",
        places=[Place("src", ["job"]), Place("dst", ["job"])],
        transitions=[Transition("move", handler="move")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="move",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="move",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
    )
    model = net_render_model(net)
    raw = {
        "annotations": {
            "petrinet.dsl/v1": {
                "views": {
                    "wired": {
                        "positions": {"place:src": {"x": 10, "y": 20}},
                        "routes": {},
                    }
                },
                "arcHandles": {},
            }
        }
    }
    # when: the view is applied through the structural index
    dot = apply_view(model, raw, "wired")
    # then: the place statement is pinned and the layout engine changes
    assert model.dot == net_to_dot(net)
    assert 'pos="10,20!"' in dot
    assert "layout=neato;" in dot
    assert "splines=ortho;" in dot
    try:
        apply_view(model, raw, "missing")
    except ViewApplicationError as error:
        assert "unknown view 'missing'" in str(error)
    else:
        raise AssertionError("unknown view was accepted")


def test_a_composition_draws_clusters_and_wires_from_parsed_nets() -> None:
    # given: two already-parsed nets and one wire between their ports
    left = Net(
        name="left",
        places=[Place("out", ["job"], port=Port("output", "job"))],
        transitions=[],
        arcs=[],
    )
    right = Net(
        name="right",
        places=[Place("inn", ["job"], port=Port("input", "job"))],
        transitions=[],
        arcs=[],
    )
    composition = Composition(
        nets=[NetRef("left.json", "left"), NetRef("right.json", "right")],
        wires=[Wire("left", "out", "right", "inn")],
        parsed_nets={"left": left, "right": right},
    )
    # when: the composition is drawn, and the legend is drawn
    dot = composition_to_dot(composition)
    # then: the wire joins the qualified ports and the legend is a graph
    assert '"left.out" -> "right.inn"' in dot
    assert "subgraph cluster_" in dot
    assert legend_dot().startswith("digraph ")
    assert not hasattr(velocitron_viz, "main")
    assert not hasattr(render_mod, "main")
