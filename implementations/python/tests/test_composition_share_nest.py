"""Shared places, compositions used inside compositions, and ``velocitron equiv``
(spec/composition.md; ADR 0040, ADR 0041, ADR 0042).

The fixture is a small lock: ``take`` starts a job when the lock is free,
``give`` ends it and gives the lock back. ``take`` and ``give`` live in two
nets that share the lock. A third net, ``worker``, refines the abstract
``[work]`` of ``give``. The pair is also used as one constituent of an outer
composition, which must merge to the same net as the flat composition.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from velocitron_petrinet import merge_composition
from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import emit_petrinet
from velocitron_dsl import PetrinetDslError
from velocitron_petrinet import (
    NetValidationError,
    parse_composition,
)
from velocitron_analysis import (
    load,
    prove,
)
from velocitron_play import (
    parse_play,
)
from velocitron_play_check import (
    check_play,
)
from velocitron_viz import (
    composition_ports_dot,
    composition_to_dot,
    net_to_dot,
)

LOCK = Path(__file__).parent / "fixtures" / "lock"
_TAKE = (LOCK / "take.petrinet").read_text(encoding="utf-8")
_GIVE = (LOCK / "give.petrinet").read_text(encoding="utf-8")
_PAIR = (LOCK / "pair.petrinet").read_text(encoding="utf-8")
_NESTED = (LOCK / "nested.petrinet").read_text(encoding="utf-8")
_WORKER = (LOCK / "worker.petrinet").read_text(encoding="utf-8")


def _write(directory: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")


@pytest.fixture
def nets(tmp_path: Path) -> Path:
    for source in LOCK.iterdir():
        shutil.copy(source, tmp_path / source.name)
    return tmp_path


# ── share ────────────────────────────────────────────────────────────────


def test_share_fuses_places_that_are_not_ports(nets: Path) -> None:
    # when:
    net, composed = load(nets / "pair.petrinet")

    # then: one lock place, named after both members, taken and given back
    assert composed is not None
    names = {place.name for place in net.places}
    assert "give.lock__take.lock" in names
    assert "take.lock" not in names and "give.lock" not in names
    lock = next(p for p in net.places if p.name == "give.lock__take.lock")
    assert lock.port is None
    assert lock.annotations == {"fusion": True}


def test_a_shared_fusion_place_stays_open_for_the_prover(nets: Path) -> None:
    # given:
    net, composed = load(nets / "pair.petrinet")
    assert composed is not None

    # when:
    report = prove(net, composition=composed)

    # then: the environment supplies the lock, so take can fire
    assert "give.lock__take.lock" not in composed.fused()
    assert "take.busy" in composed.fused()
    assert "give.lock__take.lock" in report.model["roles"]["resources"]
    dead = [p for p in report.proofs if p.subject == "no dead transitions"]
    assert [p.status for p in dead] == ["proved"]


def test_a_shared_place_without_a_fusion_member_is_closed(nets: Path) -> None:
    # given: neither member of the lock says the environment supplies it
    _write(
        nets, {"take.petrinet": _TAKE.replace("(lock) annotation fusion true\n", "")}
    )
    _, composed = load(nets / "pair.petrinet")
    assert composed is not None

    # then: the lock is closed like a wired place
    assert "give.lock__take.lock" in composed.fused()


def test_a_share_compiles_to_json_and_back() -> None:
    # when:
    document = compile_petrinet_text(_PAIR)

    # then:
    assert document["shares"] == [
        {"places": [{"net": "take", "place": "lock"}, {"net": "give", "place": "lock"}]}
    ]
    assert "share take.(lock) ~ give.(lock)" in emit_petrinet(document)


@pytest.mark.parametrize(
    ("share", "message"),
    [
        (
            "share take.(lock) ~ give.(nothing)",
            "share take.(lock) ~ give.(nothing): net 'give' has no place named 'nothing'",
        ),
        (
            "share take.(lock) ~ give.(done)",
            "share take.(lock) ~ give.(done): give.(done) accepts job, but "
            "take.(lock) accepts key",
        ),
        (
            "share take.(lock) ~ take.(lock)",
            "share take.(lock) ~ take.(lock): a place is shared with itself",
        ),
    ],
)
def test_a_share_that_does_not_fit_is_a_pn202(
    nets: Path, share: str, message: str
) -> None:
    # given:
    source = _PAIR.replace("share take.(lock) ~ give.(lock)", share)

    # when:
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(
            source, "pair.petrinet", origin=nets, net_loader=_loader(nets)
        )

    # then: the diagnostic points at the share fact
    diagnostic = raised.value.diagnostic
    assert diagnostic.code == "PN202"
    assert diagnostic.message == message
    assert diagnostic.span.start.line == 5


def test_a_share_naming_an_unknown_alias_is_a_pn202() -> None:
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(_PAIR.replace("give.(lock)\n", "nobody.(lock)\n"))
    assert raised.value.diagnostic.code == "PN202"
    assert raised.value.diagnostic.message == "share references unknown alias nobody"


def test_a_play_composes_with_an_inline_share(nets: Path) -> None:
    # given:
    play = parse_play(
        """play lock "One job takes and gives back the lock"
