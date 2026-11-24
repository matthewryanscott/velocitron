"""The progress line of a long exploration (proofs.md, The progress line).

Every ten seconds an exploration writes one line: markings so far, markings
a second since the line before, the memory the process holds, the time so
far, the share of the state cap used, and how many markings still wait to
be explored, rising or falling. The memory figure is how an author knows to
lower the state cap; there is no memory limit of its own.

``progress_line`` holds the words. The shared cases in
``packages/spec/conformance/prove/progress-lines.json`` pin them, so any
prover that writes the line writes the same one.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from time import monotonic
from typing import Any, Literal

EVERY_SECONDS = 10.0

Trend = Literal["rising", "falling", "steady"]


def _number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _memory(size: int) -> str:
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    return f"{round(size / 1_000_000)} MB"


def _duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60:02} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02} min"


def progress_line(
    net: str,
    *,
    markings: int,
    per_second: int,
    memory_bytes: int,
    seconds: int,
    max_states: int,
    waiting: int,
    trend: Trend,
) -> str:
    """The progress line for these figures, without its newline."""
    return " · ".join(
        (
            f"prove {net}: {_number(markings)} markings",
            f"{_number(per_second)} a second",
            _memory(memory_bytes),
            _duration(seconds),
            f"{markings * 100 // max_states} % of the state cap",
            f"{_number(waiting)} waiting, {trend}",
        )
    )


def memory_in_use() -> int:
    """The bytes the process holds now: the physical footprint on macOS
    (compressed pages count, as Activity Monitor shows), the resident size
    on Linux, the peak resident size where only that is known, and 0 where
    nothing is (the browser)."""
    if sys.platform == "darwin":
        found = _darwin_footprint()
        if found is not None:
            return found
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/self/statm", encoding="ascii") as statm:
                resident = int(statm.read().split()[1])
            return resident * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            pass
    try:
        import resource
    except ImportError:
        return 0
    # ru_maxrss is bytes on macOS and KiB on Linux and the BSDs.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


_libc: Any = None


def _darwin_footprint() -> int | None:
    """``ri_phys_footprint`` of ``proc_pid_rusage(RUSAGE_INFO_V0)``: after
    the 16-byte uuid, the ninth 64-bit field (sys/resource.h)."""
    import ctypes

    global _libc
    if _libc is None:
        _libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    info = (ctypes.c_uint64 * 12)()
    if _libc.proc_pid_rusage(os.getpid(), 0, ctypes.byref(info)) != 0:
        return None
    return int(info[9])


def _now() -> float:
    # Read through the module, so a test can move the clock.
    return monotonic()


class Progress:
    """The progress of one exploration: ``tick`` after each marking it
    expands writes a line once ten seconds have passed since the last."""

    def __init__(
        self,
        net: str,
        max_states: int,
        write: Callable[[str], object],
        *,
        clock: Callable[[], float] = _now,
        memory: Callable[[], int] = memory_in_use,
    ) -> None:
        self._net = net
        self._max_states = max_states
        self._write = write
        self._clock = clock
        self._memory = memory
        self._started = self._last = clock()
        self.next_at = self._started + EVERY_SECONDS
        self._last_markings = 0
        # The exploration starts with the initial marking waiting.
        self._last_waiting = 1

    def tick(self, markings: int, waiting: int) -> None:
        now = self._clock()
        if now < self.next_at:
            return
        elapsed = now - self._last
        per_second = (
            int((markings - self._last_markings) / elapsed) if elapsed > 0 else 0
        )
        if waiting > self._last_waiting:
            trend: Trend = "rising"
        elif waiting < self._last_waiting:
            trend = "falling"
        else:
            trend = "steady"
        self._write(
            progress_line(
                self._net,
                markings=markings,
                per_second=per_second,
                memory_bytes=self._memory(),
                seconds=int(now - self._started),
                max_states=self._max_states,
                waiting=waiting,
                trend=trend,
            )
            + "\n"
        )
        self._last, self._last_markings, self._last_waiting = now, markings, waiting
        self.next_at = now + EVERY_SECONDS
