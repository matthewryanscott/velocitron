"""Syntax checking for Petri-net DSL and play content in files and fences.

``velocitron check`` walks files and directories, compiles every
``*.petrinet`` file and every ``petrinet`` fenced code block found in
Markdown files through the DSL compiler, parses every ``*.play`` file
and every ``play`` fence with the play parser, and reports each
diagnostic at its location in the file the author edits — for fences that
means the Markdown file's own line numbers, not the extracted snippet's.

This is *syntax* validation, distinct from :mod:`velocitron_analysis` (the
advisory semantic lint over an already-parsed
:class:`~velocitron_engine.Net`, ADR 0016) and from ``velocitron play
check``, which plays a play against its net: this module answers "is
this text valid at all?", not "is this valid net a likely bug?" or "does
this play hold?".

Fences whose info string carries ``no-lint`` after the language (i.e.
opened with ```` ```petrinet no-lint ````) hold intentionally-invalid
teaching examples and are skipped.

Composition documents in standalone ``*.petrinet`` files resolve their
``use`` references relative to the file, exactly like ``velocitron
validate``; composition fences are compiled without resolving references,
so the referenced files need not exist next to the Markdown. A play's
``net`` and ``use`` references are never loaded here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
from typing import Any

from velocitron_dsl import PetrinetDslError
from velocitron_petrinet import (
    NetValidationError,
    compile_petrinet_text,
    read_petrinet_text,
)
from velocitron_play import PlayError, parse_play

_CHECKED_SUFFIXES = frozenset({".petrinet", ".play", ".md"})
_FENCE_LANGUAGES = frozenset({"petrinet", "play"})
_SKIPPED_DIRECTORY_NAMES = frozenset({"node_modules", "__pycache__", "venv"})
_NO_LINT_MARKER = "no-lint"
_FENCE_LINE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")


@dataclass(frozen=True)
class MarkdownFence:
    """One ``petrinet`` or ``play`` fenced block extracted from Markdown."""

    text: str
    line_offset: int
    """Add to a 1-based snippet line to get the Markdown file line."""

    lint: bool
    """False when the info string opts out via ``no-lint``."""

    language: str
    """The fence's language: ``petrinet`` or ``play``."""


@dataclass(frozen=True)
class CheckReport:
    """Aggregated result of one ``velocitron check`` invocation."""

    petrinet_files: int
    markdown_files: int
    fences: int
    skipped_fences: int
    errors: tuple[str, ...]
    play_files: int = 0
    play_fences: int = 0

    def summary(self) -> str:
        text = (
            f"checked {self.petrinet_files} petrinet file(s), "
            f"{self.play_files} play file(s), "
            f"{self.fences} petrinet fence(s) and {self.play_fences} "
            f"play fence(s) in {self.markdown_files} "
            f"markdown file(s): {len(self.errors)} error(s)"
        )
        if self.skipped_fences:
            text += f" ({self.skipped_fences} no-lint fence(s) skipped)"
        return text


def extract_fences(markdown: str) -> list[MarkdownFence]:
    """Extract ``petrinet`` and ``play`` fenced blocks with line offsets."""
    fences: list[MarkdownFence] = []
    marker: str | None = None
    language: str | None = None
    lint = True
    opened_at = 0
    content: list[str] = []

    def close_fence() -> None:
        if language is not None:
            fences.append(
                MarkdownFence("\n".join(content) + "\n", opened_at, lint, language)
            )

    for number, line in enumerate(markdown.splitlines(), start=1):
        match = _FENCE_LINE.match(line)
        if marker is None:
            if match is None:
                continue
            info = match["info"]
            if match["marker"].startswith("`") and "`" in info:
                # Per CommonMark, a backtick fence's info string cannot
                # contain backticks; this line is prose, not a fence.
                continue
            marker = match["marker"]
            tokens = info.split()
            language = tokens[0] if tokens and tokens[0] in _FENCE_LANGUAGES else None
            lint = _NO_LINT_MARKER not in tokens[1:]
            opened_at = number
            content = []
            continue
        if (
            match is not None
            and match["marker"][0] == marker[0]
            and len(match["marker"]) >= len(marker)
            and not match["info"].strip()
        ):
            close_fence()
            marker = None
            continue
        content.append(line)
    if marker is not None:
        # Per CommonMark, an unterminated fence runs to end of document.
        close_fence()
    return fences


def _composition_loader(
    origin: Path,
) -> Callable[[str], Mapping[str, Any] | Path | str]:
    """Load composition ``use`` references relative to the checked file.

    Mirrors :func:`velocitron_cli.dispatch._composition_loader`. The dispatcher
    imports this module, so sharing the helper from there would cycle.
    """

    def load(ref: str) -> Mapping[str, Any] | Path | str:
        path = Path(ref)
        if not path.is_absolute():
            path = origin / path
        suffix = path.suffix.lower()
        if suffix == ".json":
            return path
        if suffix == ".petrinet":
            return compile_petrinet_text(read_petrinet_text(path), str(path))
        raise NetValidationError(f"unsupported composition net reference: {ref!r}")

    return load


