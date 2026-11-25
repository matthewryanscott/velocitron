"""The fusion-place position lint (ADR 0067)."""

from __future__ import annotations

from velocitron_analysis import (
    RULE_FUSION_PLACE_POSITION,
    RULE_PLACE_POSITION_OVERRIDDEN,
    RULE_SINGLE_COPY_POSITION,
    LintFinding,
    lint_net,
)
from velocitron_engine import (
    Arc,
    ConsumePattern,
    Net,
    Place,
    ProduceTemplate,
    Transition,
)


def _lock(*, fusion: bool = True, copies: int = 2) -> Net:
    places = [
        Place("ready", ["job"]),
        Place("held", ["job"]),
        Place(
            "lock",
            ["permit"],
            annotations={"fusion": True} if fusion else None,
        ),
    ]
    transitions = [Transition("acquire")]
    arcs = [
        Arc(
            from_place="ready",
            to_transition="acquire",
            consume=ConsumePattern("job", None, "consume"),
        ),
        Arc(
            from_place="lock",
            to_transition="acquire",
            consume=ConsumePattern("permit", None, "consume"),
        ),
        Arc(
            from_transition="acquire",
            to_place="held",
            produce=ProduceTemplate("job", "held"),
        ),
    ]
    if copies > 1:
        transitions.append(Transition("release"))
        arcs.append(
            Arc(
                from_place="held",
                to_transition="release",
                consume=ConsumePattern("job", None, "consume"),
            )
        )
        arcs.append(
            Arc(
                from_transition="release",
                to_place="lock",
                produce=ProduceTemplate("permit", "lock"),
            )
        )
        arcs.append(
            Arc(
                from_transition="release",
                to_place="ready",
                produce=ProduceTemplate("job", "ready"),
            )
        )
    return Net(name="lock", places=places, transitions=transitions, arcs=arcs)


def _with_view(net: Net, positions: dict[str, object], view: str = "lanes") -> Net:
    annotations = dict(net.annotations or {})
    payload = dict(annotations.get("petrinet.dsl/v1", {}))
    views = dict(payload.get("views", {}))
    views[view] = {"positions": positions, "routes": {}}
    payload["views"] = views
    annotations["petrinet.dsl/v1"] = payload
    return Net(
        name=net.name,
        places=net.places,
        transitions=net.transitions,
        arcs=net.arcs,
        annotations=annotations,
    )


def test_a_whole_place_position_on_several_copies_is_flagged() -> None:
    # given: two copies of a fusion lock, and a view that positions the place
    net = _with_view(_lock(), {"place:lock": {"x": 10, "y": 20}})

    # when: linting
    findings = lint_net(net)

    # then: the view and the place are named
    assert findings == [
        LintFinding(
            rule=RULE_FUSION_PLACE_POSITION,
            transition="",
            place="lock",
            view="lanes",
            message=(
                "view 'lanes' positions fusion place 'lock', which draws 2 "
                "copies; a whole-place position stacks every copy on one point"
            ),
        )
    ]


def test_one_copy_or_a_plain_place_is_clean() -> None:
    # given: a fusion lock one transition uses, and a plain place positioned
    one = _with_view(_lock(copies=1), {"place:lock": {"x": 0, "y": 0}})
    plain = _with_view(_lock(fusion=False), {"place:lock": {"x": 0, "y": 0}})

    # when/then: neither stacks copies
    assert lint_net(one) == []
    assert lint_net(plain) == []


def test_a_position_on_the_transition_is_clean() -> None:
    # given: the view pins a transition and not the fusion place
    net = _with_view(_lock(), {"transition:acquire": {"x": 0, "y": 0}})

    # when/then: nothing is flagged
    assert lint_net(net) == []


def test_the_place_can_silence_the_rule() -> None:
    # given: the place acknowledges the rule
    net = _lock()
    place = net.places[2]
    silenced = Net(
        name=net.name,
        places=[
            *net.places[:2],
            Place(
                place.name,
                place.accepts,
                annotations={
                    "fusion": True,
                    "lint": {"suppress": [RULE_FUSION_PLACE_POSITION]},
                },
            ),
        ],
        transitions=net.transitions,
        arcs=net.arcs,
    )

    # when/then: the finding is silent, and a malformed acknowledgement is not
    assert lint_net(_with_view(silenced, {"place:lock": {"x": 1, "y": 2}})) == []
    broken = Net(
        name=net.name,
        places=[
            *net.places[:2],
            Place(
                place.name,
                place.accepts,
                annotations={"fusion": True, "lint": "nope"},
            ),
        ],
        transitions=net.transitions,
        arcs=net.arcs,
    )
    assert [
        finding.rule
        for finding in lint_net(_with_view(broken, {"place:lock": {"x": 1, "y": 2}}))
    ] == [RULE_FUSION_PLACE_POSITION]


