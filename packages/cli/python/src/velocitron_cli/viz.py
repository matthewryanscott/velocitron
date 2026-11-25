"""``velocitron-viz`` console command.

Document loading and the argument parser live here. Drawing stays in
``velocitron_viz``. The ``velocitron-viz`` console script calls
:func:`main`.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from velocitron_dsl import PetrinetDslError
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
from velocitron_viz import (
    DEFAULT_VIEW,
    DETAIL_LEVELS,
    Composition,
    LayoutMetricsError,
    Marking,
    Net,
    RenderStyle,
    Token,
    apply_view,
    arc_handle_index,
    composition_overview_dot,
    composition_ports_dot,
    composition_to_dot,
    has_view,
    layout_metrics,
    legend_dot,
    net_render_model,
    net_to_dot,
    read_decorations,
    read_fusion_modes,
    stamp_arc_ids,
    view_setting,
)

_LAYOUT_LINE = re.compile(r"(?m)^[ \t]*layout=([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$")
_GRAPHVIZ_VERSION = re.compile(r"graphviz version (\S+)")

__all__ = ["main"]


def _merge_validated(composition: Composition) -> Net:
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


class _VizError(Exception):
    """A deterministic, user-facing ``velocitron-viz`` failure."""


class _SourceError(_VizError):
    """A source document could not be read, compiled, or validated."""


def _json_quote(value: str) -> str:
    """Quote a user-supplied name with JSON's deterministic string grammar."""
    return json.dumps(value, ensure_ascii=False)


