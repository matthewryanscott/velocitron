"""Console commands for the Petri-net DSL.

Canonical emission (``to-petrinet``), enablement text (``explain``),
structural equivalence (``equiv``), and the CEL backend hint are supplied
by :func:`velocitron_cli.configure`. ``main`` calls
:func:`velocitron_cli.install_default_hooks` first, so a missing hook
becomes the implementation in the package that owns it. The bundled skill
directory is :func:`velocitron_skill.skill_root` unless that hook overrides
it. This module does not import ``velocitron``.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

import json5

from velocitron_analysis import LintFinding, kept_problems, lint_net, share_problems
from velocitron_codegen import net_document
from velocitron_dsl import PetrinetDslError, SourcePosition, lower_petrinet_text
from velocitron_engine import Arc, Marking, Net
from velocitron_merge import NetValidationError as MergeNetValidationError
from velocitron_merge import merge_composition
from velocitron_petrinet import (
    NetValidationError,
    compile_petrinet_text,
    parse_composition,
    parse_net,
    read_petrinet_text,
    validate_net,
)
from velocitron_play import (
    TRUNK,
    WALK_SCOPES,
    PlayError,
    parse_play,
    read_play,
)
from velocitron_play_check import (
    check_play,
    render_sequence,
    render_walkthrough,
    trace_document,
)
from velocitron_runtime import KEY as WAIT_KEY
from velocitron_runtime import wait_problems
from velocitron_skill import skill_root
from velocitron_viz import render_canonical_json

from . import codegen as codegen_cli
from . import prove as prove_cli
from .check import check_paths
from .host import HOST, install_default_hooks


def _program_version() -> str:
    """This package's version when it is installed."""
    for dist in ("velocitron-cli",):
        try:
            return f"velocitron {version(dist)}"
        except PackageNotFoundError:
            continue
    return "velocitron 0.1.0"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="velocitron")
    parser.add_argument("--version", action="version", version=_program_version())
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "to-json", "to-petrinet"):
        item = commands.add_parser(command)
        item.add_argument("input", metavar="INPUT")
        if command == "to-json":
            item.add_argument("--semantic-only", action="store_true")
            item.add_argument(
                "--merged",
                action="store_true",
                help=(
                    "For a composition: print the single merged net "
                    "(qualified names, fused places, refinements applied) "
                    "that `velocitron check`, `velocitron prove` and plays "
                    "use, as a net document validated against "
                    "spec/net.schema.json. Not valid with --semantic-only."
                ),
            )
        elif command == "to-petrinet":
            item.add_argument("--compact", action="store_true")
    explain = commands.add_parser("explain")
    explain.add_argument("input", metavar="INPUT")
    explain.add_argument("--format", choices=("markdown", "text"), default="markdown")
    explain.add_argument(
        "--level", choices=("practitioner", "newcomer"), default="practitioner"
    )
    explain_marking = explain.add_mutually_exclusive_group()
    explain_marking.add_argument(
        "--marking",
        metavar="NAME",
        help="say what can happen from authored named marking NAME "
        "(default: the initial marking)",
    )
    explain_marking.add_argument(
        "--marking-json",
        metavar="JSON",
        help="say what can happen from one inline JSON marking object",
    )
    skill = commands.add_parser("skill")
    skill.add_argument("pathname", metavar="PATHNAME")
    check = commands.add_parser(
        "check",
        help=(
            "validate syntax in *.petrinet and *.play files and in "
            "```petrinet and ```play fences"
        ),
        description=(
            "Validate Petri-net DSL syntax in *.petrinet files and "
            "```petrinet fenced code blocks, and play syntax in "
            "*.play files and ```play fences, inside Markdown files. "
            "Directories are walked recursively (hidden directories, "
            "node_modules, and virtualenvs are skipped). Fences opened "
            "with ```petrinet no-lint or ```play no-lint hold "
            "intentionally-invalid examples and are skipped. This checks "
            "syntax only; it is distinct from the advisory semantic lint in "
            "velocitron_analysis (ADR 0016) and from `velocitron play check`, "
            "which plays a play against its net."
        ),
    )
    check.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="files or directories to check (default: current directory)",
    )
    prove_cli.add_parser(commands)
    codegen_cli.add_parser(commands)
    equiv_add_parser = HOST.equiv_add_parser
    if equiv_add_parser is not None:
        equiv_add_parser(commands)
    play = commands.add_parser(
        "play",
        help="check a .play file against its net, or render a trace, walkthrough or sequence diagram",
    )
    play_commands = play.add_subparsers(dest="play_command", required=True)
    play_check = play_commands.add_parser(
        "check",
        help="play every path (or the named ones) and report the first failing step",
        description=(
            "Play each path of a .play file through the engine by symbolic "
            "firing. Prints FILE: OK, N paths passed and exits 0 when every "
            "path passes; prints FILE:LINE:COL: error[SCnnn]: MESSAGE with "
            "detail lines and exits 1 otherwise."
        ),
    )
    play_check.add_argument(
        "input", metavar="FILE", help="a .play file, or - for stdin"
    )
    play_check.add_argument("--origin", metavar="DIR", help=_ORIGIN_HELP)
    play_check.add_argument(
        "--path", dest="play_paths", action="append", metavar="NAME"
    )
    play_check.add_argument("--json", action="store_true")
    play_walk = play_commands.add_parser(
        "walk",
        help="render one path as a Markdown (or JSON) walkthrough",
        description=(
            "Check one path (the trunk by default) and render it: the touched "
            "subnet with its starting marking, then one section per step with "
            "the marking before and after side by side. A failing path renders "
            "up to the failure, ends with it, and exits 1."
        ),
    )
    play_walk.add_argument("input", metavar="FILE", help="a .play file, or - for stdin")
    play_walk.add_argument("--origin", metavar="DIR", help=_ORIGIN_HELP)
    play_walk.add_argument("--path", dest="play_path", metavar="NAME")
    play_walk.add_argument("--format", choices=("md", "json"), default="md")
    play_walk.add_argument("-o", "--output", metavar="OUT")
    play_walk.add_argument(
        "--direction", type=str.lower, choices=("tb", "lr"), default="tb"
    )
    play_walk.add_argument(
        "--scope",
        choices=WALK_SCOPES,
        help=(
            "what each step's graph draws: step (its transition and places, "
            "the default), neighbors (plus their other transitions, faded) or "
            "subnet (every node the path touches); overrides the play's "
            "scope setting"
        ),
    )
    play_walk.add_argument(
        "--sequence",
        choices=("beside", "only", "none"),
        help=(
            "add the path's sequence diagram before the walkthrough (beside), "
            "draw only the diagram (only), or leave it out (none); overrides "
            "the play's `show sequence` setting"
        ),
    )
    play_sequence = play_commands.add_parser(
        "sequence",
        help="render one path as a sequence diagram (PlantUML or JSON)",
        description=(
            "Check one path (the trunk by default) and project it onto a "
            "sequence diagram: one lifeline per actor, an arrow per hand-off "
            "between actors. A failing path renders up to the failure, ends "
            "with it, and exits 1."
        ),
    )
    play_sequence.add_argument(
        "input", metavar="FILE", help="a .play file, or - for stdin"
    )
    play_sequence.add_argument("--origin", metavar="DIR", help=_ORIGIN_HELP)
    play_sequence.add_argument("--path", dest="play_path", metavar="NAME")
    play_sequence.add_argument(
        "--format", choices=("plantuml", "json"), default="plantuml"
    )
    play_sequence.add_argument("-o", "--output", metavar="OUT")
    play_trace = play_commands.add_parser(
        "trace",
        help="print one path's trace as JSON",
        description=(
            "Check one path (the trunk by default) and print its trace as "
            "JSON: per step its line, kind, title, statement, actor, records "
            "(each marked where the clock matured the firing), the marking "
            "after each record, and per record its resolved actor plus, on "
            "a lived place, the column and read label. A failing path "
            "prints up to the failure and exits 1."
        ),
    )
    play_trace.add_argument(
        "input", metavar="FILE", help="a .play file, or - for stdin"
    )
    play_trace.add_argument("--origin", metavar="DIR", help=_ORIGIN_HELP)
    play_trace.add_argument("--path", dest="play_path", metavar="NAME")
    play_trace.add_argument("-o", "--output", metavar="OUT")
    return parser


