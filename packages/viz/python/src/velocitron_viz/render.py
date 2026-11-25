"""Graphviz DOT rendering for velocitron nets and compositions.

Renders a parsed :class:`~velocitron_engine.Net` or
:class:`~velocitron_engine.Composition` as a graphviz ``digraph`` covering
every net-schema feature (`spec/net-schema.md`, `spec/composition.md`):

- **Places** are ellipses labeled with their accepted token types; a selected
  marking renders bounded, deterministic complete-token detail inside each
  nonempty place.
- **Ports** (boundary places) are double-ringed and tinted — blue for
  ``input``, orange for ``output`` — with the port direction and type named
  on the node.
- **Transitions** are boxes naming their handler ref; a guarded transition
  gains a purple border and a ``guard:`` line; a declared ``priority``
  (honored by the built-in ``priority`` firing policy, ADR 0014) is shown
  grayed.
- **Consume arcs** are solid black edges labeled with the token type
  (``n × type`` when ``weight > 1``) and the predicate (inline CEL, or
  ``pred: name`` for a handler ref). ``mode: "inhibit"`` renders as the
  classic inhibitor glyph — crimson, dashed, open-dot arrowhead — labeled
  ``no type``; ``mode: "read"`` (test-without-consume) renders blue and
  dashed, labeled ``read``.
- **Produce arcs** are solid black edges labeled with the token type, plus a
  ``+ data`` line when the template carries a literal payload, or a
  ``+ data cel`` line (the DSL's ``data cel`` fact) when it carries a
  computed CEL fallback expression (ADR 0023).
- **Compositions** render each aliased net as a cluster and each wire as a
  bold purple edge between the two port places; ``merged=True`` renders the
  single fused net produced by :func:`velocitron_petrinet.merge_composition`
  instead, and :func:`composition_ports_dot` (CLI ``--ports-only``) collapses
  each net to just its boundary ports for a compact wiring diagram, and
  :func:`composition_overview_dot` (CLI ``--overview``) draws each net as one
  box named by its description, with the places between the nets.
- **Fusion places** (``annotations: {"fusion": true}`` — CONTEXT.md "Fusion
  place") render as a local dashed gray instance at each connected transition
  instead of one hub node with arcs radiating everywhere; ``render_fusion=
  False`` (CLI ``--no-fusion``) restores the single-node view.
- ``description`` fields become SVG tooltips on nodes and edges.
- **Views** (``--view <name>``, payload ``views[<name>]``: authored positions
  and handled-arc routes) are applied over a :class:`RenderModel`
  (:func:`net_render_model`) by :func:`velocitron_viz.apply_view`, never
  by splicing rendered text (ADR 0024). A view named ``default`` applies
  without the flag; ``--no-view`` turns it off.
- **Decorations** (payload ``decorations``, ADR 0028) apply with or without a
  view: a highlight fills a node or thickens an arc in amber, a note adds an
  italic line, a summary replaces expressions at ``summary`` detail, a
  quiet color loses its arc type labels, and ``beside`` keeps each fusion
  copy of a place on its transition's rank, next to it (``dot`` only; a
  view with positions drops it, ADR 0029). With no side, two neighbor
  transitions of one choice share one copy between them (ADR 0035).

Output is markdown-embeddable on request: :class:`RenderStyle` (CLI
``--plain-labels`` / ``--no-tooltips``, or the ``--doc`` preset) swaps the
HTML-like labels for plain quoted ones and drops tooltips, and ``--fence``
wraps the DOT in a ```` ```dot ```` code fence — so the CLI output can be
pasted into a markdown document unedited.

Inhibit arcs render as crimson dashed ``odot`` edges. Document loading
and the ``velocitron-viz`` console script stay in the language
implementation.
"""

from __future__ import annotations

import itertools
import json
import textwrap
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

from .canonical import render_canonical_json
from .schema import (
    Arc,
    Composition,
    ConsumePattern,
    Marking,
    Net,
    Place,
    Port,
    Predicate,
    ProduceTemplate,
    Token,
    Transition,
)
from .view import (
    Decoration,
    Decorations,
)


# ── Palette ──────────────────────────────────────────────────────────────

_INPUT_PORT_FILL = "#e7f1fb"
_INPUT_PORT_BORDER = "#1f6feb"
_OUTPUT_PORT_FILL = "#fff3e0"
_OUTPUT_PORT_BORDER = "#b45309"
_TRANSITION_FILL = "lightyellow"
_GUARD_BORDER = "#7b2d8b"
_READ_COLOR = "#1f6feb"
_INHIBIT_COLOR = "crimson"
_WIRE_COLOR = "#6a3d9a"
_MARKING_COLOR = "#1a7f37"
_MUTED = "#666666"
_FUSION_BORDER = "gray40"
_FUSION_FONT = "gray30"
_HIGHLIGHT_FILL = "#FFE08A"
_HIGHLIGHT_COLOR = "#D97706"
_NOTE_COLOR = "#0F766E"

_EXPRESSION_WRAP_CHARS = 60
_SUMMARY_MAX_CHARS = 48
_TOKEN_GROUP_LIMIT = 8
_TOKEN_TYPE_LIMIT = 64
_TOKEN_DATA_LIMIT = 160
_UNNAMED_NET_NAME = "unnamed"
_GENERIC_TOKEN_TYPE = "token"


# ── Render style ─────────────────────────────────────────────────────────

Detail = Literal["full", "summary", "structure"]
DETAIL_LEVELS: tuple[Detail, ...] = ("full", "summary", "structure")


@dataclass(frozen=True)
class RenderStyle:
    """Rendering options threaded through the attribute helpers.

    ``html_labels=False`` swaps the HTML-like labels for plain double-quoted
    ones — same content, far less markup — so the DOT source stays readable
    when embedded in a markdown document. ``tooltips=False`` omits the
    ``description`` tooltips (noise in embedded source; SVG-only anyway).
    The CLI exposes these as ``--plain-labels`` / ``--no-tooltips``, with
    ``--doc`` as the both-at-once preset.

    ``detail`` (CLI ``--detail``) sets how much behavior the labels show.
    ``full`` shows every expression whole, wrapped across lines.
    ``summary`` shortens predicates, correlations, timers and data templates
    to one line. ``structure`` drops handler refs, guards, timers,
    priorities, predicates, correlations and data templates, and keeps the
    topology, colors, weights and arc modes.

    ``quiet_colors`` (CLI ``--quiet-color``, DSL ``decorate color C quiet``)
    hides the type label on consume and produce arcs of those colors, as is
    always done for the Generic ``token`` color.

    ``shown_fields`` (DSL ``decorate color C show "f" …``) maps a color to
    the field paths its marking rows show; other colors show full data.
    """

    html_labels: bool = True
    tooltips: bool = True
    detail: Detail = "full"
    quiet_colors: frozenset[str] = frozenset()
    shown_fields: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )


_NO_DECORATION = Decoration()


_DEFAULT_STYLE = RenderStyle()


# ── Escaping ─────────────────────────────────────────────────────────────


def _quote(identifier: str) -> str:
    """Quote a DOT node ID (qualified names like ``alias.place`` need it)."""
    escaped = identifier.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dot_string(text: str) -> str:
    """Escape text for a double-quoted DOT attribute value (e.g. tooltip)."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _html(text: str) -> str:
    """Escape text for use inside an HTML-like label."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Label fragments ──────────────────────────────────────────────────────


def _truncate_display(text: str, limit: int) -> str:
    """Bound a display string by Unicode scalars without affecting semantics."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _escape(text: str, style: RenderStyle) -> str:
    """Escape text for the style's label mode (plain labels escape later)."""
    return _html(text) if style.html_labels else text


def _expression_text(text: str, style: RenderStyle) -> str:
    """An expression at the style's detail level, escaped for its label mode.

    ``full`` keeps every character and wraps at spaces so a long CEL
    expression does not stretch its node or edge; ``summary`` cuts it to one
    line ending in ``…``.
    """
    if style.detail == "summary":
        return _escape(_truncate_display(text, _SUMMARY_MAX_CHARS), style)
    return _wrapped_text(text, style)


