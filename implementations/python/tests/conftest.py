import gc
import sys

import pytest

from velocitron_cel import NO_CEL_WARNING_ENV

# One exploration on the C++ backend can leave a multi-gigabyte glibc arena
# resident after its Python objects are gone. The next exploration then grows
# past the hosted runner's memory. Trim only while that arena is still
# resident: walking it after every test is what stretched the C++ job.
_TRIM_ABOVE_KB = 1_000_000


@pytest.fixture(autouse=True)
def no_cel_backend_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the CLI's Rust-backend note out of stderr checks on the pure-Python leg."""
    monkeypatch.setenv(NO_CEL_WARNING_ENV, "1")


def _resident_kb() -> int:
    try:
        status = open("/proc/self/status", encoding="ascii")
    except OSError:
        return 0
    with status:
        for line in status:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> None:
    """Return a leftover multi-gigabyte arena while the process still holds one."""
    del item, nextitem
    if not sys.platform.startswith("linux") or _resident_kb() < _TRIM_ABOVE_KB:
        return
    import ctypes

    gc.collect()
    trim = getattr(ctypes.CDLL(None), "malloc_trim", None)
    if trim is not None:
        trim(0)