def test_beside_does_not_keep_a_whole_place_position_off_the_copies() -> None:
    # given: the lock is beside its transitions, and the view positions it
    net = _lock()
    shadowed = Net(
        name=net.name,
        places=net.places,
        transitions=net.transitions,
        arcs=net.arcs,
        annotations={
            "petrinet.dsl/v1": {
                "decorations": {"place:lock": {"beside": {"side": "left"}}},
                "views": {
                    "lanes": {
                        "positions": {"place:lock": {"x": 10, "y": 20}},
                        "routes": {},
                    }
                },
            }
        },
    )

    # when: linting
    findings = lint_net(shadowed)

    # then: the two copies still share the place point, so the stack is flagged
    assert [finding.rule for finding in findings] == [RULE_FUSION_PLACE_POSITION]
    assert findings[0].place == "lock"
    assert findings[0].view == "lanes"
    assert "stacks every copy" in findings[0].message


def test_a_shared_beside_copy_is_shadowed_rather_than_stacked() -> None:
    # given: two neighbor transitions share one beside copy, and the view
    # positions that place
    switch = Place("switch", ["job"], annotations={"fusion": True})
    net = Net(
        name="choice",
        places=[Place("pending", ["job"]), Place("done", ["job"]), switch],
        transitions=[Transition("hold"), Transition("skip")],
        arcs=[
            Arc(
                from_place="pending",
                to_transition=name,
                consume=ConsumePattern("job", None, "consume"),
            )
            for name in ("hold", "skip")
        ]
        + [
            Arc(
                from_transition=name,
                to_place="done",
                produce=ProduceTemplate("job", "done"),
            )
            for name in ("hold", "skip")
        ]
        + [
            Arc(
                from_place="switch",
                to_transition=name,
                consume=ConsumePattern("job", None, "read"),
            )
            for name in ("hold", "skip")
        ],
        annotations={
            "petrinet.dsl/v1": {
                "decorations": {"place:switch": {"beside": {}}},
                "views": {
                    "lanes": {
                        "positions": {"place:switch": {"x": 1, "y": 2}},
                        "routes": {},
                    }
                },
            }
        },
    )

    # when/then: one drawn copy takes the place point, so nothing stacks
    findings = lint_net(net)
    assert findings == []


def test_every_copy_position_overrides_the_place_entry() -> None:
    # given: a view that positions the place and each drawn copy
    net = _with_view(
        _lock(),
        {
            "place:lock": {"x": 0, "y": 0},
            "place:lock@transition:acquire": {"x": 10, "y": 0},
            "place:lock@transition:release": {"x": 20, "y": 0},
        },
    )

    # when/then: the place entry is flagged as overridden, not as a stack
    findings = lint_net(net)
    assert [finding.rule for finding in findings] == [RULE_PLACE_POSITION_OVERRIDDEN]
    assert findings[0].place == "lock"
    assert "overrides" in findings[0].message


def test_a_copy_position_on_a_place_drawn_once_is_warned() -> None:
    # given: the view draws the lock as one node and also positions a copy
    net = _with_view(
        _lock(),
        {
            "place:lock": {"x": 0, "y": 0},
            "place:lock@transition:acquire": {"x": 10, "y": 0},
        },
    )
    assert net.annotations is not None
    payload = net.annotations["petrinet.dsl/v1"]
    assert isinstance(payload, dict)
    payload["decorations"] = {"place:lock": {"single": True}}

    # when: linting
    findings = lint_net(net)

    # then: the copy fact does not apply, and the place is not a stack
    assert findings == [
        LintFinding(
            rule=RULE_SINGLE_COPY_POSITION,
            transition="",
            place="lock",
            view="lanes",
            message=(
                "view 'lanes' positions a copy of fusion place 'lock', which "
                "is drawn as one node; the copy position does not apply"
            ),
        )
    ]


def test_invalid_decorations_do_not_raise() -> None:
    # given: a positioned fusion place whose decoration payload is not a map
    net = _with_view(_lock(), {"place:lock": {"x": 0, "y": 0}})
    assert net.annotations is not None
    payload = net.annotations["petrinet.dsl/v1"]
    assert isinstance(payload, dict)
    payload["decorations"] = []

    # when/then: the lint fails open
    assert lint_net(net) == []
