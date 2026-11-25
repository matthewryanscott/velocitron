"""Provable facts about a net: choice coverage, place invariants, soundness,
and the soundness of each refinement of a composition.

The property pass in ``velocitron_properties`` (ADR 0019)
checks markings a system produced. This package checks markings a net *can*
reach: it derives finite data domains from the net's own CEL (the net's
``domain`` facts and a domains file override them), models the environment
as open places, and explores one lifecycle instance explicitly through the
real engine. Each fact comes out proved, refuted (with a witness or a
shortest counterexample, written as a ``.play`` file on request) or unknown
(with the reason).

Kept records and the opt-in lint live here too: prove reads both, and kept
records read the CEL scan in this package. ``prove`` revalidates a merged
composition with ``velocitron_petrinet.validate_net``. The ``velocitron
prove`` command lives in ``velocitron_cli``. This package does not import
``velocitron``.

References: spec/proofs.md; ADR 0036; ADR 0037; ADR 0050; ADR 0052.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import json5

from velocitron_engine import Net
from velocitron_merge import NetValidationError as MergeNetValidationError
from velocitron_merge import merge_composition as _package_merge_composition
from velocitron_petrinet import NetValidationError
from velocitron_petrinet import compile_petrinet_text, read_petrinet_text
from velocitron_petrinet import parse_composition, parse_net, validate_net

from . import kept as kept_module
from .analysis import NetModel
from .kept import (
    INSTANCE,
    KeptRecord,
    KeptStartError,
    build_start,
    kept_problems,
    kept_records,
    share_problems,
)
from .lint import (
    RULE_CONSUME_WITHOUT_PRODUCE,
    RULE_CORRELATE_FREE_NAME,
    RULE_PREDICATE_NAMES_COLOR_OR_PLACE,
    RULE_FUSION_PLACE_POSITION,
    RULE_PLACE_POSITION_OVERRIDDEN,
    RULE_READ_ONLY_PRODUCER,
    LintFinding,
    binding_keys,
    lint_net,
    suppressed_rules,
)
from .choice import Cases, EngineCases, choice_proofs
from .counterexample import write_counterexamples
from .firing import Firing
from .invariants import (
    Invariant,
    declared_invariant_proofs,
    place_invariant_proofs,
    semiflows,
)
from .refinement import (
    Composed,
    RefinementCheck,
    check_refinement,
    refinement_environment,
)
from .report import Finding, Move, Proof, ProofReport
from .fast import FastPathError, KernelCases
from .soundness import Environment, soundness_proofs
from .tables import Untabled

FACTS = ("choice", "invariants", "soundness", "refinement")
DEFAULT_MAX_STATES = 50_000


@dataclass(frozen=True)
class ProofSettings:
    """What the net does not say, given by the author (a domains file).

    ``domains`` maps ``color.field.path`` to the complete list of values the
    field takes, replacing the derived domain. ``instance_color`` and
    ``final`` name the instance's color and its final places. ``injections``
    and ``updates`` bound how often the environment writes an open place
    (default once each). ``firings`` caps how often a transition, by its
    merged name, may fire on one explored path. ``starts`` is how often the
    instance starts, each time with the same keys. ``other_keys`` lets
    soundness put tokens about another key into open places too.
    """

    domains: Mapping[str, Sequence[Any]] = field(
        default_factory=dict[str, Sequence[Any]]
    )
    instance_color: str | None = None
    final: Sequence[str | Sequence[str]] | None = None
    injections: Mapping[str, int] = field(default_factory=dict[str, int])
    updates: Mapping[str, int] = field(default_factory=dict[str, int])
    firings: Mapping[str, int] = field(default_factory=dict[str, int])
    starts: int = 1
    other_keys: bool = False


def read_settings(path: Path | str) -> ProofSettings:
    """Read a domains file (JSON or JSON5); see spec/proofs.md."""
    raw = json5.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: a domains file is a JSON object")
    document = cast(dict[str, Any], raw)
    known = {"domains", "instance", "final", "environment"}
    extra = sorted(set(document) - known)
    if extra:
        raise ValueError(f"{path}: unknown key {extra[0]!r}")
    domains = document.get("domains", {})
    if not isinstance(domains, dict) or not all(
        isinstance(v, list) for v in cast(dict[str, Any], domains).values()
    ):
        raise ValueError(f"{path}: domains maps color.field to a list of values")
    environment = document.get("environment", {})
    if not isinstance(environment, dict):
        raise ValueError(f"{path}: environment is an object")
    env = cast(dict[str, Any], environment)
    firings = env.get("firings", {})
    if not isinstance(firings, dict):
        raise ValueError(f"{path}: environment.firings maps a transition to a count")
    for name, limit in cast(dict[str, Any], firings).items():
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(
                f"{path}: environment.firings.{name} is a positive count, got {limit!r}"
            )
    starts = env.get("starts", 1)
    if isinstance(starts, bool) or not isinstance(starts, int) or starts < 1:
        raise ValueError(
            f"{path}: environment.starts is a positive count, got {starts!r}"
        )
    final = document.get("final")
    return ProofSettings(
        domains=cast(dict[str, list[Any]], domains),
        instance_color=document.get("instance"),
        final=list(final) if final is not None else None,
        injections=dict(env.get("injections", {})),
        updates=dict(env.get("updates", {})),
        firings=cast(dict[str, int], firings),
        starts=starts,
        other_keys=bool(env.get("otherKeys", False)),
    )


def load_net(path: Path | str) -> Net:
    """Load a ``.petrinet`` or ``.json`` net; a composition is merged."""
    return load(path)[0]


def load(path: Path | str) -> tuple[Net, Composed | None]:
    """Load a net, or merge a composition and keep what it was merged from.

    A composition's references may be ``.petrinet`` or ``.json`` files,
    relative to the composition's directory.
    """
    path = Path(path)
    loader = _reference_loader(path.parent)
    document = _document(path, loader)
    if "nets" not in document:
        return parse_net(document), None
    composition = parse_composition(document, origin=path.parent, net_loader=loader)
    nets = composition.parsed_nets or {}
    files = {
        alias: _reference_path(path.parent, ref)
        for alias, ref in (composition.sources or {}).items()
    }
    composed = Composed(
        nets=nets,
        files=files,
        wires=composition.wires,
        refinements=composition.refinements,
        shares=composition.shares,
    )
    return _merge_composition(composition), composed


def _merge_composition(composition: Any) -> Net:
    """Merge already-parsed nets, then revalidate the result.

    ``velocitron_merge`` does not revalidate. The closing check, including
    CEL compilation, is ``validate_net``.
    """
    try:
        merged = _package_merge_composition(composition)
    except MergeNetValidationError as exc:
        raise NetValidationError(str(exc)) from exc
    validate_net(merged)
    return merged


def _reference_path(origin: Path, ref: str) -> Path:
    target = Path(ref)
    return target if target.is_absolute() else origin / target


def _reference_loader(origin: Path) -> Callable[[str], Mapping[str, Any] | Path | str]:
    # Compiling a composition parses its references once to check them, and
    # loading parses them again, so each file is compiled once and copied.
    compiled: dict[Path, dict[str, Any]] = {}

    def load_reference(ref: str) -> Mapping[str, Any] | Path | str:
        target = _reference_path(origin, ref)
        if target.suffix.lower() != ".petrinet":
            return target
        if target not in compiled:
            # The composition being parsed validates what it references, so a
            # referenced composition compiles without checking its own
            # references.
            compiled[target] = compile_petrinet_text(
                read_petrinet_text(target), str(target)
            )
        return deepcopy(compiled[target])

    return load_reference


def _document(
    path: Path, loader: Callable[[str], Mapping[str, Any] | Path | str]
) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".petrinet":
        return compile_petrinet_text(
            read_petrinet_text(path),
            str(path),
            net_loader=loader,
            origin=path.parent,
        )
    if suffix == ".json":
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"{path.name}: a net document is a JSON object")
        return cast(dict[str, Any], document)
    raise ValueError(f"unsupported net file type {suffix or path.name!r}")


def prove(
    net: Net,
    *,
    facts: Iterable[str] = FACTS,
    settings: ProofSettings | None = None,
    invariants: Sequence[Invariant] = (),
    max_states: int = DEFAULT_MAX_STATES,
    source: str | None = None,
    counterexamples: Path | str | None = None,
    net_file: Path | str | None = None,
    composition: Composed | None = None,
    wait_arrivals: bool = False,
    progress: Callable[[str], object] | None = None,
    fast: bool = False,
    one_core: bool = False,
    on_reference: Callable[[str], None] | None = None,
) -> ProofReport:
    """Prove the requested facts about ``net``.

    ``invariants`` are author-declared place invariants, proved with the
    invariants fact next to the ones the net declares. With
    ``counterexamples`` (a directory) and ``net_file`` (the net's file, for
    the plays' ``net`` line), each witness and counterexample is written
    as a ``.play`` file. ``composition`` (from :func:`load`) is what a
    merged ``net`` was merged from: its wired places are never open, and
    the refinement fact checks each of its refinements. ``wait_arrivals``
    holds each arrival back while no step can use it (ADR 0061); it is off
    by default because on a run that hits ``max_states`` it can explore
    twice the edges. ``progress`` takes each exploration's progress line,
    one every ten seconds while it runs (the command passes the error
    stream's ``write``). ``fast`` proves soundness and choice on the fast
    path, the compiled kernel (``fast.py``), which explores on every core,
    or with ``one_core`` on one in the reference's order, as the check
    against the reference does; the two give the same graph.
    ``on_reference`` is told what it cannot take (the net, or one choice's
    cases) when the reference proves that instead. A failure inside the
    kernel raises ``FastPathError``.
    """
    wanted = list(dict.fromkeys(facts))
    unknown = [fact for fact in wanted if fact not in FACTS]
    if unknown:
        raise ValueError(
            f"unknown fact {unknown[0]!r}; the facts are {', '.join(FACTS)}"
        )
    settings = settings or ProofSettings()
    _check_kept(net, composition)
    declared = net.proofs
    final = settings.final
    if final is None and declared is not None and declared.final:
        final = declared.final
    model = NetModel(
        net,
        overrides=settings.domains,
        instance_color=settings.instance_color,
        final=final,
        other_keys=settings.other_keys,
        closed=composition.fused() if composition is not None else (),
    )
    _check_firings(net, settings.firings)
    if isinstance(settings.starts, bool) or settings.starts < 1:
        raise ValueError(
            f"environment.starts is a positive count, got {settings.starts!r}"
        )
    _check_environment_writes(model, settings)
    model.kept_marking()
    environment = Environment(
        settings.injections, settings.updates, settings.firings, settings.starts
    )
    firing = Firing(net, model)
    proofs: list[Proof] = []
    exploration: dict[str, Any] | None = None
    if "choice" in wanted:
        cases: Cases = EngineCases(firing)
        if fast:
            try:
                cases = KernelCases(net, model, firing, environment, on_reference)
            except Untabled as why:
                # The soundness exploration would meet the same: the
                # reference proves the net, with one note.
                if on_reference is not None:
                    on_reference(str(why))
                fast = False
        proofs += _by_constituent(choice_proofs(net, model, cases), composition)
    if "invariants" in wanted:
        proofs += place_invariant_proofs(net, model)
        declared_invariants = [
            Invariant(dict(item.weights), item.constant, item.name)
            for item in (declared.invariants or [] if declared is not None else [])
        ]
        proofs += declared_invariant_proofs(
            net, model, [*declared_invariants, *invariants], environment
        )
    if "soundness" in wanted:
        found, explorer = soundness_proofs(
            net,
            model,
            environment=environment,
            max_states=max_states,
            wait_arrivals=wait_arrivals,
            progress=progress,
            fast=fast,
            one_core=one_core,
            on_reference=on_reference,
        )
        proofs += found
        markings, edges = explorer.size()
        exploration = {
            "states": markings,
            "edges": edges,
            "capped": explorer.capped,
            "maxStates": max_states,
        }
        if settings.firings:
            exploration["firingCaps"] = {
                name: {"limit": limit, "stopped": explorer.stopped.get(name, 0)}
                for name, limit in sorted(settings.firings.items())
            }
        if settings.starts != 1:
            exploration["starts"] = settings.starts
        if explorer.capped:
            exploration["madeBy"] = explorer.made_by()
            producers = [
                finding.transition
                for finding in lint_net(net)
                if finding.rule == RULE_READ_ONLY_PRODUCER
            ]
            if producers:
                exploration["readOnlyProducers"] = producers
    checks: list[RefinementCheck] = []
    if "refinement" in wanted and composition is not None:
        for refinement in composition.refinements:
            checks.append(
                check_refinement(
                    composition,
                    refinement,
                    domains=settings.domains,
                    environment=refinement_environment(refinement.by, environment),
                    other_keys=settings.other_keys,
                    max_states=max_states,
                    wait_arrivals=wait_arrivals,
                    progress=progress,
                )
            )
        proofs += [check.proof for check in checks]
    report = ProofReport(
        net=net.name,
        source=source,
        proofs=tuple(proofs),
        model={
            "roles": model.roles.as_json(),
            "domains": {f.text(): d.as_json() for f, d in model.domains.items()},
            "unsupported": {k: list(v) for k, v in sorted(model.unsupported.items())},
        },
        exploration=exploration,
        composition={
            "nets": {alias: str(file) for alias, file in composition.files.items()}
        }
        if composition is not None
        else None,
    )
    if counterexamples is not None:
        if net_file is None:
            raise ValueError("writing counterexamples needs the net's file")
        report = write_counterexamples(
            report,
            net,
            firing,
            Path(net_file),
            Path(counterexamples),
            instance=sorted(model.roles.instance),
            final=sorted(model.roles.final),
        )
        report = _write_refinement_counterexamples(
            report, checks, Path(counterexamples)
        )
    return report


def _check_kept(net: Net, composition: Composed | None) -> None:
    """The kept records of the nets as written, and of their shares."""
    if composition is None:
        problems = [message for _, message in kept_module.kept_problems(net)]
    else:
        problems = [
            f"{alias}: {message}"
            for alias, member in composition.nets.items()
            for _, message in kept_module.kept_problems(member)
        ]
        problems += [
            message
            for _, message in kept_module.share_problems(
                composition.nets, composition.shares
            )
        ]
    if problems:
        raise ValueError(problems[0])


def _check_environment_writes(model: NetModel, settings: ProofSettings) -> None:
    """Nobody outside the net writes a kept record (ADR 0051), and the
    instance's starts are counted by ``starts``, not per place (ADR 0052)."""
    for key, bounds in (
        ("injections", settings.injections),
        ("updates", settings.updates),
    ):
        for name in sorted(bounds):
            if name in model.roles.kept:
                raise ValueError(
                    f"environment.{key} names ({name}), but ({name}) is a kept "
                    "record: it starts from its `starts as` value, and the "
                    "environment never writes it"
                )
    for name in sorted(settings.injections):
        if name in model.roles.start:
            raise ValueError(
                f"environment.injections names ({name}), but ({name}) is where "
                "the instance starts: set environment.starts to start it more "
                "than once"
            )


def _check_firings(net: Net, firings: Mapping[str, int]) -> None:
    """A firing cap names a transition of the (merged) net by its full name."""
    names = {transition.name for transition in net.transitions}
    for name, limit in firings.items():
        if name not in names:
            close = sorted(n for n in names if n.endswith(f".{name}"))
            hint = f"; did you mean {close[0]!r}?" if len(close) == 1 else ""
            raise ValueError(
                f"environment.firings names unknown transition {name!r}{hint}"
            )
        if isinstance(limit, bool) or limit < 1:
            raise ValueError(
                f"environment.firings.{name} is a positive count, got {limit!r}"
            )


def _by_constituent(proofs: list[Proof], composition: Composed | None) -> list[Proof]:
    """Name the constituent net of each choice of a composition."""
    if composition is None:
        return proofs
    named: list[Proof] = []
    for proof in proofs:
        place = str(proof.details.get("place", ""))
        alias = max(
            (a for a in composition.nets if place.startswith(f"{a}.")),
            key=len,
            default=None,
        )
        if alias is not None:
            proof = replace(proof, details={**proof.details, "constituent": alias})
        named.append(proof)
    return named


def _write_refinement_counterexamples(
    report: ProofReport, checks: Sequence[RefinementCheck], directory: Path
) -> ProofReport:
    """Write each refinement finding as a play against the refining net."""
    written: dict[str, Proof] = {}
    for check in checks:
        if check.model is None or not any(f.path for f in check.proof.findings):
            continue
        partial = write_counterexamples(
            replace(report, proofs=(check.proof,)),
            check.net,
            Firing(check.net, check.model),
            check.file,
            directory,
            instance=sorted(check.model.roles.instance),
            final=sorted(check.model.roles.final),
            facts=("refinement",),
        )
        written[check.proof.subject] = partial.proofs[0]
    if not written:
        return report
    return replace(
        report,
        proofs=tuple(
            written.get(proof.subject, proof) if proof.fact == "refinement" else proof
            for proof in report.proofs
        ),
    )


__all__ = [
    "DEFAULT_MAX_STATES",
    "FACTS",
    "RULE_CONSUME_WITHOUT_PRODUCE",
    "RULE_CORRELATE_FREE_NAME",
    "RULE_PREDICATE_NAMES_COLOR_OR_PLACE",
    "RULE_FUSION_PLACE_POSITION",
    "RULE_PLACE_POSITION_OVERRIDDEN",
    "RULE_READ_ONLY_PRODUCER",
    "Composed",
    "FastPathError",
    "Finding",
    "INSTANCE",
    "Invariant",
    "KeptRecord",
    "KeptStartError",
    "LintFinding",
    "Move",
    "Proof",
    "ProofReport",
    "ProofSettings",
    "binding_keys",
    "build_start",
    "kept_problems",
    "kept_records",
    "lint_net",
    "load",
    "load_net",
    "prove",
    "read_settings",
    "semiflows",
    "share_problems",
    "suppressed_rules",
]