use "take.petrinet" as take
use "give.petrinet" as give
wire take.(busy) -> give.(busy)
share take.(lock) ~ give.(lock)
marking none
inject (take.todo) <- job {"id": 1}
inject (take.lock) <- key {}
fire [take.take]
expect (give.lock) empty
fire [give.work]
fire [give.give]
expect (take.lock) == key {}
""",
        origin=nets,
    )

    # when:
    report = check_play(play)

    # then:
    assert [trace.failure for trace in report.traces] == [None]


# ── the merged net's name ───────────────────────────────────────────────


def test_a_merged_net_takes_the_composition_name(nets: Path) -> None:
    # given:
    net, composed = load(nets / "pair.petrinet")
    assert composed is not None

    # when:
    report = prove(net, composition=composed)

    # then: the report names the composition, not "composition"
    assert net.name == "pair"
    assert report.text().splitlines()[0].endswith("net pair")


def test_a_json_composition_without_a_name_merges_to_composition(nets: Path) -> None:
    # given: the pair as JSON, with no name
    document = compile_petrinet_text(_PAIR, "pair.petrinet")
    del document["name"]

    (nets / "pair.json").write_text(json.dumps(document), encoding="utf-8")

    # when:
    net, _ = load(nets / "pair.json")

    # then:
    assert net.name == "composition"


# ── compositions as constituents ─────────────────────────────────────────


def test_a_composition_used_inside_another_is_flattened(nets: Path) -> None:
    # when:
    composition = parse_composition(
        compile_petrinet_text(_NESTED), origin=nets, net_loader=_loader(nets)
    )

    # then: the pair's nets are known by a dotted alias, its facts carry over
    assert list(composition.parsed_nets or {}) == ["pair.take", "pair.give", "worker"]
    assert composition.sources == {
        "pair.take": "take.petrinet",
        "pair.give": "give.petrinet",
        "worker": "worker.petrinet",
    }
    assert [(s.members) for s in composition.shares] == [
        (("pair.take", "lock"), ("pair.give", "lock"))
    ]
    assert [(r.net, r.transition, r.by) for r in composition.refinements] == [
        ("pair.give", "work", "worker")
    ]
    merged = merge_composition(composition)
    assert "pair.give.work" not in {t.name for t in merged.transitions}
    assert {p.name for p in merged.places} >= {
        "pair.take.busy",
        "pair.give.lock__pair.take.lock",
        "pair.take.todo",
    }


def test_nested_references_resolve_from_the_nested_file(tmp_path: Path) -> None:
    # given: the pair and its nets live in a subdirectory
    sub = tmp_path / "pair"
    sub.mkdir()
    _write(
        sub, {"take.petrinet": _TAKE, "give.petrinet": _GIVE, "pair.petrinet": _PAIR}
    )
    _write(
        tmp_path,
        {
            "worker.petrinet": _WORKER,
            "nested.petrinet": _NESTED.replace(
                '"pair.petrinet"', '"pair/pair.petrinet"'
            ),
        },
    )

    # when:
    net, composed = load(tmp_path / "nested.petrinet")

    # then:
    assert composed is not None
    assert composed.files["pair.take"] == tmp_path / "pair" / "take.petrinet"
    assert "pair.take.take" in {t.name for t in net.transitions}


def test_the_nested_composition_proves_and_refines(nets: Path) -> None:
    # given:
    net, composed = load(nets / "nested.petrinet")

    # when:
    report = prove(net, composition=composed)

    # then:
    refinement = [p for p in report.proofs if p.fact == "refinement"]
    assert [(p.subject, p.status) for p in refinement] == [
        ("refinement pair.give.[work] by worker", "proved")
    ]
    assert report.status == "proved"


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "pair.(take.busy)",
            "pair.(take.nothing)",
            "wire references unknown port pair.(take.nothing)",
        ),
        (
            "pair.(take.busy)",
            "pair.(nobody.busy)",
            "wire references unknown port pair.(nobody.busy)",
        ),
        (
            "pair.[give.work]",
            "pair.[give.nothing]",
            "refine pair.give.[nothing] by worker: net pair.give has no transition "
            "[nothing]",
        ),
    ],
)
def test_a_wrong_path_into_a_nested_composition_is_a_pn202(
    nets: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(PetrinetDslError) as raised:
        compile_petrinet_text(
            _NESTED.replace(old, new),
            "nested.petrinet",
            origin=nets,
            net_loader=_loader(nets),
        )
    assert raised.value.diagnostic.code == "PN202"
    assert raised.value.diagnostic.message == message


def test_a_composition_that_uses_itself_is_rejected(nets: Path) -> None:
    # given:
    _write(nets, {"loop.petrinet": 'composition loop\nuse "loop.petrinet" as again\n'})

    # when:
    with pytest.raises(PetrinetDslError) as raised:
        load(nets / "loop.petrinet")

    # then:
    assert "composition reference cycle: loop.petrinet -> loop.petrinet" in (
        raised.value.diagnostic.message
    )


def test_a_nested_composition_needs_an_alias(nets: Path) -> None:
    document = {"nets": [{"ref": "pair.petrinet"}], "wires": []}
    with pytest.raises(NetValidationError, match="needs an explicit alias"):
        parse_composition(document, origin=nets, net_loader=_loader(nets))


def test_a_composition_cannot_refine_by_a_composition(nets: Path) -> None:
    document = {
        "nets": [
            {"ref": "worker.petrinet", "alias": "worker"},
            {"ref": "pair.petrinet", "alias": "pair"},
        ],
        "wires": [],
        "refinements": [{"net": "worker", "transition": "do", "by": "pair"}],
    }
    with pytest.raises(NetValidationError, match="a refining net must be a net"):
        parse_composition(document, origin=nets, net_loader=_loader(nets))


def test_a_play_names_places_by_their_full_dotted_path(nets: Path) -> None:
    # given:
    play = parse_play(
        """play nested "One job through the nested composition"