_ORIGIN_HELP = (
    "the directory that `net` and `use` paths resolve against "
    "(default: the file's directory, or the current directory for stdin)"
)


def _play_main(args: argparse.Namespace) -> int:
    path = args.input
    try:
        if path == "-":
            path = "<stdin>"
            origin = Path(args.origin) if args.origin else Path.cwd()
            play = parse_play(sys.stdin.read(), path, origin=origin)
        else:
            play = read_play(path)
            if args.origin:
                play = replace(play, origin=Path(args.origin))
        if args.play_command == "check":
            wanted: list[str] | None = args.play_paths
        else:
            wanted = [args.play_path or TRUNK]
        unknown = [name for name in wanted or () if play.path(name) is None]
        if unknown:
            names = ", ".join(p.name for p in play.paths)
            sys.stderr.write(
                f"velocitron play: error: unknown path {unknown[0]} (paths: {names})\n"
            )
            return 2
        report = check_play(play, paths=wanted)
    except PlayError as error:
        if args.play_command == "check" and args.json:
            payload = {
                "file": path,
                "passed": False,
                "paths": [],
                "diagnostics": [error.diagnostic.as_json()],
            }
            sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        else:
            sys.stderr.write(error.diagnostic.render() + "\n")
        return 1
    except (OSError, UnicodeError) as error:
        sys.stderr.write(f"{path}:1:1: error[SC201]: {error}\n")
        return 1
    diagnostics = report.diagnostics()
    if args.play_command == "check":
        if args.json:
            payload = {
                "file": path,
                "passed": report.passed,
                "paths": [
                    {
                        "name": trace.path.name,
                        "status": "passed" if trace.passed else "failed",
                        "steps": len(trace.steps),
                        "failure": None
                        if trace.failure is None
                        else trace.failure.diagnostic.as_json(),
                    }
                    for trace in report.traces
                ],
                "diagnostics": [d.as_json() for d in diagnostics],
            }
            sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        else:
            for diagnostic in diagnostics:
                sys.stderr.write(diagnostic.render() + "\n")
            if not diagnostics:
                count = len(report.traces)
                paths = "path" if count == 1 else "paths"
                sys.stdout.write(f"{path}: OK, {count} {paths} passed\n")
        return 1 if diagnostics else 0
    (trace,) = report.traces
    if args.play_command == "trace":
        text = json.dumps(trace_document(trace), ensure_ascii=False, indent=2) + "\n"
    elif args.play_command == "sequence":
        text = render_sequence(trace, format=args.format)
    else:
        text = render_walkthrough(
            trace,
            format=args.format,
            rankdir=args.direction.upper(),
            scope=args.scope,
            sequence=args.sequence,
        )
    try:
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except OSError as error:
        sys.stderr.write(f"velocitron play: error: could not write output: {error}\n")
        return 1
    for diagnostic in diagnostics:
        sys.stderr.write(diagnostic.render() + "\n")
    return 1 if diagnostics else 0


