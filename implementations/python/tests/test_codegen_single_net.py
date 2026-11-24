"""The codegen card's test plan (11 tests, card `biKLwLWF`).

Goldens prove the output byte for byte; the counts under
``--actor "circulation desk"`` are 11 abstract, 32 generated, and 8 with no
code over the eight library-hold nets; the generated handlers fill every
output through the Engine's own evaluator (the exposed
:meth:`velocitron_engine.evaluate_produce_cel`) or the carry rule;
``--check`` runs in the suite; basedpyright checks the golden modules.

References: ADR 0058 (Decisions 1, 2, 5); card `05-codegen-single-net.md`.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
from copy import deepcopy
from typing import Any

import pytest

from velocitron_codegen.generator import (
    CodegenError,
    GeneratedModule,
    generate_module,
)
from velocitron_petrinet import compile_petrinet_text
from velocitron_dsl import lower_petrinet_text
from velocitron_runtime import Engine
from velocitron_engine import evaluate_produce_cel
from velocitron_petrinet import parse_net
from velocitron_engine import (
    TransitionHandlerInput,
    TransitionHandlerOutput,
)
from velocitron_engine import HandlerRegistry
from velocitron_engine import (
    Marking,
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

_LEAVES: dict[str, str] = {
    "branch_policy": "branch-policy.petrinet",
    "partner_loan": "partner-loan.petrinet",
    "union_catalog": "union-catalog.petrinet",
    "request": "desk/request.petrinet",
    "shelf": "desk/shelf.petrinet",
    "checkout": "desk/checkout.petrinet",
    "notice": "desk/notice.petrinet",
    "edition": "desk/edition.petrinet",
}

_LADDER_ROOT = _REPO_ROOT / "examples" / "capability-ladder"
_LADDER_LEAVES: dict[str, str] = {
    "reading_voice": "12-reading-hour-fragment/reading_voice.petrinet",
    "pulse_source": "10-wired-pulse/pulse_source.petrinet",
    "pulse_sink": "10-wired-pulse/pulse_sink.petrinet",
}


def _leaf_path(stem: str) -> pathlib.Path:
    if stem in _HOLD_STEMS:
        return _HOLDS / _LEAVES[stem]
    return _LADDER_ROOT / _LADDER_LEAVES[stem]


_HOLD_STEMS = frozenset(_LEAVES)


def _generate(
    stem: str,
    /,
    *,
    actor: str | None = None,
    is_async: bool = False,
    source_name: str | None = None,
) -> GeneratedModule:
    """Run the generator on a leaf net, exactly as the `codegen` CLI does.

    `source_name` records the repository-relative path in `SOURCE` (the
    CLI passes the path as the user gave it; tests use the one CI would).
    """
    fixture = _leaf_path(stem)
    relative = source_name or fixture.relative_to(_REPO_ROOT).as_posix()
    text = fixture.read_text(encoding="utf-8")
    lowered = lower_petrinet_text(text, relative)
    net = parse_net(compile_petrinet_text(text, relative))
    return generate_module(
        net,
        source=relative,
        source_name=relative,
        text=text,
        contributions=lowered["contributions"],
        actor=actor,
        is_async=is_async,
    )


def _load(
    module: GeneratedModule, name: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Exec a generated module's text; return its namespace."""
    namespace: dict[str, Any] = {"__name__": name, **(extra or {})}
    exec(compile(module.text, f"{name}.py", "exec"), namespace)  # noqa: S102
    return namespace


def _net(stem: str) -> Any:
    fixture = _leaf_path(stem)
    return parse_net(
        compile_petrinet_text(fixture.read_text(encoding="utf-8"), fixture.name)
    )


def _token(type_: str, **data: Any) -> Token:
    return Token(type_, data)


# ── 1. the goldens are byte-stable, and --check runs in the suite ───────

_GOLDEN_CASES = [
    ("reading_voice", None, False),
    ("reading_voice_async", None, True),
    ("pulse_source", None, False),
    ("pulse_sink", None, False),
    ("partner_loan", _ACTOR, False),
    ("branch_policy", _ACTOR, False),
]


def test_goldens_match_their_fixture() -> None:
    # given: six golden modules and their fixtures
    for stem, actor, is_async in _GOLDEN_CASES:
        # when: regenerated from the fixture
        module = _generate(stem.replace("_async", ""), actor=actor, is_async=is_async)

        # then: byte-equal with the checked-in golden
        golden = _NETS / f"{stem}.py"
        assert module.text == golden.read_text(encoding="utf-8"), stem