net "nested.petrinet"
marking none
inject (pair.take.todo) <- job {"id": 1}
inject (pair.take.lock) <- key {}
fire [pair.take.take]
fire [worker.do] -> (worker.end) job {"id": 1}
fire [pair.give.give]
expect (pair.give.done) == job {"id": 1}
expect (pair.give.lock) == key {}
""",
        origin=nets,
    )

    # when:
    report = check_play(play)

    # then:
    assert [trace.failure for trace in report.traces] == [None]


def test_the_render_draws_a_nested_cluster_and_share_lines(nets: Path) -> None:
    # given:
    composition = parse_composition(
        compile_petrinet_text(_NESTED), origin=nets, net_loader=_loader(nets)
    )

    # when:
    full = composition_to_dot(composition, style=_plain())
    ports = composition_ports_dot(composition, style=_plain())

    # then: the pair is a cluster around its nets; the lock line has no arrow
    for dot in (full, ports):
        assert 'label="pair"; labeljust=l;' in dot
        assert "dir=none" in dot
    assert '"pair.take.lock" -> "pair.give.lock" [' in ports
    assert '"pair.take.lock" [' in ports
    # and: in the full render take's lock is a fusion place, drawn only as its
    # copy at [take], so the line starts there and adds no node of its own
    assert '"pair.take.lock@take" -> "pair.give.lock" [' in full
    assert '"pair.take.lock@take" [' in full
    assert '"pair.take.lock" ' not in full


def test_the_merged_render_labels_each_lock_copy_by_its_own_nets_name(
    nets: Path,
) -> None:
    # given: the pair merged, its shared lock one place named after both members
    composition = parse_composition(
        compile_petrinet_text(_PAIR), origin=nets, net_loader=_loader(nets)
    )

    # when:
    dot = net_to_dot(merge_composition(composition), style=_plain())

    # then: each copy shows the member name its transition's net uses
    lines = dot.splitlines()
    take = next(line for line in lines if '"give.lock__take.lock@take.take" [' in line)
    give = next(line for line in lines if '"give.lock__take.lock@give.give" [' in line)
    assert 'label="take.lock\\n' in take
    assert 'label="give.lock\\n' in give
    assert 'label="give.lock__take.lock' not in dot


def _loader(directory: Path):
    def load_reference(ref: str):
        return compile_petrinet_text((directory / ref).read_text(encoding="utf-8"), ref)

    return load_reference


def _plain():
    from velocitron_viz import RenderStyle

    return RenderStyle(html_labels=False, tooltips=False)