def _relocated(error: PetrinetDslError, source: str, line_offset: int = 0) -> str:
    """Render a diagnostic against the checked file's own path and lines."""
    diagnostic = error.diagnostic
    span = diagnostic.span
    return replace(
        diagnostic,
        span=replace(
            span,
            source=source,
            start=replace(span.start, line=span.start.line + line_offset),
            end=replace(span.end, line=span.end.line + line_offset),
        ),
    ).render()


def _play_errors(text: str, source: str, line_offset: int = 0) -> list[str]:
    """Parse play text; return its diagnostic at the checked file's lines."""
    try:
        parse_play(text, source)
    except PlayError as error:
        diagnostic = error.diagnostic
        position = replace(
            diagnostic.position, line=diagnostic.position.line + line_offset
        )
        return [replace(diagnostic, position=position).render()]
    return []


def check_petrinet_file(path: Path) -> list[str]:
    """Compile one ``*.petrinet`` file; return rendered diagnostics."""
    origin = path.parent
    try:
        compile_petrinet_text(
            read_petrinet_text(path),
            str(path),
            net_loader=_composition_loader(origin),
            origin=origin,
        )
    except PetrinetDslError as error:
        return [_relocated(error, str(path))]
    except (OSError, UnicodeError, ValueError, NetValidationError) as error:
        return [f"{path}:1:1: error[PN200]: {error}"]
    return []


def check_play_file(path: Path) -> list[str]:
    """Parse one ``*.play`` file; return rendered diagnostics."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeError) as error:
        return [f"{path}:1:1: error[SC100]: {error}"]
    return _play_errors(text, str(path))


def check_markdown_file(path: Path) -> tuple[int, int, int, list[str]]:
    """Check one Markdown file's ``petrinet`` and ``play`` fences.

    Returns ``(petrinet_fences, play_fences, skipped_fences, errors)``.
    """
    try:
        markdown = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return 0, 0, 0, [f"{path}:1:1: error[PN200]: {error}"]
    petrinet = 0
    play = 0
    skipped = 0
    errors: list[str] = []
    for fence in extract_fences(markdown):
        if not fence.lint:
            skipped += 1
            continue
        if fence.language == "play":
            play += 1
            errors.extend(_play_errors(fence.text, str(path), fence.line_offset))
            continue
        petrinet += 1
        try:
            compile_petrinet_text(fence.text, str(path))
        except PetrinetDslError as error:
            errors.append(_relocated(error, str(path), fence.line_offset))
        except (ValueError, NetValidationError) as error:
            errors.append(f"{path}:{fence.line_offset + 1}:1: error[PN200]: {error}")
    return petrinet, play, skipped, errors


def _is_skipped_directory(path: Path) -> bool:
    return (
        path.name.startswith(".")
        or path.name in _SKIPPED_DIRECTORY_NAMES
        or (path / "pyvenv.cfg").is_file()
    )


def _walk(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        parent = Path(dirpath)
        dirnames[:] = sorted(
            name for name in dirnames if not _is_skipped_directory(parent / name)
        )
        for filename in sorted(filenames):
            if Path(filename).suffix.lower() in _CHECKED_SUFFIXES:
                yield parent / filename


def _candidate_files(paths: Sequence[Path], errors: list[str]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            yield from _walk(path)
        elif path.is_file():
            if path.suffix.lower() in _CHECKED_SUFFIXES:
                yield path
            else:
                errors.append(f"{path}: error: not a .petrinet, .play or .md file")
        else:
            errors.append(f"{path}: error: no such file or directory")


def check_paths(paths: Sequence[Path]) -> CheckReport:
    """Check every ``*.petrinet``/``*.play`` file and fence under ``paths``."""
    petrinet_files = 0
    play_files = 0
    markdown_files = 0
    fences = 0
    play_fences = 0
    skipped = 0
    errors: list[str] = []
    for path in _candidate_files(paths, errors):
        suffix = path.suffix.lower()
        if suffix == ".petrinet":
            petrinet_files += 1
            errors.extend(check_petrinet_file(path))
        elif suffix == ".play":
            play_files += 1
            errors.extend(check_play_file(path))
        else:
            markdown_files += 1
            checked, plays, ignored, fence_errors = check_markdown_file(path)
            fences += checked
            play_fences += plays
            skipped += ignored
            errors.extend(fence_errors)
    return CheckReport(
        petrinet_files,
        markdown_files,
        fences,
        skipped,
        tuple(errors),
        play_files,
        play_fences,
    )
