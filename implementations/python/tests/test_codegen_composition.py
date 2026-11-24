"""The composition-codegen card's 9 test groups (card `Mywzh5HN`).

Golden and `--check` for the four compositions; the wired_pulse and
reading_hour runs through the generated classes reach their
integration tests' final markings; `HashMismatch` on a merged net;
`hold_lifecycle`'s docstring share listing, the kept-facts warning
planted on a fixture copy, and 20 transitions wired; `library_holds`'
refinement (no method, the Protocol and the mixin, the basedpyright
"bad subclass" case at the constructor call); shared refs fail
generation naming both; nesting registers the flattened alias prefixes
and Engine.validate resolves every ref; and --async on wired_pulse
emits HandlerSpecs and runs under the Runtime.

References: ADR 0058 (Decisions 2 and 4).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from velocitron_cli import codegen as codegen_cli
from velocitron_codegen import (
    CompositionCodegenError,
    RefinedAway,
    generate_composition,
)
from velocitron_codegen.generator import (
    CodegenError,
    GeneratedModule,
)
from velocitron_petrinet import merge_composition
from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import lower_petrinet_text
from velocitron_runtime import Engine
from velocitron_journal import JsonlJournal
from velocitron_netbase import (
    HashMismatch,
    Registration,
    net_document,
    net_sha256,
)
from velocitron_petrinet import parse_composition
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
    Net,
    Token,
)

_PYTHON_ROOT = pathlib.Path(__file__).parents[1]
_REPO_ROOT = _PYTHON_ROOT.parents[1]
_FIXTURES = _PYTHON_ROOT / "tests" / "fixtures" / "codegen"
_HOLDS = _FIXTURES / "library_holds"
_GOLDEN = _FIXTURES / "golden"
_NETS = _GOLDEN / "velocitron_nets"
# Omitted from the default project scan; the golden checks put them back.
_PLANTED_PYRIGHT_FIXTURES = {
    "tests/fixtures/codegen/golden/bad_library_holds_composition_subclass.py",
    "tests/fixtures/codegen/golden/velocitron_nets/bad_subclass.py",
}

_ACTOR = "circulation desk"

_LADDER_ROOT = _REPO_ROOT / "examples" / "capability-ladder"

_COMPOSITIONS: dict[str, Path] = {
    "wired_pulse": _LADDER_ROOT / "10-wired-pulse/wired_pulse.petrinet",
    "reading_hour": _LADDER_ROOT
    / "12-reading-hour-fragment/reading_hour.petrinet",
    "hold_lifecycle": _HOLDS / "hold-lifecycle.petrinet",
    "library_holds": _HOLDS / "library-holds.petrinet",
}


def _argv(argv: list[str]) -> Any:
    from velocitron_cli import build_parser

    return build_parser().parse_args(argv)


def _generate(
    stem: str,
    /,
    *,
    actor: str | None = None,
    is_async: bool = False,
    members_package: str | None = "velocitron_nets",
) -> dict[str, str]:
    """Run the composition generator on a fixture, exactly as the
    maintainer script does."""
    fixture = _COMPOSITIONS[stem]
    return generate_composition(
        str(fixture), actor=actor, is_async=is_async, members_package=members_package
    )


def _merged(stem: str, *, workdir: pathlib.Path | None = None) -> Net:
    """The composition's merged Net, through the parser + merge."""
    fixture = _COMPOSITIONS[stem]
    text = fixture.read_text(encoding="utf-8")
    document = compile_petrinet_text(text, fixture.name)
    base = fixture.parent

    def load(ref: str) -> Any:
        member_path = base / ref
        return compile_petrinet_text(
            member_path.read_text(encoding="utf-8"), member_path.name
        )

    composition = parse_composition(document, origin=base, net_loader=load)
    return merge_composition(composition)


def _import_generated(
    name: str,
    *,
    extra_sys_path: list[pathlib.Path] | None = None,
) -> Any:
    """A generated composition golden as a real importable module.

    The goldens' member imports (`from velocitron_nets.x import ...`)
    resolve because `velocitron_nets/` is a real package inside the
    checked directory; an inner composition's module (hold_lifecycle)
    lives IN `velocitron_nets/` and imports its members the same way.
    """
    # Every composition golden lives in the members package.
    base = _NETS
    sys.path.insert(0, str(_GOLDEN))
    module_id = f"{name}_codegen_composition_test"
    spec = importlib.util.spec_from_file_location(
        module_id, str(base / f"{name}.py")
    )
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    if extra_sys_path:
        for path in extra_sys_path:
            sys.path.insert(0, str(path))
    try:
        loader = spec.loader
        assert loader is not None
        loader.exec_module(loaded)
        sys.modules[module_id] = loaded
    finally:
        sys.path.remove(str(_GOLDEN))
        for path in extra_sys_path or []:
            sys.path.remove(str(path))
    return loaded