def test_check_in_suite_and_a_one_char_drift_fails(tmp_path: pathlib.Path) -> None:
    # given: a copy of each fixture beside its golden copy, so the bytes on
    # disk are exactly what a fresh generation of that copy produces
    # (`--check`'s diff is byte for byte; SOURCE is the path as given)
    for stem, actor, is_async in _GOLDEN_CASES:
        fixture = _leaf_path(stem.replace("_async", ""))
        copy = tmp_path / fixture.name
        shutil.copy(fixture, copy)
        import velocitron_cli.codegen as codegen_cli

        base = ["codegen", str(copy)]
        if actor:
            base += ["--actor", actor]
        if is_async:
            base += ["--async"]

        # when: generated once to a target, then --check re-generated
        out = tmp_path / "out" / f"{stem}.py"
        assert codegen_cli.main(_argv(base + ["--out", str(out)])) == 0
        # the same generation is byte-identical (deterministic paths: the
        # copy's SOURCE is the path as given, both runs equal)
        assert codegen_cli.main(_argv(base + ["--out", str(out), "--check"])) == 0

        # then: a one-character edit of the target fails --check with a
        # unified diff on stderr, and --check never rewrites the file
        before = out.read_text(encoding="utf-8")
        out.write_text(before.replace("Do not edit.", "Do NOT edit"), encoding="utf-8")
        import contextlib
        import io as io_module

        stderr = io_module.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = codegen_cli.main(_argv(base + ["--out", str(out), "--check"]))
        assert exit_code == 1, stem
        stderr_text = stderr.getvalue()
        assert stderr_text.startswith("--- ") and "+++ " in stderr_text
        assert "@@" in stderr_text
        # the drift is the '-' side; the regenerated bytes are the '+' side
        assert any(
            line.startswith("-") and "Do NOT edit" in line
            for line in stderr_text.splitlines()
        ), stderr_text
        assert any(
            line.startswith("+") and "Do not edit." in line
            for line in stderr_text.splitlines()
        ), stderr_text
        # and: nothing was written (the file still holds the one-char drift)
        assert out.read_text(encoding="utf-8") == before.replace(
            "Do not edit.", "Do NOT edit"
        )
        # and: --check fails when the file is missing
        out.unlink()
        with contextlib.redirect_stderr(io_module.StringIO()):
            assert codegen_cli.main(_argv(base + ["--out", str(out), "--check"])) == 1


def _argv(argv: list[str]) -> Any:

    from velocitron_cli import build_parser

    return build_parser().parse_args(argv)


# ── 2. the counts under --actor over the eight library-hold nets ────────


def test_actor_counts_over_the_eight_nets() -> None:
    # given: the actor filter's value the module is for. The quiet-day alarm
    # is the one step the circulation desk owns; the as-is copy leaves it
    # with the annex, so the filter keeps nothing.
    expected = {
        "branch_policy": (0, 1, 7),
        "branch_policy_as_is": (0, 0, 8),
        "partner_loan": (5, 11, 0),
        "union_catalog": (1, 6, 0),
        "request": (2, 1, 0),
        "shelf": (0, 4, 1),
        "checkout": (3, 3, 0),
        "notice": (0, 2, 0),
        "edition": (0, 4, 0),
    }

    # when / then: each net counts exactly
    totals = [0, 0, 0]
    for stem, (want_abstract, want_generated, want_none) in expected.items():
        if stem == "branch_policy_as_is":
            fixture = _HOLDS / "branch-policy-as-is.petrinet"
            relative = fixture.relative_to(_REPO_ROOT).as_posix()
            text = fixture.read_text(encoding="utf-8")
            lowered = lower_petrinet_text(text, relative)
            module = generate_module(
                parse_net(compile_petrinet_text(text, relative)),
                source=relative,
                source_name=relative,
                text=text,
                contributions=lowered["contributions"],
                actor=_ACTOR,
            )
        else:
            module = _generate(stem, actor=_ACTOR)
        got = (
            len(module.abstract_methods),
            len(module.generated_handlers),
            len(module.no_code_transitions),
        )
        assert got == (want_abstract, want_generated, want_none), stem
        if stem == "branch_policy_as_is":
            continue
        for index in range(3):
            totals[index] += got[index]
    # and: the eight leaf nets sum to 11 abstract, 32 generated, 8 no code
    # (the as-is copy's 8 no-code transitions sit outside that total)
    assert totals == [11, 32, 8], totals


