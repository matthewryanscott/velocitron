"""The prover's fast path: the kernel explores a net from the tables the
reference fills, and its graph is the reference's, edge for edge. It
explores on every core for an ordinary run and on one core for the check,
and the two modes find the same graph. It checks soundness on its own
graph and walks each case of a choice, with the reference's answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from velocitron_analysis import (
    NetModel,
    ProofSettings,
    load,
    prove,
    read_settings,
    tables,
)
from velocitron_analysis.choice import EngineCases, choice_proofs
from velocitron_analysis.fast import (
    FastPathError,
    KernelCases,
    KernelExplorer,
    first_difference,
    run_kernel,
)
from velocitron_analysis.firing import Firing
from velocitron_analysis.soundness import Environment, Explorer
from velocitron_analysis.tables import fill
from velocitron_cli import main as cli_main

ROOT = Path(__file__).resolve().parents[3]
NETS = ROOT / "benchmarks" / "prover" / "nets"


_STOPPED = [
    "workshop",
]
_ENDED = [
    "mutex",
    "readers",
    "retry",
    "catalog",
    "lanes",
    "philosophers",
    "desk/desk",
    "health/health",
]


def _setup(name: str | Path) -> tuple[Any, NetModel, Environment]:
    """A benchmark net (by name) or a fixture net with no domains file (by
    path), its model and its environment, set up as prove does."""
    if isinstance(name, Path):
        net, composition = load(name)
        settings = ProofSettings()
    else:
        net, composition = load(NETS / f"{name}.petrinet")
        settings = read_settings(NETS / f"{name}.domains.json5")
    declared = net.proofs
    model = NetModel(
        net,
        overrides=settings.domains,
        instance_color=settings.instance_color,
        final=settings.final
        if settings.final is not None
        else (declared.final if declared is not None else None),
        other_keys=settings.other_keys,
        closed=composition.fused() if composition is not None else (),
    )
    model.kept_marking()
    environment = Environment(
        settings.injections, settings.updates, settings.firings, settings.starts
    )
    return net, model, environment


def _explorer(
    name: str | Path, max_states: int, kind: type[Explorer] = Explorer
) -> Explorer:
    """A fresh explorer of a benchmark or fixture net, set up as prove does."""
    net, model, environment = _setup(name)
    return kind(
        net,
        model,
        Firing(net, model),
        environment=environment,
        max_states=max_states,
    )


@pytest.mark.parametrize("name", _STOPPED)
def test_a_run_stopped_at_the_state_cap_matches_the_reference_edge_for_edge(
    name: str,
) -> None:
    # given: the same net explored by the reference and by the kernel, both
    #   stopped at a state cap of 20 000
    reference = _explorer(name, 20_000)
    reference.explore()

    # when: the kernel explores it, the reference filling each row on first use
    fast = run_kernel(fill(_explorer(name, 20_000)))

    # then: every marking, count, flag, edge, move and parent is the same
    assert reference.capped and fast.capped
    assert first_difference(reference, fast) is None


@pytest.mark.parametrize("name", _STOPPED)
def test_the_kernel_checks_a_stopped_run_as_the_reference_does(name: str) -> None:
    # given: the same net explored by the reference, stopped at 20 000
    reference = _explorer(name, 20_000)
    reference.explore()

    # when: the kernel explores it and checks its own graph
    fast = _explorer(name, 20_000, KernelExplorer)
    fast.explore()

    # then: the same sizes, soundness proofs (findings, paths and markings
    #   included) and what made the markings
    assert fast.size() == reference.size()
    assert fast.check() == reference.check()
    assert fast.made_by() == reference.made_by()


@pytest.mark.parametrize("name", _ENDED)
def test_a_run_that_ends_matches_the_reference_and_proves_the_same(
    name: str,
) -> None:
    # given: a small benchmark net that the reference explores to its end
    reference = _explorer(name, 50_000)
    reference.explore()

    # when: the kernel explores it, rebuilt for the comparison and checked
    #   on its own graph
    rebuilt = run_kernel(fill(_explorer(name, 50_000)))
    fast = _explorer(name, 50_000, KernelExplorer)
    fast.explore()

    # then: the graphs are the same, and so are the soundness proofs
    assert not rebuilt.capped
    assert first_difference(reference, rebuilt) is None
    assert fast.check() == reference.check()


def _graph_facts(explorer: KernelExplorer) -> tuple[object, ...]:
    """Everything the kernel's graph holds, ids and order included."""
    graph = explorer.graph
    return (
        graph.states,
        graph.edges,
        graph.capped,
        graph.markings,
        graph.marking_offsets,
        graph.used_of,
        graph.used,
        graph.flags,
        graph.parent,
        graph.edge_offsets,
        graph.edge_moves,
        graph.edge_targets,
        graph.edge_kinds,
        graph.moves,
        graph.stopped,
        graph.withheld,
        graph.deposit_errors,
        graph.held_moves,
    )