def _read(path: str) -> str:
    return read_petrinet_text(path)


def _json_document(path: str) -> dict[str, Any]:
    parsed = json.loads(_read(path))
    if not isinstance(parsed, dict):
        raise ValueError("JSON input must be an object")
    return cast(dict[str, Any], parsed)


def _strict_json_document(path: str) -> dict[str, Any]:
    def reject_non_json_constant(value: str) -> None:
        raise ValueError(f"JSON input contains non-finite value {value!r}")

    parsed = json.loads(_read(path), parse_constant=reject_non_json_constant)
    if not isinstance(parsed, dict):
        raise ValueError("JSON input must be an object")
    return cast(dict[str, Any], parsed)


def _json5_document(path: str) -> dict[str, Any]:
    parsed = json5.loads(_read(path))
    if not isinstance(parsed, dict):
        raise ValueError("JSON5 input must be an object")
    _reject_non_finite_json5_values(parsed)
    return cast(dict[str, Any], parsed)


def _reject_non_finite_json5_values(value: Any) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON5 input must not contain non-finite numbers")
    elif isinstance(value, dict):
        for nested in cast(dict[str, Any], value).values():
            _reject_non_finite_json5_values(nested)
    elif isinstance(value, list):
        for nested in cast(list[Any], value):
            _reject_non_finite_json5_values(nested)


