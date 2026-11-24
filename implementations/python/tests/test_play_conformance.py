"""The play conformance cases in ``packages/spec/conformance/play``.

Each case directory holds ``case.play``, the nets it names, and
``expected.trace.json``: one trace per path, as ``trace_json`` writes it
(no timestamps). Regenerate with ``VELOCITRON_UPDATE_GOLDEN=1`` after an
intended change, and review the diff.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from velocitron_play import (
    read_play,
)
from velocitron_play_check import (
    check_play,
    trace_json,
)

_CASES = Path(__file__).parents[3] / "packages" / "spec" / "conformance" / "play"
_CASE_DIRS = (
    sorted(p for p in _CASES.iterdir() if p.is_dir()) if _CASES.is_dir() else []
)


@pytest.mark.skipif(not _CASE_DIRS, reason="the spec tree is not present")
@pytest.mark.parametrize("case", _CASE_DIRS, ids=lambda p: p.name)
def test_case_matches_its_expected_traces(case: Path) -> None:
    # given
    play = read_play(case / "case.play")

    # when
    traces = [trace_json(t) for t in check_play(play).traces]

    # then
    expected_path = case / "expected.trace.json"
    rendered = json.dumps(traces, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("VELOCITRON_UPDATE_GOLDEN"):
        expected_path.write_text(rendered, encoding="utf-8")
    assert traces == json.loads(expected_path.read_text(encoding="utf-8"))