def _kernel_run(name: str, max_states: int, *, one_core: bool) -> KernelExplorer:
    explorer = _explorer(name, max_states, KernelExplorer)
    assert isinstance(explorer, KernelExplorer)
    explorer.one_core = one_core
    explorer.explore()
    return explorer


@pytest.mark.parametrize(
    ("name", "max_states"),
    [(name, 50_000) for name in _ENDED]
    + [(name, 20_000) for name in _STOPPED],
)
def test_every_core_finds_the_graph_one_core_finds_on_every_run(
    name: str, max_states: int
) -> None:
    # given: the net explored on one core, in the reference's order
    one = _kernel_run(name, max_states, one_core=True)

    # when: every core explores it, three times over
    runs = [_kernel_run(name, max_states, one_core=False) for _ in range(3)]

    # then: each run holds the same markings, edges, moves, parents, flags
    #   and numbering, whatever the threads did, and so proves the same
    for every in runs:
        assert _graph_facts(every) == _graph_facts(one)
        assert every.size() == one.size()
        assert every.check() == one.check()


def test_a_row_only_markings_past_the_state_cap_need_never_fails_an_every_core_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given: how many fire rows one core asks for up to a state cap of
    #   2 000, and a reference that fails the next one it is asked for
    asked: list[object] = []
    fire = tables.Rows.fire

    def counted(self: tables.Rows, *args: Any) -> Any:
        asked.append(args)
        return fire(self, *args)

    monkeypatch.setattr(tables.Rows, "fire", counted)
    one = _kernel_run("workshop", 2_000, one_core=True)
    rows_needed = len(asked)

    def fails_past(self: tables.Rows, *args: Any) -> Any:
        if len(asked) >= rows_needed:
            raise RuntimeError("a row past the state cap")
        return counted(self, *args)

    monkeypatch.setattr(tables.Rows, "fire", fails_past)
    asked.clear()
    with pytest.raises(FastPathError):
        _kernel_run("workshop", 4_000, one_core=True)
    assert len(asked) == rows_needed, "the premise: a later marking needs a row"

    # when: every core explores to the first cap
    asked.clear()
    every = _kernel_run("workshop", 2_000, one_core=False)

    # then: it asked for the rows one core asked for, and none past the cap
    assert len(asked) == rows_needed
    assert _graph_facts(every) == _graph_facts(one)


@pytest.mark.parametrize("one_core", [True, False], ids=["one core", "every core"])
def test_a_row_the_reference_cannot_fill_fails_either_mode_and_names_the_reference_flag(
    monkeypatch: pytest.MonkeyPatch, one_core: bool
) -> None:
    # given: a reference that fails to fill a fire row
    def fails(*_: object) -> None:
        raise RuntimeError("no handler output")

    monkeypatch.setattr(tables.Rows, "fire", fails)

    # when / then: the run fails with that error and the flag that runs the
    #   reference
    with pytest.raises(FastPathError) as failure:
        _kernel_run("mutex", 50_000, one_core=one_core)
    assert "could not fill a fire row" in str(failure.value)
    assert "no handler output" in str(failure.value)
    assert "--reference" in str(failure.value)


@pytest.mark.parametrize("name", _STOPPED + _ENDED)
def test_the_kernel_finds_the_cases_of_each_choice_the_engine_finds(
    name: str,
) -> None:
    # given: a benchmark net and its choices
    net, model, environment = _setup(name)
    firing = Firing(net, model)

    # when: each case is asked of the engine, and of the kernel over the
    #   tables of the cases' tokens
    engine = choice_proofs(net, model, EngineCases(firing))
    notes: list[str] = []
    kernel = choice_proofs(
        net, model, KernelCases(net, model, firing, environment, notes.append)
    )

    # then: the same proofs, findings and witnesses included
    assert notes == []
    assert kernel == engine


def test_a_choice_with_more_tokens_than_the_kernel_numbers_is_asked_of_the_engine() -> (
    None
):
    # given: a net whose choices' cases meet more tokens than its run's
    #   first tokens, the limit
    net, model, environment = _setup("lanes")
    firing = Firing(net, model)
    first = len(fill(_explorer("lanes", 0)).tokens)
    notes: list[str] = []
    cases = KernelCases(net, model, firing, environment, notes.append, limit=first)

    # when:
    found = choice_proofs(net, model, cases)

    # then: the engine answered each choice, and the caller was told of
    #   each, once
    assert found == choice_proofs(net, model, EngineCases(firing))
    assert notes
    assert len(notes) == len(set(notes)), notes
    assert all(
        note.startswith("the choice at (")
        and note.endswith(f"more than {first} tokens")
        for note in notes
    ), notes