def _explain_document(path: str) -> dict[str, Any]:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        document = _strict_json_document(path)
    elif suffix == ".json5":
        document = _json5_document(path)
    elif suffix == ".petrinet":
        document = compile_petrinet_text(_read(path), path)
    else:
        raise NetValidationError(f"unsupported explain input type: {suffix or path!r}")

    if "nets" in document:
        raise NetValidationError("explain accepts a core Net, not a composition")
    return document


def _explain_marking(
    document: dict[str, Any], name: str | None, inline: str | None
) -> tuple[Marking, str]:
    """The marking ``explain`` starts from, checked as the net's initial marking."""
    raw: Any
    if name is not None:
        annotations = cast(dict[str, Any], document.get("annotations") or {})
        payload = cast(dict[str, Any], annotations.get("petrinet.dsl/v1") or {})
        markings = cast(dict[str, Any], payload.get("markings") or {})
        if name not in markings:
            available = ", ".join(json.dumps(m) for m in sorted(markings)) or "none"
            raise NetValidationError(
                f"unknown named marking {json.dumps(name)}; "
                f"available markings: {available}"
            )
        raw, label = markings[name], f"marking {json.dumps(name)}"
    elif inline is not None:
        raw, label = json.loads(inline), "the given marking"
    else:
        raw = document.get("initialMarking") or dict[str, Any]()
        label = "the initial marking"
    net = parse_net({**document, "initialMarking": raw})
    marking = net.initial_marking or Marking()
    accepts = {place.name: place.accepts for place in net.places}
    for place, tokens in marking.items():
        if place not in accepts:
            raise NetValidationError(f"invalid marking: unknown place ({place})")
        for token in tokens:
            if token.type not in accepts[place]:
                raise NetValidationError(
                    f"invalid marking: ({place}) does not accept color {token.type}"
                )
    return marking, label


def _semantic_only(document: dict[str, Any]) -> dict[str, Any]:
    """Drop documentation recursively without reinterpreting semantic fields."""
    result = deepcopy(document)
    result.pop("description", None)
    result.pop("annotations", None)
    for collection in ("places", "transitions", "arcs"):
        raw_items = result.get(collection)
        if not isinstance(raw_items, list):
            continue
        for raw_item in cast(list[Any], raw_items):
            if isinstance(raw_item, dict):
                item = cast(dict[str, Any], raw_item)
                item.pop("description", None)
                item.pop("annotations", None)
    return result


def _merge_validated(composition: Any) -> Net:
    """Merge a composition, then revalidate the result.

    ``velocitron_merge`` does not revalidate. The closing check, including
    CEL compilation, is ``validate_net``.
    """
    try:
        merged = merge_composition(composition)
    except MergeNetValidationError as exc:
        raise NetValidationError(str(exc)) from exc
    validate_net(merged)
    return merged


def _composition_loader(origin: Path):
    def load(ref: str) -> Mapping[str, Any] | Path | str:
        path = Path(ref)
        if not path.is_absolute():
            path = origin / path
        suffix = path.suffix.lower()
        if suffix == ".json":
            return path
        if suffix == ".petrinet":
            return compile_petrinet_text(_read(str(path)), str(path))
        raise NetValidationError(f"unsupported composition net reference: {ref!r}")

    return load


def _compile_document(path: str) -> dict[str, Any]:
    override = HOST.compile_document
    if override is not None:
        return cast(dict[str, Any], override(path))
    origin = Path(path).parent
    return compile_petrinet_text(
        _read(path),
        path,
        net_loader=_composition_loader(origin),
        origin=origin,
    )


def _validate_document(document: dict[str, Any], path: str) -> str:
    override = HOST.validate_document
    if override is not None:
        return cast(str, override(document, path))
    if "nets" in document:
        origin = Path(path).parent
        parse_composition(
            document,
            origin=origin,
            net_loader=_composition_loader(origin),
        )
        return "composition"
    (HOST.parse_net or parse_net)(document)
    return "net"


_ArcKey = tuple[str, str, str, str]  # place, transition, color, mode