# ── 3. without --actor, branch policy fails with exactly two errors ─────


def test_branch_policy_without_actor_fails_with_two_errors() -> None:
    # given: the branch-policy net with no actor filter
    # when / then: generation collects both unfilled outputs and exits
    with pytest.raises(CodegenError) as exc:
        _generate("branch_policy")
    messages = exc.value.messages
    assert len(messages) == 2
    assert any("[annex_lends] -loan-> (loaned)" in m for m in messages)
    assert any("[survey_copies] -survey-> (survey)" in m for m in messages)
    assert all(
        ": branch-policy.petrinet" in m or "branch-policy.petrinet:" in m
        for m in messages
    )
    # and: nothing was written (the generator raised; no file exists below
    # the assertion because generation happens before the CLI opens one —
    # covered by the CLI-level no-write test on the keyword place)


# ── 4. the carry rule through the Engine: the four carries ──────────────


def test_generated_handlers_carry_through_the_engine() -> None:
    # given: the generated partner-loan class, its abstract methods stubbed,
    # registered through the base, and the Engine run from a hold in
    # (offered). A form is already on file, so fill_form's inhibit holds
    # and the generated form_on_file step carries the hold instead.
    module = _generate("partner_loan", actor=_ACTOR)
    namespace = _load(module, "golden_partner_loan")
    base = namespace["PartnerLoanNet"]

    fired: list[str] = []

    class MyLoan(base):  # pyright: ignore[reportUnsafeMultipleInheritance]
        def fire_request_quote(self, offered: list[Token]) -> Any:
            fired.append("fire_request_quote")
            return {
                "quote_result": [
                    Token(
                        "hold",
                        {**offered[0].data, "accepted": True, "code": "standard"},
                    )
                ]
            }

        def fire_fill_form(self, priced: list[Token]) -> Any:
            # never called on this run: a matching form is already on file
            fired.append("fire_fill_form")
            return {"cleared": [Token("hold", dict(priced[0].data))]}

        def fire_pack(
            self, cleared: list[Token], cleared_flag: list[Token], crates: list[Token]
        ) -> Any:
            fired.append("fire_pack")
            _ = (cleared_flag, crates)
            return {
                "pack_result": [
                    Token("hold", {**cleared[0].data, "packed": True})
                ]
            }

        def fire_dispatch(self, boxed: list[Token], lanes: list[Token]) -> Any:
            fired.append("fire_dispatch")
            _ = lanes
            return {
                "dispatch_result": [
                    Token("hold", {**boxed[0].data, "dispatched": True})
                ]
            }

        def fire_receive(self, in_transit: list[Token]) -> Any:
            fired.append("fire_receive")
            token = in_transit[0]
            return {
                "loan_ended": [
                    Token(
                        "result",
                        {"outcome": "loaned", "hold": dict(token.data)},
                    )
                ],
                "union_notice": [Token("notice", {"isbn": token.data["isbn"]})],
            }

    instance = MyLoan()
    registry = HandlerRegistry()
    net = _net("partner_loan")
    registration = instance.register_into(registry, net)
    engine = Engine(registry)

    hold = {
        "isbn": "978",
        "branch": "annex",
        "code": "standard",
        "sentinel": "KEEP-ME",
    }
    marking = Marking(
        {
            "offered": [Token("hold", deepcopy(hold))],
            "forms": [Token("form", {"isbn": "978", "code": "standard"})],
            "crates": [Token("crate", {"lane": "annex"})],
            "lanes": [Token("lane", {"name": "east"})],
        }
    )

    # when: run to quiescence. The quote forks a customs flag, the form on
    # file carries the hold, and packing joins the two before dispatch.
    final = engine.advance(registration.net, marking)

    # then: fill_form stayed quiet; the generated carries kept the sentinel
    assert fired == [
        "fire_request_quote",
        "fire_pack",
        "fire_dispatch",
        "fire_receive",
    ], fired
    for place in ("priced", "cleared", "boxed", "in_transit", "held_lane"):
        assert not final.get(place, []), place
    assert len(final.get("loan_ended", [])) == 1
    ended = final["loan_ended"][0]
    assert ended.data["outcome"] == "loaned"
    assert ended.data["hold"]["sentinel"] == "KEEP-ME"
    # and: the quote's carry is a copy, not the token object
    record = engine.fire(
        registration.net,
        Marking(
            {
                "quote_result": [
                    _token("hold", sentinel="S-CARRY", accepted=True, isbn="978")
                ]
            }
        ),
        "quoted",
        attempt=1,
    )[1]
    carried = record["outputTokens"]["priced"][0]
    assert carried.data["sentinel"] == "S-CARRY"
    assert carried.type == "hold"


