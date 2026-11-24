"""Check a ``.play`` document against a net and step a walkthrough.

``check_play`` resolves the play, then plays every path through
``velocitron_engine`` by symbolic firing. ``render_walkthrough`` draws one
checked path. ``trace_document`` prints one path's records and resolved
labels as JSON.

The ``.play`` grammar and AST live in ``velocitron_play``. Journal
durability stays in ``velocitron_journal``. ``records_to_play`` writes the
play that replays a journal. The product CLI lives in ``velocitron_cli``.
This package does not import ``velocitron``.
"""

from __future__ import annotations

from .records import RecordsToPlayError, records_to_play
from .check import (
    CheckResult,
    OutputSource,
    PlayNet,
    PlayReport,
    PlayTrace,
    StepFailure,
    StepResult,
    check_play,
    load_play_net,
    net_fills,
    produce_templates,
)
from .check import _Player as _Player  # pyright: ignore[reportPrivateUsage]
from .sequence import (
    OUTSIDE,
    Activate,
    Box,
    Deactivate,
    Delay,
    Divider,
    Failure,
    GroupClose,
    GroupOpen,
    Lifeline,
    Message,
    Note,
    SequenceEvent,
    SequenceView,
    humanize,
    place_label,
    render_plantuml,
    render_sequence,
    resolve_actor,
    resolve_column,
    resolve_read_label,
    resolve_step_title,
    sequence_json,
    sequence_view,
)
from .trace import trace_document
from .walkthrough import (
    marking_json,
    render_walkthrough,
    trace_json,
    walkthrough_document,
)

__all__ = [
    "CheckResult",
    "OutputSource",
    "PlayNet",
    "PlayReport",
    "PlayTrace",
    "RecordsToPlayError",
    "SequenceView",
    "StepFailure",
    "StepResult",
    "_Player",
    "Activate",
    "Box",
    "Deactivate",
    "Delay",
    "Divider",
    "Failure",
    "GroupClose",
    "GroupOpen",
    "Lifeline",
    "Message",
    "Note",
    "OUTSIDE",
    "SequenceEvent",
    "check_play",
    "humanize",
    "load_play_net",
    "net_fills",
    "place_label",
    "produce_templates",
    "records_to_play",
    "resolve_actor",
    "resolve_column",
    "resolve_read_label",
    "resolve_step_title",
    "marking_json",
    "render_plantuml",
    "render_sequence",
    "render_walkthrough",
    "sequence_json",
    "sequence_view",
    "trace_document",
    "trace_json",
    "walkthrough_document",
]