@dataclass(frozen=True)
class _NetSourceMap:
    """Source positions of one net's transitions and arcs."""

    transitions: dict[str, SourcePosition]
    arcs: dict[int, SourcePosition]  # by index in net.arcs
    predicates: dict[int, SourcePosition]  # the arc's `predicate` fact
    correlates: dict[int, SourcePosition]  # the arc's `correlate` fact
    positions: dict[tuple[str, str], SourcePosition]  # (view, place)

    def position(self, finding: LintFinding) -> SourcePosition | None:
        """The source position of what ``finding`` flags, if known."""
        if finding.view is not None and finding.place is not None:
            found = self.positions.get((finding.view, finding.place))
            if found is not None:
                return found
        if finding.arc is None:
            return self.transitions.get(finding.transition)
        facts = {"predicate": self.predicates, "correlate": self.correlates}
        if finding.inscription is not None:
            fact = facts[finding.inscription].get(finding.arc)
            if fact is not None:
                return fact
        return self.arcs.get(finding.arc)


def _position(span: Mapping[str, Any]) -> SourcePosition:
    start = cast(Mapping[str, int], span["start"])
    return SourcePosition(start["byteOffset"], start["line"], start["column"])


def _transition_name_position(
    source_bytes: bytes, span: Mapping[str, Any], name: str, is_input: bool
) -> SourcePosition:
    """Where an arc's span writes ``[name]``, else the span's start.

    The IR carries a span of the name only for a consume arc; an input arc's
    span ends with ``[name]`` and a produce arc's span starts with it.
    """
    written = f"[{name}]".encode()
    if is_input:
        end = cast(Mapping[str, int], span["end"])
        offset = end["byteOffset"] - len(written)
        line, column = end["line"], end["column"] - len(name) - 2
    else:
        start = cast(Mapping[str, int], span["start"])
        offset, line, column = start["byteOffset"], start["line"], start["column"]
    if source_bytes[offset : offset + len(written)] != written:
        return _position(span)
    return SourcePosition(offset + 1, line, column + 1)


def _arc_id(raw: Mapping[str, Any]) -> tuple[str, int, int]:
    return (raw["document"], raw["statement"], raw["part"])


def _net_arc_key(arc: Arc) -> _ArcKey | None:
    if arc.consume is not None and arc.from_place and arc.to_transition:
        return (arc.from_place, arc.to_transition, arc.consume.type, arc.consume.mode)
    if arc.produce is not None and arc.to_place and arc.from_transition:
        return (arc.to_place, arc.from_transition, arc.produce.type, "produce")
    return None


def _net_source_map(text: str, source_name: str, net: Net) -> _NetSourceMap:
    """Map ``net``, compiled from the `.petrinet` ``text``, back to its source.

    Arcs are matched to their declarations by endpoints, color and mode, in
    order, because the compiler may reorder arcs (`order` facts).
    """
    contributions = cast(
        list[dict[str, Any]], lower_petrinet_text(text, source_name)["contributions"]
    )
    source_bytes = text.encode("utf-8")
    transitions: dict[str, SourcePosition] = {}
    positions: dict[tuple[str, str], SourcePosition] = {}
    declarations: dict[_ArcKey, list[tuple[tuple[str, int, int], SourcePosition]]] = {}
    handles: dict[str, list[tuple[str, int, int]]] = {}
    facts: dict[str, dict[str, SourcePosition]] = {"predicate": {}, "correlate": {}}
    for contribution in contributions:
        kind = contribution["kind"]
        target = cast(dict[str, Any], contribution["target"])
        value = cast(dict[str, Any], contribution["value"])
        span = cast(dict[str, Any], contribution["span"])
        if kind == "transition.declare":
            transitions.setdefault(target["name"], _position(span))
        elif kind == "view.position":
            subject_raw = value.get("subject")
            view_name = target.get("name")
            if isinstance(subject_raw, dict) and isinstance(view_name, str):
                subject = cast("dict[str, Any]", subject_raw)
                place_name = subject.get("name")
                if subject.get("type") == "place" and isinstance(place_name, str):
                    positions.setdefault((view_name, place_name), _position(span))
        elif kind == "arc.declare":
            source, destination = value["from"], value["to"]
            is_input = source["type"] == "place"
            place = source["name"] if is_input else destination["name"]
            transition = destination["name"] if is_input else source["name"]
            transitions.setdefault(
                transition,
                _position(value["transitionNameSpan"])
                if "transitionNameSpan" in value
                else _transition_name_position(
                    source_bytes, span, transition, is_input
                ),
            )
            key = (place, transition, value["color"]["value"], value["mode"])
            declarations.setdefault(key, []).append(
                (_arc_id(target["id"]), _position(span))
            )
        elif kind == "arc.handle":
            handles[target["name"]] = [_arc_id(raw) for raw in value["arcIds"]]
        elif kind in ("arc.predicate", "arc.correlate"):
            facts[kind.removeprefix("arc.")][target["name"]] = _position(span)

    fact_by_arc_id: dict[str, dict[tuple[str, int, int], SourcePosition]] = {
        name: {
            arc_id: position
            for handle, position in by_handle.items()
            for arc_id in handles.get(handle, ())
        }
        for name, by_handle in facts.items()
    }
    arcs: dict[int, SourcePosition] = {}
    predicates: dict[int, SourcePosition] = {}
    correlates: dict[int, SourcePosition] = {}
    used: dict[_ArcKey, int] = {}
    for index, arc in enumerate(net.arcs):
        key = _net_arc_key(arc)
        if key is None or used.get(key, 0) >= len(declarations.get(key, ())):
            continue
        arc_id, position = declarations[key][used.get(key, 0)]
        used[key] = used.get(key, 0) + 1
        arcs[index] = position
        if arc_id in fact_by_arc_id["predicate"]:
            predicates[index] = fact_by_arc_id["predicate"][arc_id]
        if arc_id in fact_by_arc_id["correlate"]:
            correlates[index] = fact_by_arc_id["correlate"][arc_id]
    return _NetSourceMap(transitions, arcs, predicates, correlates, positions)


