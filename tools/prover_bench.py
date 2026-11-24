#!/usr/bin/env python3
"""Run the prover on the benchmark set and compare with the recorded numbers.

From the repository root, in the integration-test environment:

    uv run --project implementations/python python tools/prover_bench.py

For each net of the set (`benchmarks/prover/set.json5`) it runs
`velocitron prove --json` in a fresh process and prints one row: markings,
edges, wall time, peak memory and the count of each result, then each
proof's result under it. A net the set marks heavy runs at a lower state cap
so the command finishes; its row says so.

The record is two files in `benchmarks/prover/numbers/`, one line a net:
`counts.jsonl` holds what is the same on any machine (the settings, whether
the run stopped at the state cap, markings, edges and each proof's result);
`timings.jsonl` holds wall time and peak memory, to two figures, with the
machine they come from. The command exits 1 when a net's counts differ from
its record, or a net has no record. Time and memory are printed beside the
recorded ones and never compared. A net the set marks measured only (the
compositions) prints its differences and never fails the command. A net the
set marks fast only runs on the fast path alone: a reference run leaves it
out and says so.

`--record` rewrites the record of the nets it records and keeps the other
lines; `--quick` leaves out the nets recorded at over a minute, which is the
set CI runs; `--net NAME` runs only the named nets. `--fast` proves on the
fast path, on every core; with `--one-core` too, on one core in the
reference's order, so CI can hold both modes to the same record (I7). Each
net is recorded on its own path: `--record` records the reference's nets,
and `--fast --record` the fast-only nets, whose timings name the fast path
and its mode; a full record takes both commands. A difference on a net the
run does not record still fails it.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json5
from velocitron_analysis import DEFAULT_MAX_STATES
from velocitron_cel import get_default_adapter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SET = ROOT / "benchmarks" / "prover" / "set.json5"
COUNTS = "counts.jsonl"
TIMINGS = "timings.jsonl"
QUICK_SECONDS = 60.0
REFERENCE_PATH = "reference"
"""The path a reference run's timings name."""


@dataclass(frozen=True)
class Entry:
    """One net of the benchmark set, as the set file names it."""

    name: str
    net: Path
    domains: Path | None
    domains_name: str | None
    max_states: int
    wait_arrivals: bool
    facts: tuple[str, ...]
    heavy: str | None
    measured_only: str | None
    fast_only: str | None

    def settings(self) -> dict[str, Any]:
        """How the net was run, as its counts record keeps it."""
        settings: dict[str, Any] = {
            "domains": self.domains_name,
            "maxStates": self.max_states,
        }
        if self.wait_arrivals:
            settings["waitArrivals"] = True
        if self.facts:
            settings["facts"] = list(self.facts)
        return settings


@dataclass(frozen=True)
class Set:
    entries: tuple[Entry, ...]