def test_a_row_the_reference_cannot_fill_for_a_choice_fails_and_names_the_reference_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # given: a net whose choice cases need correlate rows, which the
    #   reference fails to fill
    net, model, environment = _setup("readers")
    cases = KernelCases(net, model, Firing(net, model), environment, None)

    def fails(*_: object) -> None:
        raise RuntimeError("no correlate")

    monkeypatch.setattr(tables.Rows, "corr", fails)

    # when / then: the choice fails with that error and the flag that runs
    #   the reference
    with pytest.raises(FastPathError) as failure:
        choice_proofs(net, model, cases)
    assert "could not fill a correlate row" in str(failure.value)
    assert "no correlate" in str(failure.value)
    assert "--reference" in str(failure.value)


def test_a_marking_the_kernel_does_not_hold_fails_and_names_the_reference_flag() -> (
    None
):
    # given: a kernel graph of a net that ended
    explorer = _explorer("mutex", 50_000, KernelExplorer)
    explorer.explore()
    markings, _ = explorer.size()

    # when / then: asking for a marking past its last fails the run, as a
    #   kernel failure while the checks run does
    with pytest.raises(FastPathError) as failure:
        explorer.marking(markings)
    assert f"the graph has no state {markings}" in str(failure.value)
    assert "--reference" in str(failure.value)


@pytest.mark.parametrize("mode", [["--fast"], ["--fast", "--one-core"]], ids=" ".join)
def test_prove_on_the_fast_path_reports_what_the_reference_reports(
    capsys: pytest.CaptureFixture[str], mode: list[str]
) -> None:
    # given: a net with a clock and a timer, proved by the CLI on each path,
    #   the fast path on every core or on one
    net = str(NETS / "retry.petrinet")
    domains = str(NETS / "retry.domains.json5")
    common = ["prove", net, "--domains", domains, "--fact", "soundness", "--json"]

    # when:
    cli_main([*common, "--max-states", "3000"])
    reference = json.loads(capsys.readouterr().out)
    cli_main([*common, "--max-states", "3000", *mode])
    fast = json.loads(capsys.readouterr().out)

    # then: the same report, counts and every proof's answer
    assert fast == reference


def test_one_core_without_the_fast_path_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given: the one-core mode asked for without the kernel it is a mode of
    net = str(NETS / "mutex.petrinet")

    # when:
    code = cli_main(["prove", net, "--one-core"])

    # then: the command refuses it and says why
    assert code == 2
    assert "--one-core needs --fast" in capsys.readouterr().err


_SPIN = """\
net spin "a job that never finishes"
(start) -job-> [spin] -job-> (start)
(held) -job-> [finish] -job-> (done)
(start) port input job
final (done)
"""


def test_the_kernel_finds_a_loop_of_one_move_as_the_reference_does(
    tmp_path: Path,
) -> None:
    # given: a net whose one move leads back to the marking it left
    path = tmp_path / "spin.petrinet"
    path.write_text(_SPIN, encoding="utf-8")
    net, composition = load(path)

    # when:
    notes: list[str] = []
    fast = prove(net, composition=composition, fast=True, on_reference=notes.append)
    reference = prove(net, composition=composition)

    # then: both refute it with the same livelock, its loop the one move
    assert notes == []
    (option,) = [p for p in fast.proofs if p.subject == "option to complete"]
    (finding,) = option.findings
    assert (option.status, finding.kind) == ("refuted", "livelock")
    assert [m.transition for m in finding.cycle] == ["spin"]
    assert fast.json() == reference.json()


def test_a_place_with_more_than_sixty_four_tokens_is_walked_on_the_fast_path() -> None:
    # given: a fixture net in which a place holds 65 tokens before 2 000
    #   markings
    path = ROOT / "implementations/python/tests/fixtures/play/evening-shift.petrinet"
    net, composition = load(path)
    crowded = _explorer(path, 2_000)
    crowded.explore()
    assert max(len(toks) for s in crowded.states for toks in s.marking.values()) > 64

    # when:
    notes: list[str] = []
    fast = prove(
        net,
        max_states=2_000,
        composition=composition,
        fast=True,
        on_reference=notes.append,
    )
    reference = prove(net, max_states=2_000, composition=composition)

    # then: the kernel walked the crowded place's bindings, as the
    #   reference did
    assert notes == []
    assert fast.json() == reference.json()


_PAIR = """\
net pair "two jobs go out together"
@two: (ready) -job-> [pair]
[pair] -job-> (done)
@two weight 2
(ready) port input job
final (done)
"""


def test_a_net_the_tables_cannot_carry_is_proved_by_the_reference_with_a_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a net with an arc of weight 2, which the tables do not carry
    path = tmp_path / "pair.petrinet"
    path.write_text(_PAIR, encoding="utf-8")
    net, composition = load(path)

    # when:
    notes: list[str] = []
    fast = prove(
        net,
        composition=composition,
        fast=True,
        on_reference=notes.append,
    )
    reference = prove(net, composition=composition)

    # then: the reference proved every fact, and the caller was told why,
    #   once
    assert notes == ["[pair] has an arc of weight 2"]
    assert fast.json() == reference.json()
