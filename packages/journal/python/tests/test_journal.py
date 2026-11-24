"""JsonlJournal appends records and reads them back."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from velocitron_engine import Token
from velocitron_journal import JsonlJournal, serialize_record_value


def _firing(transition: str = "move") -> dict[str, object]:
    return {
        "firingId": f"lane/{transition}/0",
        "netId": "lane",
        "transition": transition,
        "attempt": 0,
        "status": "completed",
        "inputTokens": {"src": [Token("job", {"id": 1})]},
        "outputTokens": {"dst": [Token("job", {"id": 1, "done": True})]},
        "error": None,
        "metadata": {},
        "timestamps": {"fired_at": "2026-01-01T00:00:00Z"},
    }


def test_jsonl_journal_numbers_every_channel_from_one_stream() -> None:
    # given: an in-memory journal
    journal = JsonlJournal()

    # when: firing, deposit, injection, trace, runtime, and a net revision append
    journal.record_firing(_firing())  # type: ignore[arg-type]
    journal.record_deposit_violation(_firing("drop"))  # type: ignore[arg-type]
    journal.record_injection(
        {
            "injectionId": "lane/@inject/src/0",
            "netId": "lane",
            "place": "src",
            "attempt": 0,
            "kind": "inject",
            "tokens": [Token("job", {"id": 2})],
            "replaced": [],
            "timestamps": {"fired_at": "2026-01-01T00:00:01Z"},
        }
    )
    journal.record_trace(
        {
            "event": "handler_started",
            "netId": "lane",
            "firingId": "lane/move/0",
            "transition": "move",
            "handler": "move",
            "method": None,
            "at": "2026-01-01T00:00:00Z",
            "status": None,
            "result": None,
            "error": None,
        }
    )
    journal.record_runtime(
        {
            "event": "suppressed",
            "netId": "lane",
            "firingId": None,
            "source": None,
            "detail": "late",
        }
    )
    journal.record_net_revision({"name": "lane"})

    # then: one monotonic sequence covers every channel
    assert [record["sequence"] for record in journal.records()] == [0, 1, 2, 3, 4, 5]
    assert journal.records()[5]["name"] == "lane"


def test_records_are_detached_copies() -> None:
    # given: one buffered firing
    journal = JsonlJournal()
    journal.record_firing(_firing())  # type: ignore[arg-type]

    # when: a caller mutates the read-back dict
    first = journal.records()
    first[0]["transition"] = "mutated"

    # then: the buffer is unchanged
    assert journal.records()[0]["transition"] == "move"


def test_flush_without_a_prefix_writes_nothing(tmp_path: Path) -> None:
    # given: a journal with no prefix
    journal = JsonlJournal()
    journal.record_firing(_firing())  # type: ignore[arg-type]

    # when: flush runs
    journal.flush()

    # then: the directory stays empty and the record is still readable
    assert list(tmp_path.iterdir()) == []
    assert journal.records()[0]["sequence"] == 0


def test_flush_writes_one_json_object_per_line(tmp_path: Path) -> None:
    # given: a journal whose prefix is inside the test directory
    prefix = tmp_path / "run"
    journal = JsonlJournal(str(prefix))
    journal.record_firing(_firing())  # type: ignore[arg-type]

    # when: flush writes the timestamped file
    journal.flush()

    # then: the line round-trips the token as type and data
    written = list(tmp_path.glob("run-*.jsonl"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["sequence"] == 0
    assert payload["inputTokens"]["src"] == [{"type": "job", "data": {"id": 1}}]


def test_serialize_record_value_rejects_an_unknown_object() -> None:
    # given: a token and a plain object the journal cannot replay
    token = Token("job", {"id": 1})

    @dataclasses.dataclass
    class Note:
        text: str

    # when: the shared serializer sees each value
    # then: a token and a dataclass become JSON objects, and anything else raises
    assert serialize_record_value(token) == {"type": "job", "data": {"id": 1}}
    assert serialize_record_value(Note("hi")) == {"text": "hi"}
    with pytest.raises(TypeError):
        serialize_record_value(object())