def _lint_warnings(path: str, net: Net) -> list[str]:
    """Each lint finding on ``net`` as a warning at the source line of what it
    flags; a net read from JSON has no source positions, so it uses 1:1."""
    source_map = (
        _net_source_map(_read(path), path, net)
        if Path(path).suffix.lower() == ".petrinet"
        else None
    )
    warnings: list[str] = []
    for finding in lint_net(net):
        position = source_map.position(finding) if source_map is not None else None
        line, column = (1, 1) if position is None else (position.line, position.column)
        warnings.append(
            f"{path}:{line}:{column}: warning[{finding.rule}]: {finding.message}"
        )
    return warnings


def _document_lint_warnings(path: str, document: dict[str, Any]) -> list[str]:
    """Lint warnings for a net, or for each net a composition uses.

    A composition is linted net by net, not as the merged net: each net's CEL
    keeps its own place names after the merge (ADR 0032), and each warning
    can then point into that net's own file.
    """
    if "nets" not in document:
        return _lint_warnings(path, parse_net(document))
    origin = Path(path).parent
    composition = parse_composition(
        document, origin=origin, net_loader=_composition_loader(origin)
    )
    warnings: list[str] = []
    for alias, net in (composition.parsed_nets or {}).items():
        member_path = str(origin / (composition.sources or {})[alias])
        for warning in _lint_warnings(member_path, net):
            if warning not in warnings:
                warnings.append(warning)
    return warnings


def _contribution_positions(
    path: str, kind: str, key: Any
) -> dict[Any, SourcePosition]:
    """Where each contribution of ``kind`` starts, by ``key(contribution)``."""
    if Path(path).suffix.lower() != ".petrinet":
        return {}
    contributions = cast(
        list[dict[str, Any]], lower_petrinet_text(_read(path), path)["contributions"]
    )
    return {
        key(item): _position(cast(dict[str, Any], item["span"]))
        for item in contributions
        if item["kind"] == kind and key(item) is not None
    }


def _kept_annotation_place(contribution: Mapping[str, Any]) -> str | None:
    value = cast(Mapping[str, Any], contribution["value"])
    target = cast(Mapping[str, Any], contribution["target"])
    if value.get("key") == "kept" and target.get("type") == "place":
        return cast(str, target["name"])
    return None