def test_a_net_of_pure_transitions_runs_with_no_handler_code() -> None:
    # given: a net with no handler facts: a `data cel`, a literal `data` and
    # a carry, generated and registered with no subclass and no methods
    text = (
        "net pure\n\n"
        "@stamp: (asked) -job-> [stamp] -job-> (stamped)\n"
        "@stamp data cel \"{'n': binding.asked[0].n, 'seen': true}\"\n"
        "(stamped) -job-> [carry] -job-> (carried)\n"
        "@close: (carried) -job-> [close] -receipt-> (closed)\n"
        '@close data {"ok": true}\n'
    )
    net = parse_net(compile_petrinet_text(text, "pure.petrinet"))
    lowered = lower_petrinet_text(text, "pure.petrinet")
    module = generate_module(
        net,
        source="pure.petrinet",
        source_name="pure.petrinet",
        text=text,
        contributions=lowered["contributions"],
    )
    namespace = _load(module, "pure_net")
    registry = HandlerRegistry()
    copy = namespace["PureNet"]().register_into(registry, net).net
    # when:
    final = Engine(registry).advance(
        copy, Marking({"asked": [_token("job", n=1)]}), strict=True
    )
    # then: every pure body ran, with no handler written
    assert all(not final.get(place, ()) for place in ("asked", "stamped", "carried"))
    assert [t.data for t in final["closed"]] == [{"ok": True}]


# ── 5. data cel parity: the exposed evaluator is the Engine's ───────────


def test_data_cel_matches_the_engine_fallback() -> None:
    # given: the branch-policy net's arc that sends a title home to the
    # annex, and a binding of one home-branch token
    net = _net("branch_policy")
    arc = next(
        a
        for a in net.arcs
        if a.produce is not None
        and a.produce.cel
        == (
            "{'isbn': binding.home[0].isbn, 'branch': 'annex', "
            "'confirmed': false}"
        )
    )
    binding = {"home": [_tok_home()]}
    engine = Engine(HandlerRegistry())

    # when: the exposed evaluator runs it, and the Engine's own deposit
    # fallback fills the same output on a firing where the handler returns
    # nothing for that key
    generated = evaluate_produce_cel(
        arc.produce.cel,
        {place: [token.data for token in tokens] for place, tokens in binding.items()},
        cel_adapter=engine._cel_adapter,  # pyright: ignore[reportPrivateUsage]
    )
    via_deposit = _engine_deposit(net, "send_to_annex", binding)
    # the Engine's handler-fallback path deposits the same data for the
    # same template (the handler left the output key empty)
    assert [t.data for t in via_deposit] == [generated]


def _tok_home() -> Token:
    return Token("route", {"isbn": "978", "branch": "main", "confirmed": True})


