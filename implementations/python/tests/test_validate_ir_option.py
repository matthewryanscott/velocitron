"""The `validate_ir` compile option (issue 28).

`compile_petrinet_text`, `compile_petrinet_sources` and `load_play_net`
take keyword-only `validate_ir: bool = True`. `check_play` takes the same
kwarg and threads it to `load_play_net` (issue 55). With `False` the
Contribution IR schema check (ADR 0026's `_IR_VALIDATOR`) is skipped:
valid sources compile to the identical document, faster; an invalid
source fails later, at resolution or net-validation time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import resolve_contribution_ir
from velocitron_dsl import PetrinetDslError
from velocitron_play_check import (
    check_play,
    load_play_net,
)
from velocitron_play import parse_play

_REPO_ROOT = Path(__file__).parents[3]
_CORPUS_ROOT = _REPO_ROOT / "packages" / "spec" / "conformance" / "petrinet"
_HOLDS_ROOT = (
    _REPO_ROOT
    / "implementations"
    / "python"
    / "tests"
    / "fixtures"
    / "codegen"
    / "library_holds"
)


def _corpus_sources() -> list[tuple[str, str]]:
    """Every corpus case's committed canonical source, by relative stem."""
    sources: list[tuple[str, str]] = []
    for case_dir in sorted(_CORPUS_ROOT.iterdir()):
        if not case_dir.is_dir():
            continue
        for path in sorted(case_dir.glob("*.canonical.source.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            sources.append((path.name, document["text"]))
    return sources


def _library_holds_sources() -> list[tuple[str, str]]:
    """The library-holds composition and all its member nets."""
    sources: list[tuple[str, str]] = []
    for path in sorted(_HOLDS_ROOT.rglob("*.petrinet")):
        sources.append(
            (path.relative_to(_HOLDS_ROOT).as_posix(), path.read_text(encoding="utf-8"))
        )
    return sources


@pytest.mark.parametrize(
    ("name", "text"),
    list(_corpus_sources()),
)
def test_corpus_nets_compile_identically_without_the_schema_check(
    name: str, text: str
) -> None:
    # when: the same canonical source compiles with and without the check
    with_check = compile_petrinet_text(text, name, validate_ir=True)
    without_check = compile_petrinet_text(text, name, validate_ir=False)

    # then: valid nets compile to the identical document both ways
    assert json.dumps(with_check, sort_keys=True) == json.dumps(
        without_check, sort_keys=True
    )


@pytest.mark.parametrize(
    ("name", "text"),
    list(_library_holds_sources()),
)
def test_library_holds_nets_compile_identically_without_the_schema_check(
    name: str, text: str
) -> None:
    # when: each library-holds net (including the library-holds composition
    # and its nested members, which load their own refs) compiles both ways
    with_check = compile_petrinet_text(text, name, validate_ir=True)
    without_check = compile_petrinet_text(text, name, validate_ir=False)

    # then: the documents are identical
    assert json.dumps(with_check, sort_keys=True) == json.dumps(
        without_check, sort_keys=True
    )


def test_invalid_ir_still_fails_loudly_with_the_check_off() -> None:
    # given: a source whose IR the schema rejects (a CEL fact on a color
    # target, which the grammar still lowers into a typed contribution)
    text = 'net wrong\n\n(p) -> [t]\n[t] -> (q)\n\n@t unknown-fact cel "1 == 1"\n'
    with pytest.raises(PetrinetDslError):
        compile_petrinet_text(text, "wrong.petrinet", validate_ir=True)

    # when: the check is off, resolution's own structural checks still run
    # and the source fails loudly — the check was an early diagnostic, not
    # the only gate
    with pytest.raises(PetrinetDslError):
        compile_petrinet_text(text, "wrong.petrinet", validate_ir=False)


def test_resolve_contribution_ir_takes_the_kwarg_directly() -> None:
    # given: one lowered corpus document
    name, text = _corpus_sources()[0]
    ir = lower_petrinet_text(text, name)

    # when / then: the seam itself skips the schema consult and agrees
    assert resolve_contribution_ir(ir, validate_ir=True) == resolve_contribution_ir(
        ir, validate_ir=False
    )


def test_load_play_net_threads_the_kwarg() -> None:
    # given: the conformance play conformance case's net and play
    case = _REPO_ROOT / "packages" / "spec" / "conformance" / "play" / "01-symbolic-firing"
    play = parse_play(
        (case / "case.play").read_text(encoding="utf-8"),
        source=str(case / "case.play"),
        origin=case,
    )

    # when: the net loads with and without the schema check
    with_check = load_play_net(play, validate_ir=True)
    without_check = load_play_net(play, validate_ir=False)

    # then: the same net resolves, in the same merged shape
    assert with_check.net == without_check.net
    assert with_check.composed == without_check.composed


def test_check_play_threads_the_kwarg() -> None:
    # given: the conformance play conformance case's net and play
    case = _REPO_ROOT / "packages" / "spec" / "conformance" / "play" / "01-symbolic-firing"
    play = parse_play(
        (case / "case.play").read_text(encoding="utf-8"),
        source=str(case / "case.play"),
        origin=case,
    )

    # when: the play checks with and without the schema check
    # then: both run (the case is valid either way); and the kwarg is
    # accepted at the check seam, threaded to `load_play_net`
    check_play(play, validate_ir=True)
    check_play(play, validate_ir=False)