def _share_members(contribution: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    places = cast(list[Mapping[str, Any]], contribution["value"]["places"])
    return frozenset((str(p.get("alias")), str(p.get("place"))) for p in places)


def _net_kept_errors(path: str, net: Net) -> list[str]:
    problems = kept_problems(net)
    if not problems:
        return []
    positions = _contribution_positions(
        path, "documentation.annotation", _kept_annotation_place
    )
    errors: list[str] = []
    for place, message in problems:
        position = positions.get(place)
        line, column = (1, 1) if position is None else (position.line, position.column)
        errors.append(f"{path}:{line}:{column}: error[PN202]: {message}")
    return errors


def _document_kept_errors(path: str, document: dict[str, Any]) -> list[str]:
    """Errors in the kept records of a net, or of each net a composition
    uses and of its shares (ADR 0051)."""
    if "nets" not in document:
        return _net_kept_errors(path, parse_net(document))
    origin = Path(path).parent
    composition = parse_composition(
        document, origin=origin, net_loader=_composition_loader(origin)
    )
    nets = composition.parsed_nets or {}
    errors: list[str] = []
    for alias, net in nets.items():
        member_path = str(origin / (composition.sources or {})[alias])
        for error in _net_kept_errors(member_path, net):
            if error not in errors:
                errors.append(error)
    positions = _contribution_positions(path, "composition.share", _share_members)
    for share, message in share_problems(nets, composition.shares):
        position = positions.get(frozenset(share.members))
        line, column = (1, 1) if position is None else (position.line, position.column)
        errors.append(f"{path}:{line}:{column}: error[PN202]: {message}")
    return errors


def _wait_annotation_transition(contribution: Mapping[str, Any]) -> str | None:
    value = cast(Mapping[str, Any], contribution["value"])
    target = cast(Mapping[str, Any], contribution["target"])
    if value.get("key") == WAIT_KEY and target.get("type") == "transition":
        return cast(str, target["name"])
    return None


def _net_wait_errors(path: str, net: Net) -> list[str]:
    problems = wait_problems(net)
    if not problems:
        return []
    positions = _contribution_positions(
        path, "documentation.annotation", _wait_annotation_transition
    )
    errors: list[str] = []
    for transition, message in problems:
        position = positions.get(transition)
        line, column = (1, 1) if position is None else (position.line, position.column)
        errors.append(f"{path}:{line}:{column}: error[PN202]: {message}")
    return errors


def _document_wait_errors(path: str, document: dict[str, Any]) -> list[str]:
    """Errors in the intended waits of a net, or of each net a composition
    uses (ADR 0057)."""
    if "nets" not in document:
        return _net_wait_errors(path, parse_net(document))
    origin = Path(path).parent
    composition = parse_composition(
        document, origin=origin, net_loader=_composition_loader(origin)
    )
    errors: list[str] = []
    for alias, net in (composition.parsed_nets or {}).items():
        member_path = str(origin / (composition.sources or {})[alias])
        for error in _net_wait_errors(member_path, net):
            if error not in errors:
                errors.append(error)
    return errors


_SKILL_MANIFEST = ".velocitron-skill-manifest.json"


def _relative_files(root: Path) -> list[str]:
    """Sorted POSIX-relative paths of every file under ``root``."""
    return sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )


