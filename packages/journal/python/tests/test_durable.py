"""Sqlite journal appends records and reads them back in order."""

from __future__ import annotations

from pathlib import Path

from velocitron_engine import Marking, Net, Place, Token, Transition
from velocitron_journal import (
    DurableJournal,
    known_instances,
    open_database,
    read_events,
    replay_events,
)


def _firing(transition: str = "move") -> dict[str, object]:
    return {
        "firingId": f"lane/{transition}/0",
        "netId": "lane",
        "transition": transition,
        "attempt": 0,
        "status": "completed",
        "inputTokens": {"src": [Token("job", {"id": 1})]},
        "outputTokens": {"dst": [Token("job", {"id": 1})]},
        "error": None,
        "metadata": {},
        "timestamps": {"fired_at": "2026-01-01T00:00:00Z"},
    }


def _empty_net() -> Net:
    return Net(
        name="lane",
        places=[Place("src", ["job"]), Place("dst", ["job"])],
        transitions=[Transition("move")],
        arcs=[],
        initial_marking=Marking(),
    )


def test_durable_journal_appends_and_replays(tmp_path: Path) -> None:
    # given: a fresh sqlite log
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, "lane-1")
    journal.record_net_revision({"name": "lane"})
    journal.record_firing(_firing())  # type: ignore[arg-type]
    journal.record_injection(
        {
            "injectionId": "lane/@inject/dst/1",
            "netId": "lane",
            "place": "dst",
            "attempt": 1,
            "kind": "inject",
            "tokens": [Token("job", {"id": 2})],
            "replaced": [],
            "timestamps": {"fired_at": "2026-01-01T00:00:01Z"},
        }
    )

    # when: another connection reads the instance
    events = read_events(connection, "lane-1")
    records = journal.records()

    # then: kinds stay in append order and replay deposits both tokens
    assert known_instances(connection) == ["lane-1"]
    assert [event.kind for event in events] == ["net_revision", "firing", "injection"]
    assert [record["sequence"] for record in records] == [0, 1, 2]
    assert records[0]["kind"] == "net_revision"
    assert records[0]["recorded_at"]
    marking = replay_events(_empty_net(), events, initial=Marking())
    assert list(marking.get("dst", [])) == [Token("job", {"id": 1}), Token("job", {"id": 2})]
    connection.close()


def test_reopen_continues_the_sequence(tmp_path: Path) -> None:
    # given: one committed firing
    path = tmp_path / "events.db"
    first = open_database(path)
    DurableJournal(first, "lane-1").record_firing(_firing())  # type: ignore[arg-type]
    first.close()

    # when: a new journal opens the same instance
    second = open_database(path)
    journal = DurableJournal(second, "lane-1")
    journal.record_deposit_violation(_firing("drop"))  # type: ignore[arg-type]

    # then: the next sequence number continues after the stored maximum
    assert [record["sequence"] for record in journal.records()] == [0, 1]
    assert journal.records()[1]["kind"] == "deposit_violation"
    second.close()


def test_records_are_fresh_copies(tmp_path: Path) -> None:
    # given: one stored firing
    connection = open_database(tmp_path / "events.db")
    journal = DurableJournal(connection, "lane-1")
    journal.record_firing(_firing())  # type: ignore[arg-type]

    # when: a caller mutates a read-back dict
    records = journal.records()
    records[0]["transition"] = "mutated"

    # then: the next read still has the stored transition
    assert journal.records()[0]["transition"] == "move"
    connection.close()