# ── 1. goldens are byte-stable, and --check runs in the suite ───────────


def test_goldens_match_their_fixture() -> None:
    # given: the four composition fixtures and their golden modules —
    # every composition module INSIDE the members package (a composition
    # module is a member module to whatever imports it)
    for stem in _COMPOSITIONS:
        # when: regenerated exactly as the maintainer script does
        texts = _generate(
            stem,
            actor=(
                _ACTOR
                if stem in ("hold_lifecycle", "library_holds")
                else None
            ),
        )
        # then: the OUTER module is byte-equal with its golden
        golden = _NETS / f"{stem}.py"
        assert texts[stem] == golden.read_text(encoding="utf-8"), stem


def test_nested_golden_matches_too() -> None:
    # given: library_holds generates its lifecycle member's module too
    texts = _generate("library_holds", actor=_ACTOR)
    # when / then: the nested lifecycle module is byte-equal with the
    # standalone lifecycle golden (one module per composition FILE: the
    # same bytes whether generated through library_holds or standalone)
    assert texts["hold_lifecycle"] == (_NETS / "hold_lifecycle.py").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("stem", sorted(_COMPOSITIONS))
def test_check_passes_on_fresh_goldens(
    stem: str, tmp_path: pathlib.Path
) -> None:
    # given: a copy of the composition and its members in tmp (every
    # module's bytes regenerate beside their files; the composition
    # module compared against its golden)
    fixture = _COMPOSITIONS[stem]
    work = tmp_path / stem
    for source in sorted((fixture.parent).rglob("*.petrinet")):
        target = work / source.relative_to(fixture.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
    composition_file = work / fixture.name
    base = ["codegen", str(composition_file)]
    if stem in ("hold_lifecycle", "library_holds"):
        base += ["--actor", _ACTOR]

    # when: generated once beside the copies...
    args = _argv([*base, "--out", str(work / f"{stem}_net.py")])
    assert codegen_cli.main(args) == 0, stem
    # ...then --check (with --out only naming the composition module)
    args = _argv([*base, "--out", str(work / f"{stem}_net.py"), "--check"])
    result = codegen_cli.main(args)
    # then: the same bytes — exit 0 (the members' `--check`s ran too)
    assert result == 0, stem


# ── 2. wired_pulse through the generated classes: the final marking ────


def test_wired_pulse_run_reaches_its_play_final_marking() -> None:
    # given: the generated composition module (imported like a user's)
    members = _import_generated("wired_pulse")
    base = _COMPOSITIONS["wired_pulse"].parent

    seen_seed_params: list[list[Any]] = []
    seen_pulse_params: list[list[Any]] = []

    class MySource(members.PulseSourceNet):
        def fire_emit(self, seed: list[Token]) -> dict[str, list[Token]]:
            seen_seed_params.append([t.data for t in seed])
            return {"pulse_out": [Token("pulse", dict(seed[0].data))]}

    class MySink(members.PulseSinkNet):
        def fire_receive(self, pulse_in: list[Token]) -> dict[str, list[Token]]:
            seen_pulse_params.append([t.data for t in pulse_in])
            return {
                "received": [
                    Token("receipt", {**token.data, "received": True})
                    for token in pulse_in
                ]
            }

    composition = members.WiredPulseComposition(source=MySource(), sink=MySink())
    registration = composition.build_registry(_merged("wired_pulse"))

    play = cast(
        dict[str, Any],
        json.loads((base / "wired_pulse.test.json").read_text(encoding="utf-8")),
    )["cases"][0]
    marking = Marking(
        {
            place: [Token(t["type"], t["data"]) for t in tokens]
            for place, tokens in play["initialMarking"].items()
        }
    )

    # when: the Engine runs the registered copy
    engine = Engine(registration.registry)
    final = engine.advance(registration.net, marking, max_steps=play["maxSteps"])

    # then: the final marking matches the BDD case's expectation exactly
    plain = {
        place: [{"type": t.type, "data": t.data} for t in tokens]
        for place, tokens in final.items()
        if tokens
    }
    assert plain == play["expectedFinalMarking"]
    # and: both handler methods ran with their LOCAL parameter names
    # (`seed` in the source's signature, `pulse_in` in the sink's —
    # the adapter translates the merged keys through binding_names;
    # exactly one firing each, carrying the play's seed data through)
    expected_seed_data = [t["data"] for t in play["initialMarking"]["source.seed"]]
    assert seen_seed_params == [expected_seed_data], seen_seed_params
    assert seen_pulse_params == [expected_seed_data], seen_pulse_params


# ── 3. reading_hour: the three-member run reaches the marking ─────


def _reading_hour_members_module() -> Any:
    """The fixture handlers (`register_all`) loaded from the ladder."""
    path = _COMPOSITIONS["reading_hour"].parent / "handlers.py"
    spec = importlib.util.spec_from_file_location("reading_hour_handlers", path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _reading_hour_registry(net: Net) -> HandlerRegistry:
    registry = HandlerRegistry()
    members = _reading_hour_members_module()
    members.register_all(registry)
    return registry


def _reading_hour_marking_and_injection() -> tuple[Any, Any]:
    play = cast(
        dict[str, Any],
        json.loads(
            (_COMPOSITIONS["reading_hour"].parent / "reading_hour.test.json").read_text(
                encoding="utf-8"
            )
        ),
    )["cases"][0]
    return play["initialMarking"], play["injections"][0]


def test_reading_hour_run_reaches_its_play_final_marking() -> None:
    # given: the generated composition module over the three members
    members_mod = _import_generated("reading_hour")

    class MyCadence(members_mod.ReadingCadenceNet):
        def fire_on_tick(
            self, tick_latch: list[Token], clock: list[Token]
        ) -> dict[str, list[Token]]:
            latch = dict(tick_latch[0].data)
            now = clock[0].data["now"]
            return {
                "tick_latch": [
                    Token("tick_latch", {**latch, "fired_at": now})
                ],
                "refresh_due_out": [
                    Token("refresh_due", {"trigger": "tick"})
                ],
            }

    class MyCurate(members_mod.ReadingPickNet):
        def fire_curate(
            self, refresh_due_in: list[Token]
        ) -> dict[str, list[Token]]:
            return {
                "speak_request": [
                    Token("speak_req", dict(refresh_due_in[0].data))
                ]
            }

    class MySpeaks(members_mod.ReadingVoiceNet):
        def fire_start(self, request_in: list[Token]) -> dict[str, list[Token]]:
            data = dict(request_in[0].data)
            return {
                "in_flight": [Token("speak_token", dict(data))],
                "work": [Token("speak_work", dict(data))],
            }

        def fire_finish(
            self, work: list[Token], in_flight: list[Token]
        ) -> dict[str, list[Token]]:
            # the recorded run's finish handler carries the request's
            # data through (the fixture's handler binds it, not mine)
            data = dict(work[0].data)
            return {"utterance_out": [Token("utterance", dict(data))]}

    composition = members_mod.ReadingHourComposition(
        cadence=MyCadence(),
        curate=MyCurate(),
        speaks=MySpeaks(),
    )
    merged = _merged("reading_hour")
    registration = composition.build_registry(merged)

    initial_marking, injection = _reading_hour_marking_and_injection()
    marking = Marking(
        {
            place: [Token(t["type"], t["data"]) for t in tokens]
            for place, tokens in initial_marking.items()
        }
    )

    # when: the injection replays, then the Engine runs to quiescence
    engine = Engine(registration.registry)
    marking, _ = engine.inject_token(
        registration.net,
        marking,
        injection["place"],
        Token(injection["token"]["type"], injection["token"]["data"]),
        attempt=injection["attempt"],
        replace=injection["replace"],
    )
    play_expected = json.loads(
        (_COMPOSITIONS["reading_hour"].parent / "reading_hour.test.json").read_text(
            encoding="utf-8"
        )
    )["cases"][0]["expectedFinalMarking"]
    final = engine.advance(registration.net, marking)

    # then: the same final marking the integration test pins
    plain = {
        place: [{"type": t.type, "data": t.data} for t in tokens]
        for place, tokens in final.items()
        if tokens
    }
    assert plain == play_expected


# ── 4. the hash gate ───────────────────────────────────────────────────


def test_check_fails_when_a_member_module_is_stale(
    tmp_path: pathlib.Path,
) -> None:
    # given: a copy of the wired_pulse fixtures whose member module on
    # disk and golden both went STALE against one changed leaf — a
    # one-character edit of `pulse_sink.petrinet` (the leaf module's own
    # generated text changes and the composition's MEMBER_SHA256 moves)
    work = tmp_path / "stale_member"
    work.mkdir()
    for source in sorted(_COMPOSITIONS["wired_pulse"].parent.glob("*.petrinet")):
        shutil.copy(source, work / source.name)
    composition_file = work / "wired_pulse.petrinet"
    sink_file = work / "pulse_sink.petrinet"
    sink_file.write_text(
        sink_file.read_text(encoding="utf-8").replace(
            "net pulse_sink", "net pulse_sink_edited"
        ),
        encoding="utf-8",
    )

    # when: `codegen --check` compares the modules' regenerated text
    # with what is on disk (the composition module's out is only the
    # composition's; each member's own file is checked beside itself)
    args = _argv(
        [
            "codegen",
            str(composition_file),
            "--out",
            str(work / "wired_pulse_net.py"),
            "--check",
        ]
    )
    result = codegen_cli.main(args)
    # then: the stale member's diff fails --check with a unified diff
    # naming the member's own file
    assert result == 1
    args_regenerate = _argv(
        [
            "codegen",
            str(composition_file),
        ]
    )
    assert codegen_cli.main(args_regenerate) == 0


def test_hash_mismatch_at_build_registry(tmp_path: pathlib.Path) -> None:
    # given: the generated composition class and the real merged net
    members = _import_generated("wired_pulse")

    class MySource(members.PulseSourceNet):
        def fire_emit(self, seed: list[Token]) -> dict[str, list[Token]]:
            return {"pulse_out": [Token("pulse", dict(seed[0].data))]}

    class MySink(members.PulseSinkNet):
        def fire_receive(self, pulse_in: list[Token]) -> dict[str, list[Token]]:
            return {"received": [Token("receipt", {**t.data, "received": True}) for t in pulse_in]}

    composition = members.WiredPulseComposition(source=MySource(), sink=MySink())
    net = _merged("wired_pulse")

    # when: the merged net is EDITED after the module was generated (one
    # place renamed — the module's SOURCE_SHA256 no longer matches)
    document = json.loads(
        json.dumps(net_document(net))
    )  # a mutable copy of the canonical document
    # Rename the place and every reference to it (a real, consistent net
    # edit whose hash moves): arc endpoints, the marking key, and every
    # bindingNames value that resolves to it.
    old = document["places"][0]["name"]
    new = f"{old}_edited"
    document["places"][0]["name"] = new
    text = json.dumps(document)
    text = text.replace(f'"{old}"', f'"{new}"')
    document = json.loads(text)
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(document, handle)
        edited_path = handle.name
    edited_net = _parse_net_document(edited_path)

    # then: HashMismatch at build_registry, no registration
    with pytest.raises(HashMismatch):
        composition.build_registry(edited_net)


def _parse_net_document(path: str) -> Net:
    from velocitron_petrinet import parse_net as _parse_net

    with open(path) as handle:
        return _parse_net(json.load(handle))


# ── 5. hold_lifecycle: docstring, warning, 20 transitions ────────────


def test_hold_lifecycle_docstring_share_listing() -> None:
    # given: the generated hold_lifecycle module's text
    texts = _generate("hold_lifecycle", actor=_ACTOR)
    text = texts["hold_lifecycle"]

    # then: the three-member share is listed ONCE, with the one merged
    # name (this level's own spelling; the library_holds golden prefixes it)
    merged_name = "checkout.shelf_slot__notice.shelf_slot__shelf.shelf_slot"
    assert text.count("shelf_slot") >= 3
    share_lines = [
        line
        for line in text.splitlines()
        if "share " in line and "shelf_slot" in line
    ]
    assert len(share_lines) == 1, share_lines
    assert share_lines[0].count(" ~ ") == 2
    assert f"fused: {merged_name}" in share_lines[0]
    # and: the library_holds golden's docstring carries the prefixed name
    outer = (_NETS / "library_holds.py").read_text(encoding="utf-8")
    prefixed = (
        "lifecycle.checkout.shelf_slot__"
        "lifecycle.notice.shelf_slot__"
        "lifecycle.shelf.shelf_slot"
    )
    assert f"fused: {prefixed}" in outer


def test_hold_lifecycle_twenty_transitions_resolved(
    tmp_path: pathlib.Path,
) -> None:
    # given: the hold_lifecycle composition registered through the
    # generated classes (actor filter on; the patron's clear_wait is
    # another actor's — it registers NotThisActor)
    _ = tmp_path
    members = _import_generated("hold_lifecycle")
    sys.path.insert(0, str(_GOLDEN))
    try:
        import velocitron_nets.checkout as checkout_mod
        import velocitron_nets.edition as edition_mod
        import velocitron_nets.notice as notice_mod
        import velocitron_nets.request as request_mod
        import velocitron_nets.shelf as shelf_mod
    finally:
        sys.path.remove(str(_GOLDEN))
    composition = members.HoldLifecycleComposition(
        request=_RequestStub(request_mod.HoldRequestNet)(),
        shelf=shelf_mod.HoldShelfNet(),
        checkout=_CheckoutStub(checkout_mod.LoanCheckoutNet)(),
        notice=notice_mod.OverdueNoticeNet(),
        edition=edition_mod.NewerEditionNet(),
    )
    merged = _merged("hold_lifecycle")
    assert len(merged.transitions) == 20

    registration = composition.build_registry(merged)
    net = registration.net

    names = {t.name for t in net.transitions}
    assert names == {
        "request.file_hold",
        "request.reopen",
        "request.decline",
        "shelf.lend",
        "shelf.recall",
        "shelf.wait_return",
        "shelf.clear_wait",
        "shelf.return_arrived",
        "checkout.borrow",
        "checkout.stamp_due",
        "checkout.notify",
        "checkout.refuse_damage",
        "checkout.cancel_edition",
        "checkout.record_other",
        "notice.remind",
        "notice.fine",
        "edition.cancel_queued",
        "edition.cancel_recalled",
        "edition.cancel_due",
        "edition.keep_checkout",
    }
    engine = Engine(registration.registry)
    record = engine.fire(
        net,
        Marking({"shelf.waiting_return": [Token("hold", {"isbn": "978"})]}),
        "shelf.clear_wait",
        attempt=0,
    )[1]
    assert record["status"] == "failed"  # NotThisActor


def _RequestStub(base: type) -> type:  # noqa: N802
    class Stub(base):  # type: ignore[valid-type,misc]
        def fire_file_hold(self, wishes: list[Token]) -> dict[str, list[Token]]:
            return {"queued": []}

        def fire_reopen(self, reorder: list[Token]) -> dict[str, list[Token]]:
            return {"queued": []}

    return Stub


def _CheckoutStub(base: type) -> type:  # noqa: N802
    class Stub(base):  # type: ignore[valid-type,misc]
        def fire_borrow(self, lending: list[Token]) -> dict[str, list[Token]]:
            return {"loan_ended": []}

        def fire_stamp_due(self, loan_ended: list[Token]) -> dict[str, list[Token]]:
            return {"loaned": [], "stamped": [], "shelf_slot": []}

        def fire_notify(self, loan_ended: list[Token]) -> dict[str, list[Token]]:
            return {"due": [], "shelf_slot": []}

    return Stub


def test_hold_lifecycle_warning_on_differing_kept_facts(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # given: a fixture copy where the shelf's kept start differs from the
    # checkout's and the notice's
    copy = tmp_path / "library_holds"
    shutil.copytree(_HOLDS, copy, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
    shelf_file = copy / "desk/shelf.petrinet"
    shelf_text = shelf_file.read_text(encoding="utf-8")
    shelf_file.write_text(
        shelf_text.replace(
            "starts as cel \"{'isbn': instance.isbn, 'free': true}\"",
            "starts as cel \"{'isbn': instance.isbn, 'free': false}\"",
        )
    )
    composition_file = copy / "hold-lifecycle.petrinet"

    # when: generated; the generator warns on stderr
    texts = generate_composition(str(composition_file), actor=_ACTOR)
    stderr_text = capsys.readouterr().err

    # then: the warning names the share and the differing field
    assert "disagree on start" in stderr_text, stderr_text
    assert texts["hold_lifecycle"]


# ── 6. library_holds refinement: no method; Protocol + mixin; pyright


def test_library_holds_no_refined_method_and_protocol_lists() -> None:
    # given: the generated library_holds module's text
    texts = _generate("library_holds", actor=_ACTOR)
    text = texts["library_holds"]

    # then: no method for checkout.borrow on the Protocol
    protocol_name = "LoanCheckoutWithoutBorrow"
    assert protocol_name in text
    protocol_block = text.split(f"class {protocol_name}(Protocol):")[1].split(
        "\nclass "
    )[0]
    assert "def fire_stamp_due" in protocol_block
    assert "def fire_notify" in protocol_block
    assert "def fire_borrow" not in protocol_block
    assert "# 42 merged transitions," in text
    assert "class RefinedBorrow:" in text
    mixin_block = text.split("class RefinedBorrow:")[1].split("\n\n\nclass ")[0]
    assert "raise RefinedAway(" in mixin_block


def test_library_holds_bad_subclass_fails_basedpyright_at_the_constructor(
    tmp_path: Path,
) -> None:
    # given: the repository's own basedpyright (pytest.skip when absent)
    from shutil import which

    executable = which("basedpyright") or str(_PYTHON_ROOT / ".venv" / "bin" / "basedpyright")
    if not Path(executable).is_file():
        pytest.skip("basedpyright is not available")
    good = _GOLDEN / "good_library_holds_subclass.py"
    bad = _GOLDEN / "bad_library_holds_composition_subclass.py"
    for fixture in (good, bad):
        assert fixture.is_file(), fixture
    result = subprocess.run(
        [
            executable,
            "--project",
            str(_pyright_config_including_planted_fixtures(tmp_path)),
            str(good),
            str(bad),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    assert "library_holds" in output

    good_lines = [
        line
        for line in output.splitlines()
        if "good_library_holds" in line and " - error" in line
    ]
    bad_line = next(
        line
        for line in output.splitlines()
        if "bad_library_holds" in line and " - error" in line
    )
    assert good_lines == [], good_lines
    assert "reportAbstractUsage" in output
    assert bad_line is not None


def _pyright_config_including_planted_fixtures(tmp_path: Path) -> Path:
    """Project rules, with the planted negative fixtures analyzable.

    Those files are excluded from ``basedpyright --project pyrightconfig.json``
    because they exist to fail ``reportAbstractUsage``. This copy drops only
    those entries. It lives outside the package, so the venv and environment
    roots are absolute paths back to the package.
    """
    cfg = json.loads((_PYTHON_ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))
    for key in ("exclude", "ignore"):
        entries = cfg.get(key)
        if isinstance(entries, list):
            cfg[key] = [item for item in entries if item not in _PLANTED_PYRIGHT_FIXTURES]
    cfg["venvPath"] = str(_PYTHON_ROOT)
    cfg["extraPaths"] = [str(_PYTHON_ROOT / "src")]
    environments = cfg.get("executionEnvironments")
    if isinstance(environments, list):
        for env in environments:
            if isinstance(env, dict):
                env["extraPaths"] = [str(_PYTHON_ROOT / "src")]
                root = env.get("root")
                if isinstance(root, str):
                    env["root"] = str(_PYTHON_ROOT / root)
    path = tmp_path / "pyrightconfig.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


# ── 7. shared refs across members fail generation naming both ─────────


def test_shared_ref_across_members_fails_naming_both(tmp_path: pathlib.Path) -> None:
    # given: two members whose transitions name the same handler ref
    dir_ = tmp_path / "shared"
    dir_.mkdir()
    (dir_ / "a.petrinet").write_text(
        'net a "a"\n(x) -> [one] -y-> (x_out)\n[one] handler "one@x"\n',
        encoding="utf-8",
    )
    (dir_ / "b.petrinet").write_text(
        'net b "b"\n(z) -> [two] -y-> (z_out)\n[two] handler "one@x"\n',
        encoding="utf-8",
    )
    file_ = dir_ / "comp.petrinet"
    file_.write_text(
        'composition comp\nuse "a.petrinet" as a\nuse "b.petrinet" as b\n',
        encoding="utf-8",
    )

    # when: generation runs the shared-ref collection (one ref, two
    # members' transitions)
    with pytest.raises(CompositionCodegenError) as exc:
        generate_composition(str(file_))
    message = "\n".join(exc.value.messages)
    # then: BOTH qualified transitions are named
    assert "[a.one]" in message, message
    assert "[b.two]" in message, message


# ── 8. nesting: the inner module registers the flattened aliases ───────


def test_nesting_registers_flattened_alias_prefixes() -> None:
    # given: the library_holds composition registered through the nested
    # lifecycle class; concrete leaves are used as generated
    sys.path.insert(0, str(_GOLDEN))
    try:
        import velocitron_nets.checkout as checkout_mod
        import velocitron_nets.edition as edition_mod
        import velocitron_nets.notice as notice_mod
        import velocitron_nets.partner_loan as loan_mod
        import velocitron_nets.request as request_mod
        import velocitron_nets.shelf as shelf_mod
        import velocitron_nets.union_catalog as catalog_mod
    finally:
        sys.path.remove(str(_GOLDEN))
    members = _import_generated("library_holds")

    class MyRequest(request_mod.HoldRequestNet):
        def fire_file_hold(self, wishes: list[Token]) -> dict[str, list[Token]]:
            return {"queued": []}

        def fire_reopen(self, reorder: list[Token]) -> dict[str, list[Token]]:
            return {"queued": []}

    class MyCheckout(members.RefinedBorrow, checkout_mod.LoanCheckoutNet):
        def fire_stamp_due(self, loan_ended: list[Token]) -> dict[str, list[Token]]:
            return {"loaned": [], "stamped": [], "shelf_slot": []}

        def fire_notify(self, loan_ended: list[Token]) -> dict[str, list[Token]]:
            return {"due": []}

    class MyLoan(loan_mod.PartnerLoanNet):
        def fire_request_quote(self, offered: list[Token]) -> dict[str, list[Token]]:
            return {"quote_result": [Token("hold", {**offered[0].data, "accepted": True})]}

        def fire_fill_form(self, priced: list[Token]) -> dict[str, list[Token]]:
            return {"cleared": [Token("hold", dict(priced[0].data))]}

        def fire_pack(self, cleared: list[Token], cleared_flag: list[Token], crates: list[Token]) -> dict[str, list[Token]]:
            return {"pack_result": [Token("hold", {**cleared[0].data, "packed": True})]}

        def fire_dispatch(self, boxed: list[Token], lanes: list[Token]) -> dict[str, list[Token]]:
            return {"dispatch_result": [Token("hold", {**boxed[0].data, "dispatched": True})]}

        def fire_receive(self, in_transit: list[Token]) -> dict[str, list[Token]]:
            return {
                "loan_ended": [Token("result", {"outcome": "loaned", "hold": dict(in_transit[0].data)})],
                "union_notice": [Token("notice", {"isbn": "978"})],
            }

    class MyCatalog(catalog_mod.UnionCatalogNet):
        def fire_poll_catalog(self, watching: list[Token], clock: list[Token]) -> dict[str, list[Token]]:
            return {"polled": [Token("watch", {"isbn": "978", "status": "shelved", "branch": "annex"})]}

    composition = members.LibraryHoldsComposition(
        lifecycle=members.HoldLifecycleComposition(
            request=MyRequest(),
            shelf=shelf_mod.HoldShelfNet(),
            checkout=MyCheckout(),
            notice=notice_mod.OverdueNoticeNet(),
            edition=edition_mod.NewerEditionNet(),
        ),
        loan=MyLoan(),
        catalog=MyCatalog(),
    )
    merged = _merged("library_holds")
    assert len(merged.transitions) == 42

    registration = composition.build_registry(merged)
    net = registration.net
    names = {t.name for t in net.transitions}
    assert "lifecycle.request.file_hold" in names
    assert "checkout.borrow" not in names
    Engine(registration.registry).validate(net)


# ── 9. --async wired_pulse: HandlerSpecs + a Runtime run ───────────────


def test_async_wired_pulse_specs_and_runtime_run() -> None:
    # given: the async generated composition under ITS OWN module package
    # name (a distinct one: the suite's earlier imports cached a
    # `velocitron_nets` whose pulse_source is the SYNC golden)
    async_dir = _PYTHON_ROOT / ".pytest_cache" / "async_wired_pulse"
    async_dir.mkdir(parents=True, exist_ok=True)
    (async_dir / "velocitron_nets_async").mkdir(exist_ok=True)
    (async_dir / "velocitron_nets_async/__init__.py").touch()
    members_texts = generate_composition(
        str(_COMPOSITIONS["wired_pulse"]), is_async=True, members_package="velocitron_nets_async"
    )
    from velocitron_codegen.generator import generate_module
    from velocitron_petrinet import parse_net

    base = _COMPOSITIONS["wired_pulse"].parent
    for name in ("pulse_source", "pulse_sink"):
        text = (base / f"{name}.petrinet").read_text(encoding="utf-8")
        low = lower_petrinet_text(text, f"{name}.petrinet")
        net = parse_net(compile_petrinet_text(text, f"{name}.petrinet"))
        module = generate_module(
            net,
            source=f"{name}.petrinet",
            source_name=f"{name}.petrinet",
            text=text,
            contributions=low["contributions"],
            is_async=True,
        )
        (async_dir / "velocitron_nets_async" / f"{name}.py").write_text(module.text)
    (async_dir / "wired_pulse.py").write_text(members_texts["wired_pulse"])

    sys.path.insert(0, str(async_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "wired_pulse_async", str(async_dir / "wired_pulse.py")
        )
        assert spec is not None and spec.loader is not None
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)

        class MySource(loaded.PulseSourceNet):
            async def fire_emit(self, seed: list[Token], *, context: Any) -> dict[str, list[Token]]:
                return {"pulse_out": [Token("pulse", dict(seed[0].data))]}

        class MySink(loaded.PulseSinkNet):
            async def fire_receive(self, pulse_in: list[Token], *, context: Any) -> dict[str, list[Token]]:
                return {"received": [Token("receipt", {**t.data, "received": True}) for t in pulse_in]}

        composition = loaded.WiredPulseComposition(
            source=MySource(), sink=MySink()
        )
        registration = composition.build_registry(
            _merged("wired_pulse"), default_lane="default"
        )

        # then: one HandlerSpec per member ref, on the default lane
        specs = registration.handler_specs
        assert set(specs) == {"emit@source", "receive@sink"}
        assert all(spec.lane == "default" for spec in specs.values())

        # and: a Runtime runs the pulse to the same final receipt
        from velocitron_journal import JsonlJournal
        from velocitron_runtime import Runtime, TokenArrival

        async def play() -> None:
            journal = JsonlJournal()
            runtime = Runtime(
                net=registration.net,
                handlers=dict(specs),
                lanes={"default": 2},
                journal=journal,
                marking=Marking({"source.seed": []}),  # a falsy-but-non-None marking: the inject drives
            )
            await runtime.start()
            await runtime.inject(
                TokenArrival("source.seed", Token("seed", {"n": 1}))
            )
            await runtime.wait_idle()
            marking_now = runtime.marking
            await runtime.stop()
            plain_now = {
                place: [{"type": t.type, "data": t.data} for t in tokens]
                for place, tokens in marking_now.items()
                if tokens
            }
            assert plain_now == {
                "sink.received": [
                    {"type": "receipt", "data": {"n": 1, "received": True}}
                ]
            }, plain_now

        asyncio.run(play())
    finally:
        sys.path.remove(str(async_dir))


# ── the RefinedAway contract ───────────────────────────────────────────


def test_refined_away_raises_from_the_mixin_path() -> None:
    # given: the library_holds module's RefinedBorrow mixin, and the
    # checkout leaf's golden
    spec = importlib.util.spec_from_file_location(
        "library_holds_golden", str(_NETS / "library_holds.py")
    )
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_GOLDEN))
    try:
        spec.loader.exec_module(loaded)
    finally:
        sys.path.remove(str(_GOLDEN))
    sys.path.insert(0, str(_GOLDEN))
    try:
        import velocitron_nets.checkout as checkout_mod
    finally:
        sys.path.remove(str(_GOLDEN))

    class MyCheckout(loaded.RefinedBorrow, checkout_mod.LoanCheckoutNet):
        def fire_stamp_due(self, loan_ended: list[Token]) -> dict[str, list[Token]]:
            return {"loaned": [], "stamped": [], "shelf_slot": []}

        def fire_notify(self, loan_ended: list[Token]) -> dict[str, list[Token]]:
            return {"due": []}

    instance = MyCheckout()

    with pytest.raises(RefinedAway):
        instance.fire_borrow([Token("hold", {"isbn": "978"})])
    assert isinstance(instance, checkout_mod.LoanCheckoutNet)
    assert type(instance).__mro__[1] is loaded.RefinedBorrow


# ── the replay card's emitted Replay<Net> (checklist item 2) ───────────


def test_emitted_replay_class_replays_a_recorded_run() -> None:
    # given: the emitted ReplayReadingVoiceNet (the golden), and a
    # recorded run of reading_voice whose live handlers succeed
    sys.path.insert(0, str(_GOLDEN))
    try:
        import velocitron_nets.reading_voice as speaks_mod
    finally:
        sys.path.remove(str(_GOLDEN))
    replay_cls = speaks_mod.ReplayReadingVoiceNet
    live_base = speaks_mod.ReadingVoiceNet

    class _Live(live_base):
        def fire_start(self, request_in: list[Token]) -> dict[str, list[Token]]:
            data = dict(request_in[0].data)
            return {
                "in_flight": [Token("speak_token", dict(data))],
                "work": [Token("speak_work", dict(data))],
            }

        def fire_finish(
            self, work: list[Token], in_flight: list[Token]
        ) -> dict[str, list[Token]]:
            return {"utterance_out": [Token("utterance", dict(work[0].data))]}

    from velocitron_analysis import load_net

    speaker_net = load_net(
        _REPO_ROOT
        / "examples/capability-ladder/12-reading-hour-fragment/reading_voice.petrinet"
    )
    recording = JsonlJournal()
    registration = _Live().register_into(HandlerRegistry(), speaker_net, journal=recording)
    recorded_marking = Engine(registration.registry, journal=recording).advance(
        registration.net,
        Marking({"request_in": [Token("speak_req", {"request": 1})]}),
    )

    # when: registered again through the EMITTED replay class, and replayed
    from velocitron_replay import ReplayCursor, replay_run

    cursor = ReplayCursor.from_journal(recording)
    replay = replay_cls(cursor, mode="strict")
    replay_registration = replay.register_into(HandlerRegistry(), speaker_net)
    result = replay_run(
        speaker_net,
        replay,
        replay_registration,
        cursor,
        mode="strict",
        marking=Marking({"request_in": [Token("speak_req", {"request": 1})]}),
    )
    plain = lambda m: {  # noqa: E731
        place: [(t.type, dict(t.data)) for t in tokens]
        for place, tokens in m.items()
        if tokens
    }
    # then: the same final marking (no stub call would have raised)
    assert plain(result.final_marking) == plain(recorded_marking)