def _read_manifest(path: Path) -> list[str]:
    """Managed-file list from a prior install's manifest (empty if absent/bad)."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    files = cast(dict[str, Any], data).get("files")
    if not isinstance(files, list):
        return []
    return [str(entry) for entry in cast(list[Any], files)]


def _install_skill(pathname: str) -> int:
    """Install or true-sync the bundled skill under ``<pathname>/velocitron/``.

    The target ``pathname`` must already exist. Every shipped file is written
    (overwriting), then — the true-sync step — any file listed in the previous
    install's manifest that the skill no longer ships is removed, while files a
    user added (in no manifest) are left untouched. A fresh manifest naming the
    managed files is written last. An existing ``SKILL.md`` marks an update.
    """
    target = Path(pathname)
    if not target.is_dir():
        raise NotADirectoryError(
            f"target path does not exist or is not a directory: {pathname}"
        )
    skill_source = HOST.skill_source
    source = skill_root() if skill_source is None else skill_source()
    dest = target / "velocitron"
    action = "updated" if (dest / "SKILL.md").is_file() else "installed"

    shipped = _relative_files(source)
    previous = _read_manifest(dest / _SKILL_MANIFEST)

    for rel in shipped:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, out)

    for rel in previous:
        if rel not in shipped:
            stale = dest / rel
            if stale.is_file():
                stale.unlink()
    for directory in sorted(
        (p for p in dest.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        if not any(directory.iterdir()):
            directory.rmdir()

    (dest / _SKILL_MANIFEST).write_text(
        json.dumps({"files": shipped}, indent=2) + "\n", encoding="utf-8"
    )
    sys.stdout.write(f"{action} velocitron skill at {dest}\n")
    return 0


# The commands that evaluate CEL often enough for the backend's speed to matter.
_CEL_COMMANDS = {"prove", "play", "equiv"}
# prove keeps CEL results, so the Rust backend hardly speeds it up (ADR 0053).
_RUST_HINT_COMMANDS = {"play", "equiv"}


def _show_backend_hint_once(command: str) -> None:
    hint_for = HOST.slow_backend_hint
    if HOST.backend_hint_shown or hint_for is None:
        return
    HOST.backend_hint_shown = True
    hint = hint_for(suggest_rust=command in _RUST_HINT_COMMANDS)
    if hint:
        sys.stderr.write(hint)


def main(argv: Sequence[str] | None = None) -> int:
    install_default_hooks()
    args = _parser().parse_args(argv)
    if args.command in _CEL_COMMANDS:
        _show_backend_hint_once(args.command)
    if args.command == "check":
        report = check_paths([Path(item) for item in args.paths] or [Path(".")])
        for issue in report.errors:
            sys.stderr.write(issue + "\n")
        sys.stdout.write(report.summary() + "\n")
        return 1 if report.errors else 0
    if args.command == "play":
        return _play_main(args)
    if args.command == "prove":
        return prove_cli.main(args)
    if args.command == "codegen":
        return codegen_cli.main(args)
    if args.command == "equiv":
        equiv_main = HOST.equiv_main
        if equiv_main is None:
            sys.stderr.write("velocitron equiv: error: equiv is not configured\n")
            return 1
        return equiv_main(args)
    if args.command == "skill":
        try:
            return _install_skill(args.pathname)
        except OSError as error:
            sys.stderr.write(f"{args.pathname}:1:1: error[PN200]: {error}\n")
            return 1
    path = args.input
    try:
        suffix = Path(path).suffix.lower()
        if args.command == "validate":
            if suffix == ".json":
                document = _json_document(path)
                kind = _validate_document(document, path)
            else:
                document = _compile_document(path)
                kind = "composition" if "nets" in document else "net"
            kept_errors = _document_kept_errors(path, document) + _document_wait_errors(
                path, document
            )
            if kept_errors:
                for error in kept_errors:
                    sys.stderr.write(error + "\n")
                return 1
            sys.stdout.write(kind + "\n")
            for warning in _document_lint_warnings(path, document):
                sys.stderr.write(warning + "\n")
        elif args.command == "to-json":
            if args.merged and args.semantic_only:
                raise ValueError("--merged and --semantic-only are mutually exclusive")
            document = _compile_document(path)
            _validate_document(document, path)

            if args.merged:
                if "nets" not in document:
                    raise ValueError("--merged applies only to a composition")
                net = _merge_validated(
                    parse_composition(
                        document,
                        origin=Path(path).parent,
                        net_loader=_composition_loader(Path(path).parent),
                    )
                )
                document = net_document(net)
            if args.semantic_only:
                document = _semantic_only(document)
            sys.stdout.write(render_canonical_json(document, indent=2) + "\n")
        elif args.command == "to-petrinet":
            if suffix == ".json":
                document = _json_document(path)
                _validate_document(document, path)
            else:
                document = _compile_document(path)
            emit = HOST.emit_petrinet
            if emit is None:
                raise ValueError(
                    "to-petrinet needs canonical emission; it is not configured"
                )
            sys.stdout.write(emit(document, compact=args.compact))
        elif args.command == "explain":
            explain = HOST.explain_net
            if explain is None:
                raise ValueError("explain is not configured")
            document = _explain_document(path)
            net = parse_net(document)
            marking, label = _explain_marking(document, args.marking, args.marking_json)
            sys.stdout.write(
                explain(
                    net,
                    format=args.format,
                    level=args.level,
                    marking=marking,
                    marking_label=label,
                )
            )
    except PetrinetDslError as error:
        sys.stderr.write(error.diagnostic.render() + "\n")
        return 1
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        NetValidationError,
    ) as error:
        sys.stderr.write(f"{path}:1:1: error[PN200]: {error}\n")
        return 1
    return 0


parser = _parser


if __name__ == "__main__":
    raise SystemExit(main())
