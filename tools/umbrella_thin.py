#!/usr/bin/env python3
"""Fail when a retired facade grows an implementation back.

The packages under ``packages/`` are the source of truth. The published
``velocitron`` and ``@velocitron/core`` libraries are gone. Their source
trees must stay gone, and a returned file must not define an extracted
implementation again. ``python3 tools/<name>_package.py check`` calls this.
``sync`` refuses to copy a package out of a facade.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "implementations" / "python" / "src" / "velocitron"
TS = ROOT / "implementations" / "typescript" / "src"

# Own definitions that mean the umbrella copied the package back.
_FORBIDDEN_DEFS: dict[str, tuple[tuple[Path, str], ...]] = {
    "cel": (
        (PY / "cel.py", "CelpyAdapter"),
        (PY / "cel.py", "CelRustAdapter"),
        (PY / "cel.py", "CachingCelAdapter"),
        (PY / "cel.py", "get_default_adapter"),
        (PY / "cel.py", "slow_backend_hint"),
        (PY / "cel.py", "rust_wheel_available"),
    ),
    "dsl": ((PY / "dsl" / "lower.py", "lower_petrinet_text"),),
    "merge": ((PY / "composition.py", "_fusion_classes"),),
    "petrinet": (
        (PY / "parser.py", "parse_net"),
        (PY / "parser.py", "parse_composition"),
        (PY / "dsl" / "api.py", "compile_petrinet_text"),
        (PY / "dsl" / "api.py", "resolve_contribution_ir"),
        (PY / "dsl" / "api.py", "emit_petrinet"),
        (PY / "dsl" / "compiler.py", "resolve_contribution_ir"),
        (PY / "composition.py", "merge_nets"),
        (PY / "composition.py", "merge_composition"),
    ),
    "play": ((PY / "play" / "language.py", "parse_play"),),
    "play-check": (
        (PY / "play" / "check.py", "check_play"),
        (PY / "play" / "check.py", "load_play_net"),
        (PY / "play" / "walkthrough.py", "render_walkthrough"),
        (PY / "play" / "walkthrough.py", "walkthrough_document"),
        (PY / "play" / "sequence.py", "sequence_view"),
        (PY / "play" / "trace.py", "trace_document"),
        (PY / "play" / "records.py", "records_to_play"),
        (PY / "play" / "records.py", "RecordsToPlayError"),
    ),
    "engine": (
        (PY / "engine.py", "_topology"),
        (PY / "schema.py", "Net"),
        (PY / "registry.py", "HandlerRegistry"),
        (PY / "contract.py", "TransitionHandler"),
        (PY / "outputs.py", "symbolic_outputs"),
    ),
    "journal": (
        (PY / "journal.py", "JsonlJournal"),
        (PY / "journal.py", "replay_events"),
        (PY / "journal.py", "replay_records"),
        (PY / "durable_sqlite.py", "DurableJournal"),
        (PY / "durable_sqlite.py", "open_database"),
        (PY / "durable_sqlite.py", "read_events"),
    ),
    "runtime": (
        (PY / "runtime.py", "Runtime"),
        (PY / "runtime.py", "HandlerSpec"),
        (PY / "runtime.py", "_Mailbox"),
        (PY / "waits.py", "holds"),
        (PY / "waits.py", "intended_waits"),
        (PY / "waits.py", "wait_problems"),
    ),
    "analysis": (
        (PY / "prove" / "__init__.py", "prove"),
        (PY / "prove" / "__init__.py", "ProofSettings"),
        (PY / "prove" / "analysis.py", "NetModel"),
        (PY / "prove" / "soundness.py", "Explorer"),
        (PY / "prove" / "firing.py", "Firing"),
        (PY / "kept.py", "KeptRecord"),
        (PY / "kept.py", "kept_problems"),
        (PY / "lint.py", "lint_net"),
        (PY / "lint.py", "LintFinding"),
    ),
    "properties": (
        (PY / "properties.py", "check_marking"),
        (PY / "properties.py", "check_replay"),
        (PY / "properties.py", "capacity_properties"),
        (PY / "properties.py", "AtMostN"),
        (PY / "properties.py", "PropertyReport"),
    ),
    "explain": ((PY / "explain.py", "explain_net"),),
    "equiv": (
        (PY / "equiv.py", "compare"),
        (PY / "equiv.py", "Equivalence"),
        (PY / "equiv.py", "add_parser"),
        (PY / "equiv.py", "main"),
    ),
    "codegen": (
        (PY / "codegen" / "generator.py", "generate_module"),
        (PY / "codegen" / "generator.py", "GeneratedModule"),
        (PY / "codegen" / "generator.py", "CodegenError"),
        (PY / "codegen" / "composition_generator.py", "generate_composition"),
        (PY / "codegen" / "composition_generator.py", "RefinedAway"),
        (PY / "codegen" / "composition_generator.py", "CompositionCodegenError"),
        (PY / "netbase.py", "net_document"),
        (PY / "netbase.py", "canonical_net_json"),
        (PY / "netbase.py", "net_sha256"),
    ),
    "netbase": (
        (PY / "netbase.py", "VelocitronNet"),
        (PY / "netbase.py", "Registration"),
        (PY / "netbase.py", "HashMismatch"),
        (PY / "netbase.py", "handler_spec"),
    ),
    "replay": (
        (PY / "replay.py", "ReplayCursor"),
        (PY / "replay.py", "ReplayBase"),
        (PY / "replay.py", "replay_run"),
        (PY / "replay.py", "ReplayOrderError"),
        (PY / "replay.py", "ReplayNetMismatch"),
        (PY / "replay.py", "Divergence"),
        (PY / "replay.py", "ReplayResult"),
    ),
    "skill": ((PY / "dsl" / "cli.py", "_skill_source_dir"),),
    "cli": (
        (PY / "dsl" / "cli.py", "_play_main"),
        (PY / "dsl" / "cli.py", "_install_skill"),
        (PY / "dsl" / "cli.py", "_parser"),
        (PY / "dsl" / "cli.py", "_explain_document"),
        (PY / "dsl" / "cli.py", "_net_source_map"),
        (PY / "codegen" / "cli.py", "generate"),
        (PY / "codegen" / "cli.py", "add_parser"),
        (PY / "prove" / "cli.py", "add_parser"),
        (PY / "dsl" / "check.py", "check_paths"),
        (PY / "dsl" / "check.py", "extract_fences"),
        (PY / "viz.py", "_load_document"),
        (PY / "viz.py", "_VizError"),
    ),
    "viz": (
        (PY / "viz.py", "net_to_dot"),
        (PY / "viz_view.py", "apply_view"),
    ),
}

# Text that means a shim grew the implementation back. Missing files are
# reported by ``_FORBIDDEN_PATHS`` instead.
_FORBIDDEN_SNIPPETS: dict[str, tuple[tuple[Path, str], ...]] = {
    "petrinet": (
        (TS / "schema" / "parse.ts", "function parseNet"),
        (TS / "schema" / "composition.ts", "function parseComposition"),
        (TS / "dsl" / "api.ts", "function compilePetrinetText"),
        (TS / "dsl" / "resolve.ts", "function resolveContributionIr"),
        (TS / "schema" / "composition-merge.ts", "function mergeNets"),
        (TS / "schema" / "composition-merge.ts", "function mergeComposition"),
    ),
    "journal": (
        (TS / "journal" / "index.ts", "class InMemoryJournal"),
        (TS / "journal" / "memory.ts", "class InMemoryJournal"),
        (TS / "journal" / "index.ts", "function replayRecords"),
        (TS / "journal" / "index.ts", "function replayEvents"),
    ),
    "runtime": (
        (TS / "runtime" / "index.ts", "class Runtime"),
        (TS / "runtime" / "runtime.ts", "class Runtime"),
        (TS / "runtime" / "waits.ts", "function intendedWaits"),
    ),
    "analysis": (
        (TS / "analysis" / "index.ts", "function readProofReport"),
        (TS / "analysis" / "report.ts", "function readProofReport"),
    ),
    "properties": (
        (TS / "properties" / "index.ts", "function checkMarking"),
        (PY / "properties.py", "def check_marking"),
        (PY / "properties.py", "class AtMostN"),
    ),
    "explain": (
        (TS / "explain" / "index.ts", "function explainNet"),
        (PY / "explain.py", "def explain_net"),
    ),
    "equiv": (
        (TS / "equiv" / "index.ts", "function compare"),
        (TS / "equiv" / "index.ts", "class Equivalence"),
        (PY / "equiv.py", "def compare"),
        (PY / "equiv.py", "class Equivalence"),
    ),
    "codegen": (
        (TS / "codegen" / "index.ts", "function generateModule"),
        (TS / "codegen" / "index.ts", "function generateComposition"),
        (PY / "netbase.py", 'SYNTH_HANDLER = "velocitron:synth:"'),
    ),
    "netbase": (
        (TS / "netbase" / "index.ts", "class VelocitronNet"),
        (TS / "netbase" / "index.ts", "function handlerSpec"),
        (PY / "netbase.py", "class VelocitronNet"),
        (PY / "netbase.py", "def handler_spec"),
    ),
    "replay": (
        (TS / "replay" / "index.ts", "class ReplayCursor"),
        (TS / "replay" / "index.ts", "function replayRun"),
        (PY / "replay.py", "class ReplayCursor"),
        (PY / "replay.py", "def replay_run"),
    ),
    "cli": (
        (TS / "cli" / "index.ts", "function main"),
        (TS / "cli" / "index.ts", "function vizMain"),
        (PY / "dsl" / "cli.py", "def _play_main"),
        (PY / "viz.py", "class _VizError"),
    ),
}

_FORBIDDEN_PATHS: dict[str, tuple[Path, ...]] = {
    "cel": (
        PY / "_celpy.py",
        PY / "_re2_standin.py",
        PY / "_vendor",
    ),
    "dsl": (
        PY / "dsl" / "lower.py",
        PY / "dsl" / "generated",
        TS / "dsl" / "generated",
    ),
    "merge": (),
    "petrinet": (
        PY / "dsl" / "compiler.py",
        TS / "dsl" / "resolve.ts",
        TS / "schema" / "validate.ts",
        TS / "schema" / "generated",
        TS / "dsl" / "ir" / "generated-validator.ts",
    ),
    "play": (PY / "play" / "generated",),
    "play-check": (),
    "engine": (),
    "viz": (),
    "journal": (
        TS / "journal" / "memory.ts",
        TS / "journal" / "types.ts",
    ),
    "runtime": (),
    "analysis": (
        PY / "prove" / "analysis.py",
        PY / "prove" / "celscan.py",
        PY / "prove" / "choice.py",
        PY / "prove" / "counterexample.py",
        PY / "prove" / "firing.py",
        PY / "prove" / "invariants.py",
        PY / "prove" / "refinement.py",
        PY / "prove" / "report.py",
        PY / "prove" / "soundness.py",
    ),
    "properties": (),
    "explain": (),
    "equiv": (),
    "codegen": (),
    "netbase": (),
    "replay": (),
    "cli": (),
    "skill": (PY / "skill",),
}


def _defines(path: Path, name: str) -> bool:
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return True
    return False


def problems(package: str) -> list[str]:
    found: list[str] = []
    for path in _FORBIDDEN_PATHS[package]:
        if path.exists():
            found.append(f"{path.relative_to(ROOT)} still exists")
    for path, name in _FORBIDDEN_DEFS[package]:
        if _defines(path, name):
            found.append(f"{path.relative_to(ROOT)} defines {name}")
    for path, snippet in _FORBIDDEN_SNIPPETS.get(package, ()):
        if path.is_file() and snippet in path.read_text(encoding="utf-8"):
            found.append(f"{path.relative_to(ROOT)} contains {snippet}")
    return found


def facade_problems() -> list[str]:
    found: list[str] = []
    if PY.exists():
        found.append(f"{PY.relative_to(ROOT)} still exists")
    if TS.exists():
        found.append(f"{TS.relative_to(ROOT)} still exists")
    return found


def check(package: str) -> int:
    found = facade_problems() + problems(package)
    if found:
        print(
            f"{package} umbrella copy is back:\n"
            + "\n".join(f"- {item}" for item in found),
            file=sys.stderr,
        )
        return 1
    print(f"{package} package is the source; the umbrella does not redefine it.")
    return 0


def main(argv: list[str], package: str) -> int:
    command = argv[1] if len(argv) > 1 else "sync"
    if command == "check":
        return check(package)
    if command == "sync":
        print(
            f"{package} is sourced from packages/{package}. "
            "Copying it out of the umbrella is retired.",
            file=sys.stderr,
        )
        return 2
    print(f"usage: python3 tools/{package}_package.py [sync|check]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv, sys.argv[1] if len(sys.argv) > 1 else "cel"))
