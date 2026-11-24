"""``velocitron prove``: print each fact as PROVED, REFUTED or UNKNOWN."""

from __future__ import annotations

import argparse
import json
import sys

from velocitron_analysis import (
    DEFAULT_MAX_STATES,
    FACTS,
    FastPathError,
    load,
    prove,
    read_settings,
)
from velocitron_dsl import PetrinetDslError
from velocitron_petrinet import NetValidationError


def add_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser = commands.add_parser(
        "prove",
        help="prove choice coverage, place invariants and soundness of a net",
        description=(
            "Prove facts about every marking a net can reach: choice coverage "
            "(each token at a choice place enables exactly one way out), place "
            "invariants (weighted token counts no firing changes) and soundness "
            "of one lifecycle instance (it can always complete, completes "
            "cleanly, and every transition can fire). For a composition, also "
            "prove that each refining net is a sound block for the transition "
            "it refines. Data domains come from the net's own CEL; the net's "
            "domain facts and then --domains override them. Prints each fact as "
            "PROVED, REFUTED (with a witness or counterexample) or UNKNOWN (with "
            "the reason). Exits 0 when nothing is refuted, 1 otherwise."
        ),
    )
    parser.add_argument(
        "input", metavar="FILE", help="a .petrinet or .json net or composition"
    )
    parser.add_argument("--json", action="store_true", help="print the JSON report")
    parser.add_argument(
        "--fact",
        dest="facts",
        action="append",
        choices=FACTS,
        help="prove only this fact (repeatable; default: all)",
    )
    parser.add_argument(
        "--counterexamples",
        metavar="DIR",
        help="write each witness and counterexample as a .play file in DIR",
    )
    parser.add_argument(
        "--domains",
        metavar="FILE",
        help="a JSON or JSON5 file of domain overrides, final places and environment bounds",
    )
    parser.add_argument(
        "--max-states",
        type=int,
        default=DEFAULT_MAX_STATES,
        metavar="N",
        help=f"stop exploring after N markings (default {DEFAULT_MAX_STATES})",
    )
    parser.add_argument(
        "--wait-arrivals",
        action="store_true",
        help=(
            "hold each arrival back while no step can use it (ADR 0061); "
            "verdicts are the same, a run that ends often gets smaller, a "
            "capped run can take twice as long"
        ),
    )
    path = parser.add_mutually_exclusive_group()
    path.add_argument(
        "--fast",
        action="store_true",
        help=(
            "prove soundness and choice on the fast path, the compiled "
            "kernel; what its tables cannot carry yet is proved by the "
            "reference explorer, with a note"
        ),
    )
    path.add_argument(
        "--reference",
        action="store_true",
        help="explore soundness on the reference explorer (the default)",
    )
    parser.add_argument(
        "--one-core",
        action="store_true",
        help=(
            "with --fast: explore on one core, in the reference explorer's "
            "order, as the check against the reference does; the counts and "
            "results are the same as on every core"
        ),
    )


def main(args: argparse.Namespace) -> int:
    path = args.input
    if args.one_core and not args.fast:
        sys.stderr.write(f"{path}: error: --one-core needs --fast\n")
        return 2
    try:
        net, composition = load(path)
        settings = read_settings(args.domains) if args.domains else None
        report = prove(
            net,
            facts=args.facts or FACTS,
            settings=settings,
            max_states=args.max_states,
            source=path,
            counterexamples=args.counterexamples,
            net_file=path,
            composition=composition,
            wait_arrivals=args.wait_arrivals,
            progress=sys.stderr.write,
            fast=args.fast,
            one_core=args.one_core,
            on_reference=_note_reference,
        )
    except FastPathError as error:
        sys.stderr.write(f"{path}: error: {error}\n")
        return 1
    except PetrinetDslError as error:
        sys.stderr.write(error.diagnostic.render() + "\n")
        return 1
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        NetValidationError,
    ) as error:
        sys.stderr.write(f"{path}:1:1: error[PN200]: {error}\n")
        return 1
    sys.stdout.write(report.json() if args.json else report.text())
    return 1 if report.refuted else 0


def _note_reference(why: str) -> None:
    sys.stderr.write(
        "velocitron: the reference explorer proves what the fast path cannot "
        f"take, at its own speed: {why}\n"
    )


__all__ = ["add_parser", "main"]
