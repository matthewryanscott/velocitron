import pytest

from velocitron_cel import NO_CEL_WARNING_ENV


@pytest.fixture(autouse=True)
def no_cel_backend_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the CLI's Rust-backend note out of stderr checks on the pure-Python leg."""
    monkeypatch.setenv(NO_CEL_WARNING_ENV, "1")
