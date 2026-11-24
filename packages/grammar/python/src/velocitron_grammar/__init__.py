"""Parse a Velocitron ``.petrinet`` document.

The canonical grammar is ``packages/grammar/VelocitronPetriNet.g4``. A checkout
reads that file. A wheel reads the copy this package ships, which
``tools/antlr.py`` keeps identical.

``parse_petrinet`` is a syntax parse of a net or composition document. It does
not lower contributions, compile CEL, resolve IR, or merge a composition.
Lowering ships in ``packages/dsl``. Resolution ships in
``packages/petrinet``. Composition merge ships in ``packages/merge``. The
``.play`` grammar
lives in ``packages/play``, not in this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path
from typing import Any, Final, Literal

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext, Token
from antlr4.Recognizer import Recognizer
from antlr4.error.ErrorListener import ErrorListener
from antlr4.error.Errors import RecognitionException

from .generated.VelocitronPetriNetLexer import VelocitronPetriNetLexer
from .generated.VelocitronPetriNetParser import VelocitronPetriNetParser

GRAMMAR_FILE_NAME: Final = "VelocitronPetriNet.g4"
_SOURCE_MESSAGE: Final = "source must be strict UTF-8 text without a BOM or bare CR"
_MISSING_NAME: Final = "header is missing a name"
_BAD_STRING: Final = "header name is not a JSON string"


class PetrinetParseError(ValueError):
    """The text is not a ``.petrinet`` document this grammar accepts.

    ``line`` and ``column`` are 1-based. A source-text rejection uses line 1
    and column 1. A syntax error uses the first ANTLR diagnostic.
    """

    line: int
    column: int

    def __init__(self, message: str, *, line: int, column: int) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


@dataclass(frozen=True, slots=True)
class PetrinetParse:
    """One successfully parsed ``.petrinet`` document.

    ``kind`` is ``net`` or ``composition``. A document with no header is a net
    whose name is ``unnamed``. ``tree`` is the ANTLR ``document`` rule context.
    """

    kind: Literal["net", "composition"]
    name: str
    source_name: str
    tree: ParserRuleContext


class _CollectingListener(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[tuple[int, int, str]] = []

    def syntaxError(
        self,
        recognizer: Recognizer,
        offendingSymbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: RecognitionException | None,
    ) -> None:
        del recognizer, offendingSymbol, e
        self.errors.append((line, column + 1, msg))


def _checkout_grammar() -> Path | None:
    # packages/grammar/python/src/velocitron_grammar/__init__.py -> python/
    project_root = Path(__file__).resolve().parents[2]
    marker = project_root / "pyproject.toml"
    canonical = project_root.parent / GRAMMAR_FILE_NAME
    if project_root.name != "python" or project_root.parent.name != "grammar":
        return None
    if not marker.is_file() or not canonical.is_file():
        return None
    for line in marker.read_text(encoding="utf-8").splitlines():
        if line.strip() == 'name = "velocitron-grammar"':
            return canonical
    return None


def _read_grammar_text() -> str:
    checkout = _checkout_grammar()
    if checkout is not None:
        return checkout.read_text(encoding="utf-8")
    packaged = files("velocitron_grammar").joinpath(GRAMMAR_FILE_NAME)
    if not packaged.is_file():
        raise FileNotFoundError("velocitron-grammar grammar is not installed")
    return packaged.read_text(encoding="utf-8")


def grammar_text() -> str:
    """Return the ``.petrinet`` grammar as UTF-8 text."""
    return _read_grammar_text()


def _reject_illegal_source(text: str) -> None:
    if (
        text.startswith("\ufeff")
        or "\r" in text.replace("\r\n", "")
        or any(0xD800 <= ord(character) <= 0xDFFF for character in text)
    ):
        raise PetrinetParseError(_SOURCE_MESSAGE, line=1, column=1)


def _decoded_name(name_ctx: Any) -> str:
    if name_ctx is None:
        raise PetrinetParseError(_MISSING_NAME, line=1, column=1)
    text = name_ctx.getText()
    if text == "":
        raise PetrinetParseError(_MISSING_NAME, line=1, column=1)
    if text.startswith('"'):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PetrinetParseError(_BAD_STRING, line=1, column=1) from exc
        if not isinstance(decoded, str):
            raise PetrinetParseError(_BAD_STRING, line=1, column=1)
        return decoded
    return text


def parse_petrinet(text: object, source_name: object = "<memory>") -> PetrinetParse:
    """Parse one complete ``.petrinet`` document.

    ``text`` and ``source_name`` must be ``str``. A syntax error raises
    :class:`PetrinetParseError` and does not return a recovered tree. The
    result is not contribution IR.
    """
    if not isinstance(text, str):
        raise TypeError("petrinet source must be a str")
    if not isinstance(source_name, str):
        raise TypeError("source name must be a str")
    _reject_illegal_source(text)
    lexer = VelocitronPetriNetLexer(InputStream(text))
    listener = _CollectingListener()
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    stream = CommonTokenStream(lexer)
    parser = VelocitronPetriNetParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.document()
    stream.fill()
    if listener.errors:
        line, column, message = listener.errors[0]
        raise PetrinetParseError(message, line=line, column=column)
    composition = tree.compositionHeader()
    if composition is not None:
        return PetrinetParse(
            kind="composition",
            name=_decoded_name(composition.name()),
            source_name=source_name,
            tree=tree,
        )
    header = tree.netHeader()
    name = "unnamed" if header is None else _decoded_name(header.name())
    return PetrinetParse(kind="net", name=name, source_name=source_name, tree=tree)


__all__ = [
    "GRAMMAR_FILE_NAME",
    "PetrinetParse",
    "PetrinetParseError",
    "grammar_text",
    "parse_petrinet",
]
