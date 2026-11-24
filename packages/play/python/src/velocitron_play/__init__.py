"""Parse a Velocitron ``.play`` document.

The canonical grammar is ``packages/play/VelocitronPlay.g4``. A checkout reads
that file. A wheel reads the copy this package ships, which ``tools/antlr.py``
keeps identical.

``parse_play`` lowers one play to an AST and reports ``SC1xx``. It does not
check the play against a net, render a walkthrough, or draw a sequence
diagram. Those steps stay in ``velocitron_play``. Published ``velocitron``
keeps its own copy of the lowerer and does not depend on this package.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Final

from .facts import play_facts, project_source
from .language import (
    TRUNK,
    WALK_SCOPES,
    ActorDecl,
    ActorKind,
    AdvanceBody,
    AssumeGuardBody,
    AssumePredicateBody,
    BoxDecl,
    Condition,
    Diagnostic,
    ExpectBody,
    FireBody,
    InjectBody,
    NameRef,
    OutputClause,
    Play,
    PlayError,
    PlayPath,
    Position,
    RefineDecl,
    SequenceMode,
    ShareDecl,
    ShowDecl,
    Step,
    TokenExpr,
    TokenLiteral,
    UpdateBody,
    UseDecl,
    WalkScope,
    WireDecl,
    WithClause,
    parse_play,
    read_play,
    step_label_names,
)

GRAMMAR_FILE_NAME: Final = "VelocitronPlay.g4"


def _checkout_grammar() -> Path | None:
    # packages/play/python/src/velocitron_play/__init__.py -> python/
    project_root = Path(__file__).resolve().parents[2]
    marker = project_root / "pyproject.toml"
    canonical = project_root.parent / GRAMMAR_FILE_NAME
    if project_root.name != "python" or project_root.parent.name != "play":
        return None
    if not marker.is_file() or not canonical.is_file():
        return None
    for line in marker.read_text(encoding="utf-8").splitlines():
        if line.strip() == 'name = "velocitron-play"':
            return canonical
    return None


def _read_grammar_text() -> str:
    checkout = _checkout_grammar()
    if checkout is not None:
        return checkout.read_text(encoding="utf-8")
    packaged = files("velocitron_play").joinpath(GRAMMAR_FILE_NAME)
    if not packaged.is_file():
        raise FileNotFoundError("velocitron-play grammar is not installed")
    return packaged.read_text(encoding="utf-8")


def grammar_text() -> str:
    """Return the ``.play`` statement grammar as UTF-8 text."""
    return _read_grammar_text()


__all__ = [
    "GRAMMAR_FILE_NAME",
    "TRUNK",
    "WALK_SCOPES",
    "ActorDecl",
    "ActorKind",
    "AdvanceBody",
    "AssumeGuardBody",
    "AssumePredicateBody",
    "BoxDecl",
    "Condition",
    "Diagnostic",
    "ExpectBody",
    "FireBody",
    "InjectBody",
    "NameRef",
    "OutputClause",
    "Play",
    "PlayError",
    "PlayPath",
    "Position",
    "RefineDecl",
    "SequenceMode",
    "ShareDecl",
    "ShowDecl",
    "Step",
    "TokenExpr",
    "TokenLiteral",
    "UpdateBody",
    "UseDecl",
    "WalkScope",
    "WireDecl",
    "WithClause",
    "grammar_text",
    "parse_play",
    "play_facts",
    "project_source",
    "read_play",
    "step_label_names",
]
