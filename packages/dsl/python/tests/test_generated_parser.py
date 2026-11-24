"""The generated ANTLR parser imports and reports a syntax error."""

from __future__ import annotations

import pytest
from antlr4 import CommonTokenStream, InputStream

from velocitron_dsl.generated.VelocitronPetriNetLexer import VelocitronPetriNetLexer
from velocitron_dsl.generated.VelocitronPetriNetParser import VelocitronPetriNetParser


def test_document_reports_unsupported_sentinel_as_positioned_syntax_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given: an input that is intentionally not a complete document
    lexer = VelocitronPetriNetLexer(InputStream("sentinel"))
    parser = VelocitronPetriNetParser(CommonTokenStream(lexer))

    # when: parsing the generated document entry point
    parser.document()

    # then: the parser emits an ordinary diagnostic at the sentinel's span
    diagnostics = capsys.readouterr().err.splitlines()
    assert diagnostics
    assert diagnostics[0].startswith("line 1:0 ")
    assert parser.getNumberOfSyntaxErrors() == len(diagnostics)