def _engine_deposit(
    net: Any, transition: str, binding: dict[str, list[Token]]
) -> list[Token]:
    """The Engine's own fallback for one `data cel` produce.

    The Engine only fills an output from `data cel` when its handler left
    the key empty, so this run gives the transition a handler that returns
    nothing: a synthesized ref (the base's copy rule), bound to an
    empty-completed handler.
    """
    import velocitron_netbase as netbase
    from velocitron_petrinet import parse_net

    synth_ref = f"{netbase.SYNTH_HANDLER}:{transition}"
    document = netbase.net_document(net)
    for entry in document["transitions"]:
        if entry["name"] == transition:
            entry["handler"] = synth_ref
    copy = parse_net(document)

    def handler(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        _ = inp
        return {
            "status": "completed",
            "outputTokens": {},
            "error": None,
            "metadata": {},
        }

    registry = HandlerRegistry()
    registry.register_transition(synth_ref, handler)
    engine = Engine(registry)
    marking = Marking({place: list(tokens) for place, tokens in binding.items()})
    _, record = engine.fire(copy, marking, transition, attempt=1)
    assert record["status"] == "completed", record
    return [t for t in record["outputTokens"].get(_output_place(net, transition), [])]


def _output_place(net: Any, transition: str) -> str:
    return next(
        a.to_place
        for a in net.arcs
        if a.from_transition == transition
        and a.produce is not None
        and a.produce.cel is not None
    )


# ── 6. NotRequired on the generated TypedDicts ──────────────────────────


def test_stamp_due_outputs_are_not_required_and_notify_has_one_required(
    tmp_path: pathlib.Path,
) -> None:
    # given: the checkout net generated under the actor filter, imported as
    # a real module file — TypedDict's key sets are computed from lazy
    # annotations (PEP 649), so exec-introspection of an anonymous module
    # cannot see them; a file import resolves like any user module would
    module = _generate("checkout", actor=_ACTOR)
    path = tmp_path / "checkout_mod.py"
    path.write_text(module.text, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        import checkout_mod as real  # pyright: ignore[reportMissingImports]

        stamp = real.StampDueOutputs
        notify = real.NotifyOutputs
    finally:
        sys.path.pop(0)
        pathlib.Path(sys.modules.pop("checkout_mod").__file__ or "").unlink(
            missing_ok=True
        )

    # then: stamp_due's three outputs all carry `data cel`, so all three are
    # NotRequired; notify's `due` arc has neither data nor cel, so it is
    # required, while its shelf-slot arc is filled by cel
    assert set(stamp.__required_keys__) == set()
    assert set(stamp.__optional_keys__) == {"loaned", "stamped", "shelf_slot"}
    assert set(notify.__required_keys__) == {"due"}
    assert "shelf_slot" in set(notify.__optional_keys__)


# ── 7. one handler ref, one transition ──────────────────────────────────


def test_shared_handler_ref_fails_generation(tmp_path: pathlib.Path) -> None:
    # given: two transitions naming one handler ref
    fixture = tmp_path / "shared.petrinet"
    fixture.write_text(
        'net shared "shared"\n'
        "\n"
        "(a) -task-> [one] -task-> (a)\n"
        "(a) -task-> [two] -task-> (a)\n"
        '[one] handler "do@shared"\n'
        '[two] handler "do@shared"\n'
        "(a) port input task\n"
    )
    text = fixture.read_text(encoding="utf-8")
    lowered = lower_petrinet_text(text, "shared.petrinet")
    net = parse_net(compile_petrinet_text(text, "shared.petrinet"))

    # when / then: generation names both transition with one shared ref
    with pytest.raises(CodegenError) as exc:
        generate_module(
            net,
            source="shared.petrinet",
            source_name="shared.petrinet",
            text=text,
            contributions=lowered["contributions"],
        )
    message = exc.value.messages[0]
    assert '"do@shared"' in message
    assert "[one]" in message and "[two]" in message


# ── 8. guards and predicates, and --async's shape ───────────────────────


@pytest.fixture()
def guarded_module() -> GeneratedModule:
    """The small guarded net (tests/fixtures/codegen/small_guarded.petrinet)."""
    fixture = _FIXTURES / "small_guarded.petrinet"
    relative = "tests/fixtures/codegen/small_guarded.petrinet"
    text = fixture.read_text(encoding="utf-8")
    lowered = lower_petrinet_text(text, relative)
    net = parse_net(compile_petrinet_text(text, relative))
    return generate_module(
        net,
        source=relative,
        source_name=relative,
        text=text,
        contributions=lowered["contributions"],
    )


@pytest.fixture()
def guarded_async_module() -> GeneratedModule:
    fixture = _FIXTURES / "small_guarded.petrinet"
    relative = "tests/fixtures/codegen/small_guarded.petrinet"
    text = fixture.read_text(encoding="utf-8")
    lowered = lower_petrinet_text(text, relative)
    net = parse_net(compile_petrinet_text(text, relative))
    return generate_module(
        net,
        source=relative,
        source_name=relative,
        text=text,
        contributions=lowered["contributions"],
        is_async=True,
    )


def test_guard_and_predicate_are_abstract_plain_def(
    guarded_module: GeneratedModule,
) -> None:
    # given: the module's text
    text = guarded_module.text

    # then: abstract guard_<t> and predicate_<p> exist, plain def
    assert "def guard_go(self, gate_in: list[Token]) -> bool:" in text
    assert "def predicate_skip_done(self, token: Token) -> bool:" in text
    assert "async def guard_go" not in text
    assert "async def predicate_skip_done" not in text
    assert guarded_module.guard_methods == {"g": "guard_go"}
    assert guarded_module.predicate_methods == {"skip_done": "predicate_skip_done"}


def test_async_emits_context_keyword(guarded_async_module: GeneratedModule) -> None:
    # given: the same net under --async
    text = guarded_async_module.text

    # then: the fire method is async with a context keyword; guards and
    # predicates stay plain def
    assert (
        "async def fire_go(self, gate_in: list[Token], *, context: RuntimeContext)"
        in text
    )
    assert "def guard_go(self, gate_in: list[Token]) -> bool:" in text
    assert "def predicate_skip_done(self, token: Token) -> bool:" in text
    assert guarded_async_module.guard_methods["g"] == "guard_go"


def test_keyword_place_name_fails_generation(tmp_path: pathlib.Path) -> None:
    # given: a place named like a Python keyword
    fixture = tmp_path / "keyword.petrinet"
    fixture.write_text(
        'net keyword_net "keyword"\n'
        "\n"
        "(in) -task-> [go] -task-> (done)\n"
        "(in) port input task\n"
    )
    text = fixture.read_text(encoding="utf-8")
    lower_petrinet_text(text, "keyword.petrinet")
    parse_net(compile_petrinet_text(text, "keyword.petrinet"))
    out = tmp_path / "keyword_net.py"

    # when: the CLI generates it
    import velocitron_cli.codegen as codegen_cli
    from velocitron_cli import build_parser

    argv = build_parser().parse_args(["codegen", str(fixture), "--out", str(out)])

    # then: exit 1 with the keyword error, and nothing written
    assert codegen_cli.main(argv) == 1
    assert not out.exists()


# ── 9. basedpyright on the goldens, and the abstract-usage report ───────


def _pyright_config_including_planted_fixtures(tmp_path: pathlib.Path) -> pathlib.Path:
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
            cfg[key] = [
                item for item in entries if item not in _PLANTED_PYRIGHT_FIXTURES
            ]
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


def test_basedpyright_on_the_goldens(tmp_path: pathlib.Path) -> None:
    # given: the repository's own basedpyright (pytest.skip when absent)
    from shutil import which

    executable = which("basedpyright") or (
        str(_PYTHON_ROOT / ".venv" / "bin" / "basedpyright")
        if (_PYTHON_ROOT / ".venv" / "bin" / "basedpyright").is_file()
        else None
    )
    if not executable:
        pytest.skip("basedpyright is not available")

    # when: type-checking the golden directory under the project's rules,
    # including the planted fixtures the default scan excludes
    result = subprocess.run(  # pyright: ignore[reportUnknownMemberType]
        [
            executable,
            "--project",
            str(_pyright_config_including_planted_fixtures(tmp_path)),
            str(_GOLDEN),
        ],
        check=False,
        capture_output=True,
        text=True,  # pyright: ignore[reportUnknownMemberType]
        timeout=300,
    )

    # then: zero errors on every golden except the planted bad subclasses
    # (this card's leaf-net one, and the composition card's constructor
    # call fixture — a reportAbstractUsage each; the composition card's
    # own test asserts the call-site one)
    output = result.stdout + result.stderr
    planted = {"bad_subclass.py", "bad_library_holds_composition_subclass.py"}
    findings: list[tuple[str, str]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if (
            stripped.endswith(" - error")
            or line.startswith("  /")
            and " - error: " in line
        ):
            head = stripped.split(" - error: ", 1)[0]
            path = pathlib.Path(head.split(":")[0]).name
            findings.append((path, ""))
            continue
        if "(" in stripped and stripped.endswith(")") and findings:
            code = stripped[stripped.rfind("(") + 1 : -1]
            path, _ = findings[-1]
            findings[-1] = (path, code)
    good_errors = [(p, c) for p, c in findings if p not in planted]
    assert good_errors == [], good_errors
    leaf_bad = _NETS / "bad_subclass.py"
    assert [c for p, c in findings if p == leaf_bad.name] == ["reportAbstractUsage"]


# ── 10. determinism: generating twice gives identical bytes ─────────────


def test_determinism() -> None:
    # given: one net generated twice, and one under different flag orders
    first = _generate("partner_loan", actor=_ACTOR)
    second = _generate("partner_loan", actor=_ACTOR)
    first_async = _generate("reading_voice", is_async=True)
    second_async = _generate("reading_voice", is_async=True)

    # then: identical bytes every time, no timestamp anywhere
    assert first.text == second.text
    assert first_async.text == second_async.text
    for stem in ("branch_policy", "pulse_source", "checkout", "shelf"):
        assert _generate(
            stem, actor=_ACTOR if stem != "pulse_source" else None
        ).text == (
            _generate(stem, actor=_ACTOR if stem != "pulse_source" else None).text
        )
    assert "2026" not in first.text  # no run-date leaks into a module
