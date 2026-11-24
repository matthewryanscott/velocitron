"""The public replay seam drives Engine.fire from a journal tape."""

from __future__ import annotations

import importlib.util
from typing import Any, ClassVar

import pytest

from velocitron_engine import (
    Arc,
    ConsumePattern,
    Engine,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    ProduceTemplate,
    Token,
    Transition,
)
from velocitron_journal import JsonlJournal
from velocitron_netbase import VelocitronNet, net_sha256
from velocitron_replay import (
    ReplayBase,
    ReplayCursor,
    ReplayNetMismatch,
    ReplayOrderError,
    replay_run,
)


class _Cel:
    def compile(self, expr: str) -> str:
        return expr

    def eval(self, compiled: str, data: dict[str, Any]) -> bool:
        del compiled, data
        return False


def _net() -> Net:
    return Net(
        name="move",
        places=[Place("src", ["job"]), Place("dst", ["job"])],
        transitions=[Transition("move", handler="move@move")],
        arcs=[
            Arc(
                from_place="src",
                to_transition="move",
                consume=ConsumePattern("job", None, "consume"),
            ),
            Arc(
                from_transition="move",
                to_place="dst",
                produce=ProduceTemplate("job", "dst"),
            ),
        ],
        initial_marking=Marking(),
    )


def test_package_does_not_import_the_umbrella() -> None:
    # then: the driver is importable without the umbrella package
    assert importlib.util.find_spec("velocitron") is None
    assert importlib.util.find_spec("velocitron_replay") is not None


def test_strict_replay_answers_from_the_tape() -> None:
    # given: a recorded one-step run whose handler produced the destination token
    net = _net()
    digest = net_sha256(net)
    called = {"live": 0, "replay": 0}

    class Live(VelocitronNet):
        NET_NAME = "move"
        SOURCE = "move.petrinet"
        SOURCE_SHA256 = digest
        HANDLER_REFS: ClassVar[dict[str, str]] = {"move@move": "fire_move"}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"move": ("src",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"move": ("dst",)}

        def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
            called["live"] += 1
            assert [token.data for token in src] == [{"n": 1}]
            return {"dst": [Token("job", {"done": True})]}

    recording = JsonlJournal()
    registration = Live().register_into(HandlerRegistry(), net, journal=recording)
    assert registration.registry is not None
    start = Marking({"src": [Token("job", {"n": 1})]})
    recorded = Engine(
        registration.registry, journal=recording, cel_adapter=_Cel()
    ).advance(registration.net, start)
    assert called["live"] == 1
    assert [token.data for token in recorded["dst"]] == [{"done": True}]

    class ReplayMove(ReplayBase):
        NET_NAME = "move"
        SOURCE = "move.petrinet"
        SOURCE_SHA256 = digest
        HANDLER_REFS: ClassVar[dict[str, str]] = {"move@move": "fire_move"}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"move": ("src",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"move": ("dst",)}

        def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
            called["replay"] += 1
            raise AssertionError("replay never calls fire_move")

    # when: the same tape is replayed through the public driver
    cursor = ReplayCursor.from_journal(recording, owner="move")
    replay = ReplayMove(cursor)
    replay_registration = replay.register_into(HandlerRegistry(), net)
    result = replay_run(
        net,
        replay,
        replay_registration,
        cursor,
        marking=start,
        journal=JsonlJournal(),
        cel_adapter=_Cel(),
    )

    # then: the marking matches the recording and the user method did not run
    assert called["replay"] == 0
    assert result.net_matches is True
    assert result.divergence is None
    assert result.steps == 1
    assert [token.data for token in result.final_marking["dst"]] == [{"done": True}]


def test_out_of_order_firing_raises_replay_order_error() -> None:
    # given: a tape whose next firing is f-1
    cursor = ReplayCursor(
        [
            {
                "firingId": "f-1",
                "status": "completed",
                "attempt": 0,
                "outputTokens": {},
                "sequence": 1,
            }
        ],
        owner="move",
    )

    # when: the engine asks for a different firing id
    with pytest.raises(ReplayOrderError) as caught:
        cursor.next_firing("f-2")

    # then: the error names the tape, the call, and the position
    assert caught.value.expected == "f-1"
    assert caught.value.got == "f-2"
    assert caught.value.sequence == 1
    assert caught.value.owner == "move"


def test_strict_mode_refuses_a_different_net_revision() -> None:
    # given: a tape whose net revision does not hash to the registration
    net = _net()
    digest = net_sha256(net)

    class ReplayMove(ReplayBase):
        NET_NAME = "move"
        SOURCE = "move.petrinet"
        SOURCE_SHA256 = digest
        HANDLER_REFS: ClassVar[dict[str, str]] = {"move@move": "fire_move"}
        INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"move": ("src",)}
        OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {"move": ("dst",)}

        def fire_move(self, *, src: list[Token]) -> dict[str, list[Token]]:
            del src
            raise AssertionError("replay never calls fire_move")

    cursor = ReplayCursor([{"name": "not-a-net", "sequence": 0}])
    replay = ReplayMove(cursor)
    registration = replay.register_into(HandlerRegistry(), net)

    # when / then: strict mode stops before the first step
    with pytest.raises(ReplayNetMismatch):
        replay_run(
            net,
            replay,
            registration,
            cursor,
            cel_adapter=_Cel(),
        )
