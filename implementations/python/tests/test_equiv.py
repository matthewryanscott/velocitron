"""``velocitron equiv``: two nets are the same net up to renaming (ADR 0042).

The fixtures in fixtures/lock hold one lock three ways: a single net, a flat
composition of its pieces, and a composition that uses another composition.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from velocitron_cli import main as velocitron_main
from velocitron_equiv import compare
from velocitron_analysis import load

LOCK = Path(__file__).parent / "fixtures" / "lock"
_SINGLE = (LOCK / "single.petrinet").read_text(encoding="utf-8")
_TAKE = (LOCK / "take.petrinet").read_text(encoding="utf-8")


@pytest.fixture
def lock_nets(tmp_path: Path) -> Path:
    for source in LOCK.iterdir():
        shutil.copy(source, tmp_path / source.name)
    return tmp_path


def _write(directory: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")


def test_the_nested_and_flat_compositions_are_equivalent(lock_nets: Path) -> None:
    # given:
    nested, nested_composed = load(lock_nets / "nested.petrinet")
    flat, flat_composed = load(lock_nets / "flat.petrinet")

    # when:
    result = compare(flat, nested, flat_composed, nested_composed)

    # then:
    assert result.differences == ()
    assert ("(take.busy)", "(pair.take.busy)") in result.renaming


def test_a_composition_is_equivalent_to_the_single_net(lock_nets: Path) -> None:
    # given:
    single, _ = load(lock_nets / "single.petrinet")
    flat, flat_composed = load(lock_nets / "flat.petrinet")

    # when:
    result = compare(single, flat, None, flat_composed)

    # then: same behavior; the ports of the pieces are interface facts only
    assert result.equivalent
    assert ("(lock)", "(give.lock__take.lock)") in result.renaming
    assert "(done): no port in the first net, output port job in the second" in (
        result.interface
    )


def test_a_changed_predicate_is_a_difference(lock_nets: Path) -> None:
    # given:
    _write(
        lock_nets, {"changed.petrinet": _SINGLE + '@lock_in predicate cel "id == 1"\n'}
    )
    single, _ = load(lock_nets / "single.petrinet")
    changed, _ = load(lock_nets / "changed.petrinet")

    # when:
    result = compare(single, changed)

    # then:
    assert result.differences == (
        "arc (lock) -key-> [take]: predicate none in the first net, `id == 1` in "
        "the second",
    )


def test_a_wired_lock_is_not_the_same_as_a_supplied_one(lock_nets: Path) -> None:
    # given: the lock is closed when no member says the environment supplies it
    _write(
        lock_nets,
        {
            "take.petrinet": _TAKE.replace("(lock) annotation fusion true\n", ""),
        },
    )
    single, _ = load(lock_nets / "single.petrinet")
    flat, flat_composed = load(lock_nets / "flat.petrinet")

    # when:
    result = compare(single, flat, None, flat_composed)

    # then:
    assert result.differences == (
        "place (lock) supplied by the environment: yes in the first net, no in "
        "the second",
    )


def test_the_equiv_command_exits_by_the_result(
    lock_nets: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # when:
    same = velocitron_main(
        ["equiv", str(lock_nets / "flat.petrinet"), str(lock_nets / "nested.petrinet")]
    )
    same_out = capsys.readouterr().out
    _write(
        lock_nets,
        {
            "changed.petrinet": _SINGLE.replace(
                "[take] -job-> (busy)", "[take] -job-> (done)"
            )
        },
    )
    different = velocitron_main(
        [
            "equiv",
            "--json",
            str(lock_nets / "single.petrinet"),
            str(lock_nets / "changed.petrinet"),
        ]
    )
    different_out = json.loads(capsys.readouterr().out)
    missing = velocitron_main(
        ["equiv", str(lock_nets / "none.petrinet"), str(lock_nets / "flat.petrinet")]
    )

    # then:
    assert same == 0
    assert same_out.startswith("equivalent up to renaming:")
    assert different == 1
    assert different_out["equivalent"] is False
    assert (
        "arc [take] -job-> (busy) is only in the first net"
        in different_out["differences"]
    )
    assert missing == 2
