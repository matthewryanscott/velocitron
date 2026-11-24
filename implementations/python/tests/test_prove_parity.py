"""Prove reports stay the same when the prover gets faster.

Every ``.petrinet`` under ``examples/`` and the test fixtures is proved with
every fact and a low state cap, so the big nets stop early but always at the
same place. A ``<stem>.domains.json5`` beside a net is its domains file. The
pinned entry per net is its exploration size, each fact's status, and a
digest of the whole report: every finding, witness and path. A change that
only makes ``prove`` faster must keep every entry. Regenerate with
``VELOCITRON_UPDATE_GOLDEN=1`` after an intended change of what ``prove``
finds, and review the diff.

References: spec/proofs.md.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from velocitron_analysis import load, prove, read_settings


_ROOT = Path(__file__).resolve().parents[3]
_GOLDEN = Path(__file__).parent / "fixtures" / "prove" / "parity.json"
# 300, the same bound as test_prove_arrivals. A 2_000-state exploration on
# the C++ backend leaves a multi-gigabyte allocator arena resident: arrivals
# + composition + parity peaked at 7,418,192 KB on main and 6,104,352 KB on
# this branch. The hosted runner has about 7 GB and is shut down (the runner
# shutdown signal) once the process crosses that. Nets that end do so under
# 300 states; the ones that do not stop at the same place on every backend.
_MAX_STATES = 300


def _corpus() -> list[str]:
    return sorted(
        path.relative_to(_ROOT).as_posix()
        for base in ("examples", "implementations/python/tests/fixtures")
        for path in (_ROOT / base).rglob("*.petrinet")
    )


def _entry(
    name: str, *, fast: bool = False, notes: list[str] | None = None
) -> dict[str, Any]:
    path = _ROOT / name
    domains = path.with_name(f"{path.stem}.domains.json5")
    net, composition = load(path)
    report = prove(
        net,
        settings=read_settings(domains) if domains.exists() else None,
        max_states=_MAX_STATES,
        composition=composition,
        fast=fast,
        on_reference=None if notes is None else notes.append,
    ).as_json()
    exploration = report.get("exploration") or {}
    # What made the markings is for the author; two provers are not compared
    # on it (proofs.md, What made the markings), so the digest leaves it out.
    exploration.pop("madeBy", None)
    # A composition's report names its files by absolute path; the digest
    # names them from the repository root, so any checkout pins the same.
    text = json.dumps(report, sort_keys=True, ensure_ascii=False)
    text = text.replace(json.dumps(str(_ROOT))[1:-1] + "/", "")
    return {
        "states": exploration.get("states"),
        "edges": exploration.get("edges"),
        "facts": {f"{f['fact']}: {f['subject']}": f["status"] for f in report["facts"]},
        "report": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _pinned() -> dict[str, Any]:
    """The committed golden. A file that is not JSON fails here, before any net is proved."""
    text = _GOLDEN.read_text(encoding="utf-8")
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{_GOLDEN.name} is not JSON ({exc}). "
            "Regenerate it with VELOCITRON_UPDATE_GOLDEN=1 and do not reformat it."
        ) from exc
    if not isinstance(loaded, dict) or not loaded:
        raise AssertionError(f"{_GOLDEN.name} has no pinned nets")
    return loaded


def test_the_pinned_golden_is_json() -> None:
    # given: the file the parity tests load
    # then: it parses, so a truncated or hand-edited golden fails before the corpus runs
    pinned = _pinned()
    assert all(
        isinstance(entry, dict) and "report" in entry for entry in pinned.values()
    )


def test_every_report_matches_its_pinned_result() -> None:
    # given: the nets of the examples and the fixtures
    corpus = _corpus()
    updating = os.environ.get("VELOCITRON_UPDATE_GOLDEN")
    pinned = None if updating else _pinned()
    # when: each is proved
    results = {name: _entry(name) for name in corpus}
    # then: each report is the pinned one, or the golden is rewritten as JSON
    if updating:
        text = json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        json.loads(text)
        _GOLDEN.write_text(text, encoding="utf-8")
        return
    assert pinned is not None
    assert sorted(results) == sorted(pinned)
    changed = [name for name in corpus if results[name] != pinned[name]]
    assert changed == [], {name: (pinned[name], results[name]) for name in changed}


def test_the_fast_path_gives_every_pinned_report() -> None:
    # given: the same nets, proved on the fast path
    corpus = _corpus()
    pinned = _pinned()
    # when:
    notes: dict[str, list[str]] = {name: [] for name in corpus}
    results = {name: _entry(name, fast=True, notes=notes[name]) for name in corpus}
    # then: each report, its findings, witnesses and paths, is the pinned one
    changed = [name for name in corpus if results[name] != pinned[name]]
    assert changed == [], {name: (pinned[name], results[name]) for name in changed}
    # and: the kernel proved all but the nets its tables cannot carry yet
    assert {name for name in corpus if notes[name]} == set(_ON_REFERENCE)


# The corpus nets with a guard, a predicate handler or an arc of weight 2 or
# more, which the kernel's tables cannot carry yet.
_ON_REFERENCE = [
    "examples/capability-ladder/04-source-router/source-router-predicate-handlers.petrinet",
    "examples/capability-ladder/06-batch-gate/batch-gate.petrinet",
    "examples/capability-ladder/08-guarded-curation-choice/guarded-curation-choice.petrinet",
    "examples/capability-ladder/13-museum-loan/museum-loan.petrinet",
    "implementations/python/tests/fixtures/codegen/small_guarded.petrinet",
    "implementations/python/tests/fixtures/play/shop.petrinet",
    "implementations/python/tests/fixtures/prove/deadline.petrinet",
    "implementations/python/tests/fixtures/prove/redelivery.petrinet",
    "implementations/python/tests/fixtures/prove/side-copy-count.petrinet",
]
