"""Render a built net without the umbrella package."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

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


def test_single_draws_one_dashed_fusion_node_and_a_view_can_override_it() -> None:
    """decorate single keeps the fusion style; a view wins; --no-fusion wins."""
    # given: switch asks to be one node, and budget stays a beside copy
    net = Net(
        name="single",
        places=[
            Place("queued", ["job"]),
            Place("running", ["job"]),
            Place("switch", ["flag"], annotations={"fusion": True}),
            Place("budget", ["credit"], annotations={"fusion": True}),
        ],
        transitions=[Transition("start"), Transition("finish")],
        arcs=[
            Arc(
                from_place="queued",
                to_transition="start",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="start",
                to_place="running",
                produce=ProduceTemplate("job", "running"),
            ),
            Arc(
                from_place="switch",
                to_transition="start",
                consume=ConsumePattern("flag", None, "read"),
            ),
            Arc(
                from_place="switch",
                to_transition="finish",
                consume=ConsumePattern("flag", None, "read"),
            ),
            Arc(
                from_place="budget",
                to_transition="start",
                consume=ConsumePattern("credit", None, "read"),
            ),
        ],
    )
    decorations = Decorations(
        nodes={
            "place:switch": Decoration(single=True),
            "place:budget": Decoration(beside=True),
        }
    )
    plain = RenderStyle(html_labels=False, tooltips=False)

    def edge(dot: str, source: str, target: str) -> str:
        return next(
            line for line in dot.splitlines() if f'"{source}" -> "{target}"' in line
        )

    # when: rendered from the decoration, from each view override, and with the flag
    dot = net_to_dot(net, decorations=decorations, style=plain)
    copies = net_to_dot(
        net, decorations=decorations, fusion_modes={"switch": "copies"}, style=plain
    )
    collapsed = net_to_dot(
        net, decorations=decorations, fusion_modes={"budget": "single"}, style=plain
    )
    flat = net_to_dot(net, decorations=decorations, render_fusion=False, style=plain)

    # then: switch is one dashed node whose arcs take part in ranking
    assert '"switch@' not in dot
    assert 'class="fusion", style=dashed, color="gray40"' in dot
    assert "constraint=false" not in edge(dot, "switch", "start")
    assert "constraint=false" not in edge(dot, "switch", "finish")
    # and: budget stays a beside copy, so its arc does not rank
    assert '"budget@start"' in dot
    assert "constraint=false" in edge(dot, "budget@start", "start")
    assert "cluster_beside_0" in dot
    # and: the view can put switch back to copies
    assert '"switch@start"' in copies and '"switch@finish"' in copies
    # and: the view can collapse budget, dropping its beside row
    assert '"budget" [' in collapsed
    assert '"budget@' not in collapsed
    assert "cluster_beside" not in collapsed
    assert 'class="fusion"' in collapsed
    # and: --no-fusion still draws ordinary nodes and wins over the decoration
    assert '"switch" [' in flat and '"budget" [' in flat
    assert "switch@" not in flat and "budget@" not in flat
    assert 'class="fusion"' not in flat


def test_a_copy_position_does_not_apply_to_a_single_fusion_node() -> None:
    """A place drawn once takes its place position; a copy fact is not an error."""
    # given: switch is one node, and the view also positions one of its copies
    net = Net(
        name="single",
        places=[
            Place("queued", ["job"]),
            Place("switch", ["flag"], annotations={"fusion": True}),
        ],
        transitions=[Transition("start"), Transition("finish")],
        arcs=[
            Arc(
                from_place="queued",
                to_transition="start",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_place="switch",
                to_transition="start",
                consume=ConsumePattern("flag", None, "read"),
            ),
            Arc(
                from_place="switch",
                to_transition="finish",
                consume=ConsumePattern("flag", None, "read"),
            ),
        ],
    )
    decorations = Decorations(nodes={"place:switch": Decoration(single=True)})
    model = net_render_model(
        net,
        decorations=decorations,
        style=RenderStyle(html_labels=False, tooltips=False),
    )
    raw = {
        "annotations": {
            "petrinet.dsl/v1": {
                "arcHandles": {},
                "views": {
                    "lanes": {
                        "positions": {
                            "place:switch": {"x": 4, "y": 8},
                            "place:switch@transition:start": {"x": 40, "y": 80},
                            "transition:start": {"x": 1, "y": 2},
                        },
                        "routes": {},
                    }
                },
            }
        }
    }

    # when: the view is applied
    dot = apply_view(model, raw, "lanes")

    # then: the one node takes the place point, and the copy point is unused
    assert '"switch@' not in dot
    switch = next(line for line in dot.splitlines() if '"switch" [' in line)
    assert 'pos="4,8!"' in switch
    assert "40,80" not in dot


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
    # pairs from the left of the structural order (rank, then name)
    assert groups == [("hold", "send", "skip")]
    assert dict(paired.copies) == {
        ("switch", "hold"): "switch@hold+skip",
        ("switch", "skip"): "switch@hold+skip",
    }
    assert paired.rows == (("hold", "switch@hold+skip", "skip"),)
    assert three.rows == (("hold", "switch@hold+send", "send", "skip", "switch@skip"),)


def test_reordering_declarations_does_not_change_the_drawing() -> None:
    # given: a net, the same net with every declaration reversed, and a choice
    # whose arcs are reversed
    net = _feature_net()
    reversed_net = Net(
        name=net.name,
        places=list(reversed(net.places)),
        transitions=list(reversed(net.transitions)),
        arcs=list(reversed(net.arcs)),
        initial_marking=net.initial_marking,
        description=net.description,
        annotations=net.annotations,
    )
    switch = Place("switch", ["job"], annotations={"fusion": True})
    read = _read_switch
    forward = _choice(
        [read("hold"), read("skip"), read("send")],
        [switch],
        ["hold", "skip", "send"],
    )
    backward = Net(
        name=forward.name,
        places=list(reversed(forward.places)),
        transitions=list(reversed(forward.transitions)),
        arcs=list(reversed(forward.arcs)),
    )
    decorations = Decorations(nodes={"place:switch": Decoration(beside=True)})
    # when: each pair is drawn
    drawn = net_to_dot(net)
    drawn_reversed = net_to_dot(reversed_net)
    choice = net_to_dot(forward, decorations=decorations)
    choice_reversed = net_to_dot(backward, decorations=decorations)
    # then: the bytes match, and the initially marked place is not waiting
    # on where it was declared
    assert drawn == drawn_reversed
    assert choice == choice_reversed
    assert sibling_groups(forward, {"switch"}) == sibling_groups(backward, {"switch"})
    place_names = [
        line.split('"')[1]
        for line in drawn.splitlines()
        if line.startswith('    "')
        and "->" not in line
        and line.rstrip().endswith("];")
    ]
    assert place_names.index("buffer") < place_names.index("in_port")
    assert place_names.index("buffer") < place_names.index("out_port")
    # and: a view still finds each arc by its declaration index
    model = net_render_model(reversed_net)
    text = model.dot.splitlines()
    for index, arc in enumerate(reversed_net.arcs):
        endpoints = [
            arc.from_place,
            arc.to_place,
            arc.from_transition,
            arc.to_transition,
        ]
        line = text[model.arc_lines[index]]
        assert all(name is None or f'"{name}"' in line for name in endpoints)


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
        ("switch@hold", "hold", "switch@send", "send", "skip", "switch@skip"),
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


def test_an_unshared_place_with_copy_positions_keeps_one_copy_each() -> None:
    # given: the clock is beside unshared, and the view pins each choice copy
    net = _lease_choice()
    decorations = Decorations(
        nodes={"place:clock": Decoration(beside=True, beside_share=False)}
    )
    model = net_render_model(net, decorations=decorations)
    # when: those copies have their own positions (ADR 0068)
    dot = apply_view(
        model,
        _lanes(
            {
                "transition:commit": {"x": 0, "y": 0},
                "transition:expire": {"x": 200, "y": 0},
                "place:clock@transition:commit": {"x": -40, "y": 0},
                "place:clock@transition:expire": {"x": 240, "y": 0},
            }
        ),
        "lanes",
    )
    # then: one node per transition, each on its own point
    assert (
        model.copy_lines[("clock", "commit")] != model.copy_lines[("clock", "expire")]
    )
    assert "clock@commit+expire" not in dot
    assert 'pos="-40,0!"' in _node(dot, "clock@commit")
    assert 'pos="240,0!"' in _node(dot, "clock@expire")


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
    # then: budget, first in the structural order, is nearest, and switch
    # is one gap farther
    gap = _gap("start", "switch", "job")
    assert f'pos="-{_coord(gap)},0!"' in _node(dot, "budget@start")
    assert f'pos="-{_coord(2 * gap)},0!"' in _node(dot, "switch@start")


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


def test_a_whole_place_position_beats_beside_and_stays_an_anchor() -> None:
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
                "transition:release_a": {"x": 200, "y": 0},
                "place:lock": {"x": 10, "y": 20},
                "place:ready_a": {"from": "place:lock", "delta": {"x": 10, "y": 0}},
            }
        ),
        "lanes",
    )
    # then: both copies take the place point, and ready_a uses that anchor
    assert 'pos="10,20!"' in _node(dot, "lock@acquire_a")
    assert 'pos="10,20!"' in _node(dot, "lock@release_a")
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


def test_a_copy_position_beats_the_place_which_beats_beside() -> None:
    # given: beside lock, a place position, one copy position, and a relative base
    net = _lease_lock()
    decorations = Decorations(
        nodes={"place:lock": Decoration(beside=True, beside_side="left")}
    )
    model = net_render_model(net, decorations=decorations)
    # when: the view is applied
    dot = apply_view(
        model,
        _lanes(
            {
                "transition:acquire_a": {"x": 0, "y": 0},
                "transition:release_a": {"x": 200, "y": 0},
                "place:lock": {"x": 10, "y": 20},
                "place:lock@transition:acquire_a": {
                    "from": "transition:acquire_a",
                    "delta": {"x": -70, "y": 0},
                },
                "place:ready_a": {
                    "from": "place:lock@transition:acquire_a",
                    "delta": {"x": 5, "y": 0},
                },
            }
        ),
        "lanes",
    )
    # then: the copy entry wins, the other copy takes the place, and ready_a
    # sits on the copy's rendered point
    assert (
        model.copy_lines[("lock", "acquire_a")]
        != model.copy_lines[("lock", "release_a")]
    )
    assert 'pos="-70,0!"' in _node(dot, "lock@acquire_a")
    assert 'pos="10,20!"' in _node(dot, "lock@release_a")
    assert 'pos="-65,0!"' in _node(dot, "ready_a")
    assert f'pos="-{_coord(_gap("release_a", "lock", "permit"))},0!"' not in _node(
        dot, "lock@release_a"
    )


def test_a_shared_copy_uses_its_one_agreed_position() -> None:
    # given: hold and skip share one beside copy
    switch = Place("switch", ["job"], annotations={"fusion": True})
    net = _choice(
        [_read_switch("hold"), _read_switch("skip")], [switch], ["hold", "skip"]
    )
    decorations = Decorations(nodes={"place:switch": Decoration(beside=True)})
    model = net_render_model(net, decorations=decorations)
    # when: one agreed entry places the shared copy, and pending is relative to it
    dot = apply_view(
        model,
        _lanes(
            {
                "transition:hold": {"x": 0, "y": 0},
                "transition:skip": {"x": 300, "y": 0},
                "place:switch": {"x": 10, "y": 10},
                "place:switch@transition:hold": {"x": 40, "y": 80},
                "place:switch@transition:skip": {"x": 40, "y": 80},
                "place:pending": {
                    "from": "place:switch@transition:skip",
                    "delta": {"x": 0, "y": -10},
                },
            }
        ),
        "lanes",
    )
    # then: both transitions name the same line, and that line is the entry
    assert model.copy_lines[("switch", "hold")] == model.copy_lines[("switch", "skip")]
    assert 'pos="40,80!"' in _node(dot, "switch@hold+skip")
    assert 'pos="150,0!"' not in _node(dot, "switch@hold+skip")
    assert 'pos="40,70!"' in _node(dot, "pending")
    # and: two different points for that one copy are rejected
    try:
        apply_view(
            model,
            _lanes(
                {
                    "place:switch@transition:hold": {"x": 1, "y": 1},
                    "place:switch@transition:skip": {"x": 2, "y": 2},
                }
            ),
            "lanes",
        )
    except ViewApplicationError as error:
        assert "shared copy of place 'switch'" in str(error)
    else:
        raise AssertionError("disagreeing shared-copy positions were accepted")


def _six_lock() -> Net:
    # given: one fusion lock used by three workers, six drawn copies
    arcs: list[Arc] = []
    places = [Place("lock", ["permit"], annotations={"fusion": True})]
    transitions: list[Transition] = []
    for worker in ("a", "b", "c"):
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


def _six_positions() -> dict[str, object]:
    positions: dict[str, object] = {"place:lock": {"x": 9999, "y": 9999}}
    for index, worker in enumerate(("a", "b", "c")):
        origin = index * 640
        positions[f"transition:acquire_{worker}"] = {"x": origin, "y": 560}
        positions[f"transition:release_{worker}"] = {"x": origin, "y": 0}
        positions[f"place:lock@transition:acquire_{worker}"] = {
            "x": origin - 220,
            "y": 560,
        }
        positions[f"place:lock@transition:release_{worker}"] = {
            "x": origin - 220,
            "y": 0,
        }
        positions[f"place:held_{worker}"] = {"x": origin, "y": 280}
        positions[f"place:done_{worker}"] = {"x": origin, "y": -280}
        if worker == "a":
            positions["place:ready_a"] = {
                "from": "place:lock@transition:acquire_a",
                "delta": {"x": 0, "y": 280},
            }
        else:
            positions[f"place:ready_{worker}"] = {"x": origin, "y": 840}
    return positions


def six_lock_dot() -> str:
    """The pinned six-copy lock, the golden both renderers must match."""
    decorations = Decorations(
        nodes={"place:lock": Decoration(beside=True, beside_side="left")}
    )
    return apply_view(
        net_render_model(_six_lock(), decorations=decorations),
        _lanes(_six_positions()),
        "lanes",
    )


def _plain_layout(dot: str) -> tuple[float, dict[str, tuple[float, float]]]:
    binary = shutil.which("dot")
    assert binary is not None, "graphviz dot is required"
    completed = subprocess.run(
        [binary, "-Tplain"],
        input=dot,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    scale = 0.0
    nodes: dict[str, tuple[float, float]] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "graph":
            scale = float(parts[1])
        elif parts[0] == "node":
            # Plain output quotes a name that contains ``@``. The origin is
            # the layout's corner, so callers compare distances, not raw x, y.
            nodes[parts[1].strip('"')] = (float(parts[2]), float(parts[3]))
    return scale, nodes


def test_six_pinned_lock_copies_do_not_stack_or_scale() -> None:
    # given: three workers, six copies, each copy pinned on its own point
    dot = six_lock_dot()
    copies = [
        f"lock@{step}_{worker}"
        for worker in ("a", "b", "c")
        for step in ("acquire", "release")
    ]
    # when: the golden drawing is read, and neato lays it out
    golden = (
        Path(__file__).resolve().parents[2] / "fixtures" / "lease-lock-six-copies.dot"
    )
    placed = [_node(dot, name) for name in copies]
    points = []
    for line in placed:
        start = line.index('pos="') + 5
        points.append(line[start : line.index("!", start)])
    scale, plain = _plain_layout(dot)
    # then: the drawing matches the other renderer, no two copies share a point,
    # the whole-place point is unused, and overlap=scale does not shrink it
    assert dot == golden.read_text(encoding="utf-8")
    assert len(set(points)) == 6
    assert "9999,9999" not in dot
    assert 'pos="-220,840!"' in _node(dot, "ready_a")
    # overlap=scale leaves the pins. Plain coordinates are shifted to the
    # layout corner; the distances between copies stay the authored ones.
    assert scale == 1
    anchor = plain["lock@acquire_a"]
    shift = (anchor[0] - (-220 / 72), anchor[1] - (560 / 72))
    for worker_index, worker in enumerate(("a", "b", "c")):
        origin = worker_index * 640
        for name, point in (
            (f"lock@acquire_{worker}", (origin - 220, 560)),
            (f"lock@release_{worker}", (origin - 220, 0)),
        ):
            found = plain[name]
            assert abs(found[0] - (point[0] / 72 + shift[0])) < 0.02, (name, found)
            assert abs(found[1] - (point[1] / 72 + shift[1])) < 0.02, (name, found)
    ready = plain["ready_a"]
    copy = plain["lock@acquire_a"]
    assert abs((ready[1] - copy[1]) - (280 / 72)) < 0.02