def _wrapped_text(text: str, style: RenderStyle) -> str:
    """Text wrapped at spaces, every character kept, escaped for the label mode."""
    rows = textwrap.wrap(
        text,
        _EXPRESSION_WRAP_CHARS,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [text]
    separator = "<br/>" if style.html_labels else "\n"
    return separator.join(_escape(row, style) for row in rows)


_LABEL_CHAR_POINTS = 6
"""A generous width per character of a 9 pt bold label, in points."""

_UNPAIRED = "\0unpaired"
"""The ``twin_label`` of a node drawn outside a pair."""


def _decoration_lines(
    decoration: Decoration,
    style: RenderStyle,
    twin_label: str | None = _UNPAIRED,
) -> list[str]:
    """Label lines for a highlight label and a note, shown at every detail level.

    ``twin_label`` is the highlight label of the same node in the other half
    of a pair. When the two differ, both take a fixed-width cell, and a node
    with no label of its own gets the twin's in transparent ink, so twins
    keep one size.
    """
    lines: list[str] = []
    label_text = decoration.highlight_label
    if style.html_labels and twin_label != _UNPAIRED and twin_label != label_text:
        color = _FAILURE_COLOR if decoration.failure else _HIGHLIGHT_COLOR
        if label_text is None:
            color, label_text = "#00000000", twin_label
        assert label_text is not None
        width = _LABEL_CHAR_POINTS * max(len(label_text), len(twin_label or "")) + 4
        lines.append(
            '<table border="0" cellborder="0" cellspacing="0" cellpadding="0">'
            f'<tr><td fixedsize="true" width="{width}" height="12">'
            f'<font point-size="9" color="{color}"><b>{_html(label_text)}</b>'
            "</font></td></tr></table>"
        )
    elif label_text is not None:
        label = _escape(label_text, style)
        color = _FAILURE_COLOR if decoration.failure else _HIGHLIGHT_COLOR
        lines.append(
            f'<font point-size="9" color="{color}"><b>{label}</b></font>'
            if style.html_labels
            else label
        )
    if decoration.note is not None:
        lines.append(
            _small(
                _wrapped_text(decoration.note, style), _NOTE_COLOR, style, italic=True
            )
        )
    return lines


def _summary_line(decoration: Decoration, style: RenderStyle) -> str | None:
    """The authored summary, when the summary detail level should show it."""
    if style.detail != "summary" or decoration.summary is None:
        return None
    return _small(_wrapped_text(decoration.summary, style), _MUTED, style, italic=True)


def _small(text: str, color: str, style: RenderStyle, *, italic: bool = False) -> str:
    """A secondary label line: already-escaped text in a small colored font."""
    if not style.html_labels:
        return text
    body = f"<i>{text}</i>" if italic else text
    return f'<font point-size="9" color="{color}">{body}</font>'


def _break_after_commas(text: str) -> str:
    """Insert a line break after each JSON comma outside a quoted string.

    Wide inline token data (e.g. ``{"a":1,"b":2,...}``) otherwise renders as
    one unbroken line, stretching the node far past its neighbors.
    """
    pieces: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        pieces.append(char)
        if escaped:
            escaped = False
        elif char == "\\" and in_string:
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif char == "," and not in_string:
            pieces.append("\n")
    return "".join(pieces)


TokenMark = Literal["consumed", "produced", "read", "replaced", "injected"]
"""What one step did to one token, drawn on that token's marking row."""

TokenMarks = Mapping[str, Sequence["TokenMark | None"]]
"""Per place, one optional mark per token, aligned with the rendered
marking's token order for that place."""

TokenChanges = Mapping[str, Sequence[frozenset[str]]]
"""Per place, the field paths a step changed in each token, aligned like
:data:`TokenMarks`. A changed field is always shown, emphasized."""

# mark → (text color, row fill, struck through). Consumed is pink and
# produced light blue, a pair that color-blind readers tell apart; a read
# row has no fill and a dashed outline, so it differs by shape, not hue.
_TOKEN_MARK_STYLES: dict[str, tuple[str, str | None, bool]] = {
    "consumed": ("#9D174D", "#FBCFE8", True),
    "replaced": ("#9D174D", "#FBCFE8", True),
    "produced": ("#1E3A8A", "#BFDBFE", False),
    "injected": ("#1E3A8A", "#BFDBFE", False),
    "read": ("#374151", None, False),
}
_CHANGED_COLOR = "#B45309"
_FAILURE_FILL = "#FDE2E1"
_FAILURE_COLOR = "#B42318"
_FADED_COLOR = "#9CA3AF"
_FADED_FILL = "#F3F4F6"
_FIELD_LINE_CHARS = 48

Segment = tuple[str, bool]
"""A run of row text, and whether it is emphasized (a changed field)."""


@dataclass(frozen=True)
class MarkingRow:
    """One drawn marking row: a group of equal tokens, and its mark."""

    segments: tuple[Segment, ...]
    mark: TokenMark | None = None

    @property
    def text(self) -> str:
        return "".join(text for text, _ in self.segments)


def _field_value(data: Any, path: str) -> tuple[bool, Any]:
    value = data
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return False, None
        value = cast(Mapping[str, Any], value)[key]
    return True, value


def _field_text(value: Any) -> str:
    if isinstance(value, str) and value and "," not in value:
        return value
    return render_canonical_json(value)


def _token_segments(
    token: Token, fields: Sequence[str] | None, changed: frozenset[str]
) -> tuple[Segment, ...]:
    """A token's data: the chosen and changed fields, or its full JSON."""
    if fields is None:
        canonical = render_canonical_json(token.data)
        if canonical == "{}":
            return ()
        return (
            (
                " "
                + _break_after_commas(_truncate_display(canonical, _TOKEN_DATA_LIMIT)),
                False,
            ),
        )
    paths = [*fields, *sorted(p for p in changed if p not in fields)]
    parts: list[Segment] = []
    for path in paths:
        present, value = _field_value(token.data, path)
        if present:
            parts.append((f"{path}={_field_text(value)}", path in changed))
    if not parts:
        return ((" …", False),)
    segments: list[Segment] = []
    width = 0
    for index, (text, emphasized) in enumerate(parts):
        if index == 0:
            separator = " "
        elif width + len(text) + 3 > _FIELD_LINE_CHARS:
            separator, width = "\n", 0
        else:
            separator = " · "
        segments.append((separator, False))
        segments.append((text, emphasized))
        width += len(separator) + len(text)
    return tuple(segments)


def marking_rows(
    tokens: Sequence[Token],
    marks: Sequence[TokenMark | None] = (),
    changes: Sequence[frozenset[str]] = (),
    shown_fields: Mapping[str, Sequence[str]] | None = None,
) -> list[MarkingRow]:
    """The selected tokens as sorted, grouped rows.

    Tokens group by color, displayed data and mark, so a marked token keeps
    a row of its own next to an unmarked twin. A color in ``shown_fields``
    shows only those fields (dotted paths reach into nested objects) and the
    fields in ``changes``; any other color shows its full data.
    """
    shown = shown_fields or {}
    groups: dict[tuple[str, tuple[Segment, ...], str], int] = {}
    for position, token in enumerate(tokens):
        mark = marks[position] if position < len(marks) else None
        changed = changes[position] if position < len(changes) else frozenset[str]()
        segments = _token_segments(token, shown.get(token.type), changed)
        key = (token.type, segments, mark or "")
        groups[key] = groups.get(key, 0) + 1

    rows: list[MarkingRow] = []
    for index, ((type_, segments, mark), count) in enumerate(sorted(groups.items())):
        if index == _TOKEN_GROUP_LIMIT:
            remaining = len(groups) - index
            suffix = "group" if remaining == 1 else "groups"
            rows.append(MarkingRow(((f"… + {remaining} more token {suffix}", False),)))
            break
        display_type = (
            ""
            if type_ == _GENERIC_TOKEN_TYPE
            else f" {_truncate_display(type_, _TOKEN_TYPE_LIMIT)}"
        )
        prefix = "●" if count == 1 else f"● × {count}"
        rows.append(
            MarkingRow(
                ((f"{prefix}{display_type}", False), *segments),
                cast("TokenMark | None", mark or None),
            )
        )
    return rows


def _segments_html(segments: Sequence[Segment], *, ghost: bool) -> str:
    pieces: list[str] = []
    for text, emphasized in segments:
        body = _html(text).replace(chr(10), "<br/>")
        if emphasized:
            color = "#00000000" if ghost else _CHANGED_COLOR
            body = f'<font color="{color}"><b><u>{body}</u></b></font>'
        pieces.append(body)
    return "".join(pieces)


def _marked_row_html(row: MarkingRow, *, ghost: bool = False) -> str:
    """One marking row as an HTML table row, styled by its token mark.

    A ghost row has the same markup in transparent ink and no fill or
    outline: it takes the same space as the row it stands in for.
    """
    text = _segments_html(row.segments, ghost=ghost)
    mark = row.mark
    if mark is None:
        color = "#00000000" if ghost else _MARKING_COLOR
        return (
            f'<tr><td align="left"><font point-size="9" color="{color}">'
            f"{text}</font></td></tr>"
        )
    color, fill, struck = _TOKEN_MARK_STYLES[mark]
    body = f"<s>{text}</s>" if struck else f"<b>{text}</b>"
    cell = ['align="left"']
    if ghost:
        color = "#00000000"
    elif fill is not None:
        cell.append(f'bgcolor="{fill}"')
    else:
        cell.append(f'border="1" style="dashed" color="{color}"')
    if ghost and fill is None:
        cell.append('border="1" color="#00000000"')
    return (
        f'<tr><td {" ".join(cell)}><font point-size="9" '
        f'color="{color}">{body} <i>{mark}</i></font></td></tr>'
    )


def _marking_lines(
    tokens: Sequence[Token],
    style: RenderStyle = _DEFAULT_STYLE,
    marks: Sequence[TokenMark | None] = (),
    changes: Sequence[frozenset[str]] = (),
    rows: Sequence[tuple[MarkingRow, bool]] | None = None,
) -> list[str]:
    """Bounded token summaries for a selected Place marking.

    ``rows`` replaces the rows drawn from ``tokens``: each is a row and
    whether it is a ghost (see :func:`net_pair_dot`).
    """
    if rows is None:
        rows = [
            (row, False)
            for row in marking_rows(tokens, marks, changes, style.shown_fields)
        ]
    if not rows:
        return []
    if not style.html_labels:
        return [
            row.text if row.mark is None else f"{row.text} [{row.mark}]"
            for row, ghost in rows
            if not ghost
        ]
    html_rows = "".join(_marked_row_html(row, ghost=ghost) for row, ghost in rows)
    color = "#00000000" if all(ghost for _, ghost in rows) else _MARKING_COLOR
    return [
        f'<table border="1" cellborder="0" cellspacing="0" cellpadding="4" '
        f'style="rounded" color="{color}">{html_rows}</table>'
    ]


def _tokens_tooltip(tokens: Sequence[Token]) -> str:
    return "\n".join(
        render_canonical_json(token.data)
        if token.type == _GENERIC_TOKEN_TYPE
        else f"{token.type} {render_canonical_json(token.data)}"
        for token in tokens
    )


def _port_line(port: Port, style: RenderStyle = _DEFAULT_STYLE) -> str:
    type_suffix = "" if port.type == _GENERIC_TOKEN_TYPE else f" · {port.type}"
    if not style.html_labels:
        return f"port {port.direction}{type_suffix}"
    color = _INPUT_PORT_BORDER if port.direction == "input" else _OUTPUT_PORT_BORDER
    html_type_suffix = (
        "" if port.type == _GENERIC_TOKEN_TYPE else f" &#183; {_html(port.type)}"
    )
    return (
        f'<font point-size="9" color="{color}">'
        f"port {port.direction}{html_type_suffix}</font>"
    )


def _predicate_line(predicate: Predicate, style: RenderStyle = _DEFAULT_STYLE) -> str:
    if predicate.cel is not None:
        text = _expression_text(predicate.cel, style)
    else:
        text = _escape(f"pred: {predicate.handler}", style)
    return _small(text, _MUTED, style, italic=True)


def _tooltip_attr(description: str | None, style: RenderStyle = _DEFAULT_STYLE) -> str:
    """A leading-comma ``tooltip`` attribute, or empty when no description."""
    if not description or not style.tooltips:
        return ""
    return f', tooltip="{_dot_string(description)}"'


def _label_attr(lines: list[str], style: RenderStyle) -> str:
    """A ``label=`` attribute joining lines per the style's label mode."""
    if not style.html_labels:
        return f'label="{_dot_string(chr(10).join(lines))}"'
    # A Graphviz HTML-like label is EITHER a text run OR a single <table>;
    # top-level text cannot precede a <table>, and `dot` exits 1 on the
    # syntax error (strict backends such as Kroki then reject the graph).
    # The marking badge (`_marking_lines`) is the module's only <table>, so
    # when one is present wrap the whole label in a borderless outer table:
    # each text line becomes its own row above the badge's row. Without a
    # badge the plain <br/>-joined text run is already valid and unchanged.
    if not any(line.startswith("<table") for line in lines):
        return f"label=<{'<br/>'.join(lines)}>"
    cells = "".join(f'<tr><td align="center">{line}</td></tr>' for line in lines)
    return (
        'label=<<table border="0" cellborder="0" cellspacing="0" '
        f'cellpadding="0">{cells}</table>>'
    )


# ── Node attributes ──────────────────────────────────────────────────────


def _is_fusion(place: Place) -> bool:
    """Whether a place carries the ``annotations.fusion`` tag (CONTEXT.md
    "Fusion place"): one logical place, rendered as a local dashed instance
    at each transition that connects to it."""
    return bool(place.annotations and place.annotations.get("fusion"))


def _place_attrs(
    place: Place,
    tokens: Sequence[Token] = (),
    *,
    label: str | None = None,
    style: RenderStyle = _DEFAULT_STYLE,
    fusion: bool = False,
    decoration: Decoration = _NO_DECORATION,
    marks: Sequence[TokenMark | None] = (),
    changes: Sequence[frozenset[str]] = (),
    rows: Sequence[tuple[MarkingRow, bool]] | None = None,
    twin_label: str | None = _UNPAIRED,
) -> str:
    """Bracket contents for a place node (ellipse; ports double-ringed;
    ``fusion=True`` styles a local dashed fusion-place instance).

    The tooltip holds the place's description and every token's full data,
    which the label may abridge."""
    name = label or place.name
    accepted_colors = [type_ for type_ in place.accepts if type_ != _GENERIC_TOKEN_TYPE]
    if style.html_labels:
        lines = [f"<b>{_html(name)}</b>"]
        if accepted_colors:
            lines.append(
                f'<font point-size="9" color="{_MUTED}">'
                f"&#10216;{_html(', '.join(accepted_colors))}&#10217;</font>"
            )
    else:
        lines = [name]
        if accepted_colors:
            lines.append(f"⟨{', '.join(accepted_colors)}⟩")
    if place.port is not None:
        lines.append(_port_line(place.port, style))
    lines.extend(_decoration_lines(decoration, style, twin_label))
    lines.extend(_marking_lines(tokens, style, marks, changes, rows))
    attrs = f"shape=ellipse, {_label_attr(lines, style)}"
    if fusion:
        # A fusion instance is dashed and muted; the fusion styling replaces
        # the port tint (a fusion port would be pathological anyway).
        attrs += (
            f', class="fusion", style=dashed, color="{_FUSION_BORDER}", '
            f'fontcolor="{_FUSION_FONT}"'
        )
    elif place.port is not None:
        if place.port.direction == "input":
            fill, border = _INPUT_PORT_FILL, _INPUT_PORT_BORDER
        else:
            fill, border = _OUTPUT_PORT_FILL, _OUTPUT_PORT_BORDER
        attrs += f', peripheries=2, style=filled, fillcolor="{fill}", color="{border}"'
    if decoration.highlight:
        fill_style = '"dashed,filled"' if fusion else "filled"
        attrs += (
            f', style={fill_style}, fillcolor="{_HIGHLIGHT_FILL}", '
            f'color="{_HIGHLIGHT_COLOR}", penwidth=2'
        )
    tooltip = "\n\n".join(filter(None, [place.description, _tokens_tooltip(tokens)]))
    return attrs + _tooltip_attr(tooltip, style)


def _transition_attrs(
    transition: Transition,
    *,
    label: str | None = None,
    style: RenderStyle = _DEFAULT_STYLE,
    decoration: Decoration = _NO_DECORATION,
    twin_label: str | None = _UNPAIRED,
) -> str:
    """Bracket contents for a transition node (filled box; guard purpled).

    A faded transition shows only its name, in gray."""
    name = label or transition.name
    if decoration.faded:
        text = f"<b>{_html(name)}</b>" if style.html_labels else name
        return (
            f'shape=box, style="filled,dashed", fillcolor="{_FADED_FILL}", '
            f'color="{_FADED_COLOR}", fontcolor="{_FADED_COLOR}", '
            f"{_label_attr([text], style)}"
            + _tooltip_attr(transition.description, style)
        )
    lines = [f"<b>{_html(name)}</b>" if style.html_labels else name]
    summary = _summary_line(decoration, style)
    if style.detail != "structure":
        if transition.handler is not None:
            lines.append(
                _small(f"{_escape(transition.handler, style)}()", _MUTED, style)
            )
        if summary is not None:
            lines.append(summary)
        if transition.guard is not None and summary is None:
            lines.append(
                _small(
                    f"guard: {_escape(transition.guard, style)}?", _GUARD_BORDER, style
                )
            )
        if transition.timer is not None and summary is None:
            lines.append(
                _small(
                    f"timer: {_expression_text(transition.timer.cel, style)}",
                    _MUTED,
                    style,
                )
            )
        if transition.priority is not None and summary is None:
            lines.append(_small(f"priority {transition.priority}", _MUTED, style))
    lines.extend(_decoration_lines(decoration, style, twin_label))
    attrs = (
        f"shape=box, style=filled, fillcolor={_TRANSITION_FILL}, "
        f"{_label_attr(lines, style)}"
    )
    if transition.guard is not None:
        attrs += f', color="{_GUARD_BORDER}", penwidth=1.6'
    if decoration.failure:
        attrs += (
            f', fillcolor="{_FAILURE_FILL}", color="{_FAILURE_COLOR}", penwidth=2.5'
        )
    elif decoration.highlight:
        attrs += (
            f', fillcolor="{_HIGHLIGHT_FILL}", color="{_HIGHLIGHT_COLOR}", penwidth=2'
        )
    return attrs + _tooltip_attr(transition.description, style)


# ── Edge attributes ──────────────────────────────────────────────────────


def _consume_edge_attrs(
    pattern: ConsumePattern,
    description: str | None,
    style: RenderStyle = _DEFAULT_STYLE,
    decoration: Decoration = _NO_DECORATION,
) -> str:
    """Bracket contents for a consume-arc edge, styled by mode."""
    times = "&#215;" if style.html_labels else "×"
    generic = pattern.type == _GENERIC_TOKEN_TYPE
    hidden_type = generic or (
        pattern.mode == "consume" and pattern.type in style.quiet_colors
    )
    weight = f"{pattern.weight} {times} " if pattern.weight != 1 else ""
    type_ = (
        ""
        if hidden_type
        else (_html(pattern.type) if style.html_labels else pattern.type)
    )
    if pattern.mode == "inhibit":
        head = "no" if generic else f"no {type_}"
        edge_style = f'arrowhead=odot, color="{_INHIBIT_COLOR}", style=dashed'
        if style.html_labels:
            head = f'<font color="{_INHIBIT_COLOR}">{head}</font>'
    elif pattern.mode == "read":
        head = f"read {weight}{type_}".rstrip()
        edge_style = f'color="{_READ_COLOR}", style=dashed'
        if style.html_labels:
            head = f'<font color="{_READ_COLOR}">{head}</font>'
    else:
        head = f"{weight}{type_}".rstrip()
        edge_style = ""
    if style.html_labels and head:
        head = f'<font point-size="10">{head}</font>'
    lines = [head] if head else []
    summary = _summary_line(decoration, style)
    if summary is not None:
        lines.append(summary)
    elif style.detail != "structure":
        if pattern.predicate is not None:
            lines.append(_predicate_line(pattern.predicate, style))
        if pattern.correlate is not None:
            lines.append(
                _small(
                    _expression_text(pattern.correlate, style),
                    _MUTED,
                    style,
                    italic=True,
                )
            )
    lines.extend(_decoration_lines(decoration, style))
    attrs = _label_attr(lines, style) if lines else ""
    if edge_style:
        attrs += f", {edge_style}" if attrs else edge_style
    attrs = _highlight_edge(attrs, decoration)
    tooltip = _tooltip_attr(description, style)
    return attrs + tooltip if attrs else tooltip.removeprefix(", ")


def _highlight_edge(attrs: str, decoration: Decoration) -> str:
    """Append the highlight pen; a later DOT attribute overrides an earlier one."""
    if not decoration.highlight:
        return attrs
    highlight = f'color="{_HIGHLIGHT_COLOR}", penwidth=2.5'
    return f"{attrs}, {highlight}" if attrs else highlight


def _produce_edge_attrs(
    template: ProduceTemplate,
    description: str | None,
    style: RenderStyle = _DEFAULT_STYLE,
    decoration: Decoration = _NO_DECORATION,
) -> str:
    """Bracket contents for a produce-arc edge."""
    if template.type == _GENERIC_TOKEN_TYPE or template.type in style.quiet_colors:
        lines = []
    elif style.html_labels:
        lines = [f'<font point-size="10">{_html(template.type)}</font>']
    else:
        lines = [template.type]
    summary = _summary_line(decoration, style)
    if summary is not None:
        lines.append(summary)
    elif style.detail != "structure":
        if template.data is not None:
            data = _expression_text(f"+ data {json.dumps(template.data)}", style)
            lines.append(_small(data, _MUTED, style, italic=True))
        elif template.cel is not None:
            data = _expression_text(f"+ data cel {template.cel}", style)
            lines.append(_small(data, _MUTED, style, italic=True))
    lines.extend(_decoration_lines(decoration, style))
    attrs = _highlight_edge(_label_attr(lines, style) if lines else "", decoration)
    tooltip = _tooltip_attr(description, style)
    return attrs + tooltip if attrs else tooltip.removeprefix(", ")


_WIRE_ATTRS = f'penwidth=2.2, color="{_WIRE_COLOR}"'
# A share has no direction (ADR 0040): a dashed line, no arrowhead.
_SHARE_ATTRS = f'penwidth=2.2, color="{_WIRE_COLOR}", style=dashed, dir=none'


# ── Graph assembly ───────────────────────────────────────────────────────

_GRAPH_DEFAULTS = [
    '    node [fontname="Helvetica"];',
    '    edge [fontname="Helvetica", fontsize=10];',
]


@dataclass(frozen=True)
class RenderModel:
    """Structural index of one rendered standalone net (ADR 0024).

    The view application pass (:mod:`velocitron_viz`) consults this
    instead of parsing rendered DOT text: ``node_lines`` maps a
    ``"place:<name>"`` / ``"transition:<name>"`` subject key to the statement
    line indexes of that node's canonical statement plus every fusion
    instance, ``arc_lines`` maps each arc's declaration index to its edge
    statement line, and ``graph_attr_line`` is the semantically valid line for
    inserting graph-level attributes (e.g. ``splines=ortho`` — after the
    graph defaults, before the body). ``beside_lines`` are the statements
    that keep ``beside`` fusion copies next to their transitions. Line
    indexes refer to ``dot``.
    """

    dot: str
    node_lines: Mapping[str, tuple[int, ...]]
    arc_lines: tuple[int, ...]
    graph_attr_line: int
    beside_lines: tuple[int, ...] = ()


class _RenderIndex:
    """Mutable statement recorder threaded through rendering.

    ``_net_body`` reports each authored element's statement position as it
    emits; ``net_render_model`` offsets the positions into full-text line
    numbers. No renderer output changes as a result.
    """

    def __init__(self, offset: int):
        self.node_lines: dict[str, list[int]] = {}
        self.arc_lines: list[int] = []
        self.beside_lines: list[int] = []
        self.offset = offset

    def record_node(self, key: str, position: int) -> None:
        self.node_lines.setdefault(key, []).append(self.offset + position)

    def record_arc(self, index: int, position: int) -> None:
        """Record ``net.arcs[index]``'s edge line. Emission order is not index order."""
        if len(self.arc_lines) <= index:
            self.arc_lines.extend([-1] * (index + 1 - len(self.arc_lines)))
        self.arc_lines[index] = self.offset + position

    def record_beside(self, position: int) -> None:
        self.beside_lines.append(self.offset + position)


def _arc_edge(
    arc: Arc,
    indent: str = "    ",
    prefix: str = "",
    *,
    style: RenderStyle = _DEFAULT_STYLE,
    copies: Mapping[tuple[str, str], str] | None = None,
    beside_copies: AbstractSet[str] = frozenset(),
    decoration: Decoration = _NO_DECORATION,
) -> str:
    """One DOT edge statement for an arc (consume or produce).

    An endpoint whose (place, transition) pair is in ``copies`` is rewritten
    to that fusion copy's node id; an arc to a copy in ``beside_copies``
    leaves its rank and order to the beside row.
    """
    copy_ids = copies or {}
    if arc.consume is not None:
        assert arc.from_place is not None and arc.to_transition is not None
        from_place = copy_ids.get((arc.from_place, arc.to_transition), arc.from_place)
        source = _quote(f"{prefix}{from_place}")
        target = _quote(f"{prefix}{arc.to_transition}")
        attrs = _consume_edge_attrs(arc.consume, arc.description, style, decoration)
        place_node = from_place
    else:
        assert arc.produce is not None
        assert arc.to_place is not None and arc.from_transition is not None
        to_place = copy_ids.get((arc.to_place, arc.from_transition), arc.to_place)
        source = _quote(f"{prefix}{arc.from_transition}")
        target = _quote(f"{prefix}{to_place}")
        attrs = _produce_edge_attrs(arc.produce, arc.description, style, decoration)
        place_node = to_place
    if decoration.faded:
        # A faded arc only shows that the neighbor is there: no label.
        dashed = arc.consume is not None and arc.consume.mode != "consume"
        attrs = f'color="{_FADED_COLOR}"' + (", style=dashed" if dashed else "")
        if arc.consume is not None and arc.consume.mode == "inhibit":
            attrs += ", arrowhead=odot"
    if place_node in beside_copies:
        # The beside row's invisible chain already fixes this arc's rank and
        # order. A write to a left copy runs against the chain, and dot
        # breaks that cycle by moving the copy to the other side.
        attrs = f"{attrs}, constraint=false" if attrs else "constraint=false"
    if attrs:
        return f"{indent}{source} -> {target} [{attrs}];"
    return f"{indent}{source} -> {target};"


def member_label(place: str, transition: Transition | None = None) -> str:
    """A merged place's name as one of its members' qualified names.

    A merge names a fused place by joining its members' names with ``__``
    (:func:`velocitron_petrinet.merge_nets`). Next to ``transition`` the
    label is the member in that transition's own net, the name its CEL
    reads the place by; elsewhere it is the first member, the one whose
    description the fused place keeps. Any other place keeps its name.
    """
    members = place.split("__")
    if transition is not None and "." in transition.name:
        alias = transition.name.rsplit(".", 1)[0]
        for key, bound in (transition.binding_names or {}).items():
            if bound == place:
                return f"{alias}.{key}"
        for member in members:
            local = member.removeprefix(f"{alias}.")
            if local != member and "." not in local:
                return member
    return members[0]


def _flow_ranks(net: Net) -> dict[tuple[str, str], int]:
    """Distance of each place and transition from the initial marking.

    Rank 0 is a place that holds a token in the initial marking, a place
    nothing produces, or a transition with no input. Every other node is one
    step farther than the nearest of those, along consume, read, inhibit, and
    produce arcs. A component that has none of those starts is walked from
    its alphabetically first node and ranked after everything already
    reached. The same names always get the same ranks: declaration order is
    not an input (ADR 0067).
    """
    place_names = [place.name for place in net.places]
    transition_names = [transition.name for transition in net.transitions]
    places = set(place_names)
    transitions = set(transition_names)
    place_out: dict[str, set[str]] = {name: set() for name in place_names}
    transition_out: dict[str, set[str]] = {name: set() for name in transition_names}
    place_in = {name: 0 for name in place_names}
    transition_in = {name: 0 for name in transition_names}
    for arc in net.arcs:
        if (
            arc.consume is not None
            and arc.from_place in places
            and arc.to_transition in transitions
        ):
            place_out[arc.from_place].add(arc.to_transition)
            transition_in[arc.to_transition] += 1
        elif (
            arc.produce is not None
            and arc.from_transition in transitions
            and arc.to_place in places
        ):
            transition_out[arc.from_transition].add(arc.to_place)
            place_in[arc.to_place] += 1

    ranks: dict[tuple[str, str], int] = {}
    queue: deque[tuple[str, str]] = deque()

    def seed(kind: str, name: str, rank: int) -> None:
        key = (kind, name)
        if key in ranks:
            return
        ranks[key] = rank
        queue.append(key)

    def expand() -> None:
        while queue:
            kind, name = queue.popleft()
            rank = ranks[(kind, name)]
            if kind == "place":
                nxt_kind, nxts = "transition", sorted(place_out[name])
            else:
                nxt_kind, nxts = "place", sorted(transition_out[name])
            for nxt in nxts:
                key = (nxt_kind, nxt)
                if key not in ranks:
                    ranks[key] = rank + 1
                    queue.append(key)

    marked: set[str] = set()
    if net.initial_marking:
        for name, tokens in net.initial_marking.items():
            if tokens and name in places:
                marked.add(name)
    for name in sorted(marked | {name for name in place_names if place_in[name] == 0}):
        seed("place", name, 0)
    for name in sorted(name for name in transition_names if transition_in[name] == 0):
        seed("transition", name, 0)
    expand()
    while True:
        missing = [
            ("place", name) for name in place_names if ("place", name) not in ranks
        ] + [
            ("transition", name)
            for name in transition_names
            if ("transition", name) not in ranks
        ]
        if not missing:
            return ranks
        missing.sort(key=lambda item: (item[1], item[0]))
        base = max(ranks.values()) + 1 if ranks else 0
        seed(missing[0][0], missing[0][1], base)
        expand()


def _node_order(kind: str, name: str, ranks: Mapping[tuple[str, str], int]) -> tuple[int, str]:
    return (ranks[(kind, name)], name)


def _decoration_order_key(decoration: Decoration) -> tuple[bool, bool, bool, str, str, str]:
    return (
        decoration.faded,
        decoration.failure,
        decoration.highlight,
        decoration.highlight_label or "",
        decoration.note or "",
        decoration.summary or "",
    )


def _arc_order_key(
    arc: Arc, ranks: Mapping[tuple[str, str], int], decoration: Decoration
) -> tuple[object, ...]:
    """Structural sort key for one edge statement. Ties render the same line."""
    if arc.consume is not None:
        source = ("place", arc.from_place or "")
        target = ("transition", arc.to_transition or "")
        predicate = arc.consume.predicate
        detail: tuple[object, ...] = (
            "consume",
            arc.consume.mode,
            arc.consume.type,
            arc.consume.weight,
            "" if predicate is None else (predicate.cel or ""),
            "" if predicate is None else (predicate.handler or ""),
            arc.consume.correlate or "",
            "",
            "",
        )
    else:
        source = ("transition", arc.from_transition or "")
        target = ("place", arc.to_place or "")
        template = arc.produce
        assert template is not None
        data = (
            ""
            if template.data is None
            else json.dumps(template.data, ensure_ascii=False)
        )
        detail = ("produce", "produce", template.type, 0, "", "", "", data, template.cel or "")

    def endpoint(kind_name: tuple[str, str]) -> tuple[int, str]:
        if kind_name in ranks:
            return _node_order(kind_name[0], kind_name[1], ranks)
        return (10**9, kind_name[1])

    return (
        *endpoint(source),
        *endpoint(target),
        *detail,
        arc.description or "",
        _decoration_order_key(decoration),
    )


def _fusion_instances(
    net: Net, fusion: set[str], ranks: Mapping[tuple[str, str], int]
) -> list[tuple[str, str]]:
    """(place, transition) pairs needing a local fusion instance.

    A transition that touches the place via several arcs (inhibit and
    produce, for example) shares one instance. The pairs come back in
    structural order, not arc order.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for arc in net.arcs:
        if arc.from_place in fusion:
            assert arc.to_transition is not None
            pair = (arc.from_place, arc.to_transition)
        elif arc.to_place in fusion:
            assert arc.from_transition is not None
            pair = (arc.to_place, arc.from_transition)
        else:
            continue
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    pairs.sort(
        key=lambda pair: (
            *_node_order("place", pair[0], ranks),
            *_node_order("transition", pair[1], ranks),
        )
    )
    return pairs


def sibling_groups(net: Net, fusion: AbstractSet[str]) -> list[tuple[str, ...]]:
    """Choices: transitions whose one drawn input place is the same place.

    Fusion places do not count as inputs, since each copy sits beside its
    own transition. A group lists its transitions in structural order
    (:func:`_flow_ranks`, then name); groups follow their place's structural
    order. Only groups of two or more are returned.
    """
    ranks = _flow_ranks(net)
    inputs: dict[str, set[str]] = {}
    for arc in net.arcs:
        place, transition = arc.from_place, arc.to_transition
        if place is None or transition is None or place in fusion:
            continue
        inputs.setdefault(transition, set()).add(place)
    groups: dict[str, list[str]] = {}
    for transition, places in inputs.items():
        if len(places) == 1:
            place = next(iter(places))
            groups.setdefault(place, []).append(transition)
    ordered = [
        (
            place,
            tuple(sorted(names, key=lambda name: _node_order("transition", name, ranks))),
        )
        for place, names in groups.items()
        if len(names) > 1
    ]
    ordered.sort(key=lambda item: _node_order("place", item[0], ranks))
    return [names for _, names in ordered]


@dataclass(frozen=True)
class FusionLayout:
    """Where the fusion copies of one render go (ADR 0029, ADR 0035).

    ``copies`` maps each (place, transition) pair with a fusion copy to the
    copy's node id; a shared copy has one id for two pairs. ``rows`` are the
    ``beside`` rows, left to right, of transition names and copy ids.
    """

    copies: Mapping[tuple[str, str], str]
    rows: tuple[tuple[str, ...], ...]


def _copy_id(place: str, transitions: Sequence[str]) -> str:
    return f"{place}@{'+'.join(transitions)}"


def fusion_layout(
    net: Net, fusion: AbstractSet[str], decorations: Decorations
) -> FusionLayout:
    """The fusion copies of ``net`` and the ``beside`` rows that place them.

    Each transition with ``beside`` copies gets a row: ``left`` copies
    before it, ``right`` copies after it, the first copy in structural
    order nearest; a copy with no side goes to the side that has fewer
    copies so far, ``left`` on a tie (ADR 0029, ADR 0067).

    Two transitions that are neighbors in a sibling group (see
    :func:`sibling_groups`) and both have a copy of the same ``beside``
    place with no side share one copy, drawn between them (ADR 0035). A run
    of more such neighbors pairs from the left; when the run is odd, the
    last one keeps its own copy, on its right. The transitions a run links
    share one row, in group order, so the shared copy is always between
    its two transitions.
    """
    ranks = _flow_ranks(net)
    instances = _fusion_instances(net, set(fusion), ranks)

    def beside(place: str) -> Decoration | None:
        decoration = decorations.nodes.get(f"place:{place}", _NO_DECORATION)
        return decoration if decoration.beside else None

    beside_places: dict[str, list[str]] = {}
    for place, transition in instances:
        if beside(place) is not None:
            beside_places.setdefault(transition, []).append(place)

    shared: dict[tuple[str, str], str] = {}
    gaps: dict[tuple[str, str], list[str]] = {}
    outer_right: set[tuple[str, str]] = set()
    segments: list[tuple[str, ...]] = []
    for group in sibling_groups(net, fusion):
        linked = [False] * (len(group) - 1)
        places = sorted(
            {
                place
                for transition in group
                for place in beside_places.get(transition, ())
            },
            key=lambda place: _node_order("place", place, ranks),
        )
        for place in places:
            decoration = beside(place)
            if decoration is None or decoration.beside_side is not None:
                continue
            start = 0
            while start < len(group):
                end = start
                while end < len(group) and place in beside_places.get(group[end], ()):
                    end += 1
                run = group[start:end]
                for i in range(0, len(run) - 1, 2):
                    pair = run[i], run[i + 1]
                    copy = _copy_id(place, pair)
                    shared[(place, pair[0])] = shared[(place, pair[1])] = copy
                    gaps.setdefault(pair, []).append(place)
                if len(run) > 1:
                    linked[start : end - 1] = [True] * (len(run) - 1)
                    if len(run) % 2:
                        outer_right.add((place, run[-1]))
                start = end + 1 if end == start else end
        first = 0
        for i in range(len(group)):
            if i == len(group) - 1 or not linked[i]:
                if i > first:
                    segments.append(group[first : i + 1])
                first = i + 1

    segment_of = {t: index for index, segment in enumerate(segments) for t in segment}

    def row(transitions: Sequence[str]) -> tuple[str, ...]:
        order: list[str] = []
        for index, transition in enumerate(transitions):
            before = transitions[index - 1] if index > 0 else None
            after = transitions[index + 1] if index + 1 < len(transitions) else None
            # A shared copy counts on both of its transitions' sides.
            left: list[str] = []
            right: list[str] = []
            shared_left = len(gaps.get((before, transition), ())) if before else 0
            shared_right = len(gaps.get((transition, after), ())) if after else 0
            for place in beside_places[transition]:
                if (place, transition) in shared:
                    continue
                decoration = beside(place)
                assert decoration is not None
                side = decoration.beside_side or (
                    "right"
                    if (place, transition) in outer_right
                    else "left"
                    if len(left) + shared_left <= len(right) + shared_right
                    else "right"
                )
                (left if side == "left" else right).append(
                    _copy_id(place, [transition])
                )
            order.extend([*reversed(left), transition, *right])
            if after is not None:
                order.extend(
                    _copy_id(place, (transition, after))
                    for place in gaps.get((transition, after), ())
                )
        return tuple(order)

    for transition, places_beside in beside_places.items():
        places_beside.sort(key=lambda place: _node_order("place", place, ranks))
    rows: dict[str | int, tuple[str, ...]] = {}
    for transition in beside_places:
        key = segment_of.get(transition, transition)
        if key not in rows:
            rows[key] = row(
                segments[segment_of[transition]]
                if transition in segment_of
                else (transition,)
            )
    transition_names = {transition.name for transition in net.transitions}

    def _row_key(nodes: tuple[str, ...]) -> tuple[int, str]:
        for node in nodes:
            if node in transition_names:
                return _node_order("transition", node, ranks)
        return (10**9, "")

    copies = {
        (place, transition): shared.get(
            (place, transition), _copy_id(place, [transition])
        )
        for place, transition in instances
    }
    return FusionLayout(copies=copies, rows=tuple(sorted(rows.values(), key=_row_key)))


def _beside_statements(layout: FusionLayout, *, indent: str, prefix: str) -> list[str]:
    """Statements that keep each ``beside`` row together, in its order.

    Each row gets an invisible cluster around a ``rank=same`` group, so
    its nodes share a rank and no other node lands between them, and an
    invisible edge chain that fixes their order across the rank.
    """
    if not layout.rows:
        return []
    # Clusters are ranked on their own unless the whole graph is ranked at
    # once; without newrank a cluster can pull its transition above its inputs.
    statements = [f"{indent}newrank=true;"]
    # dot's last crossing pass, over the whole graph, can rotate a cluster's
    # row and break its invisible chain (ADR 0035 Decision 3).
    statements.append(f"{indent}remincross=false;")
    for index, row in enumerate(layout.rows):
        order = [_quote(f"{prefix}{node}") for node in row]
        # The prefix keeps the cluster names of two renders in one graph apart.
        statements.append(
            f'{indent}subgraph "cluster_{prefix}beside_{index}" '
            f'{{ label=""; peripheries=0; margin=0; {{ rank=same; {"; ".join(order)}; }} }}'
        )
        statements.append(f"{indent}{' -> '.join(order)} [style=invis];")
    return statements


def _net_body(
    net: Net,
    *,
    indent: str = "    ",
    prefix: str = "",
    include_marking: bool = True,
    marking: Marking | None = None,
    style: RenderStyle = _DEFAULT_STYLE,
    render_fusion: bool = True,
    recorder: _RenderIndex | None = None,
    decorations: Decorations = Decorations(),
    token_marks: TokenMarks | None = None,
    token_changes: TokenChanges | None = None,
    marking_rows: Mapping[str, Sequence[tuple[MarkingRow, bool]]] | None = None,
    twin_labels: Mapping[str, str | None] | None = None,
) -> list[str]:
    """Node and edge statements for one net, optionally name-prefixed.

    When ``recorder`` is given, each statement's position is reported as it
    is emitted, so ``net_render_model`` can index the rendered text by
    authored element (ADR 0024). ``marking_rows`` (by place) and
    ``twin_labels`` (by node key) are the per-half facts of a pair render.
    """

    def _node_decoration(key: str) -> Decoration:
        return decorations.nodes.get(key, _NO_DECORATION)

    def _marks(place: Place) -> Sequence[TokenMark | None]:
        if token_marks is None:
            return ()
        return token_marks.get(place.name, ())

    def _changes(place: Place) -> Sequence[frozenset[str]]:
        if token_changes is None:
            return ()
        return token_changes.get(place.name, ())

    def _rows(place: Place) -> Sequence[tuple[MarkingRow, bool]] | None:
        if marking_rows is None:
            return None
        return marking_rows.get(place.name, ())

    def _twin(key: str) -> str | None:
        return _UNPAIRED if twin_labels is None else twin_labels.get(key)

    selected_marking = (
        (marking if marking is not None else net.initial_marking)
        if include_marking
        else None
    )
    fusion: set[str] = (
        {p.name for p in net.places if _is_fusion(p)} if render_fusion else set()
    )

    def _tokens(place: Place) -> Sequence[Token]:
        if selected_marking is not None and place.name in selected_marking:
            return selected_marking[place.name]
        return ()

    lines: list[str] = []
    ranks = _flow_ranks(net)
    for place in sorted(net.places, key=lambda place: _node_order("place", place.name, ranks)):
        if place.name in fusion:
            continue  # rendered as local instances below
        node = _quote(f"{prefix}{place.name}")
        if recorder is not None:
            recorder.record_node(f"place:{place.name}", len(lines))
        attrs = _place_attrs(
            place,
            _tokens(place),
            label=member_label(place.name),
            style=style,
            decoration=_node_decoration(f"place:{place.name}"),
            marks=_marks(place),
            changes=_changes(place),
            rows=_rows(place),
            twin_label=_twin(f"place:{place.name}"),
        )
        lines.append(f"{indent}{node} [{attrs}];")
    lines.append("")
    for transition in sorted(
        net.transitions, key=lambda transition: _node_order("transition", transition.name, ranks)
    ):
        node = _quote(f"{prefix}{transition.name}")
        if recorder is not None:
            recorder.record_node(f"transition:{transition.name}", len(lines))
        attrs = _transition_attrs(
            transition,
            style=style,
            decoration=_node_decoration(f"transition:{transition.name}"),
            twin_label=_twin(f"transition:{transition.name}"),
        )
        lines.append(f"{indent}{node} [{attrs}];")
    lines.append("")
    layout = fusion_layout(net, fusion, decorations)
    if fusion:
        place_by_name = {p.name: p for p in net.places}
        drawn: set[str] = set()
        transition_by_name = {t.name: t for t in net.transitions}
        copy_order = sorted(
            layout.copies.items(),
            key=lambda item: (
                *_node_order("place", item[0][0], ranks),
                *_node_order("transition", item[0][1], ranks),
            ),
        )
        for (place_name, transition_name), copy in copy_order:
            if copy in drawn:
                continue
            drawn.add(copy)
            place = place_by_name[place_name]
            node = _quote(f"{prefix}{copy}")
            if recorder is not None:
                recorder.record_node(f"place:{place_name}", len(lines))
            attrs = _place_attrs(
                place,
                _tokens(place),
                label=member_label(place_name, transition_by_name.get(transition_name)),
                style=style,
                fusion=True,
                decoration=_node_decoration(f"place:{place_name}"),
                marks=_marks(place),
                changes=_changes(place),
                rows=_rows(place),
                twin_label=_twin(f"place:{place_name}"),
            )
            lines.append(f"{indent}{node} [{attrs}];")
        lines.append("")
    beside_copies = set(itertools.chain.from_iterable(layout.rows)) - {
        transition.name for transition in net.transitions
    }
    arc_order = sorted(
        range(len(net.arcs)),
        key=lambda index: _arc_order_key(
            net.arcs[index], ranks, decorations.arcs.get(index, _NO_DECORATION)
        ),
    )
    for index in arc_order:
        arc = net.arcs[index]
        lines.append(
            _arc_edge(
                arc,
                indent,
                prefix,
                style=style,
                copies=layout.copies,
                beside_copies=beside_copies,
                decoration=decorations.arcs.get(index, _NO_DECORATION),
            )
        )
        if recorder is not None:
            recorder.record_arc(index, len(lines) - 1)
    beside_lines = _beside_statements(layout, indent=indent, prefix=prefix)
    for statement in beside_lines:
        if recorder is not None:
            recorder.record_beside(len(lines))
        lines.append(statement)
    return lines


def net_render_model(
    net: Net,
    *,
    rankdir: str = "TB",
    include_marking: bool = True,
    marking: Marking | None = None,
    style: RenderStyle = _DEFAULT_STYLE,
    render_fusion: bool = True,
    decorations: Decorations = Decorations(),
    token_marks: TokenMarks | None = None,
    token_changes: TokenChanges | None = None,
) -> RenderModel:
    """Render a standalone net and return it with its structural index (ADR 0024).

    Same options and output as :func:`net_to_dot`; the returned
    :class:`RenderModel` additionally indexes which statement line carries
    each authored element, which is what the view application pass
    (:func:`velocitron_viz.apply_view`) consults.

    ``token_marks`` styles single marking rows (consumed, produced, read,
    replaced, injected), as a play walkthrough draws one step;
    ``token_changes`` emphasizes the fields a step changed.
    """
    recorder = _RenderIndex(offset=0)
    header = [
        "digraph net {",
        f"    rankdir={rankdir};",
    ]
    if net.name != _UNNAMED_NET_NAME:
        if style.html_labels:
            title = f"label=<<b>{_html(net.name)}</b>>; labelloc=t;"
        else:
            title = f'label="{_dot_string(net.name)}"; labelloc=t;'
        header.append(f"    {title}")
    header.extend(_GRAPH_DEFAULTS)
    # the blank separator joins header and body: body line i lives at
    # len(header) + 1 + i in the full text
    recorder.offset = len(header) + 1
    graph_attr_line = len(header)
    dot = (
        "\n".join(
            [
                *header,
                "",
                *_net_body(
                    net,
                    include_marking=include_marking,
                    marking=marking,
                    style=style,
                    render_fusion=render_fusion,
                    recorder=recorder,
                    decorations=decorations,
                    token_marks=token_marks,
                    token_changes=token_changes,
                ),
                "}",
            ]
        )
        + "\n"
    )
    return RenderModel(
        dot=dot,
        node_lines={
            key: tuple(indexes) for key, indexes in recorder.node_lines.items()
        },
        arc_lines=tuple(recorder.arc_lines),
        graph_attr_line=graph_attr_line,
        beside_lines=tuple(recorder.beside_lines),
    )


def net_to_dot(
    net: Net,
    *,
    rankdir: str = "TB",
    include_marking: bool = True,
    marking: Marking | None = None,
    style: RenderStyle = _DEFAULT_STYLE,
    render_fusion: bool = True,
    decorations: Decorations = Decorations(),
    token_marks: TokenMarks | None = None,
    token_changes: TokenChanges | None = None,
) -> str:
    """Render a standalone net, optionally replacing its default marking."""
    return net_render_model(
        net,
        rankdir=rankdir,
        include_marking=include_marking,
        marking=marking,
        style=style,
        render_fusion=render_fusion,
        decorations=decorations,
        token_marks=token_marks,
        token_changes=token_changes,
    ).dot


@dataclass(frozen=True)
class PairSide:
    """One half of :func:`net_pair_dot`: a label, a marking, and what to draw
    on it."""

    label: str
    marking: Marking
    decorations: Decorations = Decorations()
    token_marks: TokenMarks | None = None
    token_changes: TokenChanges | None = None


def _side_rows(place: str, side: PairSide, style: RenderStyle) -> list[MarkingRow]:
    marks = side.token_marks.get(place, ()) if side.token_marks else ()
    changes = side.token_changes.get(place, ()) if side.token_changes else ()
    return marking_rows(side.marking.get(place, ()), marks, changes, style.shown_fields)


def _twin_rows(
    before: list[MarkingRow], after: list[MarkingRow]
) -> tuple[list[tuple[MarkingRow, bool]], list[tuple[MarkingRow, bool]]]:
    """Both halves' rows for one place, in one order, padded with ghosts.

    Rows drawn in both halves come first, then the rows only ``before``
    draws, then the rows only ``after`` draws. Each half draws the other's
    own rows as ghosts, so the place has the same label size in both.
    """
    remaining = list(after)
    common: list[MarkingRow] = []
    before_only: list[MarkingRow] = []
    for row in before:
        if row in remaining:
            remaining.remove(row)
            common.append(row)
        else:
            before_only.append(row)
    shared = [(row, False) for row in common]
    return (
        shared
        + [(row, False) for row in before_only]
        + [(row, True) for row in remaining],
        shared
        + [(row, True) for row in before_only]
        + [(row, False) for row in remaining],
    )


def net_twin_dots(
    net: Net,
    before: PairSide,
    after: PairSide,
    *,
    rankdir: str = "TB",
    style: RenderStyle = _DEFAULT_STYLE,
    render_fusion: bool = True,
    splines: str | None = None,
) -> tuple[str, str]:
    """Draw ``net`` twice, as two graphs that get one layout.

    Both graphs come from the ordinary rendering pass, with the same node
    ids, and each node has the same size as its twin: a marking row drawn
    in one half only is a transparent ghost in the other, and a highlight
    label that differs takes a fixed-width cell. Two equal graphs get one
    layout from ``dot``, so only tokens and highlights differ when they are
    shown side by side. One graph with both halves cannot promise this:
    ``dot`` lays out its parts together and drifts one against the other,
    and ``pack``, which lays them out apart, drops edge labels.
    View positions are not applied.
    """
    rows_before: dict[str, list[tuple[MarkingRow, bool]]] = {}
    rows_after: dict[str, list[tuple[MarkingRow, bool]]] = {}
    for place in net.places:
        rows_before[place.name], rows_after[place.name] = _twin_rows(
            _side_rows(place.name, before, style), _side_rows(place.name, after, style)
        )
    keys = [f"place:{p.name}" for p in net.places] + [
        f"transition:{t.name}" for t in net.transitions
    ]

    def label_of(side: PairSide, key: str) -> str | None:
        decoration = side.decorations.nodes.get(key)
        return None if decoration is None else decoration.highlight_label

    def graph(
        side: PairSide,
        rows: Mapping[str, Sequence[tuple[MarkingRow, bool]]],
        twin: PairSide,
    ) -> str:
        title = (
            f"label=<<b>{_html(side.label)}</b>>;"
            if style.html_labels
            else f'label="{_dot_string(side.label)}";'
        )
        lines = [
            "digraph net {",
            f"    rankdir={rankdir};",
            f'    {title} labelloc=t; labeljust=l; fontname="Helvetica";',
        ]
        if splines is not None:
            lines.append(f"    splines={splines};")
        lines.extend(_GRAPH_DEFAULTS)
        lines.append("")
        lines.extend(
            _net_body(
                net,
                marking=side.marking,
                style=style,
                render_fusion=render_fusion,
                decorations=side.decorations,
                token_marks=side.token_marks,
                token_changes=side.token_changes,
                marking_rows=rows,
                twin_labels={key: label_of(twin, key) for key in keys},
            )
        )
        lines.append("}")
        return "\n".join(lines) + "\n"

    return graph(before, rows_before, after), graph(after, rows_after, before)


def composition_to_dot(
    composition: Composition,
    *,
    rankdir: str = "TB",
    include_marking: bool = True,
    style: RenderStyle = _DEFAULT_STYLE,
    render_fusion: bool = True,
) -> str:
    """Render a composition: one cluster per aliased net, wires between ports.

    A refined transition and its arcs are left out of their net's cluster,
    as the merge leaves them out; the refining net's cluster title names
    the transition it refines. A composition used inside another draws as a
    cluster around its own nets' clusters (ADR 0041). Shared places are
    joined by dashed lines without arrows (ADR 0040). A wire or share to a
    fusion place joins its first copy.

    Requires ``composition.parsed_nets`` (as produced by
    :func:`velocitron_petrinet.parse_composition`).
    """
    parsed = composition.parsed_nets
    if parsed is None:
        raise ValueError(
            "composition has no parsed_nets; parse it via parse_composition"
        )
    lines = [
        "digraph composition {",
        f"    rankdir={rankdir};",
        "    compound=true;",
        *_GRAPH_DEFAULTS,
        "",
    ]

    # A fusion place draws as one copy per transition and no node of its
    # own, so a wire or share to it joins its first copy instead.
    endpoints: dict[str, str] = {}

    def leaf(alias: str, net: Net, indent: str) -> list[str]:
        refined = {r.transition for r in composition.refinements if r.net == alias}
        if refined:
            net = replace(
                net,
                transitions=[t for t in net.transitions if t.name not in refined],
                arcs=[
                    arc
                    for arc in net.arcs
                    if (arc.to_transition or arc.from_transition) not in refined
                ],
            )
        if render_fusion:
            fusion = {p.name for p in net.places if _is_fusion(p)}
            layout = fusion_layout(net, fusion, Decorations())
            for (place, _), copy in layout.copies.items():
                endpoints.setdefault(f"{alias}.{place}", f"{alias}.{copy}")
        subtitles = [
            f"refines {r.net}.[{r.transition}]"
            for r in composition.refinements
            if r.by == alias
        ]
        return [
            *_cluster_head(alias, net, subtitles, indent, style),
            *_net_body(
                net,
                indent=indent,
                prefix=f"{alias}.",
                include_marking=include_marking,
                style=style,
                render_fusion=render_fusion,
            ),
        ]

    lines.extend(_clusters(parsed, leaf, "    ", style))
    lines.extend(_composition_edges(composition, endpoints))
    lines.append("}")
    return "\n".join(lines) + "\n"


def composition_ports_dot(
    composition: Composition,
    *,
    rankdir: str = "TB",
    style: RenderStyle = _DEFAULT_STYLE,
) -> str:
    """Render a composition as a compact wiring diagram: ports only.

    Each aliased net collapses to a cluster holding just its boundary ports
    and its shared places (styled as in the full view); wires and shares
    join them as usual. Internal places, transitions, arcs, and markings
    are omitted — this is the view for reading the cross-net topology, not
    any net's internals. Unwired ports still render: they are the
    composition's own boundary.

    Requires ``composition.parsed_nets`` (as produced by
    :func:`velocitron_petrinet.parse_composition`).
    """
    parsed = composition.parsed_nets
    if parsed is None:
        raise ValueError(
            "composition has no parsed_nets; parse it via parse_composition"
        )
    lines = [
        "digraph composition_ports {",
        f"    rankdir={rankdir};",
        *_GRAPH_DEFAULTS,
        "",
    ]
    shared = {
        f"{net}.{place}" for share in composition.shares for net, place in share.members
    }

    def leaf(alias: str, net: Net, indent: str) -> list[str]:
        body = _cluster_head(alias, net, [], indent, style)
        ranks = _flow_ranks(net)
        for place in sorted(net.places, key=lambda place: _node_order("place", place.name, ranks)):
            if place.port is None and f"{alias}.{place.name}" not in shared:
                continue
            node = _quote(f"{alias}.{place.name}")
            body.append(f"{indent}{node} [{_place_attrs(place, style=style)}];")
        return body

    lines.extend(_clusters(parsed, leaf, "    ", style))
    lines.extend(_composition_edges(composition))
    lines.append("}")
    return "\n".join(lines) + "\n"


# ── Composition overview ─────────────────────────────────────────────────

_PART_ATTRS = 'shape=box, style="rounded,filled", fillcolor="#FFFFFF", penwidth=1.4'
_WIRED_ATTRS = 'shape=ellipse, style=filled, fillcolor="#FFF2CC"'
_END_ATTRS = (
    'shape=doublecircle, style=filled, fillcolor="#EEEEEE", fontsize=10, margin=0'
)
_SHARED_RECORD_ATTRS = 'shape=cylinder, style=filled, fillcolor="#F4F4F4", fontsize=10'
_OUTSIDE_RECORD_ATTRS = (
    'shape=cylinder, style="filled,dashed", fillcolor="#F4F4F4", fontsize=10'
)
_FLOW_EDGE_ATTRS = f'penwidth=1.6, color="{_WIRE_COLOR}"'
_END_EDGE_ATTRS = 'penwidth=1.2, color="#444444"'
_RECORD_EDGE_ATTRS = 'style=dashed, dir=none, color="#777777", fontcolor="#555555"'
_REFINES_EDGE_ATTRS = 'style=dotted, dir=none, color="#777777"'
_OVERVIEW_PART_WRAP = 40
_OVERVIEW_PLACE_WRAP = 24
_OVERVIEW_END_WRAP = 10

_Use = Literal["takes", "writes", "reads"]
_OverviewKind = Literal["wired", "end", "shared", "outside", "kept"]


@dataclass
class _OverviewPlace:
    """One place of the overview: a fused group of members, or one local place."""

    members: list[tuple[str, Place]]
    uses: dict[str, set[_Use]] = field(default_factory=dict[str, set[_Use]])
    wired: bool = False
    kind: _OverviewKind | None = None


def _lives_in_record(net: Net, place: Place) -> bool:
    """Whether ``place`` lives in a column its net declares as a ``record``."""
    lives = (place.annotations or {}).get("lives")
    actors = (net.annotations or {}).get("actors")
    if not isinstance(lives, str) or not isinstance(actors, list):
        return False
    return any(
        isinstance(actor, Mapping)
        and cast(Mapping[str, Any], actor).get("name") == lives
        and cast(Mapping[str, Any], actor).get("kind") == "record"
        for actor in cast(list[Any], actors)
    )


def _overview_label(text: str, width: int, style: RenderStyle) -> str:
    """A ``label=`` attribute holding ``text`` wrapped at ``width`` characters."""
    rows = textwrap.wrap(text, width, break_long_words=False) or [text]
    return _label_attr([_escape(row, style) for row in rows], style)


def composition_overview_dot(
    composition: Composition,
    *,
    title: str | None = None,
    rankdir: str = "TB",
    style: RenderStyle = _DEFAULT_STYLE,
) -> str:
    """Render a composition as a business-level overview.

    Each net is one box named by its description. A wired place is one node
    with an arrow from each net that produces into it and to each net that
    takes from it. A place of a color that moves through wires, which no net
    takes from, is where a case ends. Other shared places are records, joined
    to each net by a dashed line labeled with what the net does to it; a
    place that lives in a ``record`` column is a record the outside world
    keeps, drawn with a dashed border; a kept record (ADR 0051) is one this
    system keeps, drawn as a shared record. Places used inside one net only
    are left out, except those ends, outside records and kept records. A nested composition is
    a dashed cluster, and a refining net sits in a dashed cluster joined to
    the net whose transition it refines.

    Requires ``composition.parsed_nets`` (as produced by
    :func:`velocitron_petrinet.parse_composition`).
    """
    parsed = composition.parsed_nets
    if parsed is None:
        raise ValueError(
            "composition has no parsed_nets; parse it via parse_composition"
        )

    parent: dict[str, str] = {}

    def find(name: str) -> str:
        while parent.get(name, name) != name:
            name = parent[name]
        return name

    def union(first: str, second: str) -> None:
        first, second = find(first), find(second)
        if first != second:
            parent[second] = first

    for wire in composition.wires:
        union(f"{wire.from_net}.{wire.from_port}", f"{wire.to_net}.{wire.to_port}")
    for share in composition.shares:
        names = [f"{net}.{place}" for net, place in share.members]
        for name in names[1:]:
            union(names[0], name)
    wired_roots = {
        find(f"{net}.{port}")
        for wire in composition.wires
        for net, port in ((wire.from_net, wire.from_port), (wire.to_net, wire.to_port))
    }

    refined = {(r.net, r.transition) for r in composition.refinements}
    places: dict[str, _OverviewPlace] = {}
    for alias, net in parsed.items():
        for place in net.places:
            root = find(f"{alias}.{place.name}")
            entry = places.setdefault(
                root, _OverviewPlace(members=[], wired=root in wired_roots)
            )
            entry.members.append((alias, place))
        for arc in net.arcs:
            if (alias, arc.to_transition or arc.from_transition) in refined:
                continue
            if arc.consume is not None and arc.from_place is not None:
                use: _Use = "takes" if arc.consume.mode == "consume" else "reads"
                root = find(f"{alias}.{arc.from_place}")
            elif arc.to_place is not None:
                use, root = "writes", find(f"{alias}.{arc.to_place}")
            else:
                continue
            places[root].uses.setdefault(alias, set()).add(use)

    def outside(entry: _OverviewPlace) -> bool:
        return any(_lives_in_record(parsed[a], p) for a, p in entry.members)

    def kept(entry: _OverviewPlace) -> bool:
        return any("kept" in (p.annotations or {}) for _, p in entry.members)

    def colors(entry: _OverviewPlace) -> set[str]:
        return {color for _, place in entry.members for color in place.accepts}

    # The colors a case moves in: those that pass along a wire.
    case_colors = {
        color
        for entry in places.values()
        if entry.wired and not outside(entry)
        for color in colors(entry)
    }
    for entry in places.values():
        uses = set[_Use]().union(*entry.uses.values())
        fused = len(entry.members) > 1
        if outside(entry):
            entry.kind = "outside"
        elif kept(entry):
            entry.kind = "kept"
        elif colors(entry) & case_colors and "takes" not in uses:
            if "writes" in uses:
                entry.kind = "end"
        elif entry.wired or (fused and colors(entry) & case_colors):
            entry.kind = "wired"
        elif fused:
            entry.kind = "shared"

    def scope(aliases: Sequence[str]) -> tuple[str, ...]:
        paths = [tuple(alias.split(".")[:-1]) for alias in aliases]
        common: list[str] = []
        for segments in zip(*paths):
            if len(set(segments)) > 1:
                break
            common.append(segments[0])
        return tuple(common)

    def place_node(root: str) -> str:
        return _quote(f"place:{root}")

    def part_node(alias: str) -> str:
        return _quote(f"part:{alias}")

    drawn = {root: entry for root, entry in places.items() if entry.kind is not None}
    place_lines: dict[tuple[str, ...], list[str]] = {}
    attrs_by_kind = {
        "wired": _WIRED_ATTRS,
        "end": _END_ATTRS,
        "shared": _SHARED_RECORD_ATTRS,
        "outside": _OUTSIDE_RECORD_ATTRS,
        "kept": _SHARED_RECORD_ATTRS,
    }
    for root, entry in drawn.items():
        assert entry.kind is not None
        name = entry.members[0][1].name.replace("_", " ")
        # An end is a small marker named by how the case ends; a description
        # there says what the place holds, often for another view.
        described = next(
            (p.description for _, p in entry.members if p.description), None
        )
        text = name if entry.kind == "end" else described or name
        width = _OVERVIEW_END_WRAP if entry.kind == "end" else _OVERVIEW_PLACE_WRAP
        label = _overview_label(text, width, style)
        place_lines.setdefault(scope([a for a, _ in entry.members]), []).append(
            f"{place_node(root)} [{attrs_by_kind[entry.kind]}, {label}];"
        )
    for body in place_lines.values():
        body.sort()

    refining = {r.by: r for r in composition.refinements}
    counter = itertools.count()
    lines = [
        "digraph composition_overview {",
        f"    rankdir={rankdir};",
        "    newrank=true;",
        '    fontname="Helvetica";',
        *_GRAPH_DEFAULTS,
    ]
    if title:
        if style.html_labels:
            lines.append(f"    label=<<b>{_html(title)}</b>>;")
        else:
            lines.append(f'    label="{_dot_string(title)}";')
        lines.append("    labelloc=t; labeljust=l;")
    lines.append("")

    def part(alias: str, indent: str) -> list[str]:
        net = parsed[alias]
        label = _overview_label(net.description or net.name, _OVERVIEW_PART_WRAP, style)
        tooltip = _tooltip_attr(alias, style)
        node = f"{indent}{part_node(alias)} [{_PART_ATTRS}, {label}{tooltip}];"
        refinement = refining.get(alias)
        if refinement is None:
            return [node]
        transition = next(
            (
                t
                for t in parsed[refinement.net].transitions
                if t.name == refinement.transition
            ),
            None,
        )
        step = (transition.description if transition else None) or refinement.transition
        heading = _overview_label(f"refines: {step}", _OVERVIEW_PART_WRAP + 20, style)
        return [
            f"{indent}subgraph cluster_{next(counter)} {{",
            f"{indent}    {heading}; labeljust=l;",
            f'{indent}    style=dashed; color="#999999"; fontsize=10;',
            f"    {node}",
            f"{indent}}}",
        ]

    def emit(path: tuple[str, ...], indent: str) -> None:
        depth = len(path)
        children: dict[str, list[str]] = {}
        for alias in parsed:
            segments = alias.split(".")
            if tuple(segments[:depth]) != path or len(segments) == depth:
                continue
            if len(segments) == depth + 1:
                lines.extend(part(alias, indent))
            else:
                children.setdefault(segments[depth], []).append(alias)
        lines.extend(f"{indent}{line}" for line in place_lines.get(path, []))
        for head in children:
            heading = (
                f"label=<<b>{_html(head)}</b>>;"
                if style.html_labels
                else f'label="{_dot_string(head)}";'
            )
            lines.append(f"{indent}subgraph cluster_{next(counter)} {{")
            lines.append(f"{indent}    {heading} labeljust=l;")
            lines.append(f'{indent}    style=dashed; color="#999999";')
            emit((*path, head), indent + "    ")
            lines.append(f"{indent}}}")

    emit((), "    ")
    lines.append("")

    edge_lines: list[str] = []
    for root, entry in drawn.items():
        node = place_node(root)
        taken = any("takes" in uses for uses in entry.uses.values())
        writers = {alias for alias, uses in entry.uses.items() if "writes" in uses}
        for alias, uses in entry.uses.items():
            if entry.kind in ("wired", "end"):
                flow = _FLOW_EDGE_ATTRS if entry.kind == "wired" else _END_EDGE_ATTRS
                # A net that takes a case back into a place it also fills is
                # drawn as the place's producer only when no other net fills it.
                looped = {"writes", "takes"} <= uses
                if "writes" in uses and not (looped and writers - {alias}):
                    edge_lines.append(f"    {part_node(alias)} -> {node} [{flow}];")
                if "takes" in uses and not (looped and not writers - {alias}):
                    edge_lines.append(f"    {node} -> {part_node(alias)} [{flow}];")
                elif "reads" in uses:
                    edge_lines.append(
                        f'    {node} -> {part_node(alias)} [{_RECORD_EDGE_ATTRS}, dir=forward, label="reads"];'
                    )
                continue
            words = [
                word
                for use, word in (
                    ("takes", "takes"),
                    ("writes", "gives back" if taken else "writes"),
                    ("reads", "reads"),
                )
                if use in uses
            ]
            # A record nothing takes or reads is a signal: its lines need no label.
            silent = not taken and not any("reads" in u for u in entry.uses.values())
            label = "" if silent else f', label="{", ".join(words)}"'
            edge_lines.append(
                f"    {part_node(alias)} -> {node} [{_RECORD_EDGE_ATTRS}{label}];"
            )
    for refinement in composition.refinements:
        edge_lines.append(
            f"    {part_node(refinement.net)} -> {part_node(refinement.by)} "
            f"[{_REFINES_EDGE_ATTRS}];"
        )
    lines.extend(sorted(edge_lines))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _cluster_head(
    alias: str, net: Net, subtitles: list[str], indent: str, style: RenderStyle
) -> list[str]:
    """A net cluster's title, fill and tooltip, titled by its own alias."""
    own = alias.rsplit(".", 1)[-1]
    subtitles = ([net.name] if net.name != own else []) + subtitles
    if style.html_labels:
        title = _html(own)
        for subtitle in subtitles:
            title += (
                f'<br/><font point-size="9" color="{_MUTED}">{_html(subtitle)}</font>'
            )
        title_stmt = f"label=<<b>{title}</b>>; labeljust=l;"
    else:
        text = "\n".join([own, *subtitles])
        title_stmt = f'label="{_dot_string(text)}"; labeljust=l;'
    lines = [
        f"{indent}{title_stmt}",
        f'{indent}style=filled; fillcolor="#f7f7f7"; color="#bbbbbb";',
    ]
    if net.description and style.tooltips:
        lines.append(f'{indent}tooltip="{_dot_string(net.description)}";')
    return lines


def _clusters(
    parsed: Mapping[str, Net],
    leaf: Callable[[str, Net, str], list[str]],
    indent: str,
    style: RenderStyle,
) -> list[str]:
    """One cluster per net; the nets of a nested composition (aliases
    ``outer.inner``) inside one more cluster titled ``outer``."""
    lines: list[str] = []
    counter = itertools.count()

    def emit(prefix: str, aliases: list[str], indent: str) -> None:
        groups: dict[str, list[str]] = {}
        for alias in aliases:
            groups.setdefault(alias[len(prefix) :].split(".", 1)[0], []).append(alias)
        for head, members in groups.items():
            lines.append(f"{indent}subgraph cluster_{next(counter)} {{")
            if members == [f"{prefix}{head}"]:
                lines.extend(leaf(members[0], parsed[members[0]], indent + "    "))
            else:
                title = (
                    f"label=<<b>{_html(head)}</b>>; labeljust=l;"
                    if style.html_labels
                    else f'label="{_dot_string(head)}"; labeljust=l;'
                )
                lines.append(f"{indent}    {title}")
                lines.append(f'{indent}    style=dashed; color="#999999";')
                emit(f"{prefix}{head}.", members, indent + "    ")
            lines.append(f"{indent}}}")
            lines.append("")

    emit("", list(parsed), indent)
    return lines


def _composition_edges(
    composition: Composition, endpoints: Mapping[str, str] | None = None
) -> list[str]:
    """Wires as arrows from output to input; shares as plain dashed lines.

    ``endpoints`` maps a qualified place name to the node drawn for it, when
    that is not the place's own node.
    """
    nodes = endpoints or {}

    def node(net: str, place: str) -> str:
        name = f"{net}.{place}"
        return _quote(nodes.get(name, name))

    lines: list[str] = []
    for wire in composition.wires:
        source = node(wire.from_net, wire.from_port)
        target = node(wire.to_net, wire.to_port)
        lines.append(f"    {source} -> {target} [{_WIRE_ATTRS}];")
    for share in composition.shares:
        names = [node(net, place) for net, place in share.members]
        for first, second in zip(names, names[1:]):
            lines.append(f"    {first} -> {second} [{_SHARE_ATTRS}];")
    return sorted(lines)


# ── Legend ───────────────────────────────────────────────────────────────


def legend_dot(*, rankdir: str = "LR") -> str:
    """A self-contained legend digraph exercising every visual convention.

    Built through the same attribute helpers as real renders, so the legend
    cannot drift from the styles it documents.
    """
    place = Place(name="place", accepts=["colorA", "colorB"])
    marked = Place(name="marked place", accepts=["colorA"])
    port_in = Place(
        name="input port",
        accepts=["colorA"],
        port=Port(direction="input", type="colorA"),
    )
    port_out = Place(
        name="output port",
        accepts=["colorA"],
        port=Port(direction="output", type="colorA"),
    )
    fusion_place = Place(
        name="fusion place", accepts=["colorA"], annotations={"fusion": True}
    )
    plain_t = Transition(name="transition", handler="handler_ref")
    guarded_t = Transition(
        name="guarded transition",
        handler="handler_ref",
        guard="guard_ref",
        priority=5,
    )
    tokens = [Token(type="colorA", data={}), Token(type="colorA", data={})]
    consume = ConsumePattern(type="colorA", predicate=None, mode="consume")
    weighted = ConsumePattern(type="colorA", predicate=None, mode="consume", weight=2)
    cel = ConsumePattern(
        type="colorA",
        predicate=Predicate(cel='field == "value"', handler=None),
        mode="consume",
    )
    named = ConsumePattern(
        type="colorA",
        predicate=Predicate(cel=None, handler="predicate_ref"),
        mode="consume",
    )
    read = ConsumePattern(type="colorA", predicate=None, mode="read")
    inhibit = ConsumePattern(type="colorA", predicate=None, mode="inhibit")
    produce = ProduceTemplate(type="colorA", destination="ignored")
    produce_data = ProduceTemplate(
        type="colorA", destination="ignored", data={"fixed": True}
    )
    produce_cel = ProduceTemplate(
        type="colorA", destination="ignored", cel='{"n": field - 1}'
    )
    summarized = RenderStyle(detail="summary")
    quiet = RenderStyle(quiet_colors=frozenset({"colorA"}))
    highlighted = Decoration(highlight=True, highlight_label="R2.11")
    summarized_t = Transition(
        name="summarized transition", handler="handler_ref", guard="guard_ref"
    )

    edges = [
        ("p1", "t1", _consume_edge_attrs(consume, None), "consume: removed on fire"),
        ("p2", "t2", _consume_edge_attrs(weighted, None), "weight 2: two tokens"),
        ("p3", "t3", _consume_edge_attrs(cel, None), "inline CEL predicate"),
        ("p4", "t4", _consume_edge_attrs(named, None), "named predicate handler"),
        ("p5", "t5", _consume_edge_attrs(read, None), "read: gate, don't consume"),
        ("p6", "t6", _consume_edge_attrs(inhibit, None), "inhibit: require absence"),
        ("t7", "p7", _produce_edge_attrs(produce, None), "produce: routing contract"),
        ("t8", "p8", _produce_edge_attrs(produce_data, None), "literal data template"),
        ("t9", "p9", _produce_edge_attrs(produce_cel, None), "computed data template"),
        ("p9", "p10", _WIRE_ATTRS, "composition wire (port to port)"),
        (
            "p11",
            "t11",
            _consume_edge_attrs(consume, None, decoration=highlighted),
            "highlight: amber pen and label",
        ),
        (
            "p12",
            "t12",
            _consume_edge_attrs(consume, None, quiet),
            "quiet color: no type label",
        ),
        (
            "t13",
            "p13",
            _produce_edge_attrs(
                produce_cel, None, summarized, Decoration(summary="one less")
            ),
            "summary: replaces CEL at --detail summary",
        ),
    ]
    lines = [
        "digraph legend {",
        f"    rankdir={rankdir};",
        "    label=<<b>velocitron net legend</b>>; labelloc=t;",
        *_GRAPH_DEFAULTS,
        "",
        f"    place [{_place_attrs(place)}];",
        f"    marked [{_place_attrs(marked, tokens, label='marked place')}];",
        f"    port_in [{_place_attrs(port_in, label='input port')}];",
        f"    port_out [{_place_attrs(port_out, label='output port')}];",
        f"    fusion [{_place_attrs(fusion_place, label='fusion place (local instance)', fusion=True)}];",
        f"    transition [{_transition_attrs(plain_t)}];",
        f"    guarded [{_transition_attrs(guarded_t, label='guarded transition')}];",
        f"    highlighted [{_place_attrs(place, label='highlighted place', decoration=highlighted)}];",
        f"    noted [{_place_attrs(place, label='place with a note', decoration=Decoration(note='a note'))}];",
        f"    summarized [{_transition_attrs(summarized_t, style=summarized, decoration=Decoration(summary='a summary in place of the guard'))}];",
        # A beside copy shares its transition's rank, as fusion_layout asks.
        f"    beside_t [{_transition_attrs(Transition(name='beside transition'))}];",
        f"    beside_p [{_place_attrs(fusion_place, label='beside copy', fusion=True)}];",
        "    { rank=same; beside_p; beside_t; }",
        f"    beside_p -> beside_t [{_consume_edge_attrs(read, None)}];",
        "",
        "    subgraph cluster_overview {",
        "        label=<<b>composition overview (--overview)</b>>; labeljust=l;",
        '        style=dashed; color="#999999";',
        f'        ov_part [{_PART_ATTRS}, label="a net, by its description"];',
        f'        ov_wired [{_WIRED_ATTRS}, label="wired place"];',
        f'        ov_end [{_END_ATTRS}, label="end"];',
        f'        ov_shared [{_SHARED_RECORD_ATTRS}, label="shared or kept record"];',
        f'        ov_outside [{_OUTSIDE_RECORD_ATTRS}, label="outside record"];',
        f"        ov_part -> ov_wired [{_FLOW_EDGE_ATTRS}];",
        f"        ov_part -> ov_end [{_END_EDGE_ATTRS}];",
        f'        ov_part -> ov_shared [{_RECORD_EDGE_ATTRS}, label="takes"];',
        f'        ov_part -> ov_outside [{_RECORD_EDGE_ATTRS}, label="reads"];',
        "    }",
        "",
    ]
    for index, (src, dst, attrs, caption) in enumerate(edges):
        for node in (src, dst):
            shape = "box" if node.startswith("t") else "ellipse"
            fill = (
                f", style=filled, fillcolor={_TRANSITION_FILL}"
                if shape == "box"
                else ""
            )
            lines.append(
                f'    {node}_{index} [shape={shape}, label=""{fill}, '
                f"width=0.35, height=0.28, fixedsize=true];"
            )
        lines.append(f"    {src}_{index} -> {dst}_{index} [{attrs}];")
        lines.append(
            f"    c_{index} [shape=plaintext, label=<"
            f'<font point-size="9" color="{_MUTED}">{_html(caption)}</font>>];'
        )
        lines.append(f"    {dst}_{index} -> c_{index} [style=invis];")
    lines.append("}")
    return "\n".join(lines) + "\n"