def read_set(path: Path) -> Set:
    document = json5.loads(path.read_text(encoding="utf-8"))
    root = path.parent / document.get("root", ".")
    entries: list[Entry] = []
    for item in document["nets"]:
        net_name: str = item["net"]
        domains_name: str | None = item.get("domains")
        if domains_name is None:
            beside = net_name.removesuffix(".petrinet") + ".domains.json5"
            domains_name = beside if (root / beside).exists() else None
        entries.append(
            Entry(
                name=item.get("name", net_name.removesuffix(".petrinet")),
                net=root / net_name,
                domains=root / domains_name if domains_name else None,
                domains_name=domains_name,
                max_states=int(item.get("maxStates", DEFAULT_MAX_STATES)),
                wait_arrivals=bool(item.get("waitArrivals", False)),
                facts=tuple(item.get("facts", ())),
                heavy=item.get("heavy"),
                measured_only=item.get("measuredOnly"),
                fast_only=item.get("fastOnly"),
            )
        )
    names = [entry.name for entry in entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise SystemExit(f"{path}: nets named twice: {', '.join(duplicates)}")
    return Set(entries=tuple(entries))


def read_lines(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["net"]] = record
    return records


def write_lines(path: Path, bench_set: Set, records: dict[str, dict[str, Any]]) -> None:
    """One line a net, in set order; a net left out of the set loses its line."""
    lines = [
        json.dumps(records[entry.name], ensure_ascii=False)
        for entry in bench_set.entries
        if entry.name in records
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def two_figures(value: float) -> float:
    """Round to two significant figures, so chance noise rarely moves a line."""
    return float(f"{value:.2g}")


@dataclass(frozen=True)
class Run:
    """One net proved once: its counts line, or why there is none, and its cost."""

    counts: dict[str, Any] | None
    error: str | None
    seconds: float
    peak_mb: float


def run(entry: Entry, *, fast: bool = False, one_core: bool = False) -> Run:
    """Prove one net in a fresh process, so its peak memory is its own;
    ``fast`` proves it on the fast path, on one core with ``one_core``."""
    command = [
        sys.executable,
        "-m",
        "velocitron_cli",
        "prove",
        str(entry.net),
        "--json",
        "--max-states",
        str(entry.max_states),
    ]
    if entry.domains is not None:
        command += ["--domains", str(entry.domains)]
    if entry.wait_arrivals:
        command.append("--wait-arrivals")
    for fact in entry.facts:
        command += ["--fact", fact]
    if fast:
        command.append("--fast")
    if one_core:
        command.append("--one-core")
    started = time.perf_counter()
    # stderr stays the terminal's: the CEL slow-backend note must show.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    assert process.stdout is not None
    output = process.stdout.read()
    _pid, status, rusage = os.wait4(process.pid, 0)
    seconds = time.perf_counter() - started
    process.returncode = os.waitstatus_to_exitcode(status)
    # ru_maxrss is bytes on macOS and KiB on Linux.
    peak_mb = rusage.ru_maxrss * (1 if sys.platform == "darwin" else 1024) / 1_000_000
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        return Run(None, f"prove failed (exit {process.returncode})", seconds, peak_mb)
    exploration = report.get("exploration") or {}
    proofs: dict[str, str] = {}
    for fact in report["facts"]:
        key = f"{fact['fact']}: {fact['subject']}"
        number = 2
        while key in proofs:
            key = f"{fact['fact']}: {fact['subject']} #{number}"
            number += 1
        proofs[key] = fact["status"]
    counts = {
        "net": entry.name,
        **entry.settings(),
        "capped": bool(exploration.get("capped", False)),
        "markings": exploration.get("states"),
        "edges": exploration.get("edges"),
        "proofs": proofs,
    }
    return Run(counts, None, seconds, peak_mb)


def differences(
    name: str, counts: dict[str, Any], recorded: dict[str, Any] | None
) -> list[str]:
    """Where this run's counts differ from the record; time and memory never do."""
    if recorded is None:
        return [f"{name}: no recorded numbers"]
    found: list[str] = []
    for key in (
        "domains",
        "maxStates",
        "waitArrivals",
        "facts",
        "capped",
        "markings",
        "edges",
    ):
        if counts.get(key) != recorded.get(key):
            found.append(
                f"{name}: {key} {counts.get(key)}, recorded {recorded.get(key)}"
            )
    proofs: dict[str, str] = counts["proofs"]
    was: dict[str, str] = recorded.get("proofs", {})
    for proof in sorted(proofs.keys() | was.keys()):
        now, then = proofs.get(proof), was.get(proof)
        if now != then:
            found.append(
                f"{name}: {proof} {(now or 'missing').upper()}, "
                f"recorded {(then or 'missing').upper()}"
            )
    return found


def row(entry: Entry, result: Run, timing: dict[str, Any] | None) -> str:
    if result.counts is None:
        return f"{entry.name:34} {result.error}"
    counts = result.counts
    seconds = f"{result.seconds:8.1f} s"
    if timing is not None:
        seconds += f" (was {timing['seconds']:.1f} s)"
    tally: dict[str, int] = {}
    for status in counts["proofs"].values():
        tally[status] = tally.get(status, 0) + 1
    results = " · ".join(
        f"{status} {tally[status]}"
        for status in ("proved", "refuted", "unknown")
        if status in tally
    )
    marks = []
    if entry.heavy:
        marks.append(f"heavy, cap {entry.max_states}")
    elif counts["capped"]:
        marks.append(f"state cap {entry.max_states} hit")
    if entry.measured_only:
        marks.append("measured only")
    if entry.fast_only:
        marks.append("fast only")
    if entry.wait_arrivals:
        marks.append("wait arrivals")
    if entry.facts:
        marks.append("facts " + ", ".join(entry.facts))
    mark = f"  [{'; '.join(marks)}]" if marks else ""
    # A run of choices and invariants alone explores nothing.
    markings, edges = (
        "—" if counts[key] is None else counts[key] for key in ("markings", "edges")
    )
    return (
        f"{entry.name:34} {markings:>9} {edges:>10} "
        f"{seconds:24} {result.peak_mb:8.1f} MB  {results}{mark}"
    )


def _path(args: argparse.Namespace) -> str:
    if not args.fast:
        return REFERENCE_PATH
    return "fast (one core)" if args.one_core else "fast (every core)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--set", type=Path, default=DEFAULT_SET, help="the benchmark set file"
    )
    parser.add_argument(
        "--numbers",
        type=Path,
        metavar="DIR",
        help=f"the directory of {COUNTS} and {TIMINGS} (default: numbers/ beside the set)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help=(
            "write the numbers of the nets this path records: the reference's "
            "nets, or with --fast the fast-only nets"
        ),
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=f"leave out nets recorded at over {QUICK_SECONDS:.0f} s",
    )
    parser.add_argument(
        "--net", action="append", metavar="NAME", help="run only this net (repeatable)"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help=(
            "prove on the fast path; its counts are compared with the record, "
            "and only the nets the set marks fast only record their numbers"
        ),
    )
    parser.add_argument(
        "--one-core",
        action="store_true",
        help="with --fast: the kernel explores on one core, in the reference's order",
    )
    args = parser.parse_args(argv)
    if args.one_core and not args.fast:
        parser.error("--one-core needs --fast")
    numbers: Path = args.numbers or args.set.parent / "numbers"
    bench_set = read_set(args.set)
    counts_record = read_lines(numbers / COUNTS)
    timings_record = read_lines(numbers / TIMINGS)

    entries = list(bench_set.entries)
    if args.net:
        unknown = sorted(set(args.net) - {entry.name for entry in entries})
        if unknown:
            parser.error(f"not in the set: {', '.join(unknown)}")
        entries = [entry for entry in entries if entry.name in args.net]
        fast_only = [entry.name for entry in entries if entry.fast_only]
        if fast_only and not args.fast:
            parser.error(
                f"runs on the fast path alone: {', '.join(fast_only)} (add --fast)"
            )
    left_out: list[str] = []
    if not args.fast:
        left_out = [f"{entry.name} (fast only)" for entry in entries if entry.fast_only]
        entries = [entry for entry in entries if not entry.fast_only]
    slow: list[str] = []
    if args.quick:
        kept = []
        for entry in entries:
            seconds = timings_record.get(entry.name, {}).get("seconds")
            if seconds is not None and seconds > QUICK_SECONDS:
                slow.append(f"{entry.name} (recorded {seconds:.1f} s)")
            else:
                kept.append(entry)
        entries = kept

    machine = {
        "machine": platform.platform(),
        "cel": type(get_default_adapter()).__name__,
        "velocitron": None,
        "date": datetime.date.today().isoformat(),
    }
    print(
        f"benchmark set {args.set.name}: {len(entries)} nets, "
        f"{_path(args)} path; "
        f"CEL {machine['cel']}, {machine['machine']}"
    )
    print(
        f"{'net':34} {'markings':>9} {'edges':>10} {'wall time':24} {'peak mem':>11}  results"
    )
    started = time.perf_counter()
    failing: list[str] = []
    recorded_over: list[str] = []
    measured: list[str] = []
    recorded: list[str] = []
    failed = False
    for entry in entries:
        result = run(entry, fast=args.fast, one_core=args.one_core)
        print(row(entry, result, timings_record.get(entry.name)), flush=True)
        for label, note in (
            ("heavy", entry.heavy),
            ("measured only", entry.measured_only),
            ("fast only", entry.fast_only),
        ):
            if note:
                print(f"    {label}: {note}")
        if result.counts is None:
            failed = True
            failing.append(f"{entry.name}: {result.error}")
            continue
        for proof, status in result.counts["proofs"].items():
            print(f"    {status.upper():8} {proof}")
        found = differences(entry.name, result.counts, counts_record.get(entry.name))
        record = args.record and bool(entry.fast_only) == args.fast
        if entry.measured_only:
            measured.extend(found)
        else:
            (recorded_over if record else failing).extend(found)
        if record:
            recorded.append(entry.name)
            counts_record[entry.name] = result.counts
            timings_record[entry.name] = {
                "net": entry.name,
                "path": _path(args),
                "seconds": two_figures(result.seconds),
                "peakMB": two_figures(result.peak_mb),
                **machine,
            }
    print(f"{len(entries)} nets in {time.perf_counter() - started:.1f} s")
    if left_out:
        print(f"left out of the reference: {', '.join(left_out)}")
    if slow:
        print(f"left out by --quick: {', '.join(slow)}")
    if recorded:
        write_lines(numbers / COUNTS, bench_set, counts_record)
        write_lines(numbers / TIMINGS, bench_set, timings_record)
        print(f"recorded in {numbers / COUNTS} and {numbers / TIMINGS}")
    for heading, lines in (
        ("recorded over these differences:", recorded_over),
        ("differences from the record:", failing),
        ("differences on nets measured only, which never fail:", measured),
    ):
        if lines:
            print(heading)
            for line in lines:
                print(f"  {line}")
    return 1 if failed or failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
