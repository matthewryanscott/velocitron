"""Nox sessions for testing CEL backend configurations.

Each session syncs the integration-test project with a specific set of
optional CEL backends, then runs the full test suite. This exercises the
adapter-preference chain (Rust -> C++ -> cel-python) and the
environment-dependent skips in ``test_cel_adapter.py``.
"""

from __future__ import annotations

import nox

PYTHON_DIR = "implementations/python"


def _sync(session: nox.Session, *args: str) -> None:
    session.chdir(PYTHON_DIR)
    session.run(
        "uv",
        "sync",
        "--locked",
        "--no-default-groups",
        "--group",
        "test",
        *args,
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
        external=True,
    )


@nox.session(venv_backend="uv", tags=["cel"])
def test_celpy(session: nox.Session) -> None:
    """Test with only the core cel-python backend (no optional backends)."""
    _sync(session)
    session.run("pytest", *session.posargs)


@nox.session(venv_backend="uv", tags=["cel"])
def test_cel_expr(session: nox.Session) -> None:
    """Test with cel-expr-python (C++ binding) installed."""
    _sync(session, "--extra", "cel-cpp")
    session.run("pytest", *session.posargs)


@nox.session(venv_backend="uv", tags=["cel"])
def test_cel_rust(session: nox.Session) -> None:
    """Test with common-expression-language (Rust binding) installed."""
    _sync(session, "--extra", "cel-rust")
    session.run("pytest", *session.posargs)


@nox.session(venv_backend="uv", tags=["cel"])
def test_all(session: nox.Session) -> None:
    """Test with both optional CEL backends installed."""
    _sync(session, "--extra", "cel-cpp", "--extra", "cel-rust")
    session.run("pytest", *session.posargs)


@nox.session(venv_backend="uv")
def pyodide_parity(session: nox.Session) -> None:
    """Install the wheel in Pyodide and diff its output against the native
    CLI on the play conformance cases (ADR 0058).

    The first run fetches the pinned Pyodide package and wheels into
    ``tools/.pyodide-parity/``; later runs are fully offline."""
    session.run(
        "uv", "run", "--no-sync", "--project", PYTHON_DIR,
        "python", "tools/pyodide_parity.py",
    )


@nox.session(venv_backend="uv")
def prover_bench(session: nox.Session) -> None:
    """Prove each net of the benchmark set and compare the markings, edges and
    results with ``benchmarks/prover/numbers/``; exits 1 on a difference.

    Pass the command's flags after ``--``: ``nox -s prover_bench -- --quick``,
    ``-- --record`` to accept the new numbers."""
    session.run(
        "uv", "run", "--no-sync", "--project", PYTHON_DIR,
        "python", "tools/prover_bench.py", *session.posargs,
    )
