"""The CLI's note that the Rust CEL backend would be faster (ADR 0053)."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocitron_cli import HOST
from velocitron_cel import (
    NO_CEL_WARNING_ENV,
    CelAdapter,
    CelExprAdapter,
    CelpyAdapter,
    CelRustAdapter,
    interpreter_machine,
    rust_wheel_available,
    slow_backend_hint,
)
import velocitron_cli as cli

NET = Path(__file__).parent / "fixtures" / "prove" / "mutex.petrinet"


def test_the_pure_python_backend_gets_the_install_command():
    hint = slow_backend_hint(
        CelpyAdapter(), environ={}, wheel_available=True, re2_standin=False
    )
    assert hint is not None
    assert "pip install 'velocitron-cel[cel-rust]'" in hint
    assert NO_CEL_WARNING_ENV in hint


@pytest.mark.parametrize("adapter", [CelRustAdapter(), CelExprAdapter()])
def test_a_native_backend_gets_no_hint(adapter: CelAdapter):
    assert (
        slow_backend_hint(adapter, environ={}, wheel_available=True, re2_standin=False)
        is None
    )


def test_no_hint_without_a_rust_wheel_for_the_platform():
    assert (
        slow_backend_hint(
            CelpyAdapter(), environ={}, wheel_available=False, re2_standin=False
        )
        is None
    )


def test_the_environment_variable_silences_the_hint():
    environ = {NO_CEL_WARNING_ENV: "1"}
    assert (
        slow_backend_hint(
            CelpyAdapter(), environ=environ, wheel_available=True, re2_standin=False
        )
        is None
    )


@pytest.mark.parametrize(
    (
        "system",
        "machine",
        "version",
        "implementation",
        "libc",
        "free_threaded",
        "expected",
    ),
    [
        ("Darwin", "arm64", (3, 14), "CPython", "", False, True),
        ("Linux", "x86_64", (3, 12), "CPython", "glibc", False, True),
        ("Windows", "AMD64", (3, 13), "CPython", "", False, True),
        ("Linux", "x86_64", (3, 15), "CPython", "glibc", False, True),
        ("Darwin", "arm64", (3, 15), "CPython", "", False, False),
        ("Linux", "x86_64", (3, 12), "CPython", "", False, False),
        ("Linux", "riscv64", (3, 12), "CPython", "glibc", False, False),
        ("Windows", "ARM64", (3, 13), "CPython", "", False, False),
        ("Darwin", "arm64", (3, 14), "CPython", "", True, False),
        ("Linux", "x86_64", (3, 14), "CPython", "glibc", True, True),
        ("Linux", "x86_64", (3, 12), "PyPy", "glibc", False, False),
        ("Linux", "aarch64", (3, 13), "CPython", "glibc", False, True),
        ("Linux", "armv7l", (3, 14), "CPython", "glibc", False, True),
        ("Linux", "i686", (3, 15), "CPython", "glibc", False, True),
        ("Linux", "aarch64", (3, 15), "CPython", "glibc", False, False),
        ("Windows", "win32", (3, 13), "CPython", "", False, False),
        ("Linux", "x86_64", (3, 13), "CPython", "glibc", True, False),
        ("Linux", "x86_64", (3, 16), "CPython", "glibc", False, False),
    ],
)
def test_rust_wheel_platforms(
    system: str,
    machine: str,
    version: tuple[int, int],
    implementation: str,
    libc: str,
    free_threaded: bool,
    expected: bool,
):
    assert (
        rust_wheel_available(
            system, machine, version, implementation, libc, free_threaded
        )
        is expected
    )


def _fake_hint(suggest_rust: bool = True) -> str:
    return "use the Rust backend\n" if suggest_rust else "matches() uses re\n"


def test_the_cli_writes_the_hint_once_per_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(HOST, "slow_backend_hint", _fake_hint)
    monkeypatch.setattr(HOST, "backend_hint_shown", False)
    cli.main(["equiv", str(NET), str(NET)])
    cli.main(["equiv", str(NET), str(NET)])
    assert capsys.readouterr().err.count("use the Rust backend") == 1


def test_prove_gets_no_rust_suggestion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(HOST, "slow_backend_hint", _fake_hint)
    monkeypatch.setattr(HOST, "backend_hint_shown", False)
    cli.main(["prove", "--fact", "invariants", str(NET)])
    err = capsys.readouterr().err
    assert "use the Rust backend" not in err
    assert "matches() uses re" in err


def test_without_the_rust_suggestion_only_the_re2_note_is_left():
    adapter = CelpyAdapter()
    quiet = slow_backend_hint(
        adapter, environ={}, wheel_available=True, re2_standin=False, suggest_rust=False
    )
    assert quiet is None
    hint = slow_backend_hint(
        adapter, environ={}, wheel_available=True, re2_standin=True, suggest_rust=False
    )
    assert hint is not None
    assert "matches()" in hint and "pip install" not in hint


def test_a_command_that_evaluates_no_cel_gets_no_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(HOST, "slow_backend_hint", _fake_hint)
    monkeypatch.setattr(HOST, "backend_hint_shown", False)
    cli.main(["validate", str(NET)])
    assert "use the Rust backend" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("system", "machine", "bits", "expected"),
    [
        ("Linux", "x86_64", 64, "x86_64"),
        ("Linux", "x86_64", 32, "i686"),
        ("Linux", "aarch64", 32, "armv7l"),
        ("Linux", "armv6l", 32, "armv6l"),
        ("Windows", "AMD64", 32, "win32"),
        ("Windows", "ARM64", 64, "ARM64"),
    ],
)
def test_the_wheel_follows_the_interpreter_not_the_kernel(
    system: str, machine: str, bits: int, expected: str
):
    assert interpreter_machine(system, machine, bits) == expected


def test_the_re2_stand_in_gets_a_note_without_a_rust_wheel():
    hint = slow_backend_hint(
        CelpyAdapter(), environ={}, wheel_available=False, re2_standin=True
    )
    assert hint is not None
    assert "matches()" in hint
    assert "pip install" not in hint


def test_both_notes_share_one_hide_line():
    hint = slow_backend_hint(
        CelpyAdapter(), environ={}, wheel_available=True, re2_standin=True
    )
    assert hint is not None
    assert "matches()" in hint and "pip install" in hint
    assert hint.count(NO_CEL_WARNING_ENV) == 1


def test_the_environment_variable_silences_the_re2_note():
    environ = {NO_CEL_WARNING_ENV: "1"}
    assert (
        slow_backend_hint(
            CelpyAdapter(), environ=environ, wheel_available=False, re2_standin=True
        )
        is None
    )