def _decode_json_object(text: str, *, context: str) -> dict[str, Any]:
    """Decode strict JSON, rejecting duplicate keys at every object depth."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value!r}")

    def object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _VizError(
                    f"invalid {context}: duplicate object key {_json_quote(key)}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=object_from_pairs,
            parse_constant=reject_constant,
        )
    except _VizError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise _VizError(f"invalid {context}") from error
    if not isinstance(value, dict):
        raise _VizError(f"invalid {context}: expected a JSON object")
    return cast(dict[str, Any], value)


def _load_document(
    path: Path,
) -> tuple[str, Net | Composition, dict[str, Any]]:
    """Load and validate a JSON or DSL net/composition document."""
    try:
        if path.suffix.lower() == ".petrinet":
            doc = compile_petrinet_text(read_petrinet_text(path), str(path))
        else:
            doc = _decode_json_object(path.read_text(), context="JSON source")
    except OSError as error:
        raise _SourceError(f"could not read source {_json_quote(str(path))}") from error
    except PetrinetDslError as error:
        raise _SourceError(f"invalid DSL source {_json_quote(str(path))}") from error
    except _VizError as error:
        raise _SourceError(f"invalid JSON source {_json_quote(str(path))}") from error

    try:
        if "places" in doc:
            return "net", parse_net(doc), doc
        if "nets" in doc:

            def load_ref(ref: str) -> dict[str, Any] | Path | str:
                ref_path = Path(ref)
                if not ref_path.is_absolute():
                    ref_path = path.parent / ref_path
                if ref_path.suffix.lower() == ".json":
                    return ref_path
                if ref_path.suffix.lower() == ".petrinet":
                    return compile_petrinet_text(
                        read_petrinet_text(ref_path), str(ref_path)
                    )
                raise ValueError(f"unsupported composition net reference: {ref!r}")

            return (
                "composition",
                parse_composition(doc, origin=path.parent, net_loader=load_ref),
                doc,
            )
    except (NetValidationError, OSError, PetrinetDslError, ValueError) as error:
        raise _SourceError(f"invalid source {_json_quote(str(path))}") from error
    raise _SourceError(f"unsupported source document {_json_quote(str(path))}")


def _validate_selected_marking(raw_marking: Mapping[str, Any], net: Net) -> Marking:
    """Validate one named or inline marking against the standalone Net."""
    places = {place.name: place for place in net.places}
    parsed: dict[str, list[Token]] = {}
    for place_name in sorted(raw_marking):
        raw_tokens = raw_marking[place_name]
        if place_name not in places:
            raise _VizError(f"invalid marking: unknown place {_json_quote(place_name)}")
        if not isinstance(raw_tokens, list):
            raise _VizError(
                f"invalid marking at place {_json_quote(place_name)}: "
                "tokens must be an array"
            )
        raw_tokens = cast(list[Any], raw_tokens)
        tokens: list[Token] = []
        for index, raw_token in enumerate(raw_tokens):
            prefix = (
                f"invalid marking at place {_json_quote(place_name)}, token {index}: "
            )
            if not isinstance(raw_token, dict):
                raise _VizError(prefix + "token must be an object")
            raw_token = cast(dict[str, Any], raw_token)
            if set(raw_token) != {"type", "data"}:
                raise _VizError(prefix + "token must contain exactly type and data")
            type_ = raw_token["type"]
            data = raw_token["data"]
            if not isinstance(type_, str) or not type_:
                raise _VizError(prefix + "type must be a nonempty string")
            if not isinstance(data, dict):
                raise _VizError(prefix + "data must be an object")
            data = cast(dict[str, Any], data)
            if type_ not in places[place_name].accepts:
                colors = ", ".join(
                    _json_quote(color) for color in sorted(places[place_name].accepts)
                )
                raise _VizError(
                    prefix
                    + f"type {_json_quote(type_)} is not accepted "
                    + f"(accepted colors: {colors})"
                )
            tokens.append(Token(type=type_, data=data))
        parsed[place_name] = tokens
    return Marking(parsed)


def _json_object_fields(value: Any) -> Mapping[str, Any]:
    """Return JSON object fields, treating every non-object as absent."""
    return cast(Mapping[str, Any], value) if isinstance(value, dict) else {}


def _named_marking(raw_document: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """Get an authored named marking without ever falling back to initial."""
    annotations = _json_object_fields(raw_document.get("annotations"))
    payload = _json_object_fields(annotations.get("petrinet.dsl/v1"))
    markings = _json_object_fields(payload.get("markings"))
    available = sorted(markings)
    if name not in markings:
        rendered = (
            ", ".join(_json_quote(candidate) for candidate in available) or "none"
        )
        raise _VizError(
            f"unknown named marking {_json_quote(name)}; available markings: {rendered}"
        )
    marking: Any = markings[name]
    if not isinstance(marking, dict):
        raise _VizError(f"invalid named marking {_json_quote(name)}")
    return cast(dict[str, Any], marking)


def _layout_engine(dot: str) -> str:
    """The engine named by a ``layout=`` line, or ``dot`` when the DOT names none."""
    match = _LAYOUT_LINE.search(dot)
    return match.group(1) if match is not None else "dot"


def _graphviz_binary(engine: str) -> str:
    binary = shutil.which(engine)
    if binary is None:
        raise _VizError(
            f"Graphviz is required for --metrics but {engine!r} was not found on PATH"
        )
    return binary


def _graphviz_version(engine: str) -> str | None:
    """The version Graphviz prints for ``engine -V``, when that binary exists."""
    binary = shutil.which(engine) or shutil.which("dot")
    if binary is None:
        return None
    try:
        completed = subprocess.run(
            [binary, "-V"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _GRAPHVIZ_VERSION.search(completed.stderr or completed.stdout)
    return match.group(1) if match is not None else None


def _run_graphviz(dot: str, engine: str) -> str:
    """Lay ``dot`` out with ``engine -Tjson`` and return the JSON text."""
    try:
        completed = subprocess.run(
            [_graphviz_binary(engine), "-Tjson"],
            input=dot,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise _VizError(f"Graphviz {engine} timed out") from error
    except OSError as error:
        raise _VizError(f"Graphviz {engine} could not be started") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        suffix = detail[-1] if detail else f"exit {completed.returncode}"
        raise _VizError(f"Graphviz {engine} failed: {suffix}")
    return completed.stdout


def _metrics_document(
    report: Mapping[str, Any], *, graphviz_version: str | None, engine: str | None
) -> dict[str, Any]:
    """The printed metrics object, with the engine that actually drew it."""
    return {
        "crossings": report["crossings"],
        "pairs": report["pairs"],
        "overlaps": report["overlaps"],
        "edge_node_overlaps": report["edge_node_overlaps"],
        "edge_length": report["edge_length"],
        "bends": report["bends"],
        "graphviz_version": graphviz_version,
        "engine": engine,
    }


def _measure_dot(dot: str) -> dict[str, Any]:
    engine = _layout_engine(dot)
    try:
        measured = layout_metrics(_run_graphviz(dot, engine))
    except LayoutMetricsError as error:
        raise _VizError(str(error)) from error
    return _metrics_document(
        measured,
        graphviz_version=_graphviz_version(engine),
        engine=engine,
    )


def _measure_json(text: str) -> dict[str, Any]:
    try:
        measured = layout_metrics(text)
    except LayoutMetricsError as error:
        raise _VizError(str(error)) from error
    engine = measured["engine"]
    version_engine = engine if isinstance(engine, str) else "dot"
    return _metrics_document(
        measured,
        graphviz_version=_graphviz_version(version_engine),
        engine=engine if isinstance(engine, str) else None,
    )


def _write_metrics(report: Mapping[str, Any], output: Path | None) -> int:
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    try:
        if output is not None:
            output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except OSError:
        destination = output if output is not None else Path("<stdout>")
        sys.stderr.write(
            f"velocitron-viz: error: could not write output {_json_quote(str(destination))}\n"
        )
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: render a net or composition document to Graphviz DOT."""
    parser = argparse.ArgumentParser(
        prog="velocitron-viz",
        description=(
            "Render a velocitron Net or composition JSON/.petrinet document "
            "as a Graphviz DOT digraph (to stdout or a .dot file)."
        ),
        epilog=(
            "Marking selection (standalone Net sources only):\n"
            "  Default: render the authored initial marking. If none is declared, "
            "render an empty marking.\n"
            "  --marking NAME       Render authored named marking NAME. "
            "NAME is case-sensitive.\n"
            "  --marking-json JSON  Render one inline JSON marking object. "
            "No file or stdin indirection.\n"
            "  --no-marking         Omit marking detail. Mutually exclusive with "
            "--marking and --marking-json.\n"
            "\n"
            "Examples:\n"
            "  velocitron-viz design.petrinet\n"
            "  velocitron-viz design.petrinet --marking queued\n"
            "  velocitron-viz design.petrinet --marking-json "
            '\'{"request_in":[{"type":"request","data":{"id":"r-17"}}]}\'\n'
            "  velocitron-viz design.petrinet --no-marking\n"
            "  velocitron-viz design.petrinet --direction=lr\n"
            "\n"
            "Layout metrics (JSON on stdout):\n"
            "  velocitron-viz design.petrinet --metrics\n"
            "  velocitron-viz design.petrinet --metrics --view window\n"
            "  velocitron-viz --metrics -"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="Path to a Net or composition JSON/.petrinet document.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write DOT here instead of stdout.",
    )
    parser.add_argument(
        "--direction",
        "--rankdir",
        dest="rankdir",
        type=str.upper,
        choices=["TB", "LR", "BT", "RL"],
        metavar="{tb,lr,bt,rl}",
        help="Graph direction (default: tb).",
    )
    parser.add_argument(
        "--merged",
        action="store_true",
        help=(
            "For a composition: render the single merged net "
            "(place-fusion realization) instead of clusters + wires."
        ),
    )
    parser.add_argument(
        "--ports-only",
        action="store_true",
        help=(
            "For a composition: collapse each net to just its boundary "
            "ports — a compact wiring diagram of the cross-net topology."
        ),
    )
    parser.add_argument(
        "--overview",
        action="store_true",
        help=(
            "For a composition: one box per net, named by its description, "
            "with the wired places, the ends and the shared records between them."
        ),
    )
    marking_options = parser.add_mutually_exclusive_group()
    marking_options.add_argument(
        "--marking",
        metavar="NAME",
        help="Render authored named marking NAME (case-sensitive; standalone Nets only).",
    )
    marking_options.add_argument(
        "--marking-json",
        metavar="JSON",
        help="Render one inline JSON marking object (no file or stdin indirection).",
    )
    marking_options.add_argument(
        "--no-marking",
        action="store_true",
        help=(
            "Omit marking detail. Mutually exclusive with --marking and --marking-json."
        ),
    )
    parser.add_argument(
        "--plain-labels",
        action="store_true",
        help=(
            "Plain double-quoted labels instead of HTML-like labels "
            "(same content, readable DOT source)."
        ),
    )
    parser.add_argument(
        "--no-tooltips",
        action="store_true",
        help="Omit description tooltips from nodes and edges.",
    )
    parser.add_argument(
        "--doc",
        action="store_true",
        help=(
            "Markdown-embedding preset: --plain-labels --no-tooltips. "
            "Pair with --fence to emit a ready-to-paste code fence."
        ),
    )
    parser.add_argument(
        "--detail",
        choices=DETAIL_LEVELS,
        help=(
            "How much behavior labels show: full (every expression, wrapped; "
            "the default), summary (expressions cut to one line), or structure "
            "(no handlers, guards, timers, priorities, predicates, "
            "correlations or data templates)."
        ),
    )
    parser.add_argument(
        "--quiet-color",
        action="append",
        default=[],
        metavar="COLOR",
        help=(
            "Hide the type label on consume and produce arcs of COLOR "
            "(repeatable). Read and inhibit arcs keep theirs."
        ),
    )
    parser.add_argument(
        "--fence",
        action="store_true",
        help="Wrap the output in a ```dot markdown code fence.",
    )
    parser.add_argument(
        "--no-fusion",
        action="store_true",
        help=(
            "Deprecated. Render every fusion-annotated place as one ordinary "
            "node instead of per-transition copies. Still wins over "
            "`decorate (P) single` and `view V fusion (P) single`."
        ),
    )
    view_options = parser.add_mutually_exclusive_group()
    view_options.add_argument(
        "--view",
        help=(
            "Apply a named view from annotations['petrinet.dsl/v1'].views. "
            f"Without this flag, a view named {DEFAULT_VIEW!r} applies if it exists."
        ),
    )
    view_options.add_argument(
        "--no-view",
        action="store_true",
        help=f"Apply no view, not even the {DEFAULT_VIEW!r} view.",
    )
    parser.add_argument(
        "--legend",
        action="store_true",
        help="Emit the feature legend instead of rendering a document.",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help=(
            "Print layout metrics as JSON instead of DOT. "
            "Runs the Graphviz engine named in the DOT (dot, or neato when "
            "a view pins positions). With source -, read Graphviz -Tjson "
            "from stdin."
        ),
    )
    args = parser.parse_args(argv)

    if args.metrics and args.fence:
        parser.error("--fence cannot be combined with --metrics")
    if args.metrics and args.legend:
        parser.error("--legend cannot be combined with --metrics")
    if args.source is not None and str(args.source) == "-":
        if not args.metrics:
            parser.error("reading - requires --metrics")
        if args.legend or args.view is not None or args.no_view:
            parser.error("--metrics - reads Graphviz JSON and does not take a view")
        try:
            return _write_metrics(_measure_json(sys.stdin.read()), args.output)
        except _VizError as error:
            sys.stderr.write(f"velocitron-viz: error: {error}\n")
            return 1

    style = RenderStyle(
        html_labels=not (args.plain_labels or args.doc),
        tooltips=not (args.no_tooltips or args.doc),
        detail=args.detail or "full",
        quiet_colors=frozenset(args.quiet_color),
    )
    render_fusion = not args.no_fusion
    if args.no_fusion:
        sys.stderr.write(
            "velocitron-viz: warning: --no-fusion is deprecated; "
            "draw one fusion place as a single node with `decorate (P) single`, "
            "or in one view with `view V fusion (P) single`\n"
        )

    has_marking_selector = args.marking is not None or args.marking_json is not None
    if args.legend:
        if has_marking_selector:
            parser.error("--marking and --marking-json are invalid with --legend")
        dot = legend_dot(rankdir=args.rankdir or "LR")
    elif args.source is None:
        parser.error("a source document is required unless --legend is given")
    else:
        try:
            kind, document, raw_document = _load_document(args.source)
            include_marking = not args.no_marking
            if args.merged and args.ports_only:
                parser.error("--merged and --ports-only are mutually exclusive")
            if args.overview and (args.merged or args.ports_only):
                parser.error("--overview excludes --merged and --ports-only")
            if kind == "net":
                if args.merged:
                    parser.error("--merged only applies to composition documents")
                if args.ports_only:
                    parser.error("--ports-only only applies to composition documents")
                if args.overview:
                    parser.error("--overview only applies to composition documents")
                assert isinstance(document, Net)
                selected_marking: Marking | None = None
                if args.marking is not None:
                    selected_marking = _validate_selected_marking(
                        _named_marking(raw_document, args.marking), document
                    )
                elif args.marking_json is not None:
                    selected_marking = _validate_selected_marking(
                        _decode_json_object(
                            args.marking_json,
                            context="inline marking JSON",
                        ),
                        document,
                    )
                view_name = args.view
                if (
                    view_name is None
                    and not args.no_view
                    and has_view(raw_document, DEFAULT_VIEW)
                ):
                    view_name = DEFAULT_VIEW
                if view_name is not None and args.detail is None:
                    view_detail = view_setting(raw_document, view_name, "detail")
                    if view_detail is not None:
                        if view_detail not in DETAIL_LEVELS:
                            raise _VizError(
                                f"view {_json_quote(view_name)} has invalid detail "
                                f"{_json_quote(view_detail)}"
                            )
                        style = replace(style, detail=view_detail)
                decorations = read_decorations(raw_document)
                fusion_modes = (
                    read_fusion_modes(raw_document, view_name)
                    if view_name is not None
                    else {}
                )
                style = replace(
                    style,
                    quiet_colors=style.quiet_colors | decorations.quiet_colors,
                    shown_fields=decorations.shown_fields,
                )
                model = net_render_model(
                    document,
                    rankdir=args.rankdir or "TB",
                    include_marking=include_marking,
                    marking=selected_marking,
                    style=style,
                    render_fusion=render_fusion,
                    decorations=decorations,
                    fusion_modes=fusion_modes,
                )
                model = replace(
                    model,
                    dot=stamp_arc_ids(model, arc_handle_index(raw_document)),
                )
                if view_name is not None:
                    dot = apply_view(model, raw_document, view_name)
                else:
                    dot = model.dot
                if args.metrics:
                    return _write_metrics(_measure_dot(dot), args.output)
            else:
                if args.metrics:
                    raise _VizError("--metrics applies to a standalone net")
                assert isinstance(document, Composition)
                if has_marking_selector:
                    parser.error(
                        "--marking and --marking-json apply only to standalone Nets"
                    )
                if args.merged:
                    dot = net_to_dot(
                        _merge_validated(document),
                        rankdir=args.rankdir or "TB",
                        include_marking=include_marking,
                        style=style,
                        render_fusion=render_fusion,
                    )
                elif args.overview:
                    dot = composition_overview_dot(
                        document,
                        # No title for a stream such as /dev/stdin.
                        title=args.source.stem if args.source.suffix else None,
                        rankdir=args.rankdir or "TB",
                        style=style,
                    )
                elif args.ports_only:
                    dot = composition_ports_dot(
                        document,
                        rankdir=args.rankdir or "TB",
                        style=style,
                    )
                else:
                    dot = composition_to_dot(
                        document,
                        rankdir=args.rankdir or "TB",
                        include_marking=include_marking,
                        style=style,
                        render_fusion=render_fusion,
                    )
        except _VizError as error:
            sys.stderr.write(f"velocitron-viz: error: {error}\n")
            return 1
        except ValueError as error:
            sys.stderr.write(f"velocitron-viz: error: {error}\n")
            return 1

    if args.fence:
        dot = f"```dot\n{dot}```\n"

    try:
        if args.output is not None:
            args.output.write_text(dot, encoding="utf-8")
        else:
            sys.stdout.write(dot)
    except OSError:
        destination = args.output if args.output is not None else Path("<stdout>")
        sys.stderr.write(
            f"velocitron-viz: error: could not write output "
            f"{_json_quote(str(destination))}\n"
        )
        return 1
    return 0
