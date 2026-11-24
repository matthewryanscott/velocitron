"""Generated replay imports load the extracted package."""

from __future__ import annotations

import velocitron_replay as seam
from velocitron_replay import ReplayBase, ReplayCursor, replay_run


def test_umbrella_replay_is_the_package_seam() -> None:
    # then: `from velocitron_replay import ReplayBase` is velocitron_replay
    assert seam.ReplayBase is ReplayBase
    assert seam.ReplayCursor is ReplayCursor
    assert seam.replay_run is replay_run
